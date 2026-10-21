"""Check concrete numeric claims and HTTP grading; not independent human review."""
import ipaddress
import json
from pathlib import Path
import sqlite3

import httpx

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
path=HERE/'results/network-local-v2-audit.json'
if path.exists():raise SystemExit('Audit already exists; do not submit another practice session.')
trial=json.loads((HERE/'results/network-local-v2.json').read_text())
cid,uid=trial['course_id'],trial['unit_id'];course=trial['course_snapshot']
unit=next(u for u in course['content']['units'] if u['id']==uid)
mcq,cloze,short=(next(q for q in unit['data']['questions'] if q['kind']==kind) for kind in ('mcq','cloze','short_answer'))
network=ipaddress.ip_interface('172.100.112.4/19').network
other=ipaddress.ip_interface('10.0.10.5/24').network
expected_choice=f'Broadcast: {network.broadcast_address}; Số host hợp lệ: {network.num_addresses-2}'
report={'purpose':'Development numeric-claim checks and fixed grading over the three retained v20 local outputs; not academic accuracy across subjects or independent human review.',
        'course_id':cid,'unit_id':uid,'oracle':{'network':str(network.network_address),'broadcast':str(network.broadcast_address),'hosts':network.num_addresses-2,
                                             'new_example_broadcast':str(other.broadcast_address),'new_example_hosts':other.num_addresses-2},
        'checks':{},'inference_calls':0,'human_reviewed':False,
        'citation_limit':'Reference IDs belong to the approved final-exercise unit. Whether a reader can verify every underlying principle directly at those citations still requires source support review; valid IDs alone do not prove it.'}
checks=report['checks']
checks['mcq_key_matches_computed_broadcast_and_host_count']=mcq['answer']==expected_choice and expected_choice in mcq['options']
checks['cloze_new_case_broadcast_correct']=cloze['answer']==str(other.broadcast_address)
checks['cloze_given_host_count_correct']=str(other.num_addresses-2) in cloze['prompt']
checks['short_reference_correct']=str(network.broadcast_address) in short['answer'] and str(network.num_addresses-2) in short['answer']
checks['short_explanation_network_correct']=str(network.network_address) in short['explanation']
checks['full_context_before_questions']=trial['questions_started_after_full_context']
checks['all_approved_text_covered']=trial['chapter_context']['complete'] and trial['chapter_context']['covered_characters']==trial['chapter_context']['total_characters']
with sqlite3.connect('file:'+str(ROOT/'backend/runtime/study.sqlite3')+'?mode=ro',uri=True) as db:
    source=json.loads(db.execute('SELECT content_json FROM extraction_revisions WHERE source_id=? AND revision=?',(trial['source_id'],trial['chapter_context']['extraction_revision'])).fetchone()[0])
text='\n'.join(f['text'] for f in source)
checks['cloze_prompt_is_new_not_a_source_quotation']=cloze['prompt'] not in text and '10.0.10.5' not in text
assert all(checks.values()),'A numeric/source-coverage check failed; no practice submitted.'
with httpx.Client(base_url='http://127.0.0.1:8770/api',timeout=15,trust_env=False) as client:
    client.cookies.update(json.loads((ROOT/'backend/runtime/chapter-first/network-local-v2.json').read_text()))
    def call(method,route,body=None,headers=None):
        response=client.request(method,route,json=body,headers=headers);response.raise_for_status();return response.json()
    actual=call('GET','/courses/'+cid+'/editor')
    assert actual['revision']==course['revision']
    assert next(u['data'] for u in actual['content']['units'] if u['id']==uid)==unit['data']
    session=call('POST','/courses/'+cid+'/sessions',{'expected_revision':course['revision'],'unit_id':uid},headers={'Idempotency-Key':'chapter-network-v2-fixed-roundtrip'})
    report['session_id']=session['id'];path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    values={'mcq':expected_choice,'cloze':str(other.broadcast_address),
            'short_answer':f'Broadcast: {network.broadcast_address}; host dùng được: {network.num_addresses-2}.'}
    report['grades']=[{'kind':q['kind'],'result':call('POST','/sessions/'+session['id']+'/answers',{'item_id':q['id'],'answer':values[q['kind']]})} for q in session['questions']]
    result=call('POST','/sessions/'+session['id']+'/complete');report['result']=result
    checks['two_fixed_questions_grade_correct_without_ai']=result['score']==2 and result['fixed_total']==2
    checks['short_answer_is_self_review_not_ai_score']=result['self_review_count']==1
    report['wallet_after_practice']=call('GET','/wallet')
    report['wallet_note']='Practice may earn proposed activity rewards. The inference trial itself kept20Coin before/after; no cash or provider inference occurred in this audit.'
report['all_checks_passed']=all(checks.values())
path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
assert report['all_checks_passed']
print(json.dumps({'checks':len(checks),'passed':report['all_checks_passed'],'inference_calls':0,'fixed_score':2,'self_review':1}))
