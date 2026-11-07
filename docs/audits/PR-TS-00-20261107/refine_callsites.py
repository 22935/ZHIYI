"""Refine this run's generated frontend CSV; source remains read-only."""
from pathlib import Path
import csv,re,json
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
def load(n):return list(csv.DictReader((OUT/n).open(encoding='utf-8-sig')))
def save(n,rows):
 with (OUT/n).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
routes=load('route-inventory.csv');front=[]
for r in routes:r['frontend_calls']=''
files=sorted(p for root in ['apps/frontend/src','apps/desktop/electron/src'] for p in (ROOT/root).rglob('*') if p.suffix in {'.ts','.vue','.js'} and '.spec.' not in p.name)
for p in files:
 s=p.read_text(encoding='utf-8-sig');path=p.relative_to(ROOT).as_posix()
 pattern=r'\b((?:[\w.]*[Rr]equest|api|axios|\w*[Cc]lient|http))\.(get|post|put|patch|delete|request)\b|\b(fetch|serverFetch|EventSource|WebSocket)\s*\('
 for m in re.finditer(pattern,s):
  if re.search(r'function\s*$',s[max(0,m.start()-30):m.start()]):continue
  receiver=m[1] or m[3];meth=m[2].upper() if m[2] else 'GET';i=m.end()
  if m[1]:
   while i<len(s) and s[i].isspace():i+=1
   if s[i:i+1]=='<':
    depth=1;i+=1
    while i<len(s) and depth:
     if s[i]=='<':depth+=1
     if s[i]=='>':depth-=1
     i+=1
   while i<len(s) and s[i].isspace():i+=1
   if s[i:i+1]!='(':continue
   i+=1
  if receiver in {'this.client','client'} and ('lsp-host' in path or 'documents.ts' in path):continue
  while i<len(s) and s[i].isspace():i+=1
  # Restrict options lookup to this call so the following request cannot supply its method.
  j=i;depth=1;quote=None
  while j<len(s) and depth:
   c=s[j]
   if quote:
    if c=='\\':j+=2;continue
    if c==quote:quote=None
   elif c in "'\"`":quote=c
   elif c=='(':depth+=1
   elif c==')':depth-=1
   j+=1
  chunk=s[i:j-1]
  # Capture first literal, possibly inside apiUrl/backendUrl/new URL wrappers.
  lit=re.match(r'(?:apiUrl\(|backendUrl\(|websocketUrl\(|new URL\()?[\s]*([\'"`])([\s\S]*?)\1',chunk)
  expr=lit[2] if lit else chunk.split('\n')[0].split(',')[0].strip()[:220]
  if not expr:expr='UNKNOWN dynamic argument'
  if m[3] in {'fetch','serverFetch'}:
   mt=re.search(r'method:\s*[\'"](GET|POST|PUT|PATCH|DELETE)',chunk)
   meth=mt[1] if mt else ('UNKNOWN' if re.search(r'\bmethod\b',chunk) else 'GET')
  if m[3]=='WebSocket':meth='UPGRADE'
  # Same proven local helper implementations; these expansions retain variable segments.
  normalized=expr
  normalized=re.sub(r'\$\{runPath\([^}]+\)\}',r'/runs/{runId}',normalized)
  normalized=re.sub(r'\$\{revisionPath\([^}]+\)\}',r'/missions/{missionId}/runs/{runId}/revision',normalized)
  if expr.startswith('runPath('):normalized='/runs/{runId}'
  if expr.startswith('revisionPath('):normalized='/missions/{missionId}/runs/{runId}/revision'
  base=re.search(r'baseURL:\s*([^,\n]+)',s)
  baseexpr=base[1].strip() if base else ('apiUrl(/api/agentos/v2) via agentosRequest' if receiver=='agentosRequest' else 'apiUrl(/api) via request' if 'request' in receiver.lower() else 'direct origin/helper')
  if receiver=='agentosRequest':normalized='/api/agentos/v2'+normalized
  elif m[1] and receiver in {'request','api'} and normalized.startswith('/'):
   b=re.search(r"apiUrl\(['\"]([^'\"]+)",baseexpr)
   normalized=(b[1] if b else '/api')+normalized
  if chunk.startswith('backendUrl(') and not normalized.startswith('/api/'):normalized='/api'+normalized
  variants=[normalized]
  if '${paths[action]}' in normalized:
   variants=[normalized.replace('${paths[action]}',a) for a in ['graph/materializations','graph/activation','graph/handoffs','graph/permits','execution/dispatches']]
  for u in variants:
   u=u.split('?')[0];sample=re.sub(r'\$\{[^}]+\}|\{[^}]+\}','VALUE',u)
   matches=[]
   for k,r in enumerate(routes):
    if meth not in {r['method'],'REQUEST'}:continue
    for route in [r['path'],r['api_alias']]:
     pat=re.escape(re.sub(r'\{[^}]+\}','SEGMENT',route)).replace('SEGMENT','[^/]+').replace(r'\*\*','.*')
     if route and re.fullmatch(pat+'/?',sample):matches.append(k);break
   concrete=[k for k in matches if routes[k]['classification']!='PROXY_FAMILY'];chosen=concrete or matches
   cls='EXPLICIT_ROUTE' if concrete else 'PROXY_CARRIED' if matches else 'FRONTEND_ONLY' if u.startswith('/') else 'UNKNOWN'
   if meth=='UPGRADE':cls='UNKNOWN_WEBSOCKET_TRANSPORT'
   if 'ImageViewer.vue' in path:cls='EXTERNAL_OR_ARTIFACT_FETCH'
   if 'terminal-client.ts' in path:cls='INTERNAL_TERMINAL_TRANSPORT'
   if expr=='apiUrl(path)':cls='DYNAMIC_HELPER_EXPANDED_AT_CALLERS'
   if meth=='UPGRADE' and 'realtimeAsr.ts' in path:u='/ai/realtime-asr/{sessionId}'
   target=';'.join(routes[k]['method']+' '+routes[k]['path'] for k in chosen)
   ln=s.count('\n',0,m.start())+1
   front.append(dict(file=path,line=ln,caller=receiver,method=meth,url_expression=expr,normalized_path=u,base_expression=baseexpr,classification=cls,backend_matches=target,tests=';'.join(t.relative_to(ROOT).as_posix() for t in p.parent.glob(p.stem+'.spec.*')),evidence='VERIFIED source call; path expansion INFERRED from adapter/helpers; not exercised'))
   for k in chosen:routes[k]['frontend_calls']+=';'+path+':'+str(ln)
save('frontend-callsite-inventory.csv',front);save('route-inventory.csv',routes)
stats=json.loads((OUT/'inventory-summary.json').read_text())
stats['frontend_callsites']=len(front);stats['frontend_classes']={c:sum(f['classification']==c for f in front) for c in sorted(set(f['classification'] for f in front))}
(OUT/'inventory-summary.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for f in front:
 if f['classification'] not in {'EXPLICIT_ROUTE','PROXY_CARRIED'}:print(f['file']+':'+str(f['line']),f['classification'],f['method'],f['normalized_path'])
print(json.dumps(stats,ensure_ascii=False))
