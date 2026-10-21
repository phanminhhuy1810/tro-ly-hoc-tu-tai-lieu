"""A source-quoted statement can be masked without guessing or another model call."""
import hashlib
import re
import unicodedata


def compact(value):return ' '.join(unicodedata.normalize('NFC',value).split())


class ClozeSourceError(ValueError):
    """This candidate cannot be proved from the source; it is not a file error."""
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def letter_layout(value):
    """Ignore gaps between letters only, with offsets back to the source.

    PDF extraction can join Vietnamese words. Never merge numbers (1 2 != 12),
    change punctuation/case, or accept a substring of a larger source token.
    """
    chars, positions = [], []
    for index, char in enumerate(value):
        if char.isspace() and 0 < index < len(value)-1 and value[index-1].isalpha() and value[index+1].isalpha():
            continue
        chars.append(char); positions.append(index)
    return ''.join(chars), positions


def answer_spans(statement, answer):
    canonical, offsets = letter_layout(statement)
    needle, _ = letter_layout(answer)
    spans = []
    for match in re.finditer(re.escape(needle), canonical):
        start, end = offsets[match.start()], offsets[match.end()-1]+1
        # Check boundaries in the source, not the version with spaces removed.
        if start and (statement[start-1].isalnum() or statement[start-1]=='_') and statement[start].isalnum():continue
        if end < len(statement) and statement[end-1].isalnum() and (statement[end].isalnum() or statement[end]=='_'):continue
        spans.append((start, end))
    return spans


def mask_source_excerpt(question,fragments):
    """The model selects a literal answer; the server constructs its question."""
    for fragment in fragments or []:
        if fragment['id'] not in question['source_refs']:continue
        # Never split IPv4 addresses/decimals at their internal periods.
        sentences = re.split(r'(?<=[.!?。！？])\s+(?=\D)|\n+',fragment['text'])
        # A slide often uses a heading and sub-bullets instead of a sentence.
        # Keep that literal block when a lone answer line has too little context.
        blocks = re.split(r'\n\s*\n|\n(?=\s*§)',fragment['text'])
        windows = []
        for block in blocks:
            lines = block.splitlines()
            windows.extend('\n'.join(lines[i:i+3]) for i in range(max(0,len(lines)-2)))
        for sentence in sentences + windows + blocks:
            sentence=compact(sentence)
            if not 12<=len(sentence)<=900:continue
            try:
                candidate,digest=mask_source_statement({**question,'prompt':sentence,'source_refs':[fragment['id']]},[fragment])
            except ClozeSourceError:continue
            # Several sentences can mention the same answer. The first proved
            # excerpt is sufficient: uniqueness belongs within that excerpt.
            return candidate,digest
    raise ClozeSourceError('CLOZE_SOURCE_UNVERIFIED', 'Chưa tạo câu điền khuyết: đáp án AI đề xuất chưa khớp một đoạn nguồn đủ ngữ cảnh. Các dạng câu khác vẫn được tạo tiếp.')


def mask_source_statement(question,fragments):
    raw=question['prompt'];statement=compact(raw);answer=compact(question['answer'])
    refs=set(question['source_refs'])
    if not fragments or not answer or len(answer)>120:
        raise ClozeSourceError('CLOZE_SOURCE_UNVERIFIED', 'Chưa tạo câu điền khuyết: đáp án chưa đối chiếu được với nguồn.')
    if not any(fragment['id'] in refs and statement in compact(fragment['text']) for fragment in fragments):
        raise ClozeSourceError('CLOZE_QUOTE_UNVERIFIED', 'Chưa tạo câu điền khuyết: câu AI trích chưa khớp nguồn; không tự đoán chỗ cần ẩn.')
    spans=answer_spans(statement,answer)
    if len(spans)!=1:
        raise ClozeSourceError('CLOZE_ANSWER_NOT_UNIQUE', 'Chưa tạo câu điền khuyết: cần một vị trí đáp án duy nhất trong đoạn được trích.')
    start,end=spans[0];prompt=statement[:start]+'____'+statement[end:]
    if len(re.sub(r'\W|_', '',prompt))<8:
        raise ClozeSourceError('CLOZE_CONTEXT_MISSING', 'Chưa tạo câu điền khuyết: đoạn còn lại thiếu ngữ cảnh sau khi ẩn đáp án.')
    # It remains a source quotation even when explanations use another language.
    return {**question,'prompt':'“'+prompt+'”'},hashlib.sha256(raw.encode()).hexdigest()
