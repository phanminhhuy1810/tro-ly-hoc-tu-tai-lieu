import type { AnswerValue, HelpReply, Question } from '../api/types';

export type Draft =
  | { kind: 'mcq'; optionId: string | null }
  | { kind: 'cloze'; text: string }
  | { kind: 'short_answer'; text: string }
  | { kind: 'matching'; pairs: Record<string, string> }
  | { kind: 'ordering'; order: string[] };

export function emptyDraft(question: Question): Draft {
  switch (question.kind) {
    case 'mcq':
      return { kind: 'mcq', optionId: null };
    case 'cloze':
      return { kind: 'cloze', text: '' };
    case 'short_answer':
      return { kind: 'short_answer', text: '' };
    case 'matching':
      return { kind: 'matching', pairs: {} };
    case 'ordering':
      return { kind: 'ordering', order: question.payload.options.map((o) => o.id) };
  }
}

/** Restore a draft from a saved session draft/answer (IDs as the backend stores them). */
export function draftFrom(question: Question, value: AnswerValue | null | undefined): Draft {
  const draft = emptyDraft(question);
  if (value == null) return draft;
  const optionIds = new Set(question.payload.options.map((o) => o.id));
  switch (draft.kind) {
    case 'mcq': {
      if (typeof value !== 'string') return draft;
      if (optionIds.has(value)) return { kind: 'mcq', optionId: value };
      // Older attempts stored option text.
      const byText = question.payload.options.find((o) => o.text === value);
      return { kind: 'mcq', optionId: byText?.id ?? null };
    }
    case 'cloze':
    case 'short_answer':
      return typeof value === 'string' ? { ...draft, text: value } : draft;
    case 'matching':
      return value && typeof value === 'object' && !Array.isArray(value) ? { kind: 'matching', pairs: { ...value } } : draft;
    case 'ordering':
      return Array.isArray(value) && value.every((id) => optionIds.has(id)) && value.length === optionIds.size
        ? { kind: 'ordering', order: [...value] }
        : draft;
  }
}

export function toAnswer(draft: Draft): AnswerValue {
  switch (draft.kind) {
    case 'mcq':
      return draft.optionId ?? '';
    case 'cloze':
    case 'short_answer':
      return draft.text.trim();
    case 'matching':
      return { ...draft.pairs };
    case 'ordering':
      return [...draft.order];
  }
}

/** Message shown next to the check button when the answer is not ready; null when it can be sent. */
export function missingAnswer(question: Question, draft: Draft): string | null {
  switch (draft.kind) {
    case 'mcq':
      return draft.optionId ? null : 'Chọn một đáp án trước nhé.';
    case 'cloze':
    case 'short_answer':
      return draft.text.trim() ? null : 'Viết câu trả lời của bạn trước nhé.';
    case 'matching': {
      const left = question.payload.left;
      const used = Object.values(draft.pairs);
      const complete = left.every((item) => draft.pairs[item.id]) && new Set(used).size === used.length;
      return complete ? null : `Ghép đủ ${left.length} mục, mỗi đáp án dùng một lần.`;
    }
    case 'ordering':
      return null;
  }
}

/** True when the bank item cannot be answered as stored (e.g. matching sides of different length). */
export function isMalformed(question: Question): boolean {
  if (question.kind === 'matching') return question.payload.left.length !== question.payload.options.length || question.payload.left.length === 0;
  if (question.kind === 'mcq' || question.kind === 'ordering') return question.payload.options.length < 2;
  return false;
}

export function moveItem(order: string[], from: number, to: number): string[] {
  if (from === to || from < 0 || to < 0 || from >= order.length || to >= order.length) return order;
  const next = [...order];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

/** In-place hint effects (Gizmo-style): narrow the question instead of opening a text panel. */
export interface HintEffect {
  eliminated: Set<string>;
  lockedPrefix: string[];
  pairs: Record<string, string>;
  textPrefix: string;
  criteria: string[];
}

export function noHint(): HintEffect {
  return { eliminated: new Set(), lockedPrefix: [], pairs: {}, textPrefix: '', criteria: [] };
}

export function hintEffect(reply: HelpReply | undefined): HintEffect {
  const effect = noHint();
  if (!reply) return effect;
  effect.eliminated = new Set(reply.eliminated_option_ids ?? []);
  effect.lockedPrefix = reply.ordered_option_ids ?? [];
  effect.pairs = reply.pairs ?? {};
  effect.textPrefix = reply.prefix ?? '';
  effect.criteria = reply.criteria ?? [];
  return effect;
}

/** Short learner wording for what a hint just did to the question. */
export function hintMessage(effect: HintEffect, step: number | undefined): string {
  const prefix = step && step > 1 ? `Gợi ý ${step}: ` : '';
  if (effect.textPrefix) return `${prefix}Đáp án bắt đầu bằng “${effect.textPrefix}”.`;
  if (effect.eliminated.size) return `${prefix}Đã loại ${effect.eliminated.size} lựa chọn chắc chắn sai.`;
  if (effect.lockedPrefix.length) return `${prefix}Đã xếp sẵn ${effect.lockedPrefix.length} bước đầu tiên.`;
  const pairs = Object.keys(effect.pairs).length;
  if (pairs) return `${prefix}Đã ghép sẵn ${pairs} cặp.`;
  if (effect.criteria.length) return `${prefix}Câu trả lời tốt nên có các ý bên dưới.`;
  return `${prefix}Thử đọc lại phần vừa học trước khi trả lời.`;
}

/** Apply a hint to the draft so the learner sees it on the question itself. */
export function applyHint(draft: Draft, effect: HintEffect): Draft {
  if (draft.kind === 'mcq' && draft.optionId && effect.eliminated.has(draft.optionId)) return { ...draft, optionId: null };
  if (draft.kind === 'ordering' && effect.lockedPrefix.length) {
    const rest = draft.order.filter((id) => !effect.lockedPrefix.includes(id));
    return { kind: 'ordering', order: [...effect.lockedPrefix, ...rest] };
  }
  if (draft.kind === 'matching' && Object.keys(effect.pairs).length) {
    const lockedTargets = new Set(Object.values(effect.pairs));
    const kept = Object.fromEntries(
      Object.entries(draft.pairs).filter(([left, option]) => !(left in effect.pairs) && !lockedTargets.has(option)),
    );
    return { kind: 'matching', pairs: { ...kept, ...effect.pairs } };
  }
  return draft;
}
