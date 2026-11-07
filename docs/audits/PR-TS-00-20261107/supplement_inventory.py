"""Static Python exposure, identity touchpoints and native dependency evidence."""
from pathlib import Path
import ast,csv,re,json
OUT=Path(__file__).parent;ROOT=OUT.parents[2]
def out(n,rows):
 with (OUT/n).open('x',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
main=(ROOT/'apps/agent/app/main.py').read_text(encoding='utf-8-sig');prefixes={}
for m in re.finditer(r'include_router\((\w+)\.router, prefix="([^"]+)"',main):prefixes[m[1]]=m[2]
prefixes.update(agentos_v2='/ai',agentos_c2='/ai/agentos/v2',local_workspace='/ai',chat_compaction='/ai')
rows=[]
for p in sorted((ROOT/'apps/agent/app/api').glob('*.py')):
 s=p.read_text(encoding='utf-8-sig');tree=ast.parse(s);prefix=''
 for node in ast.walk(tree):
  if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='APIRouter':
   for kw in node.keywords:
    if kw.arg=='prefix' and isinstance(kw.value,ast.Constant):prefix=kw.value.value
 for n in ast.walk(tree):
  if not isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):continue
  for d in n.decorator_list:
   if not isinstance(d,ast.Call) or not isinstance(d.func,ast.Attribute) or d.func.attr not in {'get','post','put','patch','delete','websocket','api_route'}:continue
   if not d.args or not isinstance(d.args[0],ast.Constant):continue
   mount=prefixes.get(p.stem);path=(mount or '')+prefix+d.args[0].value
   conditional='UNKNOWN optional import/feature gate' if p.stem not in {'chat','tts','llm_admin','local_workspace','agentos_v2','agentos_c2','chat_compaction'} else 'VERIFIED source registration; runtime not loaded'
   if p.stem=='sse_test':conditional='SSE_TEST_MODE gated'
   rows.append(dict(file=p.relative_to(ROOT).as_posix(),line=d.lineno,symbol=n.name,method=d.func.attr.upper(),python_path=path,mount_status=conditional if mount is not None else 'UNKNOWN no direct main mount resolved',proxy_reachable='SOURCE_CANDIDATE via /ai/**' if mount is not None and path.startswith('/ai/') and d.func.attr!='websocket' else 'not through HTTP /ai/** or unresolved mount',status_expression=';'.join(ast.unparse(k.value) for k in d.keywords if k.arg=='status_code')))
out('python-route-inventory.csv',rows)
touch=[]
patterns={'token_storage':r'(?:localStorage|sessionStorage)\.(?:getItem|setItem|removeItem)\([\'\"](?:token|userId|username)', 'authorization_header':r'Authorization|attachAuthToken', '401_redirect':r'401|handleUnauthorizedError|requiresAuth', 'desktop_session':r'ensureDesktopSession|sessionBootstrap|bootstrapLocalSession|session\.ensure', 'ipc_sender':r'senderFrame|event\.sender\.id|guard\(event\)', 'api_origin':r'apiOrigin|API_ORIGIN|VITE_API_BASE_URL|DEV_BACKEND_PROXY_TARGET', 'login_ui':r'authApi\.(?:login|register|logout)|/login|LoginView'}
for root in ['apps/frontend/src','apps/desktop/electron/src']:
 for p in sorted((ROOT/root).rglob('*')):
  if p.suffix not in {'.ts','.vue','.js'} or '.spec.' in p.name:continue
  lines=p.read_text(encoding='utf-8-sig').splitlines()
  for i,l in enumerate(lines,1):
   for kind,pat in patterns.items():
    if re.search(pat,l):touch.append(dict(file=p.relative_to(ROOT).as_posix(),line=i,kind=kind,target_behavior='KEEP IPC sender/validation' if kind=='ipc_sender' else 'KEEP origin resolution' if kind=='api_origin' else 'REPLACE with stable local identity / remove user login coupling',tests=';'.join(t.relative_to(ROOT).as_posix() for t in list(p.parent.glob(p.stem+'.spec.*'))+list((ROOT/'apps/desktop/electron/test').glob('*session*')) if t.is_file()),evidence='VERIFIED token/symbol reference; enclosing function and callers require source review'))
out('identity-touchpoint-inventory.csv',touch)
native=[]
patterns={'java_jar':r'java|jre|jlink|backendJar|backend_jar|mvn|maven','postgres':r'postgres|pg_ctl|pg_env','redis':r'redis|memurai','hands':r'hands|start_hands','ai':r'uvicorn|native_startup|release_file','desktop':r'desktop|electron','identity':r'ensure_local_account|auth/login|auth/register|sessionBootstrap','backup_restore':r'backup|restore|require_stopped','ownership_ports':r'native\.owned|native\.identity|native\.stop|takeover|occupied_ports|created'}
for root in ['ops/scripts/infra/windows/native','ops/scripts/release','.github/workflows']:
 for p in sorted((ROOT/root).rglob('*')):
  if p.suffix not in {'.py','.ps1','.yml','.mjs'}:continue
  for i,l in enumerate(p.read_text(encoding='utf-8-sig').splitlines(),1):
   for kind,pat in patterns.items():
    if re.search(pat,l,re.I):native.append(dict(file=p.relative_to(ROOT).as_posix(),line=i,category=kind,matched_symbols=';'.join(sorted(set(re.findall(pat,l,re.I)))),decision='replace JVM adapter' if kind=='java_jar' else 'remove login bootstrap' if kind=='identity' else 'preserve contract; adapt service descriptor',evidence='VERIFIED static reference'))
out('native-dependency-inventory.csv',native)
print(json.dumps({'python_route_declarations':len(rows),'identity_touchpoints':len(touch),'native_dependency_refs':len(native)}))
