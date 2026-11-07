"""Authorized PR-TS-00B cold snapshot and isolated PG15 read-only evidence.
No original Home writes, application startup, migrations, DDL/DML, or raw identities in output.
Run with existing N03 Python using -B. Private snapshot stays on E:, never in desktop ZIP.
"""
from pathlib import Path
import sys,os,json,hashlib,shutil,subprocess,time,datetime,socket,csv,zlib,collections
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).parent
BASE=Path('E:/ZhiyiAudit/PR-TS-00B-20261107-r01')
HOME=Path(os.environ['LOCALAPPDATA'])/'ZhiyiNative/default-clean-20261106'
PORT=25432
NATIVE=ROOT/'ops/scripts/infra/windows/native'
sys.path.insert(0,str(NATIVE))
import psutil,win32file,win32con,pywintypes
import persistent_runtime as persistent
import native_runtime as native
import psycopg
from psycopg.rows import dict_row
def now():return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def safe_write(p,obj):
 with p.open('x',encoding='utf-8') as f:json.dump(obj,f,ensure_ascii=False,indent=2)
def fingerprint(root):
 result={}
 for directory,dirs,files in os.walk(root,followlinks=False):
  for name in dirs+files:
   p=Path(directory)/name
   if p.is_symlink() or p.is_junction():raise RuntimeError('REPARSE_POINT_BLOCKED')
  for name in files:
   p=Path(directory)/name
   result[p.relative_to(root).as_posix()]=dict(bytes=p.stat().st_size,sha256=sha(p))
 return result
def assert_stopped(info,state):
 for name,r in state['processes'].items():
  if psutil.pid_exists(r['pid']):raise RuntimeError('RECORDED_PID_EXISTS_REQUIRE_REVIEW')
 for p in psutil.process_iter(['pid','name']):
  if any(x in (p.info['name'] or '').lower() for x in ['postgres','pg_ctl']):raise RuntimeError('POSTGRES_PROCESS_PRESENT')
 for port in [*persistent.ports(info).values(),PORT]:
  if any(c.status==psutil.CONN_LISTEN and c.laddr.port==port for c in psutil.net_connections(kind='tcp')):raise RuntimeError('PORT_OCCUPIED')
 if shutil.disk_usage('E:/').free<2*1024**3:raise RuntimeError('INSUFFICIENT_E_SPACE')
def readonly_handle(p):return win32file.CreateFile(str(p),win32con.GENERIC_READ,0,None,win32con.OPEN_EXISTING,win32con.FILE_ATTRIBUTE_NORMAL,None)
def query(conn,sql,params=None):
 # Every business statement is SELECT/WITH; transaction/role statements are explicit elsewhere.
 if sql.lstrip().split(None,1)[0].upper() not in {'SELECT','WITH'}:raise RuntimeError('NON_SELECT_REJECTED')
 return conn.execute(sql,params).fetchall()
def flyway_checksum(p):
 # Flyway ChecksumCalculator: UTF8 lines, BOM removed; no line endings in CRC32.
 crc=0
 for l in p.read_text(encoding='utf-8-sig').splitlines():crc=zlib.crc32(l.encode('utf-8'),crc)
 return crc if crc<2**31 else crc-2**32
def collect_pg(conn):
 evidence={}
 evidence['connection']=query(conn,"SELECT current_database() AS database,current_user AS effective_role,current_setting('transaction_read_only') AS transaction_read_only,current_setting('server_version') AS server_version,inet_server_addr()::text AS address,inet_server_port() AS port")
 assert evidence['connection'][0]['effective_role']=='pg_read_all_data'
 assert evidence['connection'][0]['transaction_read_only']=='on'
 evidence['role']=query(conn,"SELECT rolname,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user")
 evidence['write_privilege_tables']=query(conn,"SELECT count(*) AS n FROM pg_tables WHERE schemaname='public' AND (has_table_privilege(current_user,quote_ident(schemaname)||'.'||quote_ident(tablename),'INSERT') OR has_table_privilege(current_user,quote_ident(schemaname)||'.'||quote_ident(tablename),'UPDATE') OR has_table_privilege(current_user,quote_ident(schemaname)||'.'||quote_ident(tablename),'DELETE') OR has_table_privilege(current_user,quote_ident(schemaname)||'.'||quote_ident(tablename),'TRUNCATE'))")
 if evidence['write_privilege_tables'][0]['n']:raise RuntimeError('READ_ROLE_HAS_WRITE_PRIVILEGE')
 evidence['flyway']=query(conn,"SELECT installed_rank,version,description,type,script,checksum,success FROM flyway_schema_history ORDER BY installed_rank")
 evidence['columns']=query(conn,"SELECT table_name,column_name,data_type,udt_name,is_nullable,column_default FROM information_schema.columns WHERE table_schema='public' ORDER BY table_name,ordinal_position")
 evidence['indexes']=query(conn,"SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='public' ORDER BY tablename,indexname")
 evidence['constraints']=query(conn,"SELECT c.relname AS table_name,k.conname,k.contype,pg_get_constraintdef(k.oid) AS definition FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' ORDER BY c.relname,k.conname")
 evidence['table_counts']=[]
 names={r['table_name'] for r in evidence['columns']}
 for table in ['users','roles','conversations','messages','iam_login_sessions','local_workspace_authorizations']:
  if table not in names:raise RuntimeError('REQUIRED_TABLE_MISSING')
  evidence['table_counts'].append(dict(table=table,n=query(conn,'SELECT count(*) AS n FROM '+table)[0]['n']))
 # Raw ids retained only in process memory for cross-store reconciliation, never serialized.
 users=[str(r['id']) for r in query(conn,'SELECT id FROM users ORDER BY id')]
 owner_rows=query(conn,"SELECT user_id::text AS owner,count(*) AS n FROM conversations GROUP BY user_id")
 role_rows=query(conn,"SELECT user_id::text AS owner,role_type,count(*) AS n FROM roles GROUP BY user_id,role_type")
 grants=query(conn,'SELECT workspace_id,user_id,tenant_id,grant_id,selected,revoked,root_identity,resource_id,canonical_root FROM local_workspace_authorizations')
 evidence['orphans']=query(conn,"""SELECT 'conversation_owner_missing' AS finding,count(*) AS n FROM conversations c LEFT JOIN users u ON u.id=c.user_id WHERE c.user_id IS NOT NULL AND u.id IS NULL
 UNION ALL SELECT 'conversation_owner_null',count(*) FROM conversations WHERE user_id IS NULL
 UNION ALL SELECT 'custom_role_owner_missing',count(*) FROM roles r LEFT JOIN users u ON u.id=r.user_id WHERE r.role_type='CUSTOM' AND r.user_id IS NOT NULL AND u.id IS NULL
 UNION ALL SELECT 'custom_role_owner_null',count(*) FROM roles WHERE role_type='CUSTOM' AND user_id IS NULL
 UNION ALL SELECT 'conversation_role_missing',count(*) FROM conversations c LEFT JOIN roles r ON r.id=c.role_id WHERE c.role_id IS NOT NULL AND r.id IS NULL
 UNION ALL SELECT 'message_conversation_missing',count(*) FROM messages m LEFT JOIN conversations c ON c.id=m.conversation_id WHERE c.id IS NULL
 UNION ALL SELECT 'workspace_owner_missing',count(*) FROM local_workspace_authorizations w LEFT JOIN users u ON u.id::text=w.user_id WHERE u.id IS NULL
 UNION ALL SELECT 'cross_owner_custom_role',count(*) FROM conversations c JOIN roles r ON r.id=c.role_id WHERE r.role_type='CUSTOM' AND c.user_id IS DISTINCT FROM r.user_id""")
 evidence['grant_anomalies']=query(conn,"""SELECT 'multiple_selected_live' AS finding,count(*) AS n FROM (SELECT user_id,tenant_id FROM local_workspace_authorizations WHERE selected AND NOT revoked GROUP BY user_id,tenant_id HAVING count(*)>1) t
 UNION ALL SELECT 'duplicate_grant_id',count(*) FROM (SELECT grant_id FROM local_workspace_authorizations GROUP BY grant_id HAVING count(*)>1) t
 UNION ALL SELECT 'roots_multiple_owners',count(*) FROM (SELECT canonical_root FROM local_workspace_authorizations GROUP BY canonical_root HAVING count(DISTINCT (user_id,tenant_id))>1) t
 UNION ALL SELECT 'selected_and_revoked',count(*) FROM local_workspace_authorizations WHERE selected AND revoked""")
 evidence['migration_comparison']=[]
 for p in sorted((ROOT/'apps/backend/src/main/resources/db/migration').glob('V*.sql'),key=lambda p:int(p.name.split('__')[0][1:])):
  ver=p.name.split('__')[0][1:];rows=[r for r in evidence['flyway'] if r['version']==ver]
  evidence['migration_comparison'].append(dict(version=ver,script=p.name,sha256=sha(p),calculated_flyway_crc32=flyway_checksum(p),history_rows=len(rows),script_matches=len(rows)==1 and rows[0]['script']==p.name,checksum_matches=len(rows)==1 and rows[0]['checksum']==flyway_checksum(p),success=len(rows)==1 and rows[0]['success']))
 return evidence,dict(users=users,conversations=owner_rows,roles=role_rows,grants=grants)
def main():
 started=now();persistent.validate_home(HOME)
 if BASE.exists():raise RuntimeError('AUDIT_DESTINATION_EXISTS')
 info=persistent.manifest(HOME);state=persistent.state_for(HOME);assert_stopped(info,state)
 pg_bin=Path(info['postgresBin']);assert (HOME/'postgres/PG_VERSION').read_text().strip()=='15'
 for parent in [BASE,*BASE.parents]:
  if parent.exists() and (parent.is_junction() or parent.is_symlink()):raise RuntimeError('AUDIT_ANCESTOR_REPARSE')
 # Acquiring a read handle with share=0 does not write the original lifecycle file.
 control=HOME.with_name('.'+HOME.name+'-control')/'lifecycle.lock'
 lock=readonly_handle(control)
 BASE.mkdir(parents=True,exist_ok=False);persistent.protect(BASE)
 private=BASE/'private-evidence';private.mkdir();snapshot=BASE/'snapshot';copy=BASE/'pg-query-copy'
 before=fingerprint(HOME);prior=fingerprint(OUT)
 safe_write(private/'original-file-fingerprints.json',before)
 commands=[];proc=None;pg_identity=None;summary=dict(started=started,base=str(BASE),home_alias='N03_HOME',authorization='User explicitly approved backup/isolated inspection; no destructive source action needed',original_cluster_state='in production/offline; recovery only in copy',status='RUNNING')
 try:
  result=persistent.backup(HOME,snapshot)
  receipt=json.loads((snapshot/'snapshot.json').read_text(encoding='utf-8'))
  assert receipt['home']==str(HOME)
  for name,digest in receipt['files'].items():
   p=snapshot/'payload'/name
   assert p.resolve().is_relative_to((snapshot/'payload').resolve()) and sha(p)==digest
  payload=fingerprint(snapshot/'payload')
  excluded={'logs','webview','temp','lifecycle.lock'}
  expected={k:v for k,v in before.items() if k.split('/')[0] not in excluded}
  if payload!=expected:raise RuntimeError('SNAPSHOT_SOURCE_MISMATCH')
  summary['snapshot']=dict(status=result['status'],files=len(payload),bytes=sum(r['bytes'] for r in payload.values()),sha256_verified=True,source_file_set_matches=True,receipt_sha256=sha(snapshot/'snapshot.json'),excluded=sorted(excluded),postgres_major='15',external_workspace_included=False)
  safe_write(private/'prior-audit-file-fingerprints.json',prior)
  safe_write(private/'snapshot-verification.json',summary['snapshot'])
  shutil.copytree(snapshot/'payload/postgres',copy)
  assert fingerprint(copy)=={k.split('/',1)[1]:v for k,v in payload.items() if k.startswith('postgres/')}
  if list((copy/'pg_tblspc').iterdir()) or (copy/'pg_wal').is_junction():raise RuntimeError('EXTERNAL_PG_STORAGE_BLOCKED')
  options=['-h','127.0.0.1','-p',str(PORT)]
  settings={'data_directory':str(copy),'hba_file':str(copy/'pg_hba.conf'),'ident_file':str(copy/'pg_ident.conf'),'external_pid_file':"''",'default_transaction_read_only':'on','autovacuum':'off','archive_mode':'off','archive_command':"''",'restore_command':"''",'primary_conninfo':"''",'shared_preload_libraries':"''",'session_preload_libraries':"''",'local_preload_libraries':"''",'logging_collector':'off','ssl':'off'}
  for k,v in settings.items():options+=['-c',k+'='+v]
  cmd=[str(pg_bin/'pg_ctl.exe'),'-D',str(copy),'-l',str(private/'postgres.log'),'-o',' '.join(options),'-w','-t','60','start']
  commands.append(dict(operation='start_isolated_postgres',argv=cmd))
  start=subprocess.run(cmd,capture_output=True,timeout=75)
  (private/'pg_ctl-start.stdout').write_bytes(start.stdout);(private/'pg_ctl-start.stderr').write_bytes(start.stderr)
  summary['postgres_start_exit']=start.returncode
  if start.returncode:raise RuntimeError('ISOLATED_POSTGRES_START_FAILED')
  pid=int((copy/'postmaster.pid').read_text().splitlines()[0]);proc=psutil.Process(pid)
  pg_identity=dict(pid=pid,created=proc.create_time(),exe=proc.exe(),cluster=str(copy))
  assert Path(proc.exe()).resolve()==(pg_bin/'postgres.exe').resolve()
  assert any(str(copy).lower() in x.lower() for x in proc.cmdline())
  summary['temporary_process']=dict(pid=pid,created=pg_identity['created'],verified_executable=True,verified_copy_cluster=True)
  listeners=[c for c in psutil.net_connections(kind='tcp') if c.status==psutil.CONN_LISTEN and c.laddr.port==PORT]
  treeids={p.pid for p in [proc,*proc.children(recursive=True)]}
  assert listeners and all(c.pid in treeids and c.laddr.ip=='127.0.0.1' for c in listeners)
  # Decrypt the snapshot's DPAPI only in memory. Never serialize credentials or connection DSN.
  creds=native.credentials(snapshot/'payload')
  conn=psycopg.connect(host='127.0.0.1',port=PORT,dbname=info['database'],user='zhiyi_admin',password=creds['pgadmin'],connect_timeout=5,autocommit=True,row_factory=dict_row,options='-c default_transaction_read_only=on -c statement_timeout=15000 -c lock_timeout=2000 -c idle_in_transaction_session_timeout=30000')
  creds.clear()
  with conn:
   conn.execute('BEGIN READ ONLY');conn.execute('SET LOCAL ROLE pg_read_all_data');conn.execute('SET LOCAL row_security=on')
   try:pg,raw=collect_pg(conn)
   finally:conn.execute('ROLLBACK')
  safe_write(OUT/'PR-TS-00B-database-evidence.json',pg)
  # Raw identity data are passed in memory to a separate read-only reconciliation module.
  import importlib.util
  spec=importlib.util.spec_from_file_location('prts00b_reconcile',OUT/'PR-TS-00B-reconcile.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  cross=module.reconcile(snapshot/'payload',raw,HOME)
  safe_write(OUT/'PR-TS-00B-identity-evidence.json',cross)
  summary['queries']='VERIFIED effective pg_read_all_data role, no write privileges, READ ONLY transaction; rolled back'
  summary['database_counts']=pg['table_counts'];summary['migration_checks_all_match']=all(r['checksum_matches'] and r['script_matches'] and r['success'] for r in pg['migration_comparison'])
  summary['status']='EVIDENCE_COLLECTED'
 except BaseException as exc:
  # Do not emit raw driver errors, SQL values, usernames or filesystem data.
  summary['status']='BLOCKED';summary['error_type']=type(exc).__name__
  msg=str(exc)
  summary['error_code']=msg if msg.isupper() and len(msg)<100 else 'DETAILS_REDACTED'
 finally:
  if pg_identity:
   try:
    p=psutil.Process(pg_identity['pid'])
    assert abs(p.create_time()-pg_identity['created'])<.01 and Path(p.exe()).resolve()==Path(pg_identity['exe']).resolve()
    assert any(str(copy).lower() in x.lower() for x in p.cmdline())
    stopcmd=[str(pg_bin/'pg_ctl.exe'),'-D',str(copy),'-m','fast','-w','-t','45','stop'];commands.append(dict(operation='stop_owned_isolated_postgres',argv=stopcmd))
    stopped=subprocess.run(stopcmd,capture_output=True,timeout=60)
    (private/'pg_ctl-stop.stdout').write_bytes(stopped.stdout);(private/'pg_ctl-stop.stderr').write_bytes(stopped.stderr)
    summary['postgres_stop_exit']=stopped.returncode
    if stopped.returncode:summary['status']='BLOCKED_STOP_FAILED'
   except psutil.NoSuchProcess:summary['postgres_stop_exit']='already_exited'
   except BaseException as exc:summary['status']='BLOCKED_PROCESS_IDENTITY_OR_STOP';summary['stop_error_type']=type(exc).__name__
  elif (copy/'postmaster.pid').exists():
   # Startup failed: never signal a process without proving identity.
   summary['failed_start_pid_record_present']=True
  after=fingerprint(HOME);diff=[k for k in set(before)|set(after) if before.get(k)!=after.get(k)]
  summary['original_home_files_checked']=len(before);summary['original_home_hash_changes']=len(diff)
  safe_write(private/'original-home-hash-differences.json',diff)
  summary['prior_audit_hash_changes']=sum(not (OUT/k).exists() or sha(OUT/k)!=v['sha256'] for k,v in prior.items())
  summary['finished']=now();summary['commands']=commands
  lock.Close()
  summary['temporary_port_released']=not any(c.status==psutil.CONN_LISTEN and c.laddr.port==PORT for c in psutil.net_connections(kind='tcp'))
  safe_write(OUT/'PR-TS-00B-isolation-evidence.json',summary)
  print(json.dumps(summary,ensure_ascii=False))
 return 0 if summary['status']=='EVIDENCE_COLLECTED' else 2
if __name__=='__main__':sys.exit(main())
