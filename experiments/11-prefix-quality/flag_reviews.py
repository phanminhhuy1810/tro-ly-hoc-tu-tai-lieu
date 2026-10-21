"""Mark agent-reviewed QA questions for review; retain raw outputs and history.

These are review requests, not claims of independent human judgments or
automatic proof that every flagged answer key is false.
"""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path

import httpx

ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
out=HERE/'results/dev-v4-review-flags.json'
if out.exists():raise SystemExit('Flag audit exists; inspect it instead of repeating mutation.')
raw_path=ROOT/'experiments/08-quality-evaluation/results/dev-v4-chapter.json';raw=raw_path.read_bytes();run=json.loads(raw)
review=json.loads((HERE/'results/dev-v4-agent-review.json').read_text())
assert run['all_cases_observed'] and review['all_cases_reviewed']
report={'purpose':'QA-only review flags from Codex-assisted source/oracle review. No model calls, content/key edits or independent human claims.',
 'at':datetime.now(timezone.utc).isoformat(),'raw_run_sha256':hashlib.sha256(raw).hexdigest(),'inference_calls':0,
 'independent_human_reviews':0,'flags':[],'checks':{}}
def save():out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
save()
for assessed in review['cases']:
    needing=[q for q in assessed['questions'] if q['status']=='needs_review']
    if not needing:continue
    case=next(x for x in run['runs'] if x['case_id']==assessed['case_id']);cid,uid=case['course_id'],case['unit_id']
    cookie=ROOT/'backend/runtime/quality-evaluation/dev-v4-chapter'/(case['case_id']+'.json')
    with httpx.Client(base_url='http://127.0.0.1:8770/api',trust_env=False,timeout=15,cookies=json.loads(cookie.read_text())) as client:
        def call(method,path,body=None):
            r=client.request(method,path,json=body);r.raise_for_status();return r.json()
        before=call('GET','/courses/'+cid+'/editor');unit=next(u for u in before['content']['units'] if u['id']==uid)
        assert unit['data']==case['course_snapshot']['content']['units'][0]['data']
        old_session=call('GET','/sessions/'+case['session_id']);wallet=call('GET','/wallet')
        for item in needing:
            q=unit['data']['questions'][item['question_index']]
            assert item['question_sha256']==hashlib.sha256(json.dumps(q,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
            flag=call('POST','/courses/'+cid+'/question-reports',{'expected_revision':before['revision'],'unit_id':uid,
                'item_id':uid+':q'+str(item['question_index']),'reason':'QA do Codex đối chiếu; cần xem lại, chưa phải phán quyết người độc lập: '+item['note']})
            report['flags'].append({'case_id':case['case_id'],'question_index':item['question_index'],'reason':item['note'],'flag':flag});save()
        after=call('GET','/courses/'+cid+'/editor');after_session=call('GET','/sessions/'+case['session_id'])
        report['checks'][case['case_id']]={'course_and_data_unchanged':before==after,
            'old_session_snapshot_unchanged':all(old_session[k]==after_session[k] for k in ['revision','questions','result']),
            'coin_unchanged':call('GET','/wallet')==wallet}
        assert all(report['checks'][case['case_id']].values())
report['original_measurement_unchanged']=raw_path.read_bytes()==raw
report['flag_count']=len(report['flags']);assert report['flag_count']==9 and report['original_measurement_unchanged'];save()
print(json.dumps({'qa_review_flags':len(report['flags']),'courses':len(report['checks']),'raw_history_coin_unchanged':True,'inference_calls':0}))
