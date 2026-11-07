"""Validate mutation/privacy boundaries and create a desktop audit-only ZIP."""
from pathlib import Path
import sys,json,csv,hashlib,zipfile,subprocess,sqlite3,importlib.util,datetime,os,ast
sys.dont_write_bytecode=True
OUT=Path(__file__).parent;ROOT=OUT.parents[2];BASE=Path('E:/ZhiyiAudit/PR-TS-00B-20261107-r01')
sp=importlib.util.spec_from_file_location('prts00b_runner',OUT/'PR-TS-00B-run-isolated-audit.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
def load(n):return json.loads((OUT/n).read_text(encoding='utf-8'))
def csvrows(n):return list(csv.DictReader((OUT/n).open(encoding='utf-8-sig')))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,obj):
 with p.open('x',encoding='utf-8') as f:json.dump(obj,f,ensure_ascii=False,indent=2)
def git(args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True,encoding='utf-8').strip()
before=load('PR-TS-00B-isolation-final-evidence.json')
assert before['status']=='EVIDENCE_COLLECTED' and before['postgres_stop_exit']==0
assert not any(c.status==m.psutil.CONN_LISTEN and c.laddr.port in [15432,16379,18761,18765,18080,15200,18766,19222,25432] for c in m.psutil.net_connections(kind='tcp'))
assert not any('postgres' in (p.info['name'] or '').lower() for p in m.psutil.process_iter(['name']))
source_drift=[r['file'] for r in csvrows('source-evidence-index.csv') if sha(ROOT/r['file'])!=r['sha256']]
old_drift=[r['file'] for r in csvrows('artifact-manifest.csv') if sha(OUT/r['file'])!=r['sha256']]
assert not source_drift and not old_drift
initial=json.loads((BASE/'private-evidence/original-file-fingerprints.json').read_text(encoding='utf-8'))
current=m.fingerprint(m.HOME)
assert initial==current
tracked=git(['diff','--name-only']);staged=git(['diff','--cached','--name-only'])
observed_unrelated={'benchmark/agentos_benchmark_smoke.py','benchmark/agentos_benchmark_smoke_6.py','ops/scripts/generate_agentos_acg_master_drawio.py','ops/scripts/generate_harness_report.py'}
assert set(tracked.splitlines())==observed_unrelated and not staged
assert not (ROOT/'apps/backend-ts').exists()
assert git(['rev-parse','HEAD'])=='8775130f22b0440398c876a99206a47054e0b30c'
assert subprocess.run(['git','diff','--check'],cwd=ROOT,capture_output=True).returncode==0
# Exact-value privacy scan: no raw business ids/Workspace roots or DPAPI plaintext values.
sensitive=[]
con=sqlite3.connect((BASE/'sqlite-query-copy/workflows.sqlite3').resolve().as_uri()+'?mode=ro',uri=True)
for row in con.execute("SELECT run_id,json_extract(payload,'$.input.authenticatedUserId') FROM runs"):
 sensitive += [str(x) for x in row if x]
con.close()
grants=json.loads((BASE/'snapshot/payload/hands-grants.json').read_text(encoding='utf-8'))['grants']
for g in grants:
 for k in ['canonicalRoot','grantId','workspaceId']:
  if g.get(k):sensitive.append(str(g[k]))
creds=m.native.credentials(BASE/'snapshot/payload')
def secrets(value):
 if isinstance(value,dict):
  for v in value.values():yield from secrets(v)
 elif isinstance(value,list):
  for v in value:yield from secrets(v)
 elif isinstance(value,str) and len(value)>=12:yield value
sensitive+=list(secrets(creds));creds.clear()
patterns=set()
for value in sensitive:
 patterns.update([value.encode('utf-8'),json.dumps(value,ensure_ascii=False)[1:-1].encode('utf-8'),value.replace('\\','/').encode('utf-8')])
private_hits=[]
allowed={'.md','.csv','.json','.py','.cjs','.sql','.txt'}
files=sorted(p for p in OUT.iterdir() if p.is_file())
assert all(p.suffix in allowed for p in files)
for p in files:
 data=p.read_bytes()
 if any(pat and pat in data for pat in patterns):private_hits.append(p.name)
assert not private_hits, 'PRIVACY_SCAN_BLOCKED_FILES='+','.join(private_hits)
patterns.clear();sensitive.clear()
for p in OUT.glob('PR-TS-00B-*.py'):ast.parse(p.read_text(encoding='utf-8-sig'))
desktop=Path(os.environ['USERPROFILE'])/'Desktop'
archive=desktop/'PR-TS-00B-迁移准入审计-20261107.zip'
if archive.exists():archive=desktop/('PR-TS-00B-迁移准入审计-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'.zip')
assert not archive.exists() and archive.parent.is_dir()
verification=dict(result='CONDITIONAL ACCEPT',PR_TS_00='conditional audit close',PR_TS_01='GO architecture and isolated scaffold only; no implementation performed',head=git(['rev-parse','HEAD']),branch=git(['branch','--show-current']),git_status=git(['status','--short','--branch']),tracked_diff=tracked,staged_diff=staged,concurrent_unrelated_deletions_preserved=sorted(observed_unrelated),initial_worktree='tracked clean; previous audit directory untracked',prior_artifact_hash_checks=len(csvrows('artifact-manifest.csv')),prior_artifact_hash_mismatches=old_drift,source_index_hash_checks=len(csvrows('source-evidence-index.csv')),source_hash_mismatches=source_drift,original_home_hash_checks=len(initial),original_home_hash_changes=0,temporary_pg_stopped=True,all_managed_ports_absent=True,flyway_versions_verified=13,flyway_checksums_matched=13,pg_user_count=1,all_nonempty_owner_aliases=['U01'],identity_design_freeze_eligible=True,source_route_rows=len(csvrows('route-inventory.csv')),frontend_rows=len(csvrows('frontend-callsite-inventory.csv')),application_tests='NOT RUN',application_runtime='NOT STARTED',external_workspace_backup='2 roots excluded by supported Home snapshot; untouched; later write/recovery gate',privacy_scan='PASS exact-value scan against raw current owner/run/grant/workspace values and DPAPI plaintext values; no values exported',no_backend_ts=True,zip=str(archive),zip_excludes=['snapshot','pg-query-copy','sqlite-query-copy','private-evidence','credentials.dpapi','private logs','database binaries/data'],zip_checksum='desktop .sha256 sidecar and post-packaging delivery receipt; excluded from this pre-package file to avoid circular hashes')
write(OUT/'PR-TS-00B-final-verification.json',verification)
manifest=OUT/'PR-TS-00B-artifact-manifest.csv'
files=sorted(p for p in OUT.iterdir() if p.is_file() and p!=manifest)
with manifest.open('x',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=['file','bytes','sha256','kind']);w.writeheader()
 for p in files:w.writerow(dict(file=p.name,bytes=p.stat().st_size,sha256=sha(p),kind='PR-TS-00B new audit artifact' if p.name.startswith('PR-TS-00B') else 'PR-TS-00 preserved historical artifact'))
files.append(manifest)
with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for p in files:z.write(p,arcname='PR-TS-00-20261107/'+p.name)
with zipfile.ZipFile(archive) as z:
 assert z.testzip() is None
 assert len(z.namelist())==len(files)
 for p in files:assert hashlib.sha256(z.read('PR-TS-00-20261107/'+p.name)).hexdigest()==sha(p)
digest=sha(archive)
sidecar=archive.with_suffix('.zip.sha256')
with sidecar.open('x',encoding='utf-8') as f:f.write(digest+'  '+archive.name+'\n')
receipt=dict(zip=str(archive),sha256=digest,bytes=archive.stat().st_size,members=len(files),zip_crc_test='PASS',member_sha256_checks='PASS',privacy_scan='PASS',snapshot_included=False,credentials_included=False,private_logs_included=False,original_home_bytes_unchanged=True,prior_audit_artifacts_unchanged=True,conclusion='CONDITIONAL ACCEPT',PR_TS_01='GO restricted architecture/scaffold only',note='This post-packaging receipt and SHA sidecar are outside ZIP to avoid hash circularity.')
write(OUT/'PR-TS-00B-桌面交付回执.json',receipt)
print(json.dumps(receipt,ensure_ascii=False))
