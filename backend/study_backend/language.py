"""A conservative English-output guard, not a general language classifier."""
import re


VI_PHRASES = re.compile(r'\b(?:nếu|bao nhiêu|giải thích|địa chỉ|được|của|còn|những|đúng|sắp xếp|ghép cặp|điền|chọn|phần|nguồn|tiêu chí|chưa)\b', re.IGNORECASE)


def language_instruction(preferences):
    language = preferences.get('language', 'vi')
    if language == 'en':
        return ' OUTPUT LANGUAGE: ENGLISH. Write every title, explanation, question prompt, option, card and rubric in English even when the source is Vietnamese. Keep only explicitly requested original terms/source quotations unchanged; do not copy Vietnamese question wording from the source. '
    if language == 'source':
        return ' Giữ ngôn ngữ nguồn và từ đang học; không tự dịch mất thuật ngữ. '
    return ' Viết nội dung bằng tiếng Việt, giữ thuật ngữ gốc và từ đang học. '


def validate_language(value, preferences):
    if preferences.get('language') != 'en': return
    checked_fields = {'title','text','front','back','prompt','options','left','explanation','rubric'}
    def inspect(item, field=None):
        if isinstance(item, dict):
            for key, child in item.items(): inspect(child, key)
        elif isinstance(item, list):
            for child in item: inspect(child, field)
        elif isinstance(item, str) and field in checked_fields:
            text = item
            for term in preferences.get('terms_to_keep', []):
                text = text.replace(term, '')
            # Original quotations are legitimate in language-study questions.
            text = re.sub(r'"[^"\n]+"|“[^”\n]+”', '', text)
            if VI_PHRASES.search(text):
                raise ValueError('Đầu ra còn câu tiếng Việt dù đã chọn English; chưa lưu phần này. Có thể sửa đúng phần hoặc thử lại.')
    inspect(value)
