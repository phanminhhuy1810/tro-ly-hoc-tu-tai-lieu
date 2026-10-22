"""Repair PDF page text that lost its word gaps or carries Wingdings bullets.

Slides exported to PDF often place each word by position instead of writing a
space, so pypdf's plain mode returns "Địachỉlogic". Its layout mode keeps the
gaps but also reflows side-by-side boxes into one line, so it is used only as
a vocabulary: a plain token is split only when it is exactly a sequence of
words that the layout pass found on the same page.
"""
import re
import unicodedata

# A Vietnamese syllable has at most 7 letters ("nghiêng"), most have fewer; a
# token of 6+ letters with non-ASCII letters may be glued syllables ("Nộidung"). A real
# single syllable also appears whole in the layout pass, so it is never split.
GLUED_MIN = 6
# Office exports Wingdings bullets as these Latin-1 characters.
ALWAYS_BULLETS = '§▪'
SPACED_BULLETS = 'Øü¨Ÿ'


def nfc(text):
    return unicodedata.normalize('NFC', text)


def looks_glued(text):
    return any(len(token) >= GLUED_MIN and not token.isascii() for token in text.split())


def respace(plain, layout):
    vocabulary = set(nfc(layout).split())
    if not vocabulary:
        return plain
    longest = max(map(len, vocabulary))

    def split(token):
        if len(token) < GLUED_MIN or token.isascii() or token in vocabulary:
            return token
        best = [None] * (len(token) + 1)
        best[0] = ()
        for start in range(len(token)):
            if best[start] is None:
                continue
            for end in range(start + 1, min(len(token), start + longest) + 1):
                piece = token[start:end]
                if piece in vocabulary and (best[end] is None or len(best[start]) + 1 < len(best[end])):
                    best[end] = best[start] + (piece,)
        pieces = best[-1]
        return ' '.join(pieces) if pieces and len(pieces) > 1 else token

    return re.sub(r'\S+', lambda match: split(match.group()), nfc(plain))


def tidy_bullets(text):
    """Turn Wingdings bullets at the start of a line into "• "; keep "§ 5"-style references."""
    lines = []
    for line in text.split('\n'):
        body = line.lstrip()
        indent = line[:len(line) - len(body)]
        head, rest = body[:1], body[1:].lstrip()
        if (head in ALWAYS_BULLETS or head == '•') and rest[:1].isalpha():
            body = '• ' + rest
        elif head and head in SPACED_BULLETS and body[1:2].isspace() and rest[:1].isalpha():
            body = '• ' + rest
        elif head == 'q' and rest[:1].isupper() and (body[1:2].isspace() or body[1:2].isupper()):
            body = '• ' + rest
        lines.append(indent + body)
    return '\n'.join(lines)


def repair_page_text(plain, layout_reader):
    """Plain text with word gaps restored from the layout pass when they look lost."""
    text = plain
    if looks_glued(plain):
        try:
            text = respace(plain, layout_reader() or '')
        except Exception:  # The layout pass is only a repair; keep the plain reading.
            text = plain
    return tidy_bullets(text)
