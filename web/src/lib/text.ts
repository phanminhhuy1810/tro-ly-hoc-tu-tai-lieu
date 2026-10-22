// Lessons made before the PDF reader was fixed can still show slide text with
// Wingdings bullets ("§", "q") and Vietnamese words glued together
// ("Địachỉlogic"). These helpers only change what is displayed: answers are
// sent by id or exactly as typed, so grading is unaffected.

const LETTER_RUN = /[\p{L}\p{N}]{6,}/gu;
const EDGE = /^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu;

/** Lower-case words from well-formed lesson text (sections, ideas, cards). */
export function vocabularyFrom(texts: Iterable<string>): Set<string> {
  const words = new Set<string>();
  for (const text of texts) {
    for (const raw of text.normalize('NFC').split(/\s+/)) {
      const word = raw.replace(EDGE, '').toLowerCase();
      if (word) words.add(word);
    }
  }
  return words;
}

function segment(token: string, vocabulary: Set<string>, minPiece = 1): string[] | null {
  const best: (string[] | null)[] = Array(token.length + 1).fill(null);
  best[0] = [];
  for (let start = 0; start < token.length; start += 1) {
    const before = best[start];
    if (!before) continue;
    for (let end = start + minPiece; end <= token.length && end - start <= 16; end += 1) {
      const piece = token.slice(start, end);
      if (piece === token) continue;
      if (!vocabulary.has(piece) && !/^\d+$/.test(piece)) continue;
      const current = best[end];
      if (!current || before.length + 1 < current.length) best[end] = [...before, piece];
    }
  }
  return best[token.length];
}

/** Split glued words, but only into words that appear elsewhere in the same lesson. */
export function respace(text: string, vocabulary: Set<string>): string {
  if (!vocabulary.size) return text;
  return text.normalize('NFC').replace(LETTER_RUN, (token) => {
    // Vietnamese syllables are short; long ASCII words (English terms) are never touched.
    if (!/[^\x00-\x7f]/.test(token)) return token;
    const lower = token.toLowerCase();
    if (lower.length !== token.length) return token;
    // Text that quotes the slide (a saved answer, say) puts the glued run itself in the
    // vocabulary; then only split it into known words of two letters or more.
    const pieces = segment(lower, vocabulary, vocabulary.has(lower) ? 2 : 1);
    if (!pieces || pieces.length < 2) return token;
    let at = 0;
    return pieces
      .map((piece) => {
        const original = token.slice(at, at + piece.length);
        at += piece.length;
        return original;
      })
      .join(' ');
  });
}

/** "§Địa chỉ" / "qPhân loại" / "•do" → "• Địa chỉ"…; a bullet right after an opening quote is dropped. */
export function tidyBullets(text: string): string {
  return text
    .split('\n')
    .map((line) =>
      line
        .replace(/^([“"(])\s*(?:[§▪•]|q(?=\p{Lu}))\s*/u, '$1')
        .replace(/^(\s*)(?:[§▪]|q(?=\s?\p{Lu}))\s*(?=\p{L})/u, '$1• ')
        .replace(/(^|\s)[§▪](?=\s?\p{L})\s*/gu, '$1• ')
        .replace(/•(?=[\p{L}\p{N}])/gu, '• '),
    )
    .join('\n');
}

export function makeTextFix(texts: Iterable<string>): (text: string) => string {
  const vocabulary = vocabularyFrom(texts);
  return (text) => tidyBullets(respace(text, vocabulary));
}

/**
 * Requests label source excerpts R1, R2… so the model can cite them in
 * source_refs. Some local models still write "[R1]" into the answer; that
 * label means nothing to a learner, so AI-written text drops it on display.
 */
export function stripRefLabels(text: string): string {
  return (
    text
      .replace(/[ \t]?\[R\d+(?:\s*[,;]\s*R\d+)*\]/g, '')
      // Unbracketed labels only after a word that names a source (“theo tài liệu R1”), so a router called R1 stays.
      .replace(/(tài liệu|nguồn|trích đoạn|đoạn trích|đoạn)\s+R\d+(?:\s*(?:,|;|\/|và)\s*R\d+)*/giu, '$1')
  );
}

/** Search key without accents or case: “Địa chỉ” and “dia chi” match. */
export function fold(text: string): string {
  return text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/đ/g, 'd');
}
