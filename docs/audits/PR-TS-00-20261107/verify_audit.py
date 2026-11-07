"""Verify own inventory completeness and mutation boundary, not application behavior."""
from pathlib import Path
import csv,json,hashlib,subprocess,re
OUT=Path(__file__).parent;ROOT=OUT.parents[2]
def load(n):return list(csv.DictReader((OUT/n).open(encoding='utf-8-sig')))
def save(n,rows):
 with (OUT/n).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
ast=json.loads((OUT/'frontend-ast-evidence.json').read_text(encoding='utf-8'))
byfile={f['file']:f for f in ast}
touch=load('identity-touchpoint-inventory.csv')
for t in touch:
 a=byfile.get(t['file'],{});ln=int(t['line'])
 enclosing=[f for f in a.get('functions',[]) if f['start']<=ln<=f['end']]
 name=min(enclosing,key=lambda f:f['end']-f['start'])['name'] if enclosing else '<module/setup>'
 t['function']=name
 t['dependencies']=';'.join(a.get('imports',[]))
 refs=[f"{f['file']}:{c['start']}" for f in ast for c in f['calls'] if name not in {'<module/setup>','<callback>'} and c['expression'].split('.')[-1]==name]
 t['caller_symbol_candidates']=';'.join(refs) or 'UNKNOWN import/IPC/template dispatch; see source'
 t['caller_evidence']='syntax references only; not semantic binding proof'
 if t['file'].endswith('terminal-client.ts'):t['target_behavior']='KEEP independent terminal service authentication; not user JWT'
save('identity-touchpoint-inventory.csv',touch)
front=load('frontend-callsite-inventory.csv')
for f in front:
 candidates=[c for c in byfile.get(f['file'],{}).get('calls',[]) if c['start']==int(f['line']) and c['httpCandidate']]
 f['enclosing_function']=';'.join(sorted(set(c['enclosing'] for c in candidates))) or 'UNKNOWN'
 f['ast_verified']='yes' if candidates else 'no: requires review'
save('frontend-callsite-inventory.csv',front)
# No AST HTTP candidate may silently disappear from the lexical inventory.
covered={(f['file'],int(f['line'])) for f in front}
missing=[dict(file=f['file'],**c) for f in ast for c in f['calls'] if c['httpCandidate'] and (f['file'],c['start']) not in covered]
with (OUT/'frontend-ast-unmatched.json').open('x',encoding='utf-8') as f:json.dump(missing,f,ensure_ascii=False,indent=2)
production=load('java-dependency-inventory.csv')
changed=[d['file'] for d in production if hashlib.sha256((ROOT/d['file']).read_bytes()).hexdigest()!=d['sha256']]
index=load('source-evidence-index.csv')
indexchanged=[d['file'] for d in index if hashlib.sha256((ROOT/d['file']).read_bytes()).hexdigest()!=d['sha256']]
def git(args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True,encoding='utf-8').strip()
verification={'scope':'audit artifact validation only; no application tests executed','production_java_hash_mismatches':changed,'source_index_hash_mismatches':indexchanged,'tracked_diff':git(['diff','--name-only']),'staged_diff':git(['diff','--cached','--name-only']),'status':git(['status','--short','--branch']),'head':git(['rev-parse','HEAD']),'route_rows':len(load('route-inventory.csv')),'migration_rows':len(load('migration-inventory.csv')),'java_rows':len(production),'test_file_rows':len(load('test-inventory.csv')),'frontend_rows':len(front),'frontend_rows_ast_verified':sum(f['ast_verified']=='yes' for f in front),'unmatched_ast_http_candidates':missing,'business_test_execution':'NOT RUN','database_queries':'NOT RUN; real service unavailable','no_backend_ts_directory':not (ROOT/'apps/backend-ts').exists()}
assert not changed and not indexchanged
assert not verification['tracked_diff'] and not verification['staged_diff']
assert verification['no_backend_ts_directory']
with (OUT/'verification.json').open('x',encoding='utf-8') as f:json.dump(verification,f,ensure_ascii=False,indent=2)
print(json.dumps(verification,ensure_ascii=False))
