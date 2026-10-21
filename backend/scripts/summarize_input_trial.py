"""Export only the known self-authored browser OCR fixture; never auth/user rows."""
import hashlib,json,sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
source_id='04277b74f6bf4beabc0e5c70738c5d16'
data=(ROOT/'backend/runtime/sources'/source_id).read_bytes()
fixture=(ROOT/'experiments/03-ocr-inputs/fixtures/calculus-layout.png').read_bytes()
assert data==fixture
c=sqlite3.connect(ROOT/'backend/runtime/study.sqlite3');c.row_factory=sqlite3.Row
source=c.execute('SELECT status,metadata_json FROM sources WHERE id=?',(source_id,)).fetchone()
report={'purpose':'actual browser + native OCR + Qwen9B vision proposal trial on self-authored fixture; not human benchmark','source_id':source_id,'original_sha256':hashlib.sha256(data).hexdigest(),'original_matches_fixture':True,'status':source['status'],'metadata':json.loads(source['metadata_json']),'revisions':[],'proposals':[],'analyses':[]}
for row in c.execute('SELECT revision,content_json,reviewed_at FROM extraction_revisions WHERE source_id=? ORDER BY revision',(source_id,)):
 report['revisions'].append({'revision':row['revision'],'fragments':json.loads(row['content_json']),'reviewed_at':row['reviewed_at']})
for row in c.execute('SELECT id,base_revision,page,page_kind,content_json,status FROM source_proposals WHERE source_id=?',(source_id,)):
 v=dict(row);v['content']=json.loads(v.pop('content_json'));report['proposals'].append(v)
for row in c.execute('SELECT id,extraction_revision,content_json FROM source_analyses WHERE source_id=?',(source_id,)):
 v=dict(row);v['content']=json.loads(v.pop('content_json'));report['analyses'].append(v)
c.close()
file=ROOT/'backend/evidence/ocr-browser-trial.json';file.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print('saved self-authored input report; revisions',len(report['revisions']),'analyses',len(report['analyses']))
