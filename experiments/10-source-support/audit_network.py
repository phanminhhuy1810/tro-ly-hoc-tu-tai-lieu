"""Audit saved chapter generation and manually repair one QA-only prose error.

Arithmetic oracle is stdlib ipaddress, not the model's answer. The raw v22
report remains unchanged and is not relabeled as a perfect model output.
"""
import copy
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
from pathlib import Path

import httpx

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
output=HERE/'results/network-local-v22-audit.json'
if output.exists():raise SystemExit('Audit exists; inspect saved session/proposal, do not submit again.')
raw_path=HERE/'results/network-local-v22-resume.json';raw_bytes=raw_path.read_bytes();trial=json.loads(raw_bytes)
assert trial['status']=='succeeded'
cid,uid=trial['course_id'],trial['unit_id'];course=trial['course_snapshot']
unit=next(u for u in course['content']['units'] if u['id']==uid)
mcq,cloze,short=(next(q for q in unit['data']['questions'] if q['kind']==k) for k in ['mcq','cloze','short_answer'])
scope=unit['generation']['evidence_scope'];chapter=trial['chapter_context']
network=ipaddress.ip_interface('172.100.112.4/19').network
new_case=ipaddress.ip_interface('10.10.10.5/24').network
host_count=network.num_addresses-2;host_bits=32-network.prefixlen
remainder=network.prefixlen % 8;full_octets=network.prefixlen//8
expected_mcq=f'Net Addr: {network.network_address}; Số host hợp lệ: {host_count}'
root_created=trial['context_nodes'][trial['context_manifest']['root']]['created_at']
checks={
    'approved_text_coverage_33_of_33':chapter['complete'] and chapter['covered_fragments']==chapter['total_fragments']==33 and chapter['covered_characters']==chapter['total_characters'],
    'questions_started_after_complete_chapter':all(r['started_at']>root_created for r in trial['job']['progress']['requests'] if r['schema'].endswith('Draft')),
    'no_new_reading_of_chapter_on_resume':trial['checks']['no_chapter_reread'],
    'mcq_key_matches_program':mcq['answer']==expected_mcq and expected_mcq in mcq['options'],
    'cloze_value_matches_program':cloze['answer']==str(host_count),
    'new_short_case_reference_values_correct':short['answer']==f'Net Addr: {new_case.network_address}; Broadcast: {new_case.broadcast_address}; Số host hợp lệ: {new_case.num_addresses-2}.',
    'all_mindmap_nodes_have_source_refs':all(x['source_refs'] for x in unit['data']['mindmap']),
    'all_questions_cite_original_theory_not_only_exercise':all(set(q['source_refs'])&set(scope['support_source_refs']) for q in [mcq,cloze,short]),
}
assert all(checks.values()),checks
# This observed claim is wrong even though key/host arithmetic passed.
wrong='19 bits bao phủ 2 octet đầu và 1 bit của octet thứ 3'
assert wrong in mcq['explanation'] and full_octets*8+1!=network.prefixlen
assert full_octets*8+remainder==network.prefixlen and remainder==3
report={'purpose':'QA-only original-principle citation, numeric answer, fixed grading and scoped repair audit. Not independent academic acceptance.',
        'at':datetime.now(timezone.utc).isoformat(),'course_id':cid,'unit_id':uid,'inference_calls':0,'independent_human_reviewed':False,
        'raw_trial_sha256':hashlib.sha256(raw_bytes).hexdigest(),'checks':checks,
        'oracle':{'given':'172.100.112.4/19','network':str(network.network_address),'broadcast':str(network.broadcast_address),
                  'host_bits':host_bits,'usable_hosts':host_count,'full_prefix_octets':full_octets,'prefix_bits_in_next_octet':remainder,
                  'new_case':'10.10.10.5/24','new_network':str(new_case.network_address),'new_broadcast':str(new_case.broadcast_address),'new_usable_hosts':new_case.num_addresses-2},
        'model_quality_pass':False,'defects':[{'kind':'mcq_explanation','observed':wrong,'correct':'19 = 16 + 3; two full octets and three bits in the third octet.',
                                            'not_caught_by_narrow_automatic_subnet_guard':True},
                                           {'kind':'citation_precision','observed':'The new /24 example also cites exercise page33; theory pages14/15 support its derivation, but page33 is an unnecessary citation.'}],
        'review_limits':['Theory support and numeric statements were checked by Codex plus program arithmetic, not an independent human.',
                         'One selected support page9 is not relevant to these questions and was not cited by them; lexical relevance is not entailment.',
                         'The original text transcript still omits the page24 image table.'],
        'source_scope':scope}
def save():output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
save()
with httpx.Client(base_url='http://127.0.0.1:8770/api',timeout=20,trust_env=False,
                  cookies=json.loads((ROOT/'backend/runtime/chapter-first/network-local-v3-support.json').read_text())) as client:
    def call(method,path,body=None,headers=None):
        response=client.request(method,path,json=body,headers=headers);response.raise_for_status();return response.json()
    assert call('GET','/courses/'+cid+'/editor')==course
    source_before=call('GET','/sources/'+trial['source_id'])
    fragments=call('GET','/courses/'+cid+'/source-fragments?unit_id='+uid)
    by_id={f['id']:f for f in fragments}
    checks['all_sources_resolve_in_same_revision']=all(ref in by_id for q in [mcq,cloze,short] for ref in q['source_refs'])
    cited='\n'.join(by_id[r]['text'] for r in short['source_refs'])
    checks['cited_originals_contain_network_broadcast_and_host_rule']='HostID' in cited and 'xoávề0' in cited and 'bậtlên1' in cited and '2m-2' in cited
    full_text='\n'.join(f['text'] for f in source_before['fragments'])
    checks['new_case_not_extracted_from_slide']='10.10.10.5' not in full_text and short['prompt'] not in full_text
    report['cited_fragments']=fragments
    session=call('POST','/courses/'+cid+'/sessions',{'expected_revision':course['revision'],'unit_id':uid},
                 headers={'Idempotency-Key':'chapter-v22-numeric-http-audit'})
    report['practice_session_id']=session['id'];save()
    values={'mcq':expected_mcq,'cloze':str(host_count),
            'short_answer':f'Net Addr: {new_case.network_address}; Broadcast: {new_case.broadcast_address}; host hợp lệ: {new_case.num_addresses-2}.'}
    report['grades']=[{'kind':q['kind'],'result':call('POST','/sessions/'+session['id']+'/answers',{'item_id':q['id'],'answer':values[q['kind']]})} for q in session['questions']]
    report['practice_result']=call('POST','/sessions/'+session['id']+'/complete')
    checks['program_derived_fixed_answers_grade_2_of_2']=report['practice_result']['score']==2 and report['practice_result']['fixed_total']==2
    checks['short_reference_self_review_not_ai_score']=report['practice_result']['self_review_count']==1
    old_session=call('GET','/sessions/'+session['id'])
    wallet_before_manual=call('GET','/wallet')
    reason='Lời giải /19 ghi 2octet đầu +1bit là sai:19-16=3bit ở octet thứ3. Key/network/host đúng; sửa riêng giải thích, không đổi đáp án.'
    flag=call('POST','/courses/'+cid+'/question-reports',{'expected_revision':course['revision'],'unit_id':uid,'item_id':uid+':q0','reason':reason})
    report['flag']=flag;save()
    # Completing practice changes live completed flags, even without editing
    # the stored lesson. Compare preview with the immediately preceding DTO.
    before_preview=call('GET','/courses/'+cid+'/editor')
    replacement=copy.deepcopy(mcq)
    replacement['explanation']=mcq['explanation'].replace(wrong,'19 bits bao phủ 2 octet đầu và 3 bit của octet thứ 3')
    proposal=call('POST','/courses/'+cid+'/proposals',{'expected_revision':course['revision'],'unit_id':uid,'target':'question','index':0,
                'request':'Đối chiếu phép chia19=16+3 và sửa riêng số bit trong lời giải; giữ stem/key/options/nguồn/câu khác.', 'replacement':replacement})
    report['repair_proposal_id']=proposal['proposal_id'];save()
    preview=call('GET','/proposals/'+proposal['proposal_id'])
    checks['repair_preview_does_not_change_content']=call('GET','/courses/'+cid+'/editor')==before_preview
    checks['repair_preserves_key_choices_and_citations']=all(preview['after'][key]==mcq[key] for key in ['prompt','answer','options','source_refs'])
    call('POST','/proposals/'+proposal['proposal_id']+'/apply',{'expected_revision':course['revision']})
    repaired=call('GET','/courses/'+cid+'/editor');report['repaired_revision']=repaired['revision']
    after_unit=next(u for u in repaired['content']['units'] if u['id']==uid)
    checks['repair_changes_only_mcq_explanation']=after_unit['data']=={**unit['data'],'questions':[replacement,*unit['data']['questions'][1:]]}
    # The old attempt retains its item/result snapshots; review annotations may be added.
    after_session=call('GET','/sessions/'+session['id'])
    checks['old_attempt_snapshot_retained']=all(after_session[k]==old_session[k] for k in ['revision','questions','result'])
    checks['source_unchanged_by_question_repair']=call('GET','/sources/'+trial['source_id'])==source_before
    checks['manual_repair_no_coin_change']=call('GET','/wallet')==wallet_before_manual
    new_session=call('POST','/courses/'+cid+'/sessions',{'expected_revision':repaired['revision'],'unit_id':uid})
    item=next(q for q in new_session['questions'] if q['kind']=='short_answer')
    thread=call('POST','/sessions/'+new_session['id']+'/items/'+item['id']+'/help',{})
    detail=call('GET','/help/threads/'+thread['thread_id'])
    checks['inline_help_pins_exact_theory_citations']={f['id'] for f in detail['source_excerpts']}==set(short['source_refs'])
    report['inline_help_thread_id']=thread['thread_id']
    call('POST','/sessions/'+new_session['id']+'/cancel')
checks['raw_model_report_not_overwritten']=raw_path.read_bytes()==raw_bytes
report['all_workflow_checks_passed']=all(checks.values());save()
assert report['all_workflow_checks_passed'],checks
print(json.dumps({'checks':len(checks),'workflow_passed':True,'model_quality_pass':False,'qa_revision_after_scoped_repair':report['repaired_revision'],'inference_calls':0}))
