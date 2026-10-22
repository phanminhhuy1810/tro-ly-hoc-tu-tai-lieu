import type { StudyCard } from '../../api/types';

export type DeckFilter = 'due' | 'all';
export type CardMemory = { remembered: boolean | null; version: number };

/** What the learner said about a card: this round's answer first, then the saved one. */
export function memoryOf(card: StudyCard, local: Record<string, CardMemory>): CardMemory {
  return local[card.id] ?? { remembered: card.memory?.remembered ?? null, version: card.memory?.version ?? 0 };
}

/**
 * Review order: cards marked "chưa nhớ" first, then never reviewed, then
 * remembered (only when showing all). Lesson order is kept within each group.
 * No spaced-repetition schedule: that algorithm is not part of the chosen scope.
 */
export function deckOrder(cards: StudyCard[], filter: DeckFilter): StudyCard[] {
  const rank = (card: StudyCard) => (card.memory?.remembered === false ? 0 : card.memory?.remembered == null ? 1 : 2);
  const list = filter === 'due' ? cards.filter((card) => card.memory?.remembered !== true) : cards;
  return list
    .map((card, index) => ({ card, index }))
    .sort((a, b) => rank(a.card) - rank(b.card) || a.index - b.index)
    .map(({ card }) => card);
}
