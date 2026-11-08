"""Real Windows Hands crash/cancel/reconciliation acceptance using production HMAC.

Creates only a new child directory of an explicitly selected integration Home.
Never targets the default environment or substitutes an in-process service.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import secrets
import shutil
import sys
import time

import native_runtime as native
import persistent_runtime as deployment

for folder in ['apps','apps/agent','apps/agentOS','apps/agentOS/src']:
    sys.path.insert(0,str(native.ROOT/folder))
from adapters.hands_http import HandsHttpTransport, HandsOutcomeUnknown, receipt_checksum
from contracts.local_runtime import LocalRuntimeExecutionRequest


async def check(home, output, port):
    info,creds = deployment.manifest(home),native.credentials(home)
    if info.get('backend') != 'hands' or home.name == 'default':
        raise RuntimeError('Explicit isolated Hands integration Home required')
    native.port_free(port)
    case = home/('hands-exception-'+secrets.token_hex(4))
    case.mkdir()
    workspace = case/'workspace'; workspace.mkdir()
    keys,config = case/'keys.json',case/'service.json'
    native.write_json(case/'grants.json',{'grants':[{'grantId':'probe-grant','workspaceId':'probe-workspace',
        'canonicalRoot':str(workspace.resolve()),'capabilities':native.CAPS+['shell.exec'],
        'allowedCallers':['n01a-credential'],'revoked':False}]})
    setup = dict(workspaceRoot=str(workspace),credentialsFile=str(keys),grantsFile=str(case/'grants.json'),
        dataDir=str(case/'ledger'),host='127.0.0.1',port=port,confinement='none')
    env = dict(os.environ,TSX_TSCONFIG_PATH=str(native.ROOT/'apps/agentOS/src/hands/tsconfig.json'))
    command = [shutil.which('node'),str(native.ROOT/'apps/agentOS/src/hands/node_modules/tsx/dist/cli.mjs'),
        '--tsconfig',str(native.ROOT/'apps/agentOS/src/hands/tsconfig.json'),str(native.ROOT/'apps/agentOS/src/hands/hands/service-main.ts'),
        '--config',str(config)]
    child = None
    def start(faults=None):
        nonlocal child
        native.write_json(keys,{'credentials':[{'credentialId':'n01a-credential','secret':creds['hmac']}]})
        native.write_json(config,dict(setup,**({'faults':faults} if faults else {})))
        child = native.spawn(case,'service',command,env)
        for _ in range(200):
            try:
                if native.health(port,'/v1/health').get('ok'): break
            except Exception: pass
            time.sleep(.05)
        else: raise RuntimeError('Hands probe failed to start')
        keys.unlink()
    class Credentials:
        def current_signing_credential(self, resource_id): return 'n01a-credential',creds['hmac']
    transport = HandsHttpTransport(resource_id='probe',address=f'http://127.0.0.1:{port}/v1/executions',
        credential_provider=Credentials())
    identity = dict(runId='exception-probe',stepId='interruption',attemptId='attempt-1',commitId='commit-1')
    def request(key,capability,data):
        return LocalRuntimeExecutionRequest(protocolVersion='1',requestId=key,invocationId=key,resourceId='probe',
            capabilityId=capability,authorization={'grantId':'probe-grant','workspaceId':'probe-workspace'},
            input=data,limits={'timeoutSeconds':45,'maxStdoutBytes':4096,'maxStderrBytes':4096},idempotencyKey=key)
    try:
        start({'afterStarted':True})
        frozen = request('crash-write','fs.write',{'path':'uncertain.txt','content':'must not be replayed'})
        unknown = False
        try: await transport.execute_with_identity(frozen,identity)
        except HandsOutcomeUnknown: unknown = True
        assert unknown
        for _ in range(100):
            if native.owned(child) is None: break
            await asyncio.sleep(.05)
        assert native.owned(child) is None
        start()
        claim = next(json.loads(line) for line in (case/'ledger/ledger.jsonl').read_text().splitlines()
                     if json.loads(line).get('t')=='claim')
        execution_id = claim['executionId']
        recovered = await transport.query_execution(execution_id)
        assert recovered['state']=='UNKNOWN' and recovered['summary']['identity']==identity
        # Exact same immutable request resolves the same uncertain execution;
        # the service must not replay it after process recovery.
        again_unknown = False
        try: await transport.execute_with_identity(frozen.model_copy(update={'request_id':'new-client-request-id'}),identity)
        except HandsOutcomeUnknown: again_unknown = True
        assert again_unknown and not (workspace/'uncertain.txt').exists()
        await transport.execute_with_identity(request('confirmed-write','fs.write',
            {'path':'confirmed.txt','content':'real HMAC read observation'}),identity)
        observed = await transport.execute_with_identity(request('confirmed-read','fs.read',{'path':'confirmed.txt'}),identity)
        assert observed.output['content']=='real HMAC read observation'
        assert observed.output['handsReceipt']['output']['text']==observed.output['content']
        location = await transport.execute_with_identity(request('cwd-shell','shell.exec',
            {'command':'(Get-Location).Path','workdir':'.'}),identity)
        assert location.output['exitCode']==0 and isinstance(location.output['stdout'],str)
        assert Path(location.output['stdout'].strip()).resolve()==workspace.resolve()
        task = asyncio.create_task(transport.execute_with_identity(request('cancel-shell','shell.exec',
            {'command':"Start-Sleep -Seconds 20; Set-Content -LiteralPath late.txt -Value bad",'workdir':'.'}),identity))
        await asyncio.sleep(1)
        task.cancel()
        try: await task
        except asyncio.CancelledError: pass
        rows = [json.loads(line) for line in (case/'ledger/ledger.jsonl').read_text().splitlines()]
        cancelled_id = next(r['executionId'] for r in rows if r.get('t')=='claim'
                            and r['idempotencyKey']=='cancel-shell')
        for _ in range(100):
            cancelled = await transport.query_execution(cancelled_id)
            if cancelled['state']=='CANCELLED': break
            await asyncio.sleep(.1)
        receipt = cancelled['receipt']
        assert cancelled['state']=='CANCELLED' and receipt_checksum(receipt)==receipt['checksum']
        assert receipt['identity']==identity and not (workspace/'late.txt').exists()
        result = dict(status='PASS',case=str(case),crashExecutionId=execution_id,
            recoveredState=recovered['state'],sameRequestNotReplayed=True,changedClientRequestIdStable=True,
            readContractConverted=True,relativeWorkdirResolvesToWorkspace=True,stdoutContractConverted=True,uncertainFileAbsent=True,
            cancelExecutionId=cancelled_id,cancelChecksum=receipt['checksum'],cancelState=cancelled['state'],
            cancelledCommandFileAbsent=True)
    finally:
        keys.unlink(missing_ok=True)
        await transport.aclose()
        if child and native.owned(child): native.stop(child)
    native.port_free(port)
    result.update(processStopped=True,portReleased=True,temporaryKeysRemoved=not keys.exists())
    native.write_json(output,result)
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--home',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--port',type=int,default=18966)
    args=parser.parse_args()
    asyncio.run(check(args.home.resolve(),args.output,args.port))
