"""Reuse the chapter's analysis to distribute question hints, without AI calls.

Hints are not learning content, a citation, or proof of semantic correctness.
Lexical overlap only limits obviously unrelated chapter targets; the question
must still fit the unit objective and be supported by its original evidence.
"""
import hashlib
import json

from fastapi import HTTPException

from .chapter_evidence import tokens
from .question_generation import content_preferences, question_stages
from .sequences import numbered_sequence_records

QUESTION_FOCUS_VERSION = '20261021-kind-compatible-chapter-targets-v2'
LEGACY_FOCUS_VERSION = '20261021-chapter-question-targets-v1'


def digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(raw.encode()).hexdigest()


def binding(context_id, scope, unit, prefs, reading, version=QUESTION_FOCUS_VERSION):
    return {'version': version, 'context_id': context_id,
            'evidence_sha256': scope['sha256'],
            'unit_sha256': digest({k: unit[k] for k in ('id', 'title', 'objective')}),
            'preferences_sha256': digest(content_preferences(prefs)),
            'reading_sha256': digest(reading)}


def validate(previous, context_id, scope, unit, prefs, reading):
    try:
        unsigned = {k: v for k, v in previous.items() if k != 'sha256'}
        valid = (reading is not None and previous['version'] in {QUESTION_FOCUS_VERSION, LEGACY_FOCUS_VERSION}
                 and previous['sha256'] == digest(unsigned)
                 and all(previous.get(k) == v for k, v in binding(context_id, scope, unit, prefs, reading, previous['version']).items())
                 and {k: v['kind'] for k, v in previous['assignments'].items()} == dict(question_stages(prefs))
                 and all(isinstance(v['topic'], str) and 0 < len(v['topic']) <= 300 for v in previous['assignments'].values()))
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise HTTPException(409, 'Gợi ý phân bổ câu đã lưu không khớp chương/bài; giữ checkpoint, chưa gọi AI hoặc đổi ý cũ.')
    return previous


def prepare(context_id, scope, unit, prefs, reading, brief, fragments, previous=None):
    if previous:
        validate(previous, context_id, scope, unit, prefs, reading)
        if previous['brief_sha256'] != digest(brief):
            raise HTTPException(409, 'Bản phân tích chương đã đổi so với phân bổ câu đang tiếp tục.')
        return previous
    focus = set(scope['focus_source_refs'])
    local_terms = tokens(' '.join([unit['title'], unit['objective'],
                                  *[f['text'] for f in fragments if f['id'] in focus]]))
    candidates = []
    for index, topic in enumerate(brief.get('question_targets', [])):
        terms = tokens(topic)
        overlap = terms & local_terms
        score = len(overlap) / max(1, len(terms))
        if len(overlap) >= 3 and score >= .35:
            candidates.append({'topic': topic, 'basis': 'chapter_question_target', 'index': index})
    # A whole-chapter target may be unrelated to this unit. Local section
    # titles supply a bounded fallback; they too remain model-authored hints.
    if len(candidates) < 2:
        for index, section in enumerate(reading['sections']):
            if set(section['source_refs']) & focus and section['title'] not in [c['topic'] for c in candidates]:
                candidates.append({'topic': section['title'], 'basis': 'unit_section_title', 'index': index})
            if len(candidates) >= 3: break
    if not candidates:
        candidates = [{'topic': unit['title'], 'basis': 'approved_unit_title', 'index': 0}]
    occurrences, kind_offsets, assignments = {}, {}, {}
    procedures = numbered_sequence_records(fragments)
    for key, kind in question_stages(prefs):
        kind_offsets.setdefault(kind, len(kind_offsets))
        occurrence = occurrences.get(kind, 0)
        candidate = candidates[(kind_offsets[kind] + occurrence) % len(candidates)]
        occurrences[kind] = occurrence + 1
        assignments[key] = {'kind': kind, **candidate}
        if kind == 'ordering':
            # A conceptual target cannot be ordered into source steps. Select
            # a real numbered procedure instead of forcing that target into
            # an incompatible question kind (observed on dev-v5 calculus).
            if procedures:
                index = occurrence % len(procedures)
                refs = list(dict.fromkeys(ref for step in procedures[index] for ref in step['source_refs']))
                assignments[key] = {'kind': kind, 'topic': 'Trình tự các bước trong quy trình được đánh số của bài.',
                                    'basis': 'explicit_source_sequence', 'index': index, 'sequence_source_refs': refs}
            else:
                assignments[key] = {'kind': kind, 'topic': 'Nguồn chưa có quy trình đánh số đủ căn cứ.',
                                    'basis': 'backend_source_gate', 'index': 0}
    result = {**binding(context_id, scope, unit, prefs, reading), 'brief_sha256': digest(brief),
              'assignments': assignments, 'ai_calls': 0, 'is_suggestion_not_evidence': True}
    result['sha256'] = digest(result)
    return validate(result, context_id, scope, unit, prefs, reading)


def record_request(plan, applied, key, job_id):
    """Pin before inference; old stages without such a record stay unlabelled."""
    if key not in plan['assignments']: raise ValueError('Câu ngoài phân bổ đã duyệt.')
    applied[key] = {'plan_sha256': plan['sha256'], 'job_id': job_id}


def validate_requests(plan, applied):
    try:
        valid = (not applied or (plan is not None and set(applied) <= set(plan['assignments'])
                 and all(v['plan_sha256'] == plan['sha256'] and isinstance(v['job_id'], str)
                         and 0 < len(v['job_id']) <= 100 for v in applied.values())))
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise HTTPException(409, 'Ghi nhận gợi ý câu không khớp checkpoint; chưa gán lại nguồn gốc câu cũ.')


def instruction(plan, key):
    item = plan['assignments'][key]
    if item['kind'] == 'ordering':
        refs = item.get('sequence_source_refs')
        return ('\nPHẠM VI CÂU SẮP XẾP: dùng quy trình đánh số có thật trong nguyên văn của bài'
                + (' tại các đoạn ' + json.dumps(refs, ensure_ascii=False) if refs else '')
                + '. Các gợi ý phân biệt khái niệm trong bản tổng hợp không phải yêu cầu tạo một quy trình mới. '
                'Câu sắp xếp kiểm tra trình tự các hành động đã đánh số; giữ nguyên cụm bước để backend đối chiếu. '
                'Câu ở dạng khác đã dùng quy trình không làm quy trình này mất khả dụng. ')
    return ('\nGỢI Ý Ý KIỂM TRA CHO RIÊNG CÂU NÀY (dữ liệu phân bổ, không phải nguồn): '
            + json.dumps({'topic': item['topic'], 'basis': item['basis']}, ensure_ascii=False)
            + '. Ưu tiên ý này nếu phù hợp mục tiêu bài và có căn cứ trong nguồn nguyên văn được gửi. '
            'Nếu không phù hợp dạng câu hoặc thiếu căn cứ, chọn ý khác có căn cứ trong đúng bài; '
            'không suy đáp án từ gợi ý, không bịa tiền đề và không bỏ nguyên lý chỉ vì dạng khác đã dùng. '
            'Riêng sắp xếp phải dùng quy trình đánh số có thật, không biến một khái niệm trong gợi ý thành quy trình. ')
