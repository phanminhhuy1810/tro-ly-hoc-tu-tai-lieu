import type { QuestionKind, Unit } from '../api/types';

export const ALL_KINDS: QuestionKind[] = ['mcq', 'cloze', 'matching', 'ordering', 'short_answer'];

/** Units a practice round can draw from: open and already generated. */
export function practiceUnits(units: Unit[]): Unit[] {
  return units.filter((unit) => unit.unlocked !== false && unit.data && unit.data.questions.length > 0);
}

/** Question kinds present in the chosen units, in the usual order. */
export function kindsIn(units: Unit[], unitIds: string[]): QuestionKind[] {
  const chosen = new Set(unitIds);
  const present = new Set(units.filter((u) => chosen.has(u.id)).flatMap((u) => u.data?.questions.map((q) => q.kind) ?? []));
  return ALL_KINDS.filter((kind) => present.has(kind));
}

/** How many saved questions match the scope (the server may still hold back ones flagged for review). */
export function availableCount(units: Unit[], unitIds: string[], kinds: QuestionKind[]): number {
  const chosen = new Set(unitIds);
  const allowed = new Set(kinds);
  return units.filter((u) => chosen.has(u.id)).reduce((n, u) => n + (u.data?.questions.filter((q) => allowed.has(q.kind)).length ?? 0), 0);
}

/** A round of about ten questions by default; never more than the bank holds. */
export function defaultCount(available: number): number {
  return Math.max(1, Math.min(10, available));
}
