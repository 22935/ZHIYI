"""Collect from the already-started owned copy; avoid pg_ctl inherited output pipes.
Attempt2 remains recorded, including its launcher timeout. No original-cluster fallback.
"""
from pathlib import Path
import sys,json,subprocess,importlib.util
sys.dont_write_bytecode=True
OUT=Path(__file__).parent
sp=importlib.util.spec_from_file_location('prts00b_runner',OUT/'PR-TS-00B-run-isolated-audit.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
def main():
 private=m.BASE/'private-evidence';copy=m.BASE/'pg-query-copy';snapshot=m.BASE/'snapshot'
 info=m.persistent.manifest(m.HOME);pg_bin=Path(info['postgresBin'])
 pid=int((copy/'postmaster.pid').read_text().splitlines()[0]);p=m.psutil.Process(pid)
 ident=dict(pid=pid,created=p.create_time(),exe=p.exe())
 def verify():
  x=m.psutil.Process(ident['pid'])
  assert abs(x.create_time()-ident['created'])<.01
  assert Path(x.exe()).resolve()==(pg_bin/'postgres.exe').resolve()
  assert any(str(copy).lower() in c.lower() for c in x.cmdline())
  return x
 verify();children={x.pid for x in [p,*p.children(recursive=True)]}
 listeners=[c for c in m.psutil.net_connections(kind='tcp') if c.status==m.psutil.CONN_LISTEN and c.laddr.port==m.PORT]
 assert listeners and all(c.pid in children and c.laddr.ip=='127.0.0.1' for c in listeners)
 initial=json.loads((private/'original-file-fingerprints.json').read_text(encoding='utf-8'))
 result=dict(started=m.now(),status='RUNNING',attached_only_to_current_audit_copy=True,temporary_process=dict(pid=pid,created=ident['created'],executable_verified=True,copy_cluster_verified=True,loopback_listener_verified=True),commands=[])
 try:
  creds=m.native.credentials(snapshot/'payload')
  conn=m.psycopg.connect(host='127.0.0.1',port=m.PORT,dbname=info['database'],user='zhiyi_admin',password=creds['pgadmin'],connect_timeout=5,autocommit=True,row_factory=m.dict_row,options='-c default_transaction_read_only=on -c statement_timeout=15000 -c lock_timeout=2000 -c idle_in_transaction_session_timeout=30000')
  creds.clear()
  with conn:
   conn.execute('BEGIN READ ONLY');conn.execute('SET LOCAL ROLE pg_read_all_data');conn.execute('SET LOCAL row_security=on')
   try:pg,raw=m.collect_pg(conn)
   finally:conn.execute('ROLLBACK')
  m.safe_write(OUT/'PR-TS-00B-database-evidence.json',pg)
  r=importlib.util.spec_from_file_location('prts00b_reconcile',OUT/'PR-TS-00B-reconcile.py');rm=importlib.util.module_from_spec(r);r.loader.exec_module(rm)
  cross=rm.reconcile(snapshot/'payload',raw,m.HOME)
  m.safe_write(OUT/'PR-TS-00B-identity-evidence.json',cross)
  result.update(status='EVIDENCE_COLLECTED',effective_read_only_role_verified=True,read_only_transaction_verified=True,write_privilege_tables=pg['write_privilege_tables'][0]['n'],table_counts=pg['table_counts'],migration_checks_all_match=all(x['checksum_matches'] and x['script_matches'] and x['success'] for x in pg['migration_comparison']),single_identity_candidate=cross['single_identity_candidate'])
 except BaseException as exc:
  result['status']='BLOCKED';result['error_type']=type(exc).__name__;msg=str(exc);result['error_code']=msg if msg.isupper() and len(msg)<100 else 'DETAILS_REDACTED'
 finally:
  verify()
  cmd=[str(pg_bin/'pg_ctl.exe'),'-D',str(copy),'-m','fast','-w','-t','45','stop'];result['commands'].append(dict(operation='stop_verified_owned_copy',argv=cmd))
  with (private/'pg_ctl-final-stop.stdout').open('xb') as so,(private/'pg_ctl-final-stop.stderr').open('xb') as se:
   stopped=subprocess.run(cmd,stdout=so,stderr=se,timeout=60,creationflags=subprocess.CREATE_NO_WINDOW)
  result['postgres_stop_exit']=stopped.returncode
  if stopped.returncode:result['status']='BLOCKED_STOP_FAILED'
  result['temporary_port_released']=not any(c.status==m.psutil.CONN_LISTEN and c.laddr.port==m.PORT for c in m.psutil.net_connections(kind='tcp'))
  after=m.fingerprint(m.HOME);result['original_home_hash_changes']=sum(initial.get(k)!=after.get(k) for k in set(initial)|set(after));result['original_home_files_checked']=len(initial)
  receipt=json.loads((snapshot/'snapshot.json').read_text(encoding='utf-8'))
  result['snapshot_sha256_verified_after_queries']=all(m.sha(snapshot/'payload'/name)==digest for name,digest in receipt['files'].items())
  result['finished']=m.now();m.safe_write(OUT/'PR-TS-00B-isolation-final-evidence.json',result);print(json.dumps(result,ensure_ascii=False))
 return 0 if result['status']=='EVIDENCE_COLLECTED' else 2
if __name__=='__main__':sys.exit(main())
