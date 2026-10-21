"""Recognize explicit numbered procedures without joining unrelated sources."""
import re


# An attached function argument such as h'(0) is not a numbered step. Keep
# parenthesized/inline labels (including Step(1)) and genuine zero-based lists.
MARKER = re.compile(r'\b(?:bước|step)\s*\(?\s*(\d+)\s*[:.)-]?\s+|(?<![\w\x27’′″)\]}])\((\d+)\)(?!\s*=)\s*|^\s*(\d+)[.)]\s+', re.I | re.M)
CONTEXT = re.compile(r'quy trình|các bước|procedure|sequence of steps|steps to', re.I)
ACTION = re.compile(
    r'^(?:đọc|tính|xác định|lấy|loại(?: bỏ)?|kiểm tra|chọn|nhập|lưu|mở|đóng|'
    r'thực hiện|so sánh|phân bổ|sắp xếp|kết nối|khởi động|cài đặt|thay|áp dụng|'
    r'rút gọn|chứng minh|xét|giải|quan sát|thu thập|mã hóa|'
    r'read|calculate|compute|identify|find|take|remove|check|choose|select|enter|'
    r'save|open|close|compare|allocate|sort|connect|start|install|apply|solve)\b', re.I)


def _origin(fragment):
    locator = fragment.get('locator', {})
    identifier = locator.get('component_fragment_id') or fragment.get('id', '')
    parts = identifier.rsplit(':', 2)
    default_origin = tuple(parts[:-1]) if len(parts) == 3 else None
    origin = (locator['component_source_id'], locator.get('component_revision')) if locator.get('component_source_id') else default_origin
    ordinal = int(parts[-1]) if len(parts) == 3 and parts[-1].isdigit() else None
    return origin, ordinal


def numbered_sequence_records(fragments):
    """Number + source wording proves relative order, never a paraphrased guess.

    An explicit procedure heading or Step labels still qualifies. A bare numeric
    list qualifies only when every item starts with a recognizable action. Source
    component/revision boundaries and missing fragment ranges split the scope.
    """
    chunks = []
    for fragment in fragments:
        origin, ordinal = _origin(fragment)
        if not chunks or origin != chunks[-1]['origin'] or (
                ordinal is not None and chunks[-1]['last'] is not None and ordinal != chunks[-1]['last'] + 1):
            chunks.append({'origin': origin, 'last': ordinal, 'fragments': []})
        chunks[-1]['fragments'].append(fragment)
        chunks[-1]['last'] = ordinal
    result = []
    for chunk in chunks:
        texts=[];spans=[];offset=0
        for fragment in chunk['fragments']:
            value=fragment.get('text','')
            spans.append((offset,offset+len(value),fragment['id']))
            texts.append(value);offset+=len(value)+1
        text = '\n'.join(texts)
        marks = list(MARKER.finditer(text))
        groups, current = [], []
        for index, mark in enumerate(marks):
            number = int(next(value for value in mark.groups() if value))
            end = marks[index+1].start() if index+1 < len(marks) else len(text)
            raw_phrase = re.split(r'[;\n]', text[mark.end():end], maxsplit=1)[0]
            phrase = raw_phrase.strip(' .:')
            labelled = mark.group(1) is not None
            refs=[ref for start,stop,ref in spans if start<mark.end()+len(raw_phrase) and stop>mark.start()]
            if current and number != current[-1]['number'] + 1:
                groups.append(current);current = []
            current.append({'number':number,'phrase':phrase,'labelled':labelled,'source_refs':refs,
                            'start':mark.start(),'end':mark.end()+len(raw_phrase)})
        if current:groups.append(current)
        previous_end=0
        for group in groups:
            preceding=text[previous_end:group[0]['start']]
            group_refs={ref for step in group for ref in step['source_refs']}
            headings='\n'.join(f.get('locator',{}).get('heading','') for f in chunk['fragments'] if f['id'] in group_refs)
            has_context=bool(CONTEXT.search(preceding+'\n'+headings))
            previous_end=group[-1]['end']
            if len(group) >= 2 and all(len(step['phrase'].split()) >= 2 for step in group) and (
                    has_context or all(step['labelled'] for step in group) or all(ACTION.match(step['phrase']) for step in group)):
                result.append(group)
    return result


def numbered_sequences(fragments):
    """Compatibility view used by the source gate; proof records retain IDs."""
    return [[(step['number'],step['phrase']) for step in group]
            for group in numbered_sequence_records(fragments)]
