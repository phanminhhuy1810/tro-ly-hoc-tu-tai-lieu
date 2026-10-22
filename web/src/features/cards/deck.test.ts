import { describe, expect, it } from 'vitest';
import type { StudyCard } from '../../api/types';
import { deckOrder, memoryOf } from './deck';

const card = (id: string, remembered: boolean | null): StudyCard => ({ id, front: id, back: '', kind: 'generated', version: 1, memory: { remembered, version: remembered === null ? 0 : 1 } });
const cards = [card('a', true), card('b', null), card('c', false), card('d', null)];

describe('deckOrder', () => {
  it('reviews "chưa nhớ" cards first, then new ones, and hides remembered cards when due only', () => {
    expect(deckOrder(cards, 'due').map((c) => c.id)).toEqual(['c', 'b', 'd']);
    expect(deckOrder(cards, 'all').map((c) => c.id)).toEqual(['c', 'b', 'd', 'a']);
  });
});

describe('memoryOf', () => {
  it('prefers what the learner marked in this round over the saved state', () => {
    expect(memoryOf(cards[1], {})).toEqual({ remembered: null, version: 0 });
    expect(memoryOf(cards[1], { b: { remembered: true, version: 1 } })).toEqual({ remembered: true, version: 1 });
  });
});
