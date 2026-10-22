import { Fragment } from 'react';
import type { GradeResult, Question } from '../../api/types';
import { Icon } from '../../components/Icon';
import { moveItem, type Draft, type HintEffect } from '../../lib/answers';
import { useTextFix } from './textFix';

const KIND_LABEL: Record<Question['kind'], string> = {
  mcq: 'Chọn một đáp án',
  cloze: 'Điền vào chỗ trống',
  matching: 'Ghép cặp',
  ordering: 'Sắp xếp theo thứ tự',
  short_answer: 'Trả lời ngắn',
};

export function kindLabel(kind: Question['kind']) {
  return KIND_LABEL[kind];
}

/** Map the grader's reference (option text or index list) back to option ids. */
function correctOptionIds(question: Question, result: GradeResult | undefined): string[] {
  if (!result) return [];
  const ref = result.reference;
  if (Array.isArray(ref)) return ref.map((i) => `option-${i}`);
  const hit = question.payload.options.find((o) => o.text === ref);
  return hit ? [hit.id] : [];
}

function Mcq({ question, draft, onChange, effect, result, locked }: ViewProps & { draft: Extract<Draft, { kind: 'mcq' }> }) {
  const fix = useTextFix();
  const correct = correctOptionIds(question, result);
  return (
    <div className="options" role="radiogroup" aria-label={question.prompt}>
      {question.payload.options.map((option, i) => {
        const chosen = draft.optionId === option.id;
        const eliminated = effect.eliminated.has(option.id);
        const isCorrect = correct.includes(option.id);
        let state = '';
        if (result) state = isCorrect ? 'is-correct' : chosen ? 'is-wrong' : 'is-muted';
        else if (eliminated) state = 'is-eliminated';
        else if (chosen) state = 'is-chosen';
        return (
          <button
            key={option.id}
            type="button"
            role="radio"
            aria-checked={chosen}
            disabled={locked || eliminated}
            className={`option ${state}`}
            onClick={() => onChange({ kind: 'mcq', optionId: option.id })}
          >
            <span className="option__key" aria-hidden="true">
              {result && isCorrect ? <Icon name="check" size={16} /> : result && chosen ? <Icon name="x" size={16} /> : String.fromCharCode(65 + i)}
            </span>
            <span className="option__text">{fix(option.text)}</span>
            {eliminated && !result && <span className="tag">đã loại</span>}
          </button>
        );
      })}
    </div>
  );
}

function Cloze({ question, draft, onChange, effect, result, locked }: ViewProps & { draft: Extract<Draft, { kind: 'cloze' }> }) {
  const fix = useTextFix();
  const prompt = fix(question.prompt);
  const [before, after] = prompt.includes('____') ? prompt.split(/_{3,}/, 2) : [prompt, ''];
  const input = (
    <input
      className={`field cloze-input ${result ? (result.correct ? 'is-correct' : 'is-wrong') : ''}`}
      value={draft.text}
      disabled={locked}
      placeholder={effect.textPrefix ? `Bắt đầu bằng “${effect.textPrefix}”` : 'Câu trả lời'}
      aria-label="Phần còn thiếu"
      onChange={(event) => onChange({ kind: 'cloze', text: event.target.value })}
    />
  );
  return (
    <p className="cloze body-l">
      {before}
      {input}
      {after}
    </p>
  );
}

function ShortAnswer({ draft, onChange, effect, locked }: ViewProps & { draft: Extract<Draft, { kind: 'short_answer' }> }) {
  return (
    <div style={{ display: 'grid', gap: 10 }}>
      <textarea
        className="field"
        rows={4}
        value={draft.text}
        disabled={locked}
        placeholder="Viết câu trả lời bằng lời của bạn…"
        aria-label="Câu trả lời của bạn"
        onChange={(event) => onChange({ kind: 'short_answer', text: event.target.value })}
      />
      {effect.criteria.length > 0 && (
        <ul className="criteria">
          {effect.criteria.map((item) => (
            <li key={item}>
              <Icon name="bulb" size={16} /> {item}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Matching({ question, draft, onChange, effect, result, locked }: ViewProps & { draft: Extract<Draft, { kind: 'matching' }> }) {
  const fix = useTextFix();
  const reference = result && Array.isArray(result.reference) ? result.reference : null;
  const used = new Map(Object.entries(draft.pairs).map(([left, option]) => [option, left]));
  return (
    <div className="matching">
      {question.payload.left.map((left, i) => {
        const value = draft.pairs[left.id] ?? '';
        const pinned = left.id in effect.pairs;
        const expected = reference ? `option-${reference[i]}` : null;
        const state = reference ? (value === expected ? 'is-correct' : 'is-wrong') : '';
        return (
          <Fragment key={left.id}>
            <span className="matching__left">{fix(left.text)}</span>
            <Icon name="arrowRight" size={18} className="matching__arrow" />
            <div className={`matching__pick ${state}`}>
              <select
                className="field"
                value={value}
                disabled={locked || pinned}
                aria-label={`Ghép với ${left.text}`}
                onChange={(event) => {
                  const option = event.target.value;
                  const pairs = { ...draft.pairs };
                  const other = used.get(option);
                  if (other && other !== left.id) delete pairs[other];
                  if (option) pairs[left.id] = option;
                  else delete pairs[left.id];
                  onChange({ kind: 'matching', pairs });
                }}
              >
                <option value="">Chọn…</option>
                {question.payload.options.map((option) => (
                  <option key={option.id} value={option.id}>
                    {fix(option.text)}
                    {used.has(option.id) && used.get(option.id) !== left.id ? ' (đang dùng)' : ''}
                  </option>
                ))}
              </select>
              {reference && value !== expected && (
                <span className="meta">Đúng: {fix(question.payload.options.find((o) => o.id === expected)?.text ?? '')}</span>
              )}
            </div>
          </Fragment>
        );
      })}
    </div>
  );
}

function Ordering({ question, draft, onChange, effect, result, locked }: ViewProps & { draft: Extract<Draft, { kind: 'ordering' }> }) {
  const fix = useTextFix();
  const reference = result && Array.isArray(result.reference) ? result.reference.map((i) => `option-${i}`) : null;
  const text = (id: string) => fix(question.payload.options.find((o) => o.id === id)?.text ?? id);
  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <ol className="ordering">
        {draft.order.map((id, i) => {
          const pinned = effect.lockedPrefix.includes(id);
          const state = reference ? (reference[i] === id ? 'is-correct' : 'is-wrong') : pinned ? 'is-pinned' : '';
          return (
            <li key={id} className={`ordering__item ${state}`}>
              <span className="ordering__num">{i + 1}</span>
              <span className="ordering__text">{text(id)}</span>
              {!result && !locked && !pinned && (
                <span className="ordering__moves">
                  <button
                    type="button"
                    className="icon-btn"
                    aria-label={`Đưa “${text(id)}” lên`}
                    disabled={i === 0 || effect.lockedPrefix.includes(draft.order[i - 1])}
                    onClick={() => onChange({ kind: 'ordering', order: moveItem(draft.order, i, i - 1) })}
                  >
                    <Icon name="up" size={18} />
                  </button>
                  <button
                    type="button"
                    className="icon-btn"
                    aria-label={`Đưa “${text(id)}” xuống`}
                    disabled={i === draft.order.length - 1}
                    onClick={() => onChange({ kind: 'ordering', order: moveItem(draft.order, i, i + 1) })}
                  >
                    <Icon name="down" size={18} />
                  </button>
                </span>
              )}
              {pinned && !result && <span className="tag tag--sage">gợi ý</span>}
            </li>
          );
        })}
      </ol>
      {reference && reference.join() !== draft.order.join() && (
        <div className="meta">
          Thứ tự đúng: {reference.map((id, i) => `${i + 1}. ${text(id)}`).join('  ·  ')}
        </div>
      )}
    </div>
  );
}

interface ViewProps {
  question: Question;
  onChange: (draft: Draft) => void;
  effect: HintEffect;
  result?: GradeResult;
  locked?: boolean;
}

export function QuestionView(props: ViewProps & { draft: Draft }) {
  const { draft } = props;
  switch (draft.kind) {
    case 'mcq':
      return <Mcq {...props} draft={draft} />;
    case 'cloze':
      return <Cloze {...props} draft={draft} />;
    case 'short_answer':
      return <ShortAnswer {...props} draft={draft} />;
    case 'matching':
      return <Matching {...props} draft={draft} />;
    case 'ordering':
      return <Ordering {...props} draft={draft} />;
  }
}
