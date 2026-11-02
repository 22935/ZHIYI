"""AgentOS-owned, NodeRunner-bound workspace tools. Hands owns no Agent loop."""
import asyncio
import json
import os
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

from adapters.audited_tool_runtime import AuditedToolRuntime
from adapters.hands_http import HandsExecutionCancelled, HandsOutcomeUnknown
from support.async_tasks import await_settled
from components.scheduler.binder import LeaseKeepAlive
from contracts.resource import ExecutionRequirement, RuntimeKind
from contracts.local_runtime import LocalRuntimeExecutionRequest, LocalRuntimeExecutionLimits
from contracts.runtime_events import RuntimeEvent
from runtime.live_events import runtime_event_broker
from app.tools.permissions import get_chat_permission_service, normalize_relative_path

TOOLS = {'read_file':'fs.read','list_files':'fs.list','write_file':'fs.write','patch_file':'fs.patch','run_tests':'shell.exec'}
FIELDS = {'read_file':{'path'},'list_files':{'path'},'write_file':{'path','content'},
          'patch_file':{'path','oldText','newText'},'run_tests':{'path','runner'}}


class FormalWorkspaceTools:
    def __init__(self, runtime, fallback, context=None, guard=None):
        self.runtime,self.fallback,self.context,self.guard = runtime,fallback,context,guard
        self.allowed_tools = frozenset(TOOLS)|frozenset(getattr(fallback,'allowed_tools',()))
        self.permissions = get_chat_permission_service()
        if not hasattr(runtime,'formal_tool_pending'): runtime.formal_tool_pending = {}

    def scoped(self, allowed):
        return AuditedToolRuntime(delegate=self,allowed_tools=self.allowed_tools.intersection(allowed))

    def bind_context(self, context, guard):
        return FormalWorkspaceTools(self.runtime,self.fallback,context,guard)

    async def verified_observations(self, context):
        """Verify only receipt references delivered by this node's ContextPack.

        This consumes existing evidence; it grants no filesystem or Shell tool
        to the verification/synthesis agent and never scans another node's data.
        """
        from adapters.hands_http import receipt_checksum
        found = {}
        def visit(value):
            if isinstance(value,dict):
                if value.get('receiptRef') and value.get('receiptChecksum'):
                    found[value['receiptRef']] = value
                for child in value.values(): visit(child)
            elif isinstance(value,list):
                for child in value: visit(child)
        visit(getattr(context.context_pack,'data',{}))
        if not found:
            return []
        if self.context is not context or self.guard is None:
            raise PermissionError('Bound NodeRunner context required for receipt verification')
        self.guard()
        observations=[]
        for ref,record in found.items():
            receipt=self.runtime.execution_value_store.get_output(run_id=context.run.run_id,output_ref=ref)
            if receipt_checksum(receipt)!=record['receiptChecksum'] or receipt['checksum']!=record['receiptChecksum']:
                raise RuntimeError('HANDS_EVIDENCE_CHECKSUM_MISMATCH')
            identity=receipt.get('identity',{})
            if identity.get('runId')!=context.run.run_id or any(identity.get(k)!=record.get(k) for k in ['stepId','attemptId','commitId']):
                raise RuntimeError('HANDS_EVIDENCE_IDENTITY_MISMATCH')
            observations.append({'kind':'hands_execution_receipt','executionId':record['executionId'],
                'receiptRef':ref,'receiptChecksum':receipt['checksum'],'content':receipt})
        return observations

    async def execute(self, name, arguments, *, operation_key=None, **kwargs):
        if name not in TOOLS: return await self.fallback.execute(name,arguments,**kwargs)
        context,rt = self.context,self.runtime
        if context is None or self.guard is None or not operation_key: raise PermissionError('Formal NodeRunner authority required')
        self.guard()
        authority = getattr(rt, 'workspace_authority', None)
        authorization = authority.resolve(context.run) if authority else rt.local_runtime_authorization
        if set(arguments)-FIELDS[name]: raise PermissionError('Tool input cannot declare host authority')
        path = normalize_relative_path(arguments.get('path','.') if name=='run_tests' else arguments.get('path'))
        if path is None: raise PermissionError('Workspace relative path required')
        data = dict(arguments,path=path)
        approval_name = name
        approval_data = data
        if name == 'run_tests':
            # Managed test command, not a model-supplied security profile or executable.
            if any(c in path for c in "'\"`\n\r") or path.startswith('-'): raise PermissionError('Invalid test path')
            runner = arguments.get('runner', 'pytest')
            if runner == 'pytest':
                executable = os.environ['AGENTOS_WORKSPACE_TEST_PYTHON']
                argv = ['-m', 'pytest', '-q', path]
            elif runner == 'node':
                executable = os.environ['AGENTOS_WORKSPACE_TEST_NODE']
                argv = ['--test'] + ([] if path == '.' else [path])
            elif runner == 'npm-test':
                if path != '.': raise PermissionError('npm-test runs only the authorized project test script')
                executable = os.environ['AGENTOS_WORKSPACE_TEST_NPM']
                argv = ['test']
            else: raise PermissionError('Unconfigured test runner')
            if not os.path.isabs(executable) or not os.path.isfile(executable):
                raise PermissionError('Trusted test executable unavailable')
            quote = lambda value: "'" + value.replace("'", "''") + "'"
            command = '& ' + ' '.join(quote(v) for v in [executable, *argv])
            data = {'command':command,'workdir':'.', 'executable': executable, 'argv': argv}
            approval_name,approval_data = 'run_command',{'command':command,'cwd':'.'}
        elif name == 'patch_file':
            approval_data = {'path':path}
        run_id,step_id = context.run.run_id,context.step.step_id
        identity = dict(runId=run_id,stepId=step_id,attemptId=context.attempt_id,commitId=context.commit_id)
        if not all(identity.values()): raise PermissionError('Frozen execution identity required')
        async def emit(kind,payload):
            if kind == 'hands_event' and payload.get('executionId'):
                rt.execution_value_store.put_tool_value(run_id=run_id,step_id=step_id,
                    key=operation_key+':admission',payload={'executionId':payload['executionId'],**identity})
            approval = payload.get('approval')
            if approval: rt.formal_tool_pending[approval['approvalId']] = approval
            await runtime_event_broker.publish(run_id,RuntimeEvent(eventType='tool.'+kind,runId=run_id,
                nodeId=step_id,attemptId=context.attempt_id,sequence=0,payload=payload))
        await self.permissions.authorize(tool_name=approval_name,arguments=approval_data,call_id=operation_key,
            session_id=run_id,workspace_id=authorization.workspace_id,emit=emit)
        self.guard()  # Human approval may have yielded while a permit was revoked.
        if authority: authorization = authority.resolve(context.run)
        healthy = await rt.local_runtime_health_projector.refresh(rt.local_runtime_transport)
        if not healthy: raise RuntimeError('Execution resource is not healthy')
        scheduled = rt.resource_binder.bind_ready(run_id=run_id,step_id=step_id,attempt_id=context.attempt_id,
            requirement=ExecutionRequirement(requiredCapabilities=[TOOLS[name]],runtimeKinds=[RuntimeKind.EXECUTION_BACKEND],
                allowedRuntimeIds=[rt.local_runtime_resource.profile.runtime_id]))
        if scheduled.binding is None or scheduled.lease is None: raise RuntimeError('Hands lease unavailable: '+str(scheduled.reason))
        keepalive = LeaseKeepAlive(rt.resource_binder.coordinator,scheduled.lease)
        keepalive.start()
        outcome_unknown = False
        try:
            request = LocalRuntimeExecutionRequest(protocolVersion='1',requestId=operation_key,invocationId=operation_key,
                resourceId=scheduled.binding.resource_id,capabilityId=TOOLS[name],authorization=authorization,
                input=data,limits=LocalRuntimeExecutionLimits(timeoutSeconds=90,maxStdoutBytes=64000,maxStderrBytes=32000),
                idempotencyKey=operation_key)
            key = operation_key+':request'
            rt.execution_value_store.put_tool_value(run_id=run_id,step_id=step_id,key=key,
                payload={'request':request.model_dump(by_alias=True,mode='json'),'identity':identity})
            self.guard()
            if authority: authority.resolve(context.run)
            await emit('execution_started',{'tool':name,'bindingId':scheduled.binding.binding_id,**identity})
            cancellation = None
            try:
                result = await rt.local_runtime_transport.execute_with_identity(request,identity,
                    event_sink=lambda event: emit('hands_event',event))
            except HandsExecutionCancelled as exc:
                cancellation, result = exc, exc.result
            receipt = result.output.get('handsReceipt')
            if not receipt: raise RuntimeError('Verified Hands receipt required before node completion')
            ref = rt.execution_value_store.put_tool_value(run_id=run_id,step_id=step_id,key=operation_key+':receipt',payload=receipt)
            record = {'tool':name,'status':result.status,'executionId':result.output['executionId'],
                'receiptChecksum':receipt['checksum'],'receiptRef':ref,'resourceId':scheduled.binding.resource_id,
                'bindingId':scheduled.binding.binding_id,**identity}
            record['workspaceId'] = authorization.workspace_id
            record['grantId'] = authorization.grant_id
            await emit('execution_completed',record)
            if cancellation is not None:
                raise cancellation
            if keepalive.failure: raise RuntimeError('Hands lease renewal failed; reconcile before retry')
            data = dict(result.output, status=result.status)
            if result.error: data['error'] = result.error.model_dump(mode='json')
            return SimpleNamespace(data=data,record=record)
        except HandsOutcomeUnknown:
            outcome_unknown = True
            # Retain the request/admission WAL and quarantine this execution
            # resource. An unknown external operation is never a release receipt.
            rt.resource_plane.set_runtime_health(scheduled.binding.resource_id, healthy=False)
            rt.resource_plane.set_runtime_enabled(scheduled.binding.resource_id, enabled=False)
            rt.execution_value_store.put_tool_value(run_id=run_id,step_id=step_id,key=operation_key+':unsettled',
                payload={'leaseId':scheduled.lease.lease_id,'resourceId':scheduled.binding.resource_id,
                         'reason':'external_outcome_unknown', **identity})
            raise
        finally:
            async def cleanup():
                try:
                    await keepalive.stop()
                finally:
                    if not outcome_unknown:
                        rt.resource_binder.release(scheduled.lease.lease_id)
            await await_settled(asyncio.create_task(cleanup(), name=f"hands-lease-cleanup:{operation_key}"))
