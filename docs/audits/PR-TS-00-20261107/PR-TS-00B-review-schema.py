"""Resolve auxiliary schema-check naming and vendor FK anomaly using local source."""
from pathlib import Path
import json,sqlite3,os,hashlib
OUT=Path(__file__).parent;BASE=Path('E:/ZhiyiAudit/PR-TS-00B-20261107-r01')
pg=json.loads((OUT/'PR-TS-00B-database-evidence.json').read_text(encoding='utf-8'))
p=next((BASE/'sqlite-query-copy').rglob('chroma.sqlite3'))
con=sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True);con.execute('PRAGMA query_only=ON')
chroma={'segments':con.execute('SELECT count(*) FROM segments').fetchone()[0], 'segments_without_actual_collection':con.execute('SELECT count(*) FROM segments s LEFT JOIN collections c ON c.id=s.collection WHERE c.id IS NULL').fetchone()[0], 'referenced_singular_collection_table_exists':bool(con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='collection'").fetchone()),'actual_plural_collections_exists':bool(con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='collections'").fetchone()),'pragma_fk_violation_count':len(con.execute('PRAGMA foreign_key_check').fetchall())};con.close()
installed=Path(os.environ['LOCALAPPDATA'])/'ZhiyiNative/python/Lib/site-packages/chromadb/migrations/sysdb'
vendor=[]
for name in ['00002-segments.sqlite.sql','00009-segment-collection-not-null.sqlite.sql']:
 p=installed/name;s=p.read_text(encoding='utf-8-sig');vendor.append(dict(installed_source='chromadb/migrations/sysdb/'+name,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),singular_reference_lines=[i for i,l in enumerate(s.splitlines(),1) if 'REFERENCES collection(id)' in l]))
cols={(r['table_name'],r['column_name']) for r in pg['columns']}
expected=[('conversations','title'),('messages','file_url'),('roles','stable_key'),('conversations','workspace_mode'),('users','avatar_url')]
identity=json.loads((OUT/'PR-TS-00B-identity-evidence.json').read_text(encoding='utf-8'))
critical=[d for d in identity['databases'] if d['logical_file'] in {'workflows.sqlite3','identity.sqlite3','checkpoints.sqlite3','content.sqlite3','provenance.sqlite3','values.sqlite3'}]
result=dict(schema_column_checks=[dict(table=t,column=c,present=(t,c) in cols) for t,c in expected],all_v5_v7_v8_columns_match=all(x in cols for x in expected),correction='Earlier auxiliary predicate used avatar_path; actual V8 column is avatar_url. No live-schema mismatch exists.',chroma=chroma,installed_vendor_source=vendor,chroma_classification='VERIFIED vendor schema refers to singular collection while actual table is collections; no segment missing its actual collection. Existing vendor schema compatibility issue; not cross-store actor inconsistency.',identity_critical_stores_integrity_ok=all(d['integrity_ok'] and not d['foreign_key_violations'] for d in critical),single_owner_identity_freeze_eligible=identity['pg_user_count']==1 and identity['distinct_owner_count']==1 and not identity['owners_not_in_pg_users'] and all(d['integrity_ok'] and not d['foreign_key_violations'] for d in critical),earlier_generic_single_identity_candidate='false included unrelated Chroma FK diagnostic; specialized identity gate evaluated separately; original evidence retained')
with (OUT/'PR-TS-00B-schema-review-evidence.json').open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
print(json.dumps(result,ensure_ascii=False))
