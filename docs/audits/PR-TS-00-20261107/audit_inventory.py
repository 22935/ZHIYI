"""PR-TS-00 read-only source inventory; writes only new audit artifacts here.
Not a Java/TS compiler. Unresolved dynamic contracts stay UNKNOWN.
"""
from pathlib import Path
import csv, hashlib, json, re, subprocess, os, socket
ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent
def read(p): return p.read_text(encoding='utf-8-sig')
def rel(p): return p.relative_to(ROOT).as_posix()
def line(s,n): return s.count('\n',0,n)+1
def write(name, text):
    with (OUT/name).open('x',encoding='utf-8',newline='') as f: f.write(text)
def csvout(name, rows):
    if not rows:return
    with (OUT/name).open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader();w.writerows(rows)
def mask(s):
    # preserve offsets, braces and strings in original remain available separately
    return re.sub(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',lambda m:re.sub(r'[^\n]',' ',m[0]),s)
def close(s,i,a='(',b=')'):
    depth=0
    for j in range(i,len(s)):
        if s[j]==a:depth+=1
        if s[j]==b:
            depth-=1
            if depth==0:return j
    raise ValueError('unbalanced source')
java=sorted((ROOT/'apps/backend/src/main/java').rglob('*.java'))
tests=sorted((ROOT/'apps/backend/src/test').rglob('*.java'))
sources={p:read(p) for p in java+tests}
byname={p.stem:p for p in java}
testrefs=lambda name:';'.join(f'{rel(p)}:{line(s,m.start())}' for p,s in sources.items() if p in tests for m in [re.search(r'\b'+re.escape(name)+r'\b',s)] if m)
deps=[]
for p in java:
    s=sources[p]
    imports=re.findall(r'^import (?:static )?(com\.kinlin\.ai\.[\w.*]+);',s,re.M)
    fields=re.findall(r'(?:private|protected)\s+(?:final\s+)?([\w<>?, .]+)\s+(\w+)\s*[;=]',s)
    decl=re.search(r'\b(class|interface|record|enum)\s+'+re.escape(p.stem)+r'\b',s)
    deps.append(dict(file=rel(p),line=line(s,decl.start()) if decl else 1,symbol=p.stem,kind=decl[1] if decl else 'UNKNOWN',layer=rel(p).split('/ai/',1)[-1].split('/')[0],sha256=hashlib.sha256(p.read_bytes()).hexdigest(),lines=len(s.splitlines()),imports=';'.join(imports),fields=';'.join(t.strip()+' '+n for t,n in fields),transaction_lines=';'.join(str(line(s,m.start())) for m in re.finditer('@Transactional',s)),cache_annotations=';'.join(m[0] for m in re.finditer(r'@Cache\w+[^\n]*',s)),identity_refs=';'.join(sorted(set(re.findall(r'AuthenticatedUser\.\w+|SecurityContextHolder|userId|tenantId',s)))),python_clients=';'.join(sorted(set(re.findall(r'\b\w*(?:Client|Transport|GatewayService)\b',s)))),exception_types=';'.join(sorted(set(re.findall(r'\b(?:throw new|catch\s*\()\s*(\w+)',s)))),tests=testrefs(p.stem),evidence='VERIFIED source inventory; behavior requires review'))
csvout('java-dependency-inventory.csv',deps)
routes=[];ann_count=0
for p in java:
    s=sources[p]; msk=mask(s)
    if not re.search(r'@(?:RestController|Controller)\b',s):continue
    cls=re.search(r'\bclass\s+\w+',msk)
    base=''
    for a in re.finditer(r'@(RequestMapping)\s*\(',s[:cls.start()]):
        end=close(msk,a.end()-1);strings=re.findall(r'"([^"\n]*)"',s[a.end():end]);base=strings[0] if strings else ''
    fields=';'.join(t.strip()+' '+n for t,n in re.findall(r'private\s+final\s+([\w<>?, .]+)\s+(\w+)\s*;',s))
    for a in re.finditer(r'@(GetMapping|PostMapping|PutMapping|PatchMapping|DeleteMapping|RequestMapping)\b',s):
        if a.start()<cls.start():continue
        ann_count+=1;start=a.end();args=''
        k=start
        while k<len(s) and s[k].isspace():k+=1
        if s[k]=='(':
            end=close(msk,k);args=s[k+1:end];start=end+1
        sig=re.search(r'public\s+([\w<>, ?\[\].]+?)\s+(\w+)\s*\(',s[start:])
        if not sig:raise ValueError(f'unparsed route {p}:{line(s,a.start())}')
        op=start+sig.end()-1;cp=close(msk,op)
        brace=msk.find('{',cp);endbody=close(msk,brace,'{','}');body=s[brace+1:endbody]
        pathargs=args.split('produces')[0].split('consumes')[0].split('method')[0]
        paths=re.findall(r'"([^"\n]*)"',pathargs) or ['']
        methods=[a[1].replace('Mapping','').upper()] if a[1]!='RequestMapping' else re.findall(r'RequestMethod\.(\w+)',args) or ['ANY']
        for path in paths:
            for method in methods:
                full=base+path or '/'
                legacy={'ai','auth','chat','conversations','files','health','metrics','rag','recommendations','roles','search','statistics','users','profile','voice'}
                alias='/api'+full if full.split('/')[1] in legacy else ''
                status=sorted(set(re.findall(r'HttpStatus\.(\w+)|\.status\((\d+)\)',body)))
                ret=sig[1].strip(); response=';'.join(x or y for x,y in status)
                if not response:response='upstream/dynamic' if any(x in body for x in ['upstream','getStatusCode','getStatus()','AgentOs','agentOs']) else '200 default on normal return; exception handler applies'
                python=';'.join(sorted(set(re.findall(r'AgentOsPaths\.\w+\([^;\n]*|"/(?:ai|rag|api)/[^"\n]*"',body))))
                routes.append(dict(method=method,path=full,api_alias=alias,controller=p.stem,java_method=sig[2],file=rel(p),line=line(s,a.start()),request_signature=' '.join(s[op+1:cp].split()),response_type=ret,status_behavior=response,status_evidence=';'.join(re.findall(r'ResponseEntity\.[^;\n]+|throw new [^;\n]+',body)),dependencies=fields,python_path_expression=python or 'UNKNOWN/indirect; inspect dependencies',auth_context='current actor' if 'AuthenticatedUser' in body else 'SecurityConfig/global; downstream context if required',special=';'.join(x for x,yes in [('SSE','ServerSentEvent' in ret or 'TEXT_EVENT_STREAM' in args),('Multipart','Multipart' in s[op:cp] or 'MULTIPART' in args),('Binary','byte[]' in ret or 'Resource' in ret),('generic proxy','**' in full)] if yes),tests=testrefs(p.stem),frontend_calls='',classification='PROXY_FAMILY' if '**' in full else 'CONFIRMED_SOURCE_MAPPING',evidence='VERIFIED static mapping; not runtime exercised'))
# Frontend scan includes calls outside services and literal/dynamic fetch, axios, EventSource.
front=[]
files=sorted(p for root in ['apps/frontend/src','apps/desktop/electron/src'] for p in (ROOT/root).rglob('*') if p.suffix in {'.ts','.vue','.js'} and '.spec.' not in p.name)
for p in files:
    s=read(p)
    patterns=[r'\b([\w.]+)\.(get|post|put|patch|delete|request)(?:<[^;\n]*?>)?\s*\(',r'\b(fetch|EventSource)\s*\(']
    hits=[]
    for pat in patterns:
        for m in re.finditer(pat,s):
            st=m.end(); chunk=s[st:st+1000]
            url=re.match(r'\s*([\'"`])([\s\S]*?)\1',chunk)
            if url:expr=url[2]
            else:expr=chunk.split('\n')[0].split(',')[0].strip()[:200]
            # Drop Map/Set/storage/DOM getters; retain request-like dynamic adapters.
            receiver=m[1]
            if len(m.groups())==2 and not any(x in receiver.lower() for x in ['request','api','axios','client','http']):continue
            meth=m[2].upper() if len(m.groups())==2 else ('GET' if receiver=='EventSource' else (re.search(r'method:\s*[\'"](\w+)',chunk)[1] if re.search(r'method:\s*[\'"](\w+)',chunk) else 'UNKNOWN'))
            # Determine instance baseURL from this file; imported request uses shared /api.
            base=re.search(r'baseURL:\s*([^,\n]+)',s)
            bases=base[1].strip() if base else 'imported adapter/config (see imports)'
            imports=';'.join(re.findall(r'^import[^\n]+',s,re.M))
            front.append(dict(file=rel(p),line=line(s,m.start()),caller=receiver,method=meth,url_expression=expr,base_expression=bases,imports=imports,classification='UNKNOWN',backend_matches='',tests=';'.join(rel(t) for t in p.parent.glob(p.stem+'.spec.*')),evidence='VERIFIED callsite; URL resolution INFERRED/UNKNOWN'))
def template_regex(path):
    # Java variable segments and TS interpolation, preserve escaped slashes.
    val=re.sub(r'\$\{[^}]+\}|\{[^}]+\}', '__SEGMENT__',path.split('?')[0])
    return '^'+re.escape(val).replace('__SEGMENT__','[^/]+').replace(r'\*\*','.*')+'/?$'
for f in front:
    expr=f['url_expression'];u=expr
    for var in ['${AGENTOS_BASE}','${BASE_PATH}','${AGENTOS_API_BASE}']:u=u.replace(var,'/agentos/v2')
    candidates={u}
    if u.startswith('/'):
        candidates.add('/api'+u)
    matches=[]
    for i,r in enumerate(routes):
        if f['method'] not in {r['method'],'UNKNOWN','REQUEST'}:continue
        # Prefer concrete mappings; proxy family can overlap.
        for c in candidates:
            norm=re.sub(r'\$\{[^}]+\}','VALUE',c.split('?')[0])
            if any(re.match(template_regex(path),norm) for path in [r['path'],r['api_alias']] if path):
                matches.append(i);break
    if matches:
        concrete=[i for i in matches if routes[i]['classification']!='PROXY_FAMILY']
        chosen=concrete or matches
        f['classification']='EXPLICIT_ROUTE' if concrete else 'PROXY_CARRIED'
        f['backend_matches']=';'.join(routes[i]['method']+' '+routes[i]['path'] for i in chosen)
        for i in chosen:routes[i]['frontend_calls']+=';'+f['file']+':'+str(f['line'])
    elif u.startswith('/') and '${' not in u:
        f['classification']='FRONTEND_ONLY_CANDIDATE' # static evidence only, not final dead-route assertion
csvout('route-inventory.csv',routes)
csvout('frontend-callsite-inventory.csv',front)
migrations=[]
for p in sorted((ROOT/'apps/backend/src/main/resources/db/migration').glob('*.sql'),key=lambda p:int(re.search(r'V(\d+)',p.name)[1])):
    s=read(p)
    migrations.append(dict(version=int(re.search(r'V(\d+)',p.name)[1]),file=rel(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),lines=len(s.splitlines()),tables=';'.join(sorted(set(re.findall(r'(?:CREATE TABLE(?: IF NOT EXISTS)?|ALTER TABLE|DROP TABLE(?: IF EXISTS)?|INSERT INTO|UPDATE|DELETE FROM)\s+(\w+)',s,re.I)))),operations=';'.join(f'{line(s,m.start())}:{m[0]}' for m in re.finditer(r'\b(?:CREATE TABLE|ALTER TABLE|CREATE (?:UNIQUE )?INDEX|DROP TABLE|INSERT INTO|UPDATE|DELETE FROM)\b',s,re.I)),jsonb=';'.join(str(line(s,m.start())) for m in re.finditer(r'\bJSONB\b',s,re.I)),live_applied='BLOCKED until verified against running DB'))
csvout('migration-inventory.csv',migrations)
testrows=[]
for p in tests:
    s=read(p);name=p.stem
    cats=[]
    for label,pat in [('REST','MockMvc|ControllerTest|HttpIntegration'),('业务行为','service/|ServiceTest'),('Projection','Projection|Serialization|ObjectMapper'),('PostgreSQL','Postgres|pg-it'),('Redis','Redis|redis-it'),('Gateway','Gateway|Transport|ClientTest|Proxy'),('SSE','Sse|SSE|Stream'),('Security','Security|Auth|Session|Jwt|Login'),('Architecture Guard','architecture/|Architecture|Guard'),('Native Runtime','NativePostgres|NativeRedis')]:
        if re.search(pat,rel(p)+'\n'+s):cats.append(label)
    decision='删除旧登录合同 + 改写无登录安全测试' if any(x in name for x in ['Session','Jwt','Login','AuthController']) else '保留合同 / 改写测试'
    testrows.append(dict(file=rel(p),categories=';'.join(cats) or '待确认',test_annotations=len(re.findall(r'@(?:Test|ParameterizedTest|RepeatedTest|TestFactory)\b',mask(s))),decision=decision,execution='NOT RUN: whole-suite isolation not proven',profiles=';'.join(re.findall(r'@ActiveProfiles[^\n]*',s)),destructive_refs=';'.join(str(line(s,m.start())) for m in re.finditer(r'deleteAll|TRUNCATE|DROP |deleteRecursively|ProcessBuilder|Runtime\.getRuntime',s))))
csvout('test-inventory.csv',testrows)
# Evidence index records named symbols/annotations, never raw config or runtime secrets.
evidence=[]
scope=['apps/backend/src','apps/frontend/src','apps/desktop/electron/src','apps/agent/app/security','apps/agent/app/execution/workspace_authority.py','ops/scripts/infra/windows/native','ops/scripts/release','.github/workflows']
for root in scope:
    rp=ROOT/root
    paths=[rp] if rp.is_file() else rp.rglob('*')
    for p in paths:
        if not p.is_file() or p.suffix not in {'.java','.py','.ts','.vue','.yml','.sql','.json','.ps1'}:continue
        if p.name in {'package-lock.json','pnpm-lock.yaml'}:continue
        try:s=read(p)
        except UnicodeError:continue
        symbols=[]
        patterns=[r'\b(?:class|interface|record|enum|def|function)\s+([\w]+)',r'\b(?:async\s+)?function\s+(\w+)',r'\b(?:const|export const)\s+(\w+)\s*=']
        for pat in patterns:
            for m in re.finditer(pat,s):symbols.append(f'{m[1]}:{line(s,m.start())}')
        evidence.append(dict(file=rel(p),lines=len(s.splitlines()),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),symbols=';'.join(dict.fromkeys(symbols))))
csvout('source-evidence-index.csv',evidence)
stats={'java_sources':len(java),'java_lines':sum(len(sources[p].splitlines()) for p in java),'controllers':len(set(r['controller'] for r in routes)),'mapping_annotations':ann_count,'method_path_rows':len(routes),'explicit_method_path_rows':sum('**' not in r['path'] for r in routes),'proxy_method_rows':sum('**' in r['path'] for r in routes),'api_alias_rows':sum(bool(r['api_alias']) for r in routes),'service_package_files':sum('/service/' in rel(p) for p in java),'spring_service_annotations':sum(bool(re.search(r'@Service\b',sources[p])) for p in java),'projection_files':sum('/projection/' in rel(p) for p in java),'projection_mappers':sum('/projection/' in rel(p) and p.stem.endswith('Mapper') for p in java),'java_test_source_files':len(tests),'test_declarations':sum(t['test_annotations'] for t in testrows),'migration_files':len(migrations),'frontend_callsites':len(front),'frontend_classes':{c:sum(f['classification']==c for f in front) for c in sorted(set(f['classification'] for f in front))}}
write('inventory-summary.json',json.dumps(stats,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(stats,ensure_ascii=False))
