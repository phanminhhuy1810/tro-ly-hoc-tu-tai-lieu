"""One explicit local9B cloze probe; no course, billing, default-model change or retry loop."""
import asyncio,ast,json,sqlite3,time,sys,hashlib
from pathlib import Path
from datetime import datetime,timezone
from study_backend.ai import LocalAI
from study_backend.models import QUESTION_DRAFTS,grade
from study_backend.generation_contract import GENERATION_PROCESSOR_VERSION
ROOT=Path(__file__).resolve().parents[2]
class Capture:
 def __init__(self):self.raw='';self.first=None;self.started=time.monotonic();self.audit={};self.fallbacks=0
 def chunk(self,text):
  if text and self.first is None:self.first=time.monotonic()-self.started
  self.raw+=text
 def usage(self,values):self.audit.update(values)
 def fallback(self):self.fallbacks+=1
async def run():
 with sqlite3.connect(f'file:{ROOT / "backend/runtime/study.sqlite3"}?mode=ro',uri=True) as db:
  if db.execute("select count(*) from jobs where status in ('queued','running')").fetchone()[0]:raise SystemExit('Another application job is active; did not run the probe.')
 tree=ast.parse((ROOT/'backend/study_backend/app.py').read_text());rules=[]
 for node in ast.walk(tree):
  if isinstance(node,ast.Dict):
   for key,value in zip(node.keys,node.values):
    if isinstance(key,ast.Constant) and key.value=='cloze' and isinstance(value,ast.Constant) and isinstance(value.value,str) and 'prompt=null' in value.value:rules.append(value.value)
 if len(rules)!=1:raise RuntimeError('Cloze instruction not found uniquely; no inference started.')
 source=[{'id':'qa-cloze','text':'Địa chỉ IPv4 có 32 bit. Subnet mask chia địa chỉ thành phần network và phần host.'}]
 real_source='--failed-course' in sys.argv
 source_context=None
 if real_source:
  with sqlite3.connect(f'file:{ROOT / "backend/runtime/study.sqlite3"}?mode=ro',uri=True) as db:
   cid='0e2ef32fe9294efba05fbd5b77860ef6'
   row=db.execute('select content_json,plan_id,revision from course_revisions where course_id=? order by revision desc limit 1',(cid,)).fetchone()
   unit=json.loads(row[0])['units'][0];plan=db.execute('select source_id,preferences_json from plans where id=?',(row[1],)).fetchone();prefs=json.loads(plan[1])
   original=db.execute('select content_json from extraction_revisions where source_id=? and revision=?',(plan[0],prefs['extraction_revision'])).fetchone()[0]
   refs=set(unit['source_refs']);source=[f for f in json.loads(original) if f['id'] in refs]
   if not source or sum(len(f['text']) for f in source)>9000:raise RuntimeError('Invalid or too large pinned scope; no inference started.')
   source_context={'source_id':plan[0],'extraction_revision':prefs['extraction_revision'],'fragment_count':len(source),'source_sha256':hashlib.sha256(original.encode()).hexdigest(),'course_id':cid,'course_revision':row[2]}
 ai=LocalAI();ai.model='qwen3.5:9b';capture=Capture();report={'purpose':'One local cloze probe; real failed-unit source when explicitly selected, otherwise self-authored; not a full lesson or held-out benchmark','started_at':datetime.now(timezone.utc).isoformat(),'model':ai.model,'processor_version':GENERATION_PROCESSOR_VERSION,'source':source,'new_AI_tasks':1,'course_mutated':False}
 try:
  result=await ai.generate_stream(QUESTION_DRAFTS['cloze'],'Tạo một câu điền khuyết tiếng Việt. '+rules[0],source,capture)
  q=result['question'];report.update(response_schema_valid=True,question_generated=q is not None,source_declined=q is None,result=result,valid=q is not None and q['prompt'].count('____')==1,correct_fixed_answer=bool(q and grade(q,q['answer'])['correct']))
 except Exception as error:report.update(response_schema_valid=False,valid=False,error_type=type(error).__name__,error=str(error)[:600])
 report.update(total_seconds=round(time.monotonic()-capture.started,3),first_content_seconds=round(capture.first,3) if capture.first else None,protocol_fallbacks=capture.fallbacks,audit=capture.audit,raw_output=capture.raw)
 report['source_context']=source_context
 if real_source:report.pop('source',None)
 filename='cloze-source-mask-real-failed-unit.json' if real_source else 'cloze-source-mask-local9b.json'
 (ROOT/'backend/evidence'/filename).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:report[k] for k in ('valid','total_seconds','first_content_seconds','protocol_fallbacks')},ensure_ascii=False))
asyncio.run(run())
