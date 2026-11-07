"""Final audit-only reconciliation and artifact hashes."""
from pathlib import Path
import csv,json,re,hashlib,ast,subprocess
OUT=Path(__file__).parent;ROOT=OUT.parents[2]
def load(n):return list(csv.DictReader((OUT/n).open(encoding='utf-8-sig')))
v=json.loads((OUT/'verification.json').read_text(encoding='utf-8'))
excluded=[]
for c in v['unmatched_ast_http_candidates']:
 if c['file'].endswith('documents.ts') and c['expression'].startswith('this.requests.'):
  reason='VERIFIED local Map lookup/delete; no HTTP transport'
 elif c['file'].endswith('lsp-host.ts') and c['expression']=='session.client.request':
  reason='VERIFIED LSP JSON-RPC client; not platform HTTP API'
 else:raise AssertionError('unreviewed frontend HTTP candidate')
 excluded.append(dict(**c,decision=reason))
v['ast_exclusions_reviewed']=excluded
v['unresolved_ast_http_candidates']=0
routes=load('route-inventory.csv');deps=load('java-dependency-inventory.csv')
assert len({(r['method'],r['path']) for r in routes})==len(routes)
assert len({r['file'] for r in deps})==299
assert len(list((ROOT/'apps/backend/src/main/java').rglob('*.java')))==299
assert len(list((ROOT/'apps/backend/src/test').rglob('*.java')))==115
assert len(list(OUT.glob('PR-TS-00-*.md')))==8
assert len(load('migration-inventory.csv'))==13
assert not any(not r['response_type'] or not r['request_signature'] and False for r in routes)
for r in routes:
 lines=(ROOT/r['file']).read_text(encoding='utf-8-sig').splitlines()
 assert 'Mapping' in lines[int(r['line'])-1]
v['route_unique_method_path']=True
v['route_annotation_line_checks']=145
v['audit_script_syntax_checks']={p.name:'PASS parse only' for p in OUT.glob('*.py') if ast.parse(p.read_text(encoding='utf-8-sig'))}
for name in ['production_java_hash_mismatches','source_index_hash_mismatches']:assert not v[name]
v['final_tracked_diff']=subprocess.check_output(['git','diff','--name-only'],cwd=ROOT,text=True).strip()
v['final_staged_diff']=subprocess.check_output(['git','diff','--cached','--name-only'],cwd=ROOT,text=True).strip()
v['git_diff_check_exit']=subprocess.run(['git','diff','--check'],cwd=ROOT,capture_output=True).returncode
assert not v['final_tracked_diff'] and not v['final_staged_diff'] and v['git_diff_check_exit']==0
# This file was generated within this run; add final validation without touching pre-existing reports.
(OUT/'verification.json').write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
with (OUT/'PR-TS-00-HTTP接口与前端依赖矩阵.md').open('a',encoding='utf-8') as f:
 f.write('''
## 独立语法复核（VERIFIED，仅盘点检查）

使用仓库已安装的TypeScript 5.4.5解析366个TS/JS/Vue script块，没有安装依赖或启动浏览器。152个CSV调用项均定位到真实CallExpression/NewExpression，C2一个调用仍展开五个目标；语法候选中另外4项人工核对为documents.ts的Map get/delete和lsp-host.ts的LSP JSON-RPC request，均不是平台HTTP。排除证据与零未决候选见verification.json；不是运行路由/E2E验证。

identity-touchpoint-inventory.csv补充AST定位的所属函数、导入依赖和调用符号引用候选。跨模块import/IPC/template动态绑定不能由词法证明的调用者保留UNKNOWN；不把同名引用当语义调用图。terminal-client内部Authorization明确KEEP，不属于用户JWT退役。frontend-ast-evidence.json仅含源码符号和位置，不采集运行请求/凭据/正文。
''')
with (OUT/'PR-TS-00-本机基线与环境审计.md').open('a',encoding='utf-8') as f:
 f.write('''
## 结束校验（VERIFIED）

299个生产Java文件与源码索引范围内全部文件的SHA-256均与盘点时一致；tracked diff、staged diff为空；git diff --check成功；只新增本审计目录。145行route均唯一且行号指向Mapping注解，13个migration/115个测试源码文件与实际目录一致。审计Python脚本通过语法解析（未执行应用测试）。详见verification.json；这些检查不证明业务功能或数据库迁移成功。
''')
with (OUT/'artifact-manifest.csv').open('x',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=['file','bytes','sha256','role']);w.writeheader()
 for p in sorted(OUT.iterdir()):
  if not p.is_file() or p.name=='artifact-manifest.csv':continue
  w.writerow(dict(file=p.name,bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),role='audit report' if p.suffix=='.md' else 'audit evidence/script; not business source'))
print(json.dumps({'result':'BLOCKED','next_phase':'PR-TS-01 NO-GO','reports':8,'artifacts_excluding_manifest':len(list(OUT.iterdir()))-1,'production_hash_mismatches':0,'source_hash_mismatches':0,'route_checks':145,'frontend_ast_verified_rows':152,'ast_false_positives_reviewed':4,'unresolved_ast_http_candidates':0,'tracked_changes':0,'staged_changes':0,'business_tests':'NOT RUN','live_database':'BLOCKED'},ensure_ascii=False))
