import { describe, expect, it } from 'vitest';
import type { Question, QuestionKind, Unit, UnitData } from '../api/types';
import { availableCount, defaultCount, kindsIn, practiceUnits } from './practice';

const q = (kind: QuestionKind) => ({ kind }) as Question;
const unit = (id: string, kinds: QuestionKind[], extra: Partial<Unit> = {}): Unit => ({
  id,
  title: id,
  source_refs: [],
  unlocked: true,
  data: { title: id, sections: [], cards: [], mindmap: [], questions: kinds.map(q) } as UnitData,
  ...extra,
});

const units = [unit('u1', ['mcq', 'cloze']), unit('u2', ['mcq', 'ordering', 'mcq']), unit('u3', ['mcq'], { unlocked: false }), unit('u4', [], { data: null })];

describe('practice scope', () => {
  it('only offers open, generated units with questions', () => {
    expect(practiceUnits(units).map((u) => u.id)).toEqual(['u1', 'u2']);
  });

  it('lists the kinds present and counts matching questions', () => {
    expect(kindsIn(units, ['u1', 'u2'])).toEqual(['mcq', 'cloze', 'ordering']);
    expect(availableCount(units, ['u1', 'u2'], ['mcq'])).toBe(3);
    expect(availableCount(units, ['u2'], ['mcq', 'ordering'])).toBe(3);
  });

  it('defaults to about ten questions but never more than available', () => {
    expect(defaultCount(25)).toBe(10);
    expect(defaultCount(4)).toBe(4);
    expect(defaultCount(0)).toBe(1);
  });
});
