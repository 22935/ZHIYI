"""Second isolated-copy attempt: Windows -c name= uses an empty value, not literal ''."""
from pathlib import Path
import sys,json,subprocess,time,importlib.util,os
sys.dont_write_bytecode=True
OUT=Path(__file__).parent
spec=importlib.util.spec_from_file_location('prts00b_runner',OUT/'PR-TS-00B-run-isolated-audit.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def main():
 private=m.BASE/'private-evidence';copy=m.BASE/'pg-query-copy';snapshot=m.BASE/'snapshot'
 info=m.persistent.manifest(m.HOME);state=m.persistent.state_for(m.HOME);m.assert_stopped(info,state)
 initial=json.loads((private/'original-file-fingerprints.json').read_text(encoding='utf-8'))
 if m.fingerprint(m.HOME)!=initial:raise RuntimeError('ORIGINAL_HOME_DRIFT_BLOCKED')
 receipt=json.loads((snapshot/'snapshot.json').read_text(encoding='utf-8'))
 assert all(m.sha(snapshot/'payload'/name)==digest for name,digest in receipt['files'].items())
 lock=m.readonly_handle(m.HOME.with_name('.'+m.HOME.name+'-control')/'lifecycle.lock')
 pg_bin=Path(info['postgresBin']);identity=None
 summary=dict(attempt=2,started=m.now(),reason='Windows empty GUC values corrected; attempt1 preserved',status='RUNNING',commands=[])
 try:
  options=['-h','127.0.0.1','-p',str(m.PORT)]
  settings={'data_directory':str(copy),'hba_file':str(copy/'pg_hba.conf'),'ident_file':str(copy/'pg_ident.conf'),'external_pid_file':'','default_transaction_read_only':'on','autovacuum':'off','archive_mode':'off','archive_command':'','restore_command':'','primary_conninfo':'','shared_preload_libraries':'','session_preload_libraries':'','local_preload_libraries':'','logging_collector':'off','ssl':'off'}
  for k,v in settings.items():options+=['-c',k+'='+v]
  cmd=[str(pg_bin/'pg_ctl.exe'),'-D',str(copy),'-l',str(private/'postgres-retry.log'),'-o',' '.join(options),'-w','-t','60','start']
  summary['commands'].append(dict(operation='start_owned_copy_retry',argv=cmd))
  r=subprocess.run(cmd,capture_output=True,timeout=75)
  (private/'pg_ctl-retry.stdout').write_bytes(r.stdout);(private/'pg_ctl-retry.stderr').write_bytes(r.stderr)
  summary['postgres_start_exit']=r.returncode
  if r.returncode:raise RuntimeError('ISOLATED_RETRY_START_FAILED')
  pid=int((copy/'postmaster.pid').read_text().splitlines()[0]);proc=m.psutil.Process(pid)
  assert Path(proc.exe()).resolve()==(pg_bin/'postgres.exe').resolve() and any(str(copy).lower() in x.lower() for x in proc.cmdline())
  identity=dict(pid=pid,created=proc.create_time(),exe=proc.exe())
  summary['temporary_process']=dict(pid=pid,created=identity['created'],verified_copy_cluster=True,verified_executable=True)
  ids={p.pid for p in [proc,*proc.children(recursive=True)]};listen=[c for c in m.psutil.net_connections(kind='tcp') if c.status==m.psutil.CONN_LISTEN and c.laddr.port==m.PORT]
  assert listen and all(c.laddr.ip=='127.0.0.1' and c.pid in ids for c in listen)
  creds=m.native.credentials(snapshot/'payload')
  conn=m.psycopg.connect(host='127.0.0.1',port=m.PORT,dbname=info['database'],user='zhiyi_admin',password=creds['pgadmin'],connect_timeout=5,autocommit=True,row_factory=m.dict_row,options='-c default_transaction_read_only=on -c statement_timeout=15000 -c lock_timeout=2000 -c idle_in_transaction_session_timeout=30000')
  creds.clear()
  with conn:
   conn.execute('BEGIN READ ONLY');conn.execute('SET LOCAL ROLE pg_read_all_data');conn.execute('SET LOCAL row_security=on')
   try:pg,raw=m.collect_pg(conn)
   finally:conn.execute('ROLLBACK')
  m.safe_write(OUT/'PR-TS-00B-database-evidence.json',pg)
  rspec=importlib.util.spec_from_file_location('prts00b_reconcile',OUT/'PR-TS-00B-reconcile.py');rm=importlib.util.module_from_spec(rspec);rspec.loader.exec_module(rm)
  cross=rm.reconcile(snapshot/'payload',raw,m.HOME)
  m.safe_write(OUT/'PR-TS-00B-identity-evidence.json',cross)
  summary['status']='EVIDENCE_COLLECTED';summary['table_counts']=pg['table_counts'];summary['migration_checks_all_match']=all(x['checksum_matches'] and x['script_matches'] and x['success'] for x in pg['migration_comparison'])
  summary['read_only_role_verified']=True;summary['read_only_transaction_verified']=True
 except BaseException as exc:
  summary['status']='BLOCKED';summary['error_type']=type(exc).__name__
  msg=str(exc);summary['error_code']=msg if msg.isupper() and len(msg)<100 else 'DETAILS_REDACTED'
 finally:
  if identity:
   try:
    p=m.psutil.Process(identity['pid'])
    assert abs(p.create_time()-identity['created'])<.01 and Path(p.exe()).resolve()==Path(identity['exe']).resolve() and any(str(copy).lower() in x.lower() for x in p.cmdline())
    cmd=[str(pg_bin/'pg_ctl.exe'),'-D',str(copy),'-m','fast','-w','-t','45','stop'];summary['commands'].append(dict(operation='stop_owned_copy',argv=cmd))
    r=subprocess.run(cmd,capture_output=True,timeout=60)
    (private/'pg_ctl-retry-stop.stdout').write_bytes(r.stdout);(private/'pg_ctl-retry-stop.stderr').write_bytes(r.stderr)
    summary['postgres_stop_exit']=r.returncode
    if r.returncode:summary['status']='BLOCKED_STOP_FAILED'
   except m.psutil.NoSuchProcess:summary['postgres_stop_exit']='already_exited'
   except BaseException as exc:summary['status']='BLOCKED_STOP';summary['stop_error_type']=type(exc).__name__
  after=m.fingerprint(m.HOME)
  summary['original_home_hash_changes']=sum(initial.get(k)!=after.get(k) for k in set(initial)|set(after))
  summary['original_home_files_checked']=len(initial)
  summary['snapshot_sha256_verified_after_queries']=all(m.sha(snapshot/'payload'/name)==digest for name,digest in receipt['files'].items())
  summary['temporary_port_released']=not any(c.status==m.psutil.CONN_LISTEN and c.laddr.port==m.PORT for c in m.psutil.net_connections(kind='tcp'))
  summary['finished']=m.now();lock.Close()
  m.safe_write(OUT/'PR-TS-00B-isolation-attempt2-evidence.json',summary)
  print(json.dumps(summary,ensure_ascii=False))
 return 0 if summary['status']=='EVIDENCE_COLLECTED' else 2
if __name__=='__main__':sys.exit(main())
