"""Hands asynchronous capability transport over the existing resource HMAC.

202 is admission only. A receipt is returned only after polling, correlation and
checksum validation. UNKNOWN/network ambiguity is non-retryable to the Agent.
"""
import asyncio
import hashlib
import json
import logging
from urllib.parse import quote
from uuid import uuid5, NAMESPACE_URL

from adapters.local_runtime_http import HttpLocalRuntimeTransport
from contracts.local_runtime import (
    LocalRuntimeCapability,
    LocalRuntimeExecutionEvent,
    LocalRuntimeExecutionResult,
    LocalRuntimeExecutionError,
)
from support.async_tasks import await_owned, await_settled, cancel_and_wait


class HandsOutcomeUnknown(RuntimeError):
    code = 'HANDS_OUTCOME_UNKNOWN'
    retryable = False


class HandsExecutionCancelled(asyncio.CancelledError):
    """Cancellation settled with a verified terminal receipt, not an admission ACK."""

    def __init__(self, result, reason):
        super().__init__(reason)
        self.result = result


class HandsAdmissionRejected(RuntimeError):
    """A definite protocol/auth/grant rejection, never an uncertain execution."""
    retryable = False

    def __init__(self, status, code):
        self.status, self.code = status, code
        super().__init__('Hands operation rejected: '+code)


def receipt_checksum(receipt):
    data = {key:value for key,value in receipt.items() if key != 'checksum'}
    return hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


class HandsHttpTransport(HttpLocalRuntimeTransport):
    # hands 事件 wire 类型 -> LocalRuntime 事件契约类型；accepted/unknown 无对应契约，
    # 由响应级 terminal/state 承载，不逐条翻译。
    _EVENT_TYPES = {
        'execution.started': 'started',
        'stdout.delta': 'stdout_delta',
        'stderr.delta': 'stderr_delta',
        'execution.completed': 'completed',
        'execution.failed': 'failed',
        'execution.cancelled': 'cancelled',
    }

    async def health(self):
        response = await self._client.get(self.address.rsplit('/v1/executions',1)[0]+'/v1/health',timeout=5)
        response.raise_for_status()
        raw = response.json()
        profile = self.credential_provider.runtime(self.resource_id)
        supported = set(raw.get('capabilities',[]))
        return {'protocolVersion':'1','resourceId':self.resource_id,'status':'online' if raw.get('ok') else 'offline',
                'capabilities':[c for c in profile.capabilities if c in supported],
                'availableSlots':profile.capacity,'utilization':0.0}
    async def _call(self, method, suffix='', payload=None, key=None):
        body = b'' if payload is None else json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()
        path = self._path + suffix
        headers = self._signed_headers(method=method,path=path,body=body,idempotency_key=key)
        response = await self._client.request(method,self.address+suffix,headers=headers,content=body,timeout=15)
        if response.status_code not in (200,202):
            if response.status_code in (400,401,403,404,409,422):
                try: code = response.json()['error']['code']
                except (ValueError,KeyError,TypeError): code = 'HANDS_HTTP_'+str(response.status_code)
                raise HandsAdmissionRejected(response.status_code, str(code))
            raise HandsOutcomeUnknown('Hands rejected a signed operation: '+str(response.status_code))
        return response.json()

    async def execute(self, request):
        if request.capability_id.value == 'shell.exec':
            # chat run_command 的流式模型：admission 即返回，终态经 stream_events 推进。
            # formal 链的 execute_with_identity 仍阻塞到收据（settlement 合同不变）。
            return await self._execute_with_identity(
                request, {}, None, {'ready': asyncio.Event(), 'executionId': None}, admission_return=True)
        return await self.execute_with_identity(request, {})

    async def execute_with_identity(self, request, identity, event_sink=None):
        admission = {'ready': asyncio.Event(), 'executionId': None}
        task = asyncio.create_task(self._execute_with_identity(request, identity, event_sink, admission),
                                   name=f"hands-execution:{request.invocation_id}")
        try:
            return await await_owned(task)
        except asyncio.CancelledError as exc:
            async def request_cancel():
                waiter = asyncio.create_task(admission['ready'].wait(), name=f"hands-admission:{request.invocation_id}")
                try:
                    await asyncio.wait({task, waiter}, return_when=asyncio.FIRST_COMPLETED)
                    if admission['executionId'] is not None and not task.done():
                        execution_id = admission['executionId']
                        await self._call('POST','/'+execution_id+'/cancel',{'executionId':execution_id})
                finally:
                    await cancel_and_wait([waiter], reason='admission_settled')
            cancel_task = asyncio.create_task(request_cancel(), name=f"hands-cancel:{request.invocation_id}")
            results = await await_settled(asyncio.gather(task, cancel_task, return_exceptions=True), propagate_cancel=False)
            if isinstance(results[1], Exception):
                logging.getLogger(__name__).warning('Hands cancellation request failed; execution reconciliation completed', exc_info=results[1])
            if isinstance(results[0], BaseException):
                raise results[0]
            raise HandsExecutionCancelled(results[0], str(exc) or 'execution_cancelled')

    async def _execute_with_identity(self, request, identity, event_sink, admission, admission_return=False):
        if request.capability_id.value == 'fs.patch' and 'patch' in (request.input or {}):
            return await self._patch_via_read_modify_write(request, identity, event_sink, admission)
        wire = request.model_dump(by_alias=True,mode='json')
        wire.pop('resourceId')  # Hands is already selected by the signed endpoint.
        wire['requestId'] = str(uuid5(NAMESPACE_URL,request.idempotency_key))
        if identity: wire['identity'] = dict(identity)
        if request.capability_id.value == 'fs.patch':
            data = wire['input']
            if 'old_text' in data: data['oldText'] = data.pop('old_text')
            if 'new_text' in data: data['newText'] = data.pop('new_text')
        if request.capability_id.value == 'fs.write':
            data = wire['input']
            overwrite = data.pop('overwrite', None)
            if overwrite is False:
                # chat 的 overwrite:False = 拒绝覆盖已存在文件，映射到 hands 的同名守卫。
                data.setdefault('createIfAbsent', True)
            data.pop('createParents', None)  # hands writeText 自建父目录；chat 侧字段名它不认识。
        if request.capability_id.value == 'shell.exec':
            data = wire['input']
            if 'cwd' in data: data.setdefault('workdir', data.pop('cwd'))
        execution_id = None
        try:
            record = await self._call('POST',payload=wire,key=request.idempotency_key)
            execution_id = record['executionId']
            admission['executionId'] = execution_id
            admission['ready'].set()
            if (admission_return
                    and record.get('state') not in {'COMPLETED', 'FAILED', 'CANCELLED', 'UNKNOWN'}):
                # admission 即返回（仅 chat 的 execute 入口声明）：
                # chat run_command 依赖 started 状态先登记再经 stream_events 推进终态，
                # 事件翻译带收据富化与 checksum 校验；fs.* 仍阻塞到终态。
                accepted_at = record.get('createdAt')
                return LocalRuntimeExecutionResult(
                    requestId=request.request_id, invocationId=request.invocation_id,
                    status='accepted', output={'executionId': execution_id},
                    startedAt=accepted_at, completedAt=accepted_at)
            cursor = -1
            deadline = asyncio.get_running_loop().time()+request.limits.timeout_seconds+30
            while record['state'] not in {'COMPLETED','FAILED','CANCELLED','UNKNOWN'}:
                if asyncio.get_running_loop().time() > deadline:
                    await self._call('POST','/'+execution_id+'/cancel',{'executionId':execution_id})
                    raise HandsOutcomeUnknown('Hands deadline reached; cancellation requested, reconciliation required')
                if event_sink:
                    events = await self._call('GET','/'+execution_id+'/events?afterSequence='+str(cursor))
                    for event in events['events']:
                        cursor = max(cursor,int(event['seq']))
                        await event_sink(event)
                await asyncio.sleep(.15)
                record = await self._call('GET','/'+execution_id)
            if event_sink:
                events = await self._call('GET','/'+execution_id+'/events?afterSequence='+str(cursor))
                for event in events['events']:
                    await event_sink(event)
            if record['state'] == 'UNKNOWN':
                raise HandsOutcomeUnknown('Hands execution '+execution_id+' is UNKNOWN; automatic replay forbidden')
            receipt = record.get('receipt')
            if not receipt or receipt_checksum(receipt) != receipt['checksum']:
                raise HandsOutcomeUnknown('Hands terminal receipt is missing or invalid')
            if any(receipt.get(key) != wire.get(key) for key in ['requestId','invocationId','capabilityId','idempotencyKey']):
                raise HandsOutcomeUnknown('Hands receipt correlation mismatch')
            if receipt.get('identity',{}) != identity or receipt['grantId'] != request.authorization.grant_id:
                raise HandsOutcomeUnknown('Hands receipt authority/identity mismatch')
            expected = {'COMPLETED':'completed','FAILED':'failed','CANCELLED':'cancelled'}[record['state']]
            if receipt['status'] != expected: raise HandsOutcomeUnknown('Hands state and receipt disagree')
            output = dict(receipt.get('output') or {})
            if request.capability_id.value == 'fs.read' and 'text' in output:
                output['content'] = output['text']  # Hands wire -> AgentOS file-tool observation.
            if request.capability_id.value == 'fs.list' and isinstance(output.get('entries'), list):
                # DSH 条目 {name,type,target:{displayPath}} -> python runtime 条目 {path,name,type}。
                output['entries'] = [
                    {
                        'path': str((entry.get('target') or {}).get('displayPath') or entry.get('name') or ''),
                        'name': entry.get('name'),
                        'type': entry.get('type'),
                        **({'size': entry['size']} if isinstance(entry.get('size'), int) else {}),
                    }
                    for entry in output['entries'] if isinstance(entry, dict)
                ]
            for channel in ('stdout','stderr'):
                if isinstance(output.get(channel),dict):
                    stream = output[channel]
                    output[channel] = stream.get('text','')
                    output[channel+'Truncated'] = bool(stream.get('truncated',False))
            output.update(executionId=execution_id,receiptChecksum=receipt['checksum'],handsReceipt=receipt)
            failure = None
            if expected in {'failed','cancelled'}:
                error = receipt.get('error') or {'code':'HANDS_CANCELLED','retryable':False,'message':'cancelled'}
                failure = LocalRuntimeExecutionError(**error)
                expected = 'failed'
            return LocalRuntimeExecutionResult(requestId=request.request_id,invocationId=request.invocation_id,
                status=expected,output=output,error=failure,startedAt=receipt['startedAt'],completedAt=receipt['completedAt'])
        except HandsOutcomeUnknown:
            raise
        except HandsAdmissionRejected:
            if execution_id is not None:
                raise HandsOutcomeUnknown('Admitted Hands execution cannot be reconciled; automatic replay forbidden')
            raise
        except Exception as exc:
            raise HandsOutcomeUnknown('Hands transport outcome requires reconciliation; no automatic replay') from exc

    async def _patch_via_read_modify_write(self, request, identity, event_sink, admission):
        """chat patch_file（unified diff）-> hands 读-改-写；读与写各有收据与账本行。

        已知偏离（对照 python local-runtime 的单收据原子 patch）：两步之间没有跨步
        原子性；并发写可被覆盖（chat 单用户场景可接受）；``encoding``/``expectedSha256``
        字段不支持（hands 文本能力仅 UTF-8）。读完成到写发出之间到达的取消会命中
        已终态的读收据（409 幂等回查），写不受影响。
        """
        from adapters.hands_patch import PatchConflictError, apply_unified_patch
        source_input = request.input
        read_request = request.model_copy(update={
            'invocation_id': request.invocation_id + ':patch-read',
            'capability_id': LocalRuntimeCapability.FS_READ,
            'input': {'path': source_input['path']},
            'idempotency_key': request.idempotency_key + ':patch-read',
        })
        read_result = await self._execute_with_identity(read_request, identity, None, admission)
        if read_result.status != 'completed':
            raise HandsOutcomeUnknown('Hands patch pre-read failed; no write was issued')
        try:
            updated = apply_unified_patch(str(read_result.output.get('content') or ''),
                                          str(source_input['patch'] or ''))
        except PatchConflictError as exc:
            raise HandsAdmissionRejected(422, 'PATCH_CONFLICT') from exc
        write_request = request.model_copy(update={
            'invocation_id': request.invocation_id + ':patch-write',
            'capability_id': LocalRuntimeCapability.FS_WRITE,
            'input': {'path': source_input['path'], 'content': updated},
            'idempotency_key': request.idempotency_key + ':patch-write',
        })
        write_result = await self._execute_with_identity(write_request, identity, event_sink, admission)
        return write_result.model_copy(update={
            'request_id': request.request_id, 'invocation_id': request.invocation_id,
        })

    async def query_execution(self, execution_id):
        return await self._call('GET','/'+execution_id)

    async def events(self, *, execution_id, after_sequence=-1, wait_seconds=0.0,
                     request_id=None, invocation_id=None):
        """把 hands 事件 wire 翻译成 LocalRuntime 事件契约（含终态收据富化）。"""
        del wait_seconds  # hands 无长轮询参数，节奏由 stream_events 控制。
        if not execution_id.strip():
            raise ValueError('execution_id is required')
        if after_sequence < -1:
            raise ValueError('after_sequence must not be below -1')
        if not request_id or not invocation_id:
            raise ValueError('hands events require request_id and invocation_id for correlation stamping')
        record = await self._call('GET', '/'+quote(execution_id, safe='')+'/events?afterSequence='+str(after_sequence))
        translated = []
        for raw in record.get('events') or []:
            event_type = self._EVENT_TYPES.get(str(raw.get('type')))
            if event_type is None:
                continue
            data = dict(raw.get('payload') or {})
            if event_type in ('stdout_delta', 'stderr_delta'):
                data = {'delta': str(data.get('text') or '')}
            elif event_type in ('completed', 'failed', 'cancelled'):
                data = await self._enrich_terminal_data(execution_id, data)
            translated.append(LocalRuntimeExecutionEvent(
                protocolVersion='1', requestId=request_id, invocationId=invocation_id, executionId=execution_id,
                eventType=event_type, sequence=int(raw.get('seq') or 0), data=data))
        return translated, bool(record.get('terminal')), str(record.get('state') or '')

    async def _enrich_terminal_data(self, execution_id, data):
        """hands 终态事件只带 checksum；退出码/超时/错误码在收据里，run_command 的 terminal 需要它们。

        shell.exec 早返回后终态结算只经过这里，因此收据 checksum 校验也在此 fail-closed。
        """
        merged = dict(data)
        try:
            record = await self.query_execution(execution_id)
        except Exception:
            logging.getLogger(__name__).warning('Hands terminal enrichment failed for %s', execution_id)
            raise HandsOutcomeUnknown('Hands terminal settlement could not be reconciled for ' + execution_id)
        receipt = record.get('receipt') or {}
        if receipt.get('checksum') and receipt_checksum(receipt) != receipt['checksum']:
            raise HandsOutcomeUnknown('Hands receipt checksum mismatch for ' + execution_id)
        output = receipt.get('output') or {}
        if isinstance(output.get('exitCode'), int):
            merged.setdefault('exitCode', output['exitCode'])
        if output.get('timedOut'):
            merged.setdefault('timedOut', True)
        if output.get('truncated'):
            merged.setdefault('truncated', True)
        error = receipt.get('error') or {}
        if error.get('code'):
            merged.setdefault('code', error['code'])
        return merged

    async def stream_events(self, *, execution_id, request_id, invocation_id, poll_seconds=0.15):
        cursor = -1
        while True:
            events, terminal, _state = await self.events(
                execution_id=execution_id, after_sequence=cursor,
                request_id=request_id, invocation_id=invocation_id)
            for event in events:
                cursor = max(cursor, event.sequence)
                yield event
            if terminal:
                return
            await asyncio.sleep(max(poll_seconds, 0.15))

    async def cancel(self, *, execution_id, request_id, invocation_id):
        """hands 只认执行引用；已终态的取消按幂等回查处理，而不是 transport 错误。"""
        del request_id, invocation_id
        try:
            record = await self._call('POST', '/'+quote(execution_id, safe='')+'/cancel',
                                      {'executionId': execution_id})
            return str(record.get('state') or 'CANCELLING')
        except HandsAdmissionRejected as exc:
            if exc.status == 409 and exc.code == 'EXECUTION_ALREADY_SETTLED':
                record = await self.query_execution(execution_id)
                return str(record.get('state') or '')
            raise

    async def workspace_root(self, authorization):
        response = await self._client.get(self.address.rsplit('/v1/executions',1)[0]+'/v1/health',timeout=5)
        response.raise_for_status()
        return response.json()['workspaceRoot']
