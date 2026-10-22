import type { Question, UnitData } from '../api/types';

// A lesson runs in two phases: learn (the tutor explains section by section
// and the learner asks until it makes sense), then practice (questions, with
// a chat beside them). Nothing here asks the backend for new content.

export type Phase = 'learn' | 'practice' | 'result';

/**
 * Practice order: a question follows the reading it relies on, i.e. it is
 * sorted by the LAST section sharing one of its source references; questions
 * that share none go last. Bank order is kept among equals. This is a
 * presentation heuristic over saved data, not a claim about authorship.
 */
export function practiceOrder(data: Pick<UnitData, 'sections'> | null, questions: Pick<Question, 'id' | 'source_refs'>[]): string[] {
  const placed = questions.map((question, bank) => {
    const refs = new Set(question.source_refs);
    let last = Number.POSITIVE_INFINITY;
    data?.sections.forEach((section, index) => {
      if (section.source_refs.some((ref) => refs.has(ref))) last = index;
    });
    return { id: question.id, last, bank };
  });
  return placed.sort((a, b) => a.last - b.last || a.bank - b.bank).map((q) => q.id);
}

export interface StartPoint {
  phase: Phase;
  /** How many sections are on screen in the learn chat (1…sections). */
  revealed: number;
  /** The recap and "start practising" prompt are shown after the last section. */
  recap: boolean;
  questionIndex: number;
}

/**
 * Where to reopen a lesson: unanswered practice first (the learner already
 * moved on), then the next unread section, then the recap.
 */
export function startPoint(sections: number, readUpTo: number, order: string[], answered: Set<string>): StartPoint {
  const unanswered = order.findIndex((id) => !answered.has(id));
  const anyAnswered = order.some((id) => answered.has(id));
  if (order.length && unanswered === -1) return { phase: 'result', revealed: Math.max(1, sections), recap: true, questionIndex: order.length - 1 };
  if (anyAnswered || sections === 0) return { phase: 'practice', revealed: Math.max(1, sections), recap: true, questionIndex: Math.max(0, unanswered) };
  const finished = readUpTo >= sections - 1;
  return {
    phase: 'learn',
    revealed: finished ? sections : Math.min(sections, Math.max(1, readUpTo + 2)),
    recap: finished,
    questionIndex: 0,
  };
}
