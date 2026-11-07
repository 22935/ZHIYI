"""Focused real-service persistence probes; never a substitute for desktop E2E.

Uses the production Lua lease coordinator against the native Redis-compatible
server. All probe keys use a dedicated database and unique namespace.
"""
import argparse
from datetime import timedelta
import hashlib
import os
from pathlib import Path
import secrets
import sys
import time
import json
import sqlite3
import urllib.request
import urllib.parse

import native_runtime as native
import persistent_runtime as deployment

for folder in ['apps','apps/agent','apps/agentOS','apps/agentOS/src']:
    sys.path.insert(0,str(native.ROOT/folder))
from components.scheduler.leases import RedisLeaseCoordinator, LeaseRenewalFailedError


def main(home, output):
    creds = native.credentials(home)
    client = deployment.redis_client(creds, db=3)
    import redis
    denied = False
    try:
        redis.Redis(host='127.0.0.1',port=16379,socket_timeout=2).ping()
    except redis.exceptions.AuthenticationError:
        denied = True
    assert denied, 'Native Redis must require AUTH'
    prefix = 'zhiyi:n03-probe:'+secrets.token_hex(8)
    coordinator = RedisLeaseCoordinator(client, key_prefix=prefix)
    lease = coordinator.acquire(lease_id='first',resource_id='probe',capacity=1,
        run_id='n03-check',step_id='probe',attempt_id='owner',ttl=timedelta(seconds=10))
    assert lease and coordinator.active_slots('probe') == 1
    args = dict(lease_id='second',resource_id='probe',capacity=1,
        run_id='n03-check',step_id='probe',attempt_id='other',ttl=timedelta(seconds=10))
    assert coordinator.acquire(**args) is None
    rejected_owner = False
    try:
        coordinator.renew(lease_id='first',owner_id='other',version=1,ttl=timedelta(seconds=10))
    except LeaseRenewalFailedError:
        rejected_owner = True
    assert rejected_owner
    renewed = coordinator.renew(lease_id='first',owner_id='owner',version=1,ttl=timedelta(seconds=10))
    assert renewed.version == 2 and coordinator.release('first')
    args.update(ttl=timedelta(milliseconds=150))
    assert coordinator.acquire(**args)
    time.sleep(.25)
    assert coordinator.active_slots('probe') == 0
    key = prefix+':ttl'
    client.set(key,'expires',px=150)
    assert 0 < client.pttl(key) <= 150
    time.sleep(.25)
    assert client.get(key) is None
    marker = 'zhiyi:n03:persistence-marker'
    previous = client.get(marker)
    if previous is None:
        previous = secrets.token_hex(32).encode()
        client.set(marker,previous)
    # No session credential is recorded here; only a random non-secret marker.
    result = {'status':'PASS','authRequired':denied,'ttlExpires':True,
        'luaAcquireCapacityRenewOwnerAndRelease':True,'expiredLeaseReclaimed':True,
        'persistenceMarkerSha256':hashlib.sha256(previous).hexdigest(),
        'serverVersion':client.info('server').get('redis_version'),
        'persistence':{k:v for k,v in client.info('persistence').items()
                       if k in ['aof_enabled','aof_last_write_status','rdb_last_bgsave_status']},
        'databases':{'backend':0,'coordination':1,'provider':2,'probes':3}}
    native.write_json(output,result)
    coordinator.close()
    print(result)


def capture(home, run_id, output):
    """Capture real persisted application identities before/after a cold restart.

    Uses the existing LocalIdentity; evidence contains only counts and hashes.
    """
    creds = native.credentials(home)
    info = deployment.manifest(home)
    def api(path):
        request = urllib.request.Request(f"http://127.0.0.1:{deployment.ports(info)['backend']}"+path,
            headers={'Origin':'kinlin-app://shell'})
        with urllib.request.urlopen(request,timeout=30) as response: return json.load(response)
    base = '/api/agentos/v2/runs/'+urllib.parse.quote(run_id,safe='')
    run = api(base)
    output_ref = run.get('outputRef')
    content = api(base+'/outputs/'+urllib.parse.quote(output_ref,safe='')) if output_ref else None
    calls = api(base+'/resource-usage/calls?pageSize=100')
    conversations = api('/api/conversations')
    counts = deployment.sql(info,creds, "\\connect zhiyi\nSELECT json_build_object("
        "'users',(SELECT count(*) FROM users), 'conversations',(SELECT count(*) FROM conversations),"
        "'messages',(SELECT count(*) FROM messages), 'loginSessions',(SELECT count(*) FROM iam_login_sessions));")
    with sqlite3.connect((home/'data/workflows.sqlite3').as_uri()+'?mode=ro',uri=True) as conn:
        workflow_counts = {table:conn.execute('SELECT count(*) FROM '+table).fetchone()[0]
            for table in ['tasks','runs','graph_execution_permits','execution_dispatch_commands']}
        stored_run = json.loads(conn.execute('SELECT payload FROM runs WHERE run_id=?', (run_id,)).fetchone()[0])
    # Dynamic execution uses the Run-frozen server binding, not the startup root.
    workspace_binding = stored_run.get('input', {}).get('workspaceBinding') or {}
    workspace = Path(workspace_binding.get('workspaceRoot') or info['workspace'])
    files = {str(p.relative_to(workspace)):hashlib.sha256(p.read_bytes()).hexdigest()
             for p in workspace.rglob('*') if p.is_file()}
    result = {'runId':run_id,'missionId':run['missionId'],'runStatus':run['status'],
        'outputRef':output_ref,'outputSha256':hashlib.sha256(json.dumps(content,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
        'workflowCounts':workflow_counts,'postgresCounts':json.loads(counts),
        'conversationIds':[x.get('contextId',x.get('id')) for x in conversations],
        'workspaceFiles':files,'modelCalls':calls,'home':str(home),
        'workspace':str(workspace), 'startupWorkspace':info['workspace'], 'workspaceBinding':workspace_binding, 'credentialsSha256':hashlib.sha256((home/'credentials.dpapi').read_bytes()).hexdigest()}
    native.write_json(output,result)
    native.write_json(output.with_name(output.stem+'-run.json'),run)
    native.write_json(output.with_name(output.stem+'-output.json'),content)
    if info.get('backend') == 'hands':
        import asyncio
        from adapters.hands_http import HandsHttpTransport, receipt_checksum
        class Credentials:
            def current_signing_credential(self, resource_id): return 'n01a-credential',creds['hmac']
        async def reconcile():
            transport = HandsHttpTransport(resource_id='capture',credential_provider=Credentials(),
                address=f"http://127.0.0.1:{deployment.ports(info)['host']}/v1/executions")
            verified=[]
            try:
                for line in (home/'hands-ledger/ledger.jsonl').read_text(encoding='utf-8').splitlines():
                    row=json.loads(line)
                    if row.get('t')!='receipt' or row['receipt'].get('identity',{}).get('runId')!=run_id: continue
                    receipt=row['receipt']
                    remote=await transport.query_execution(row['executionId'])
                    assert remote['receipt']==receipt and receipt_checksum(receipt)==receipt['checksum']
                    verified.append({'executionId':row['executionId'],'state':remote['state'],'receipt':receipt})
            finally: await transport.aclose()
            return verified
        verified=asyncio.run(reconcile())
        result['handsReceiptChecksums']={r['executionId']:r['receipt']['checksum'] for r in verified}
        result['handsReceiptsVerified']=len(verified)
        def member(node,name):
            return next((item['value'] for item in (node or {}).get('members',[]) if item['name']==name),{})
        artifact=member((content or {}).get('content',{}),'artifact')
        markdown=member(artifact,'content').get('text')
        if isinstance(markdown,str):
            result['contentArtifactEnvelope']={field:member(artifact,field).get('text') for field in
                ['artifactId','artifactKey','checksum','manifestId','mediaType']}
            with sqlite3.connect((home/'data/identity.sqlite3').as_uri()+'?mode=ro',uri=True) as identity:
                row=identity.execute("""SELECT a.artifact_id,a.artifact_key,a.checksum,a.content_ref,a.media_type,a.producer_attempt_id
                    FROM artifacts a JOIN run_artifact_bindings b ON b.artifact_id=a.artifact_id
                    WHERE b.run_id=? AND a.artifact_key='final'""",(run_id,)).fetchone()
            result['canonicalArtifact']=dict(zip(
                ['artifactId','artifactKey','checksum','manifestId','mediaType','producerAttemptId'],row)) if row else None
            result['canonicalMarkdownSha256']=hashlib.sha256(markdown.encode('utf-8')).hexdigest()
            output.with_name(output.stem+'-final.md').write_text(markdown,encoding='utf-8')
        native.write_json(output.with_name(output.stem+'-hands.json'),verified)
        native.write_json(output.with_name(output.stem+'-provenance.json'),api(base+'/provenance'))
        native.write_json(output.with_name(output.stem+'-trace.json'),api(base+'/trace?view=workspace'))
        native.write_json(output,result)
    print({'recorded':str(output),'runStatus':run['status'],'outputRef':output_ref,'files':files})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home',type=Path,default=Path(os.environ['LOCALAPPDATA'])/'ZhiyiNative/default')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--run-id',help='Capture persisted state instead of running Redis probes')
    args = parser.parse_args()
    if args.run_id: capture(args.home,args.run_id,args.output)
    else: main(args.home,args.output)
