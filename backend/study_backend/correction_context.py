"""Immutable request/source binding for a resumable chapter-aware correction."""
import hashlib
import json

from fastapi import HTTPException

CORRECTION_PROMPT_VERSION = '20261021-question-inputs-without-old-solution-v4'
CORRECTION_SCOPE_VERSION = 'whole-chapter-correction-scope-v1'


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def binding(course, unit, plan, prefs, fragments, before, body, chapter_id):
    scope = {'version': CORRECTION_SCOPE_VERSION, 'course_id': course['id'], 'base_revision': course['revision'],
             'unit_id': unit['id'], 'target': body.target, 'index': body.index,
             'request_sha256': digest(body.request), 'before_sha256': digest(before),
             'unit_sha256': digest({k: unit[k] for k in ('id', 'title', 'objective')}),
             'source_plan_id': plan['id'], 'source_id': plan['source_id'],
             'extraction_revision': prefs['extraction_revision'], 'chapter_context_id': chapter_id,
             'input_source_refs': [f['id'] for f in fragments], 'input_sha256': digest(fragments)}
    scope['sha256'] = digest(scope)
    return scope


def check_resume(previous, payload, scope):
    old = json.loads(previous['payload_json'])
    result = json.loads(previous['result_json']) if previous['result_json'] else {}
    partial = json.loads(previous['partial_json'])
    fields = ('course_id', 'unit_id', 'expected_revision', 'target', 'index', 'request', 'replacement')
    allowed = (previous['status'] in {'failed', 'cancelled'} or
               previous['status'] == 'succeeded' and result.get('continuation_required') is True and not result.get('proposal_id'))
    if (previous['task'] != 'correction' or not allowed or any(old.get(k) != payload.get(k) for k in fields)
            or partial.get('correction_scope') != scope or not partial.get('chapter_context')):
        raise HTTPException(409, 'Phần sửa đã lưu không khớp yêu cầu/phạm vi/phiên bản đang xem; giữ bản cũ, chưa gọi AI hoặc giữ Coin.')
    replacement = partial.get('replacement')
    if replacement is not None and (partial.get('replacement_sha256') != digest(replacement)
                                    or not isinstance(partial.get('replacement_provider'), dict)):
        raise HTTPException(409, 'Bản sửa checkpoint không còn hợp lệ; chưa dùng lại hoặc tự tạo lại.')
    return partial
