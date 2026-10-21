"""Conservative ordering verification against explicit source step text.

An arbitrary paraphrase cannot be proved by string matching. New AI ordering
options must retain the original step phrase (optionally quoted/bilingual).
The server checks the saved permutation against those source positions.
"""
import re
from .sequences import MARKER, numbered_sequence_records


class OrderingSourceError(ValueError):
    code='ORDERING_SOURCE_UNPROVEN'


def normalized(text):
    return ' '.join(re.findall(r'[^\W_]+', text.casefold()))


def source_order(question, fragments):
    # Qualify procedures in the pinned, approved scope before filtering refs.
    # A cited step may rely on its nearby procedure heading for context; every
    # option must still match a numbered step actually present in cited refs.
    cited=set(question['source_refs'])
    groups = numbered_sequence_records(fragments)
    if not groups:
        raise OrderingSourceError('Nguồn trích chưa có quy trình đánh số để kiểm chứng thứ tự.')
    options = [normalized(x) for x in question['options']]
    candidates=[]
    for group in groups:
        positions = []
        for option in options:
            matches = [step['number'] for step in group
                       if step['source_refs'] and set(step['source_refs'])<=cited
                       and f" {normalized(step['phrase'])} " in f' {option} ']
            if len(matches) != 1:
                break
            positions.append(matches[0])
        if len(positions) != len(options) or len(set(positions)) != len(positions):
            continue
        candidates.append(sorted(range(len(options)), key=lambda index: positions[index]))
    if candidates:
        if any(key!=candidates[0] for key in candidates):
            raise OrderingSourceError('Các quy trình được trích cho thứ tự mâu thuẫn; chọn rõ một quy trình trước khi dùng câu này.')
        return candidates[0]
    raise OrderingSourceError('Chưa đối chiếu được từng lựa chọn với một bước duy nhất trong nguồn. Giữ nguyên cụm bước gốc, có thể kèm bản dịch; không tự đoán thứ tự từ lời diễn giải.')


def verify_ordering(question, fragments):
    if question.get('kind') != 'ordering':
        return
    if question['answer'] != source_order(question, fragments):
        raise ValueError('Đáp án sắp xếp đảo thứ tự bước được ghi rõ trong nguồn; chưa dùng câu này.')


def derive_generated_ordering(question, fragments):
    """Derive a new key; hide source step labels without rewriting step wording.

    Only for the answer-free generation contract. Manual/history validation
    remains verify_ordering; it never silently repairs a supplied answer key.
    """
    if question.get('kind') != 'ordering' or 'answer' in question:
        raise ValueError('Source-derived ordering expects an ordering draft without an AI answer key.')
    key = source_order(question, fragments)
    options = []
    removed = 0
    for option in question['options']:
        text = option.lstrip()
        quote = text[0] if text.startswith(('"', '“', "'")) else ''
        body = text[1:].lstrip() if quote else text
        marker = MARKER.match(body)
        if marker:
            options.append(quote + body[marker.end():]);removed += 1
        else:options.append(option)
    result = {**question, 'options': options}
    if source_order(result, fragments) != key:
        raise ValueError('Removing source step labels changed the source match; keep this draft for review.')
    return {**result, 'answer': key}, removed
