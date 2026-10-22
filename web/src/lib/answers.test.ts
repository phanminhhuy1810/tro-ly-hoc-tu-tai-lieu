import { describe, expect, it } from 'vitest';
import type { Question } from '../api/types';
import { applyHint, draftFrom, emptyDraft, hintEffect, hintMessage, isMalformed, missingAnswer, moveItem, toAnswer } from './answers';

function question(kind: Question['kind'], options: string[], left: string[] = []): Question {
  return {
    id: 'unit-1:q0',
    unit_id: 'unit-1',
    kind,
    prompt: 'p',
    options,
    left,
    source_refs: [],
    question_revision_id: 'r',
    payload: {
      options: options.map((text, i) => ({ id: `option-${i}`, text })),
      left: left.map((text, i) => ({ id: `left-${i}`, text })),
    },
  };
}

describe('answer payloads match what the backend grades', () => {
  it('sends the option id for multiple choice', () => {
    expect(toAnswer({ kind: 'mcq', optionId: 'option-2' })).toBe('option-2');
  });

  it('sends a left-id → option-id map for matching', () => {
    expect(toAnswer({ kind: 'matching', pairs: { 'left-0': 'option-1', 'left-1': 'option-0' } })).toEqual({
      'left-0': 'option-1',
      'left-1': 'option-0',
    });
  });

  it('sends the full order of option ids for ordering and trims typed answers', () => {
    expect(toAnswer({ kind: 'ordering', order: ['option-2', 'option-0', 'option-1'] })).toEqual(['option-2', 'option-0', 'option-1']);
    expect(toAnswer({ kind: 'cloze', text: '  62 ' })).toBe('62');
  });
});

describe('missingAnswer explains what is left before checking', () => {
  it('asks for a choice or text', () => {
    const mcq = question('mcq', ['a', 'b']);
    expect(missingAnswer(mcq, emptyDraft(mcq))).toMatch(/Chọn một đáp án/);
    const cloze = question('cloze', []);
    expect(missingAnswer(cloze, { kind: 'cloze', text: '   ' })).toMatch(/Viết câu trả lời/);
  });

  it('requires every matching row and no reused answer', () => {
    const q = question('matching', ['x', 'y'], ['(2)', '(5)']);
    expect(missingAnswer(q, { kind: 'matching', pairs: { 'left-0': 'option-0' } })).toMatch(/Ghép đủ 2 mục/);
    expect(missingAnswer(q, { kind: 'matching', pairs: { 'left-0': 'option-0', 'left-1': 'option-0' } })).toMatch(/mỗi đáp án/);
    expect(missingAnswer(q, { kind: 'matching', pairs: { 'left-0': 'option-1', 'left-1': 'option-0' } })).toBeNull();
  });

  it('flags matching banks the backend cannot grade', () => {
    expect(isMalformed(question('matching', ['x', 'y', 'z'], ['(2)', '(5)']))).toBe(true);
    expect(isMalformed(question('matching', ['x', 'y'], ['(2)', '(5)']))).toBe(false);
  });
});

describe('draftFrom restores what the learner left behind', () => {
  it('accepts option ids and older option text for multiple choice', () => {
    const q = question('mcq', ['192.168.1.64', '192.168.1.65']);
    expect(draftFrom(q, 'option-1')).toEqual({ kind: 'mcq', optionId: 'option-1' });
    expect(draftFrom(q, '192.168.1.64')).toEqual({ kind: 'mcq', optionId: 'option-0' });
  });

  it('ignores an ordering that is not a full permutation', () => {
    const q = question('ordering', ['a', 'b', 'c']);
    expect(draftFrom(q, ['option-1'])).toEqual(emptyDraft(q));
  });
});

describe('hints change the question in place', () => {
  it('clears an eliminated multiple-choice selection', () => {
    const effect = hintEffect({ eliminated_option_ids: ['option-1'] });
    expect(applyHint({ kind: 'mcq', optionId: 'option-1' }, effect)).toEqual({ kind: 'mcq', optionId: null });
    expect(applyHint({ kind: 'mcq', optionId: 'option-0' }, effect)).toEqual({ kind: 'mcq', optionId: 'option-0' });
  });

  it('pins the revealed first steps of an ordering', () => {
    const effect = hintEffect({ ordered_option_ids: ['option-4', 'option-3'] });
    const draft = applyHint({ kind: 'ordering', order: ['option-0', 'option-3', 'option-4', 'option-1'] }, effect);
    expect(draft).toEqual({ kind: 'ordering', order: ['option-4', 'option-3', 'option-0', 'option-1'] });
  });

  it('fills revealed matching pairs and drops conflicting picks', () => {
    const effect = hintEffect({ pairs: { 'left-0': 'option-1' } });
    const draft = applyHint({ kind: 'matching', pairs: { 'left-0': 'option-0', 'left-1': 'option-1' } }, effect);
    expect(draft).toEqual({ kind: 'matching', pairs: { 'left-0': 'option-1' } });
  });
});

describe('hintMessage says what the hint changed', () => {
  it('names the revealed prefix for a fill-in question', () => {
    expect(hintMessage(hintEffect({ prefix: 'đị' }), 1)).toBe('Đáp án bắt đầu bằng “đị”.');
  });

  it('counts eliminated choices and numbers later hints', () => {
    expect(hintMessage(hintEffect({ eliminated_option_ids: ['option-1', 'option-2'] }), 2)).toBe('Gợi ý 2: Đã loại 2 lựa chọn chắc chắn sai.');
  });
});

describe('moveItem', () => {
  it('moves within bounds and ignores invalid moves', () => {
    expect(moveItem(['a', 'b', 'c'], 0, 2)).toEqual(['b', 'c', 'a']);
    expect(moveItem(['a', 'b'], 1, 5)).toEqual(['a', 'b']);
  });
});
