"""Source-reviewed QA manual repair; preserve model failures and old attempts.

This reference is authored by Codex, not a successful AI inference or an
independent human label. Only the explicit QA profile/course is changed.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

import httpx

ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
OUT=HERE/'results/operant-manual-recovery.json'
assert not OUT.exists(),'Inspect recorded IDs; do not replay a manual apply.'
base_path=HERE/'results/operant-correction-preview.json';new_path=HERE/'results/operant-correction-inputs-v4.json'
base_raw=base_path.read_bytes();new_raw=new_path.read_bytes();base=json.loads(base_raw);new=json.loads(new_raw)
assert base['source_review']['status']=='reject_do_not_apply' and new['source_review']['status']=='needs_review_do_not_apply'
evaluation_path=ROOT/'experiments/08-quality-evaluation/results/dev-v5-chapter-focus.json';evaluation=evaluation_path.read_bytes()
case=next(c for c in json.loads(evaluation)['runs'] if c['case_id']=='psy-dev-operant')
cid=case['course_id'];database=ROOT/'backend/runtime/study.sqlite3'
with sqlite3.connect('file:'+str(database)+'?mode=ro',uri=True) as db:
    assert not db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running')").fetchone()
    job_count=db.execute('SELECT count(*) FROM jobs').fetchone()[0]
    old_flags=db.execute('SELECT * FROM question_review_flags WHERE course_id=? ORDER BY question_revision_id',(cid,)).fetchall()

report={'purpose':'Manual recovery of one QA question with source crosscheck, not model quality, independent human review or a change to Huy course.',
        'at':datetime.now(timezone.utc).isoformat(),'course_id':cid,'case_id':case['case_id'],'reference_author':'Codex-assisted source crosscheck',
        'model_inference_calls':0,'external_inference':0,'automatic_semantic_retries':0,'independent_human_reviews':0,
        'baseline_sha256':hashlib.sha256(base_raw).hexdigest(),'paired_sha256':hashlib.sha256(new_raw).hexdigest(),'checks':{}}
def save():OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
cookie=ROOT/'backend/runtime/quality-evaluation/dev-v5-chapter-focus/psy-dev-operant.json'
with httpx.Client(base_url='http://127.0.0.1:8770/api',trust_env=False,timeout=20,cookies=json.loads(cookie.read_text())) as client:
    def call(method,path,body=None):
        r=client.request(method,path,json=body);r.raise_for_status();return r.json()
    before=call('GET','/courses/'+cid+'/editor');unit=before['content']['units'][0];q=unit['data']['questions'][4]
    assert before['revision']==2 and q==base['before_question'] and q==new['before_question']
    source=call('GET','/sources/'+case['source_id']);assert source==case['source_snapshot']
    old_session=call('GET','/sessions/'+case['session_id']);wallet=call('GET','/wallet')
    # Keep facts and question text. Do not add a different causal event to force
    # a category; the scope of these definitions requires both dimensions.
    replacement=deepcopy(q)
    replacement.update(answer='Chưa đủ dữ kiện để kết luận là negative punishment. Bước1: xét hành vi làm ồn. Bước2: hành vi đó giảm. Bước3: đề chỉ nói giữ quyền dùng máy tính khi ngồi yên, không nói quyền bị thu hồi vì làm ồn. Bước4: cần làm rõ hậu quả thêm/loại bỏ kích thích và quan hệ phụ thuộc với hành vi đang xét trước khi phân loại.',
        explanation='Theo nguồn, phân loại cần xác định cả chiều thay đổi hành vi và việc thêm hay loại bỏ kích thích. Đề cho biết làm ồn giảm nhưng không nêu việc thu hồi quyền. Không được tự thay “giữ quyền” thành “thu hồi quyền” để kết luận negative punishment.',
        rubric=['Xác định hành vi đang xét là làm ồn và chiều thay đổi là giảm.',
                'Nhận ra giữ quyền không đồng nghĩa kích thích đã bị loại bỏ; không thêm tình tiết ngoài đề.',
                'Nêu dữ kiện còn thiếu về hậu quả và quan hệ phụ thuộc trước khi kết luận loại hậu quả.'],
        source_refs=[source['fragments'][i]['id'] for i in (0,1,4,5,6,7)])
    report.update(before_revision=before['revision'],before_question=q,manual_replacement=replacement,wallet_before=wallet);save()
    proposal=call('POST','/courses/'+cid+'/proposals',{'expected_revision':2,'unit_id':unit['id'],'target':'question','index':4,
        'request':'Sửa tay sau đối chiếu nguồn: giữ đề và thừa nhận dữ kiện còn thiếu, không tự đổi giữ quyền thành thu hồi. Đây là tham khảo do Codex biên soạn, chưa là nhãn người độc lập.',
        'replacement':replacement})
    assert 'job_id' not in proposal;pid=proposal['proposal_id'];report['proposal_id']=pid;save()
    preview=call('GET','/proposals/'+pid);report['preview']=preview
    assert preview['before']==q and preview['after']==replacement
    assert call('GET','/courses/'+cid+'/editor')==before
    call('POST','/proposals/'+pid+'/apply',{'expected_revision':2})
    after=call('GET','/courses/'+cid+'/editor');report['applied_revision']=after['revision'];save()
    updated=after['content']['units'][0];checks=report['checks']
    checks['only_selected_question_changed']=updated['data']['questions']==[replacement if i==4 else v for i,v in enumerate(unit['data']['questions'])]
    checks['other_lesson_content_unchanged']=all(updated['data'][k]==unit['data'][k] for k in ('title','sections','cards','mindmap'))
    checks['other_units_unchanged']=after['content']['units'][1:]==before['content']['units'][1:]
    checks['initial_provenance_unchanged']=updated['generation']==unit['generation']
    checks['creator_metadata_kept']=all(replacement[k]==q[k] for k in ('difficulty','difficulty_basis'))
    session=call('POST','/courses/'+cid+'/sessions',{'expected_revision':after['revision'],'unit_id':unit['id']});report['new_session_id']=session['id'];save()
    item=next(x for x in session['questions'] if x['prompt']==q['prompt']);report['new_item_id']=item['id']
    draft='Tôi chưa thấy đề nói thu hồi quyền; cần làm rõ hậu quả.'
    call('PUT','/sessions/'+session['id']+'/draft',{'item_id':item['id'],'answer':draft,'expected_version':0})
    thread=call('POST','/sessions/'+session['id']+'/items/'+item['id']+'/help');report['thread_id']=thread['thread_id'];save()
    explanation=call('POST','/help/threads/'+thread['thread_id']+'/actions',{'action':'explain'})
    second=call('POST','/help/threads/'+thread['thread_id']+'/actions',{'action':'explain'})
    report['cached_explanation']=explanation
    checks['cached_reply_uses_corrected_reference']=explanation['reply']['reference']==replacement['answer'] and explanation['reply']['text']==replacement['explanation'] and explanation['reply']['rubric']==replacement['rubric']
    checks['inline_explanation_no_ai']=explanation['ai_called'] is False and second['ai_called'] is False and second['cached'] is True
    current=call('GET','/help/threads/'+thread['thread_id'])
    report['help_thread_after']=current
    checks['draft_kept_without_submit']=current['student']['draft']==draft and not current['student']['submitted']
    call('POST','/sessions/'+session['id']+'/cancel')
    checks['old_attempt_unchanged']=call('GET','/sessions/'+case['session_id'])==old_session
    checks['source_unchanged']=call('GET','/sources/'+case['source_id'])==source
    checks['both_model_outputs_retained']=base_path.read_bytes()==base_raw and new_path.read_bytes()==new_raw
    checks['raw_development_measurement_retained']=evaluation_path.read_bytes()==evaluation
    report['wallet_after']=call('GET','/wallet');checks['zero_coin_change']=report['wallet_after']==wallet
    with sqlite3.connect('file:'+str(database)+'?mode=ro',uri=True) as db:
        checks['no_new_ai_job']=db.execute('SELECT count(*) FROM jobs').fetchone()[0]==job_count
        checks['old_flags_preserved']=db.execute('SELECT * FROM question_review_flags WHERE course_id=? ORDER BY question_revision_id',(cid,)).fetchall()==old_flags
    save()
assert report['applied_revision']==3 and all(report['checks'].values()),'Keep saved state and inspect the exact failure; do not replay.'
print(json.dumps({'applied_revision':report['applied_revision'],'checks':report['checks'],'model_calls':0,'coin_change':0}),flush=True)
