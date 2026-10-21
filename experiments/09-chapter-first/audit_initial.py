"""Retain and flag the real v19 subnet failures; no model call or key repair."""
import copy
import ipaddress
import json
from pathlib import Path
import sys

import httpx

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from study_backend.subnet_reasoning import check_question, SubnetClaimError

report_path=Path(__file__).resolve().parent/'results/network-local-audit.json'
if report_path.exists():raise SystemExit('Audit exists; do not repeat mutation or overwrite evidence.')
original=json.loads((report_path.parent/'network-local.json').read_text())
cid,uid=original['course_id'],original['unit_id']
old=next(u['data'] for u in original['course_snapshot']['content']['units'] if u['id']==uid)
network=ipaddress.ip_interface('172.100.112.4/19').network
audit={'purpose':'Offline same-output factual check and review flags for the original QA-only v19 result, preserving raw model output.',
       'course_id':cid,'unit_id':uid,'network':str(network.network_address),'broadcast':str(network.broadcast_address),
       'usable_hosts':network.num_addresses-2,'inference_calls':0,'mutations':'question review flags only','questions':[]}
with httpx.Client(base_url='http://127.0.0.1:8770/api',timeout=15,trust_env=False) as client:
    client.cookies.update(json.loads((ROOT/'backend/runtime/chapter-first/network-local.json').read_text()))
    current=client.get('/courses/'+cid+'/editor').json()
    assert next(u['data'] for u in current['content']['units'] if u['id']==uid)==old
    for i,q in enumerate(old['questions']):
        before=copy.deepcopy(q)
        try:check_question(q)
        except SubnetClaimError as exc:reason=str(exc)
        else:raise AssertionError('Expected a proved mismatch in this retained output.')
        response=client.post('/courses/'+cid+'/question-reports',json={'expected_revision':current['revision'],'unit_id':uid,'item_id':uid+':q'+str(i),'reason':reason})
        response.raise_for_status()
        audit['questions'].append({'index':i,'kind':q['kind'],'guard':'SUBNET_DERIVATION_MISMATCH','reason':reason,'flag':response.json(),'raw_output_unchanged':q==before})
    after=client.get('/courses/'+cid+'/editor').json()
    audit['course_revision_unchanged']=after['revision']==current['revision']
    audit['lesson_data_unchanged']=next(u['data'] for u in after['content']['units'] if u['id']==uid)==old
report_path.write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'flagged_qa_questions':len(audit['questions']),'lesson_unchanged':audit['lesson_data_unchanged'],'inference_calls':0}))
