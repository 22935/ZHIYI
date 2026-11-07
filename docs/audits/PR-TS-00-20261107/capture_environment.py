"""Capture safe metadata only. Never decrypt credentials or import application code."""
from pathlib import Path
import os,json,hashlib,socket,subprocess,re,datetime,importlib.metadata
OUT=Path(__file__).parent;ROOT=OUT.parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def command(args):
 r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=25)
 return {'exit_code':r.returncode,'output':(r.stdout+r.stderr).strip()}
import psutil
base=Path(os.environ['LOCALAPPDATA'])/'ZhiyiNative';homes=[]
for h in base.iterdir():
 if not h.is_dir() or not (h/'environment.json').exists():continue
 e=json.loads((h/'environment.json').read_text(encoding='utf-8-sig'))
 s=json.loads((h/'runtime-state.json').read_text(encoding='utf-8-sig')) if (h/'runtime-state.json').exists() else {}
 processes=[]
 for k,r in s.get('processes',{}).items():
  try:
   proc=psutil.Process(r['pid']);created=proc.create_time()
   processes.append({'service':k,'recorded_pid':r['pid'],'exists':True,'identity_matches':abs(created-r.get('created',0))<.01,'executable_name':proc.name()})
  except psutil.NoSuchProcess:processes.append({'service':k,'recorded_pid':r['pid'],'exists':False,'identity_matches':False})
  except psutil.AccessDenied:processes.append({'service':k,'recorded_pid':r['pid'],'status':'BLOCKED access denied'})
 ports={k:p+int(e.get('portOffset',0)) for k,p in zip(['postgres','redis','ai','host','java','frontend','terminal','debug'],[15432,16379,18761,18765,18080,15200,18766,19222])}
 for k,v in list(ports.items()):
  sock=socket.socket();sock.settimeout(.25)
  try:opened=sock.connect_ex(('127.0.0.1',v))==0
  finally:sock.close()
  ports[k]={'port':v,'loopback_connectable':opened}
 logs=[]
 sessions=sorted(p for p in (h/'logs').iterdir() if p.is_dir()) if (h/'logs').exists() else []
 if sessions:
  for p in sessions[-1].glob('*'):
   if not p.is_file():continue
   # No raw logs, usernames, command lines, workspace paths, messages or tokens retained.
   b=p.read_bytes();text=b.decode('utf-8',errors='replace')
   logs.append({'file':p.name,'bytes':len(b),'sha256':sha(p),'error_word_count':len(re.findall(r'\bERROR\b',text)),'warn_word_count':len(re.findall(r'\bWARN\b',text))})
 homes.append({'home':'<LOCALAPPDATA>/ZhiyiNative/'+h.name,'environment_sha256':sha(h/'environment.json'),'state_sha256':sha(h/'runtime-state.json') if (h/'runtime-state.json').exists() else None,'format':e.get('format'),'initialized':e.get('initialized'),'portOffset':e.get('portOffset'),'database_name':e.get('database'),'database_role':e.get('databaseRole'),'processes':processes,'ports':ports,'log_session_count':len(sessions),'latest_log_metadata':logs,'database_audit':'BLOCKED no live PostgreSQL; no credentials decrypted; no query executed'})
versions={}
for name,args in {'node':['node','--version'],'java':['java','-version'],'python':[os.sys.executable,'--version'],'postgres':[str(base/'dependencies/postgresql-15.19/pgsql/bin/postgres.exe'),'--version']}.items():versions[name]=command(args)
for d in ['apps/frontend','apps/hands','apps/desktop/electron','apps/terminal-host']:
 p=ROOT/d/'package.json';j=json.loads(p.read_text(encoding='utf-8-sig'));versions[d]={'scripts':j.get('scripts',{}),'engines':j.get('engines',{}),'build_dependencies':{k:v for kind in ['dependencies','devDependencies'] for k,v in j.get(kind,{}).items() if k in ['typescript','electron','vite','electron-builder','tsx','vitest']}}
 for name in ['typescript','electron']:
  p=ROOT/d/'node_modules'/name/'package.json'
  if p.exists():versions[d][name+'_installed']=json.loads(p.read_text(encoding='utf-8-sig'))['version']
snapshot={'captured_at':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),'git':{k:command(v) for k,v in {'status':['git','status','--short','--branch'],'head':['git','rev-parse','HEAD'],'branch':['git','branch','--show-current'],'last_commit':['git','log','-1','--oneline','--decorate'],'tracked_diff':['git','diff','--stat'],'staged_diff':['git','diff','--cached','--stat'],'reference_relation':['git','rev-list','--left-right','--count','1f3e37701b4977f452514bafd208092a2ac1d80a...HEAD'],'remote_master':['git','ls-remote','origin','refs/heads/master']}.items()},'homes':homes,'versions':versions}
with (OUT/'environment-evidence.json').open('x',encoding='utf-8') as f:json.dump(snapshot,f,ensure_ascii=False,indent=2)
delta=command(['git','diff','--name-status','1f3e37701b4977f452514bafd208092a2ac1d80a','HEAD'])
with (OUT/'reference-delta.txt').open('x',encoding='utf-8') as f:f.write(delta['output']+'\n')
print(json.dumps({'captured_at':snapshot['captured_at'],'homes':[{'home':h['home'],'processes':h['processes'],'ports':h['ports'],'log_session_count':h['log_session_count']} for h in homes]},ensure_ascii=False))
