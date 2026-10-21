"""Conservative checks, not a general proof that a question is factually sound."""
from fractions import Fraction
import re
import unicodedata
from .polynomial_questions import verify_composition


_BITS_BYTES = re.compile(r'\b(\d+(?:[.,]\d+)?)\s*(bytes?|bits?)\b', re.I)


def equivalent_quantity_text(text):
    text = unicodedata.normalize('NFKC', text).casefold()
    def bits(match):
        value = Fraction(match[1].replace(',', '.')) * (8 if match[2].startswith('byte') else 1)
        return str(value) + ' bit'
    return ' '.join(_BITS_BYTES.sub(bits, text).split())


def verify_mcq_options(question):
    if question.get('kind') != 'mcq':
        return
    options = [equivalent_quantity_text(x) for x in question['options']]
    if len(options) != len(set(options)):
        raise ValueError('Trắc nghiệm có lựa chọn tương đương sau đổi đơn vị bit/byte hoặc chuẩn hóa chữ; cần sửa để chỉ có một đáp án đúng.')
    verify_composition(question)
