"""Additional copied-metadata checks. Does not reopen PostgreSQL or application services."""
from pathlib import Path
import json,sqlite3,collections,hashlib,subprocess,os,sys,csv
sys.dont_write_bytecode=True
OUT=Path(__file__).parent;ROOT=OUT.parents[2];BASE=Path('E:/ZhiyiAudit/PR-TS-00B-20261107-r01');COPY=BASE/'sqlite-query-copy';PAYLOAD=BASE/'snapshot/payload'
def write(n,v):
 with (OUT/n).open('x',encoding='utf-8') as f:json.dump(v,f,ensure_ascii=False,indent=2)
def conn(p):
 c=sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row;c.execute('PRAGMA query_only=ON');return c
evidence={}
p=next(COPY.rglob('chroma.sqlite3'))
with conn(p) as c:
 fks=c.execute('PRAGMA foreign_key_check').fetchall();counts=collections.Counter((r[0],r[2],r[3]) for r in fks)
 evidence['chroma_fk_violations']=[dict(table=t,parent=parent,fk_id=i,n=n) for (t,parent,i),n in counts.items()]
 evidence['chroma_fk_definitions']={t:[dict(r) for r in c.execute('PRAGMA foreign_key_list("'+t.replace('"','""')+'")')] for t,_,_ in counts}
 # Compare legacy schema references structurally, without emitting row ids or collection ids.
 evidence['chroma_integrity_ok']=all(r[0]=='ok' for r in c.execute('PRAGMA integrity_check'))
with conn(COPY/'workflows.sqlite3') as c:
 legacy=[dict(r) for r in c.execute("SELECT mission_id,json_extract(payload,'$.input.authenticatedUserId') AS owner,json_extract(payload,'$.input.authenticatedTenantId') AS tenant FROM tasks")]
with conn(COPY/'identity.sqlite3') as c:
 identities=[dict(r) for r in c.execute("SELECT mission_id,user_id,json_extract(metadata_json,'$.tenantId') AS tenant,json_type(metadata_json,'$.tenantId') AS tenant_json_type FROM missions")]
byid={r['mission_id']:r for r in legacy}
evidence['identity_mission_vs_legacy']=dict(identity_missions=len(identities),missing_legacy_mission=sum(r['mission_id'] not in byid for r in identities),owner_mismatches=sum(r['mission_id'] in byid and r['user_id']!=byid[r['mission_id']]['owner'] for r in identities),tenant_mismatches=sum(r['mission_id'] in byid and (r['tenant'] or None)!=(byid[r['mission_id']]['tenant'] or None) for r in identities),raw_tenant_states=dict(collections.Counter('ABSENT' if r['tenant_json_type'] is None else 'NULL' if r['tenant'] is None else 'EMPTY' if r['tenant']=='' else 'NONEMPTY' for r in identities)))
# External workspace locations are intentionally not exported. Count bounded metadata only.
grants=json.loads((PAYLOAD/'hands-grants.json').read_text(encoding='utf-8'))['grants'];roots=sorted(set(g['canonicalRoot'] for g in grants))
original=Path(os.environ['LOCALAPPDATA'])/'ZhiyiNative/default-clean-20261106'
workspaces=[]
for i,value in enumerate(roots,1):
 p=Path(value);inside=p.resolve().is_relative_to(original.resolve())
 item=dict(alias='P'+str(i).zfill(2),inside_home=inside,included_by_home_snapshot=inside,exists=p.exists(),directory=p.is_dir())
 if p.is_dir():
  count=0;links=0
  with os.scandir(p) as it:
   for entry in it:
    count+=1
    if entry.is_symlink():links+=1
  item.update(top_level_entries=count,top_level_symlinks=links)
 workspaces.append(item)
evidence['all_projected_workspace_roots']=workspaces
evidence['external_workspaces_not_copied_or_modified']=sum(not r['inside_home'] for r in workspaces)
evidence['home_snapshot_scope']='all supported Home payload files, external workspaces excluded by supported tool; no claim of whole-machine/project backup'
evidence['hands_ledger']=dict(file_count=sum(p.is_file() for p in (PAYLOAD/'hands-ledger').rglob('*')),bytes=sum(p.stat().st_size for p in (PAYLOAD/'hands-ledger').rglob('*') if p.is_file()),preserved_by_snapshot_hashes=True,contents_not_exported=True)
log=(BASE/'private-evidence/postgres-retry.log').read_text(encoding='utf-8',errors='replace')
evidence['recovery']=dict(interrupted_cluster_logged='was interrupted' in log,redo_started='redo starts' in log,redo_completed='redo done' in log,ready='ready to accept connections' in log,clean_shutdown='database system is shut down' in log,raw_log_exported=False)
info=json.loads((PAYLOAD/'environment.json').read_text(encoding='utf-8'))
r=subprocess.run([str(Path(info['postgresBin'])/'pg_controldata.exe'),'-D',str(BASE/'pg-query-copy')],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=10)
evidence['copy_cluster_cleanly_shutdown']=any('Database cluster state:' in s and 'shut down' in s for s in r.stdout.splitlines())
# Cross-check previous inventory artifacts without modifying them.
rows=list(csv.DictReader((OUT/'artifact-manifest.csv').open(encoding='utf-8-sig')))
evidence['previous_manifest_checks']=len(rows)
evidence['previous_manifest_hash_mismatches']=[r['file'] for r in rows if hashlib.sha256((OUT/r['file']).read_bytes()).hexdigest()!=r['sha256']]
pg=json.loads((OUT/'PR-TS-00B-database-evidence.json').read_text(encoding='utf-8'))
evidence['schema_expectations']={
 'live_tables':sorted(set(r['table_name'] for r in pg['columns'])),
 'feedback_table_absent':'user_feedback' not in {r['table_name'] for r in pg['columns']},
 'workspace_partial_unique_present':any(r['indexname']=='local_workspace_one_selected' and 'WHERE' in r['indexdef'] for r in pg['indexes']),
 'workspace_grant_unique_present':any(r['table_name']=='local_workspace_authorizations' and r['contype']=='u' and r['definition']=='UNIQUE (grant_id)' for r in pg['constraints']),
 'session_user_foreign_key_present':any(r['table_name']=='iam_login_sessions' and r['contype']=='f' and 'REFERENCES users(id)' in r['definition'] for r in pg['constraints']),
 'jsonb_columns':[{k:r[k] for k in ['table_name','column_name']} for r in pg['columns'] if r['udt_name']=='jsonb'],
 'v5_v7_v8_columns_present':all(any(r['table_name']==t and r['column_name']==c for r in pg['columns']) for t,c in [('conversations','title'),('messages','file_url'),('roles','stable_key'),('conversations','workspace_mode'),('users','avatar_path')])}
write('PR-TS-00B-supplement-evidence.json',evidence)
print(json.dumps(evidence,ensure_ascii=False))
