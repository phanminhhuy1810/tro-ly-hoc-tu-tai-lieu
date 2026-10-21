"""One explicitly named development-stage reproduction; retain raw failure.

Never run a final case, never retry an existing output file, and never modify
the QA course. Uses the exact production prompt/fragments from the baseline.
"""
import argparse
import asyncio
from datetime import datetime,timezone
import json
from pathlib import Path
import sqlite3
import sys
import time

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from study_backend.ai import LocalAI
from study_backend.models import QUESTION_DRAFTS
from study_backend.question_generation import lesson_instruction,question_prompt
from run_http import check_free,fingerprint,load_frozen


class Capture:
    def __init__(self):self.raw='';self.fallbacks=0;self.usage_data={}
    def chunk(self,text):self.raw+=text
    def usage(self,value):self.usage_data.update(value)
    def fallback(self):self.fallbacks+=1


async def main():
    p=argparse.ArgumentParser();p.add_argument('--case',required=True);p.add_argument('--kind',choices=['ordering','mcq'],required=True);a=p.parse_args()
    _,cases=load_frozen('dev');case=next(c for c in cases if c['id']==a.case)
    baseline=json.loads((HERE/'results/dev-v1.json').read_text())
    if not baseline['all_cases_observed']:raise SystemExit('Observe the original run to completion first; no overlapping inference.')
    item=next(c for c in baseline['runs'] if c['case_id']==case['id'])
    if item['job']['status']!='failed':raise SystemExit('Only reproduce a known failed development stage.')
    if item['job']['progress']['requests'][-1]['schema'].lower()!=('orderingdraft' if a.kind=='ordering' else 'mcqdraft'):
        raise SystemExit('Chosen kind is not the known failing stage.')
    output=HERE/'results'/('rejection-'+case['id']+'-'+a.kind+'-v16.json')
    if output.exists():raise SystemExit('Captured attempt already exists; do not overwrite or retry.')
    check_free(set())
    with sqlite3.connect('file:'+str(ROOT/'backend/runtime/study.sqlite3')+'?mode=ro',uri=True) as db:
        prefs=json.loads(db.execute('SELECT preferences_json FROM plans WHERE id=?',(item['course_snapshot']['plan_id'],)).fetchone()[0])
    unit=item['course_snapshot']['content']['units'][0]
    fragments=[f for f in item['source_snapshot']['fragments'] if f['id'] in unit['source_refs']]
    previous=[v['question'] for v in item['job']['partial'].get('questions',{}).values() if v.get('question')]
    prompt=question_prompt(lesson_instruction(prefs,unit),a.kind,unit['objective'],previous)
    capture=Capture();ai=LocalAI();ai.model='gemma4:12b-mlx';started=time.monotonic()
    report={'purpose':'One bounded dev reproduction, not raw from the original failed request or final evaluation.',
            'case_id':case['id'],'kind':a.kind,'baseline_job_id':item['job_id'],'production_sha256':fingerprint(),
            'started_at':datetime.now(timezone.utc).isoformat(),'model':ai.model,'source_ids':[f['id'] for f in fragments],
            'instruction':prompt,'semantic_retries':0,'course_mutated':False}
    try:
        report['output']=await asyncio.wait_for(ai.generate_stream(QUESTION_DRAFTS[a.kind],prompt,fragments,capture),timeout=120)
        report['status']='succeeded'
    except Exception as exc:report.update(status='failed',error_type=type(exc).__name__,error=str(exc)[:2500])
    finally:
        report.update(raw=capture.raw,protocol_fallbacks=capture.fallbacks,usage=capture.usage_data,elapsed_seconds=round(time.monotonic()-started,3))
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:report.get(k) for k in ('case_id','kind','status','error_type','elapsed_seconds')}))


if __name__=='__main__':asyncio.run(main())
