"""Exact, bounded checks for explicitly written polynomial compositions.

This is not a symbolic-math engine or a semantic grader. Unsupported notation,
domains, functions and question wording are left for review, never guessed.
Only a small polynomial grammar is parsed; model text is never executed.
"""
import ast
from fractions import Fraction
import re

MAX_DEGREE = 16
MAX_POWER = 12
TOKEN = re.compile(r'\d+(?:\.\d+)?|[A-Za-z]|\*\*|[+*/^()\-]')
ASSIGNMENT = re.compile(r'\b([fgh])\(\s*([xu])\s*\)\s*=\s*')


class Unsupported(ValueError):
    pass


class CompositionError(ValueError):
    def __init__(self, code, message, proof):
        super().__init__(message)
        self.code, self.proof = code, proof


def bounded(coefficients):
    values = list(coefficients)
    while len(values) > 1 and not values[-1]: values.pop()
    if len(values) > MAX_DEGREE + 1 or any(max(v.numerator.bit_length(), v.denominator.bit_length()) > 512 for v in values):
        raise Unsupported()
    return tuple(values)


def add(left, right):
    return bounded([(left[i] if i < len(left) else Fraction(0)) + (right[i] if i < len(right) else Fraction(0))
                    for i in range(max(len(left), len(right)))])


def multiply(left, right):
    if len(left) + len(right) - 2 > MAX_DEGREE: raise Unsupported()
    result = [Fraction(0)] * (len(left) + len(right) - 1)
    for i, a in enumerate(left):
        for j, b in enumerate(right): result[i+j] += a*b
    return bounded(result)


def polynomial(text, variable):
    if len(text) > 300: raise Unsupported()
    text = text.replace('−', '-').replace('×', '*').replace('²', '^2').replace('³', '^3')
    raw, position = [], 0
    for match in TOKEN.finditer(text):
        if text[position:match.start()].strip(): raise Unsupported()
        value = match[0]
        if value[0].isalpha():
            if value != variable: raise Unsupported()
            raw.append(('var', variable))
        elif value[0].isdigit():
            if len(value) > 20: raise Unsupported()
            number = Fraction(value)
            raw.append(('number', str(number.numerator) if number.denominator == 1 else f'({number.numerator}/{number.denominator})'))
        else: raw.append((value, '**' if value == '^' else value))
        position = match.end()
    if text[position:].strip() or not 0 < len(raw) <= 150: raise Unsupported()
    expression = []
    for i, (kind, value) in enumerate(raw):
        if i:
            previous = raw[i-1][0]
            if previous in {'number', 'var', ')'} and kind in {'number', 'var', '('}:
                if previous == kind == 'number': raise Unsupported()
                expression.append('*')
        expression.append(value)
    try: tree = ast.parse(''.join(expression), mode='eval')
    except (SyntaxError, RecursionError): raise Unsupported() from None

    def read(node):
        if isinstance(node, ast.Constant) and type(node.value) is int:
            return bounded([Fraction(node.value)])
        if isinstance(node, ast.Name) and node.id == variable:
            return (Fraction(0), Fraction(1))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = read(node.operand)
            return value if isinstance(node.op, ast.UAdd) else tuple(-v for v in value)
        if not isinstance(node, ast.BinOp): raise Unsupported()
        left, right = read(node.left), read(node.right)
        if isinstance(node.op, ast.Add): return add(left, right)
        if isinstance(node.op, ast.Sub): return add(left, tuple(-v for v in right))
        if isinstance(node.op, ast.Mult): return multiply(left, right)
        if isinstance(node.op, ast.Div) and len(right) == 1 and right[0]:
            return bounded([v/right[0] for v in left])
        if isinstance(node.op, ast.Pow) and len(right) == 1 and right[0].denominator == 1 and 1 <= right[0] <= MAX_POWER:
            result = (Fraction(1),)
            for _ in range(int(right[0])): result = multiply(result, left)
            return result
        raise Unsupported()
    try: return read(tree.body)
    except (RecursionError, OverflowError): raise Unsupported() from None


def definitions(text, strict_labels=False):
    result, spans = {}, []
    for match in ASSIGNMENT.finditer(text):
        name, variable = match[1].casefold(), match[2].casefold()
        if name in result: raise Unsupported()
        # The notation ends at math delimiters, punctuation, or prose. A
        # partial/unknown expression is never evaluated as an intended formula.
        tail = text[match.end():]
        value = re.match(r'[0-9xuXU+*/^().\s−×²³\-]+', tail)
        if not value: raise Unsupported()
        expression = value[0].rstrip().rstrip('.')
        end = tail[len(value[0]):]
        if re.match(r',\s*\d', end): raise Unsupported()
        if end and end[0] not in '$,;:?!。' and not value[0][-1].isspace():
            raise Unsupported()
        result[name] = (variable, polynomial(expression, variable))
        spans.append((match.start(), match.end()+len(value[0])))
    if strict_labels:
        rest, start = [], 0
        for a, b in spans:
            rest.append(text[start:a]); start = b
        rest.append(text[start:])
        labels = re.sub(r'\b(?:hàm|trong|ngoài|là|và|inner|outer|function|is|and)\b', '', ''.join(rest).casefold())
        if re.sub(r'[\s$,;:.()]', '', labels): raise Unsupported()
    return result


def compose(outer, inner):
    result = (Fraction(0),)
    for coefficient in reversed(outer): result = add(multiply(result, inner), (coefficient,))
    return result


def composition_proof(question):
    prompt = question.get('prompt', '')
    lower = prompt.casefold()
    if (question.get('kind') != 'mcq' or not any(term in lower for term in ('hàm trong', 'inner function'))
            or not any(term in lower for term in ('hàm ngoài', 'outer function'))
            or re.search(r'\b(?:sai|không|incorrect|invalid|not)\b', lower)):
        return None
    try:
        target = definitions(prompt)
        # If f/g are specified in the stem, it asks about that particular
        # decomposition, not whether another factorization also produces h.
        if set(target) != {'h'} or target['h'][0] != 'x': return None
        correct = []
        for index, option in enumerate(question['options']):
            pair = definitions(option, strict_labels=True)
            if set(pair) != {'f', 'g'} or pair['f'][0] != 'u' or pair['g'][0] != 'x': return None
            if compose(pair['f'][1], pair['g'][1]) == target['h'][1]: correct.append(index)
        return {'method': 'bounded_exact_polynomial_composition_v1', 'valid_option_indices': correct,
                'target_degree': len(target['h'][1])-1}
    except (Unsupported, ValueError, KeyError, TypeError, ZeroDivisionError):
        return None


def verify_composition(question):
    proof = composition_proof(question)
    if proof is None: return
    valid = proof['valid_option_indices']
    if len(valid) != 1:
        raise CompositionError('MCQ_COMPOSITION_NOT_UNIQUE',
            'Phép hợp đa thức cho thấy câu này không có đúng một lựa chọn đúng. Giữ ứng viên để đối chiếu; không tự đổi key hoặc gọi lại.', proof)
    if question.get('answer') != question['options'][valid[0]]:
        raise CompositionError('MCQ_COMPOSITION_KEY_CONFLICT',
            'Đáp án AI chọn không khớp phép hợp đa thức tính được từ chính dữ kiện câu. Chưa dùng ứng viên, không sửa key thay AI.', proof)
