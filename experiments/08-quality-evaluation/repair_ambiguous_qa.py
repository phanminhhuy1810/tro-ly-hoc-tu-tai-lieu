"""Quarantine and manually repair a measured ambiguous QA MCQ, not Huy data.

The original model output/report remains unchanged for evaluation. This runs
once, records preview/apply/history evidence and makes no model request.
"""
import copy
import hashlib
import json
from pathlib import Path

import httpx

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]


def main():
    output=HERE/'results/ambiguous-chain-qa-repair.json'
    if output.exists():raise SystemExit('Repair evidence exists. Do not repeat or overwrite it.')
    run=json.loads((HERE/'results/dev-v2.json').read_text())
    item=next(c for c in run['runs'] if c['case_id']=='calc-dev-chain')
    cid=item['course_id'];uid=item['unit_id'];old_course=item['course_snapshot']
    old_data=old_course['content']['units'][0]['data']
    index=next(i for i,q in enumerate(old_data['questions']) if 'Vì bỏ mất hệ số 3' in q.get('options',[]))
    old_question=old_data['questions'][index]
    report={'purpose':'Manual correction of one genuinely ambiguous dev-v2 QA MCQ; original evaluation output stays unchanged.',
            'course_id':cid,'base_revision':2,'question_index':index,'inference_calls':0,'payments':0,
            'ambiguity':'Both missing factor3 and failing to multiply by the inner derivative describe the defect. A single correct key is not justified.',
            'before_question':old_question,'checks':{},
            'harness_initial_guard_failure':'The first read-only attempt compared the dynamic unit.completed overlay before/after practice. Guard corrected to pin revision and lesson data; no mutation occurred before that assertion.'}
    with httpx.Client(base_url='http://127.0.0.1:8770/api',timeout=20,trust_env=False) as client:
        cookie=ROOT/'backend/runtime/quality-evaluation/dev-v2/calc-dev-chain.json'
        client.cookies.update(json.loads(cookie.read_text()))
        def call(method,path,body=None):
            r=client.request(method,path,json=body);r.raise_for_status();return r.json()
        current=call('GET','/courses/'+cid+'/editor')
        assert current['revision']==2 and current['content']['units'][0]['data']==old_data
        old_session=call('GET','/sessions/'+item['session_id'])
        bad_item=next(q for q in old_session['questions'] if q['prompt']==old_question['prompt'])
        wallet=call('GET','/wallet')
        report['flag']=call('POST','/courses/'+cid+'/question-reports',{'expected_revision':2,'unit_id':uid,'item_id':bad_item['id'],
            'reason':'QA: hai lựa chọn cùng nêu việc bỏ mất hệ số đạo hàm hàm trong; cần sửa thành một câu có key duy nhất.'})
        filtered=call('POST','/courses/'+cid+'/sessions',{'expected_revision':2,'unit_id':uid})
        report['checks']['flag_excludes_old_question_from_new_session']=all(q['id']!=bad_item['id'] for q in filtered['questions'])
        call('POST','/sessions/'+filtered['id']+'/cancel',{})
        replacement={**old_question,'prompt':"Với h(x)=(3x+1)^4, giá trị h'(0) bằng bao nhiêu?",'options':['12','4','3'],'answer':'12',
            'explanation':"Chain rule cho h'(x)=4(3x+1)^3*3=12(3x+1)^3, nên h'(0)=12."}
        proposed=call('POST','/courses/'+cid+'/proposals',{'expected_revision':2,'unit_id':uid,'target':'question','index':index,
            'request':'QA: thay câu nguyên nhân có hai lựa chọn cùng đúng bằng câu giá trị tại điểm có một đáp án, giữ các phần khác.',
            'replacement':replacement})
        preview=call('GET','/proposals/'+proposed['proposal_id']);report['preview']=preview
        report['checks']['preview_did_not_apply']=call('GET','/courses/'+cid+'/editor')['revision']==2
        applied=call('POST','/proposals/'+proposed['proposal_id']+'/apply',{'expected_revision':2});report['applied']=applied
        after=call('GET','/courses/'+cid+'/editor');after_data=after['content']['units'][0]['data']
        report['checks']['new_revision_is_3']=after['revision']==3
        report['checks']['only_selected_question_changed']=all(q==after_data['questions'][i] for i,q in enumerate(old_data['questions']) if i!=index)
        report['checks']['reading_cards_mindmap_preserved']=all(old_data[k]==after_data[k] for k in ('title','sections','cards','mindmap'))
        preserved=call('GET','/sessions/'+item['session_id'])
        report['checks']['old_snapshot_answers_result_preserved']=all(preserved.get(k)==old_session.get(k) for k in ('questions','answers','result','revision'))
        report['checks']['old_attempt_warns_about_ambiguous_key']=bool(preserved.get('reference_warnings'))
        fresh=call('POST','/courses/'+cid+'/sessions',{'expected_revision':3,'unit_id':uid})
        report['checks']['new_session_has_replacement_not_old_prompt']=any(q['prompt']==replacement['prompt'] for q in fresh['questions']) and all(q['prompt']!=old_question['prompt'] for q in fresh['questions'])
        call('POST','/sessions/'+fresh['id']+'/cancel',{})
        report['checks']['wallet_unchanged']=wallet==call('GET','/wallet')
        report['after_question']=after_data['questions'][index]
        report['all_passed']=all(report['checks'].values())
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'all_passed':report['all_passed'],'checks':report['checks']},ensure_ascii=False))
    if not report['all_passed']:raise SystemExit(1)


if __name__=='__main__':main()
