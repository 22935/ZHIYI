"""Read-only reconciliation of copied SQLite metadata. Raw ids remain in memory."""
from pathlib import Path
import sqlite3,json,shutil,collections,os,hashlib
def qi(s):return '"'+s.replace('"','""')+'"'
def reconcile(payload,pg,original_home):
 base=payload.parent.parent;work=base/'sqlite-query-copy'
 shutil.copytree(payload/'data',work)
 databases=[];runs=[];tasks=[];directowners=[];checkpoints=[];manifests=[];artifacts=[];identityruns=[];identitymissions=[];attachments=[]
 for p in sorted(work.rglob('*')):
  if p.suffix not in {'.sqlite3','.sqlite','.db'} or not p.is_file():continue
  alias='S'+str(len(databases)+1).zfill(2)
  con=sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True)
  con.row_factory=sqlite3.Row;con.execute('PRAGMA query_only=ON')
  tables=[r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
  db=dict(alias=alias,logical_file=p.name,query_only=con.execute('PRAGMA query_only').fetchone()[0],integrity_ok=all(r[0]=='ok' for r in con.execute('PRAGMA integrity_check')),tables=[],foreign_key_violations=len(con.execute('PRAGMA foreign_key_check').fetchall()))
  for t in tables:
   cols=[r[1] for r in con.execute('PRAGMA table_info('+qi(t)+')')]
   count=con.execute('SELECT count(*) FROM '+qi(t)).fetchone()[0]
   db['tables'].append(dict(table=t,columns=cols,rows=count))
   if t=='runs' and {'run_id','mission_id','payload'}.issubset(cols):
    ownercol='owner_user_id' if 'owner_user_id' in cols else 'NULL';tenantcol='owner_tenant_id' if 'owner_tenant_id' in cols else 'NULL'
    sql=f"SELECT run_id,mission_id,{ownercol} AS indexed_owner,{tenantcol} AS indexed_tenant,json_extract(payload,'$.input.authenticatedUserId') AS owner,json_extract(payload,'$.input.authenticatedTenantId') AS tenant,json_type(payload,'$.input.authenticatedTenantId') AS tenant_json_type,json_extract(payload,'$.input.workspaceBinding') AS binding FROM {qi(t)}"
    for r in con.execute(sql):runs.append(dict(r))
   if t=='tasks' and {'mission_id','payload'}.issubset(cols):
    tasks += [dict(r) for r in con.execute("SELECT mission_id,json_extract(payload,'$.input.authenticatedUserId') AS owner,json_extract(payload,'$.input.authenticatedTenantId') AS tenant FROM "+qi(t))]
   for ownercol in ['owner_user_id','user_id']:
    if ownercol in cols:
     tenantcol='owner_tenant_id' if 'owner_tenant_id' in cols else 'tenant_id' if 'tenant_id' in cols else None
     sql='SELECT '+qi(ownercol)+' AS owner,'+(qi(tenantcol) if tenantcol else 'NULL')+' AS tenant,count(*) AS n FROM '+qi(t)+' GROUP BY '+qi(ownercol)+((','+qi(tenantcol)) if tenantcol else '')
     directowners += [dict(database=alias,table=t,**dict(r)) for r in con.execute(sql)]
   if 'thread_id' in cols and 'checkpoint' in t:
    checkpoints += [dict(table=t,**dict(r)) for r in con.execute('SELECT thread_id,count(*) AS n FROM '+qi(t)+' GROUP BY thread_id')]
   if t=='content_manifests':
    manifests += [dict(r) for r in con.execute('SELECT manifest_id,owner_type,owner_id,kind,byte_length,sealed FROM content_manifests')]
   if t=='artifacts' and {'artifact_id','mission_id','origin_run_id','content_ref'}.issubset(cols):
    artifacts += [dict(r) for r in con.execute('SELECT artifact_id,mission_id,origin_run_id,content_ref FROM artifacts')]
   if t=='workflow_runs_v2':identityruns += [dict(r) for r in con.execute('SELECT run_id,mission_id FROM workflow_runs_v2')]
   if t=='missions' and {'mission_id','user_id'}.issubset(cols):identitymissions += [dict(r) for r in con.execute('SELECT mission_id,user_id FROM missions')]
   if t=='input_attachments':attachments += [dict(r) for r in con.execute('SELECT attachment_id,owner_user_id,owner_tenant_id FROM input_attachments')]
  con.close();databases.append(db)
 # One alias registry covers every store. No reversible raw identity mapping is serialized.
 owners=set(pg['users'])
 for rows,key in [(pg['conversations'],'owner'),(pg['roles'],'owner'),(pg['grants'],'user_id'),(runs,'owner'),(tasks,'owner'),(directowners,'owner'),(identitymissions,'user_id'),(attachments,'owner_user_id')]:owners.update(str(r[key]) for r in rows if r.get(key) not in (None,''))
 aliases={u:'U'+str(i+1).zfill(2) for i,u in enumerate(sorted(owners))}
 tenants=set(str(r['tenant_id']) for r in pg['grants'] if r['tenant_id'] not in (None,''))
 for rows,key in [(runs,'tenant'),(tasks,'tenant'),(directowners,'tenant'),(attachments,'owner_tenant_id')]:tenants.update(str(r[key]) for r in rows if r.get(key) not in (None,''))
 tenantaliases={t:'T'+str(i+1).zfill(2) for i,t in enumerate(sorted(tenants)) if t!='__unscoped__'}
 def actor(v):return 'NULL' if v is None else 'EMPTY' if v=='' else aliases[str(v)]
 def tenant(v):return 'NULL' if v is None else 'EMPTY' if v=='' else 'UNSCOPED_SENTINEL' if v=='__unscoped__' else tenantaliases[str(v)]
 def norm(v):return v or '__unscoped__'
 result=dict(status='VERIFIED copied metadata only',databases=databases,identity_registry_scope='single cross-store alias registry for this audit; U labels reveal no UUID; no raw mapping exported',pg_user_count=len(pg['users']),distinct_owner_count=len(owners),pg_actors=[actor(u) for u in pg['users']],owners_not_in_pg_users=[actor(u) for u in sorted(owners-set(pg['users']))],conversation_owners=[dict(actor=actor(r['owner']),n=r['n']) for r in pg['conversations']],role_owners=[dict(actor=actor(r['owner']),role_type=r['role_type'],n=r['n']) for r in pg['roles']],sqlite_direct_owner_groups=[dict(database=r['database'],table=r['table'],actor=actor(r['owner']),tenant=tenant(r['tenant']),n=r['n']) for r in directowners])
 grants={r['workspace_id']:r for r in pg['grants']};runids={r['run_id'] for r in runs};missionids={r['mission_id'] for r in tasks}|{r['mission_id'] for r in identitymissions};v2runids={r['run_id'] for r in identityruns}
 roots=set(r['canonical_root'] for r in pg['grants'])
 for r in runs:
  if r['binding']:
   b=json.loads(r['binding']);roots.add(b.get('workspaceRoot',''))
 roots.discard('');rootalias={r:'W'+str(i+1).zfill(2) for i,r in enumerate(sorted(roots))}
 def rootview(value):
  p=Path(value);exists=p.exists();inside=p.resolve().is_relative_to(original_home.resolve())
  return dict(workspace=rootalias[value],inside_original_home=inside,exists=exists,is_directory=p.is_dir(),included_in_snapshot=inside)
 result['workspace_roots']=[rootview(r) for r in sorted(roots)]
 grouped=collections.Counter()
 for g in pg['grants']:grouped[(actor(g['user_id']),tenant(g['tenant_id']),bool(g['selected']),bool(g['revoked']))]+=1
 result['grant_owner_tenant_groups']=[dict(actor=a,tenant=t,selected=s,revoked=r,n=n) for (a,t,s,r),n in sorted(grouped.items())]
 result['run_count']=len(runs);result['task_count']=len(tasks);result['runs']=[]
 runalias={r:'R'+str(i+1).zfill(2) for i,r in enumerate(sorted(runids))}
 taskowners={r['mission_id']:(r['owner'],r['tenant']) for r in tasks}
 bindingcounts=collections.Counter()
 for r in sorted(runs,key=lambda r:r['run_id']):
  b=json.loads(r['binding']) if r['binding'] else None;verdict=[]
  if not b:verdict=['NO_FROZEN_BINDING']
  else:
   g=grants.get(b.get('workspaceId'))
   if not g:verdict=['GRANT_ROW_MISSING']
   else:
    if g['revoked']:verdict.append('GRANT_REVOKED')
    if g['grant_id']!=b.get('grantId'):verdict.append('GRANT_EPOCH_MISMATCH')
    if g['user_id']!=r['owner']:verdict.append('OWNER_MISMATCH')
    if g['tenant_id']!=norm(r['tenant']):verdict.append('TENANT_MISMATCH')
    if g['resource_id']!=b.get('resourceId'):verdict.append('RESOURCE_MISMATCH')
    if g['canonical_root']!=b.get('workspaceRoot'):verdict.append('ROOT_MISMATCH')
    if g['root_identity']!=b.get('rootIdentity'):verdict.append('ROOT_IDENTITY_BINDING_MISMATCH')
    try:
     st=Path(g['canonical_root']).stat()
     if f'{st.st_dev}:{st.st_ino}'!=g['root_identity']:verdict.append('CURRENT_DIRECTORY_IDENTITY_CHANGED')
    except OSError:verdict.append('CURRENT_DIRECTORY_UNAVAILABLE')
    if not verdict:verdict=['MATCH_CURRENT_GRANT']
  for x in verdict:bindingcounts[x]+=1
  result['runs'].append(dict(run=runalias[r['run_id']],actor=actor(r['owner']),raw_tenant=tenant(r['tenant']),tenant_presence='ABSENT' if r['tenant_json_type'] is None else r['tenant_json_type'],grant_query_tenant=tenant(norm(r['tenant'])),indexed_owner_matches=r['indexed_owner']==(str(r['owner']).strip() if r['owner'] else None),indexed_tenant_matches=r['indexed_tenant']==(str(r['tenant']).strip() if r['tenant'] else None),mission_exists=r['mission_id'] in missionids,task_owner_matches=taskowners.get(r['mission_id'])==(r['owner'],r['tenant']) if r['mission_id'] in taskowners else None,binding_status=verdict))
 result['binding_summary']=dict(bindingcounts)
 result['checkpoint_summary']=dict(rows=sum(r['n'] for r in checkpoints),thread_groups=len(checkpoints),rows_with_unknown_run=sum(r['n'] for r in checkpoints if r['thread_id'] not in runids|v2runids))
 result['artifact_summary']=dict(content_manifests=len(manifests),identity_artifacts=len(artifacts),identity_runs=len(identityruns),identity_missions=len(identitymissions),identity_missions_unknown_pg_owner=sum(r['user_id'] not in pg['users'] for r in identitymissions),identity_artifact_missing_origin_run=sum(r['origin_run_id'] not in v2runids for r in artifacts),identity_artifact_missing_mission=sum(r['mission_id'] not in missionids for r in artifacts),input_attachments=len(attachments))
 manifestgroups=collections.Counter();unknownowners=0
 for m in manifests:
  typ=m['owner_type'];known=None
  if typ.lower()=='run':known=m['owner_id'] in runids|v2runids
  elif typ.lower()=='mission':known=m['owner_id'] in missionids
  if known is False:unknownowners+=1
  manifestgroups[(typ if typ in {'run','mission','task','user','system','input','artifact','attempt'} else 'OTHER',known)]+=1
 result['artifact_summary']['manifest_owner_reference_missing']=unknownowners
 result['manifest_owner_groups']=[dict(owner_type=t,reference_exists=k,n=n) for (t,k),n in manifestgroups.items()]
 # Inspect only grant projection metadata; no source application construction or backfill.
 projections=[]
 for p in payload.glob('*.json'):
  if p.stat().st_size>10_000_000:continue
  try:d=json.loads(p.read_text(encoding='utf-8-sig'))
  except (ValueError,UnicodeError):continue
  if isinstance(d,dict) and isinstance(d.get('grants'),list):
   gs=d['grants'];dynamic=[g for g in gs if str(g.get('grantId','')).startswith('wgrant_')]
   expected={g['grant_id']:g for g in pg['grants']};byid={g.get('grantId'):g for g in dynamic}
   mismatch=sum(i not in byid or bool(byid[i].get('revoked'))!=bool(g['revoked']) or byid[i].get('canonicalRoot')!=g['canonical_root'] for i,g in expected.items())
   projections.append(dict(logical_file=p.name,grants=len(gs),dynamic_grants=len(dynamic),operator_grants=len(gs)-len(dynamic),missing_or_different_dynamic_grants=mismatch,extra_dynamic_grants=len(set(byid)-set(expected))))
 result['grant_projections']=projections
 result['single_identity_candidate']=len(pg['users'])==1 and owners==set(pg['users']) and not any(not d['integrity_ok'] or d['foreign_key_violations'] for d in databases)
 result['no_identity_merge_performed']=True
 return result
