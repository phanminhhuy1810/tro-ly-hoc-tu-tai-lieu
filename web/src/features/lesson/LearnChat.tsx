import { Fragment, useEffect, useRef, useState, type ReactNode } from 'react';
import { api } from '../../api/client';
import type { Course, HelpMessage, Section, SourceFragment, Unit } from '../../api/types';
import { useApp } from '../../app/store';
import { CoinConfirm } from '../../components/CoinConfirm';
import { Icon } from '../../components/Icon';
import { Mascot, type Mood } from '../../components/Mascot';
import { Mindmap } from '../../components/Mindmap';
import { RichText } from '../../components/RichText';
import { ProblemNotice } from '../../components/StateViews';
import { describeError, formatElapsed, locatorLabel } from '../../lib/copy';
import { stripRefLabels } from '../../lib/text';
import { threadFor } from './help';
import { useTextFix } from './textFix';
import { useSectionChat, type Pending, type TutorAction } from './useSectionChat';

const ACTION_LABEL: Record<string, string> = {
  explain: 'Giải thích kỹ hơn giúp mình',
  simpler: 'Giải thích dễ hiểu hơn giúp mình',
  detail: 'Nói chi tiết hơn giúp mình',
};
const EXAMPLE = 'Cho mình một ví dụ cụ thể, dễ hình dung cho phần này.';

export function paragraphs(text: string) {
  return text
    .split(/\n{1,}/)
    .map((p) => p.trim())
    .filter(Boolean);
}

function TutorMessage({ mood = 'hello', wide, children }: { mood?: Mood; wide?: boolean; children: ReactNode }) {
  return (
    <div className={`msg msg--tutor${wide ? ' msg--wide' : ''}`}>
      <span className="msg__avatar" aria-hidden="true">
        <Mascot mood={mood} size={44} face />
      </span>
      <div className="msg__body">{children}</div>
    </div>
  );
}

function LearnerMessage({ children }: { children: ReactNode }) {
  return (
    <div className="msg msg--me">
      <div className="msg__body">{children}</div>
    </div>
  );
}

function Typing({ pending }: { pending: Pending }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);
  const elapsed = now - pending.since;
  return (
    <TutorMessage mood="think">
      <p className="typing" role="status">
        <span className="typing__dots" aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
        {pending.action === 'explain' ? 'Đang đọc lại nguồn để giải thích' : 'Đang soạn câu trả lời'}
        {elapsed > 4000 ? ` · ${formatElapsed(elapsed)}` : '…'}
      </p>
    </TutorMessage>
  );
}

function SectionCard({
  section,
  index,
  total,
  fragments,
  onAsk,
}: {
  section: Section;
  index: number;
  total: number;
  fragments: Map<string, SourceFragment>;
  onAsk: () => void;
}) {
  const fix = useTextFix();
  const [openRef, setOpenRef] = useState<string | null>(null);
  const opened = openRef ? fragments.get(openRef) : null;
  return (
    <TutorMessage mood={index === 0 ? 'hello' : 'hint'} wide>
      <article className="lesson-section" aria-label={`Phần ${index + 1}: ${section.title}`}>
        <p className="eyebrow">
          Phần {index + 1}/{total}
        </p>
        <h2 className="lesson-section__title">{fix(section.title)}</h2>
        <div className="lesson-section__text">
          {paragraphs(section.text).map((p, i) => (
            <p key={i} className="body-l">
              {fix(p)}
            </p>
          ))}
        </div>
        <footer className="lesson-section__foot">
          <div className="sources" aria-label="Nguồn của phần này">
            <Icon name="file" size={16} />
            {section.source_refs.map((ref) => (
              <button key={ref} type="button" className="source-chip" aria-expanded={openRef === ref} onClick={() => setOpenRef(openRef === ref ? null : ref)}>
                {locatorLabel(fragments.get(ref)?.locator)}
              </button>
            ))}
          </div>
          <button type="button" className="link link--quiet" onClick={onAsk}>
            <Icon name="message" size={15} /> Hỏi về phần này
          </button>
        </footer>
        {opened && (
          <blockquote className="source-quote enter">
            <span className="tag">{locatorLabel(opened.locator)}</span> {fix(opened.text)}
          </blockquote>
        )}
      </article>
    </TutorMessage>
  );
}

function Thread({ messages, onSave }: { messages: HelpMessage[]; onSave: (id: string) => void }) {
  const fix = useTextFix();
  return (
    <>
      {messages.map((message) =>
        message.role === 'user' ? (
          <LearnerMessage key={message.id}>
            {message.action === 'ask' ? <p>{message.content.text}</p> : <p className="msg__action">{ACTION_LABEL[message.action] ?? message.action}</p>}
          </LearnerMessage>
        ) : (
          <TutorMessage key={message.id} mood="hint">
            {message.content.text && <RichText text={stripRefLabels(message.content.text)} fix={fix} />}
            {message.content.needs_more_source && <p className="meta">Nguồn của phần này chưa đủ để trả lời chắc chắn — đối chiếu tài liệu gốc nhé.</p>}
            <div className="msg__tools">
              <button type="button" className="link link--quiet" onClick={() => onSave(message.id)}>
                <Icon name="save" size={15} /> Lưu vào sổ tay
              </button>
            </div>
          </TutorMessage>
        ),
      )}
    </>
  );
}

function Price({ amount }: { amount: number }) {
  return amount > 0 ? <span className="price">{amount} Coin</span> : null;
}

/**
 * Learn phase as a conversation: the tutor gives one section at a time and the
 * learner can ask as much as they need before moving on; practice comes after.
 */
export function LearnChat({
  course,
  unit,
  revealed,
  recap,
  fragments,
  questionCount,
  focusSection,
  onReveal,
  onRecap,
  onPractice,
}: {
  course: Course;
  unit: Unit;
  revealed: number;
  recap: boolean;
  fragments: Map<string, SourceFragment>;
  questionCount: number;
  /** Section to bring into view when coming back from a question ("Đọc lại phần…"). */
  focusSection: number | null;
  onReveal: (count: number) => void;
  onRecap: () => void;
  onPractice: () => void;
}) {
  const fix = useTextFix();
  const { toast, wallet } = useApp();
  const sections = unit.data?.sections ?? [];
  const ideas = unit.data?.mindmap ?? [];
  const chat = useSectionChat(course, unit, revealed);
  const [target, setTarget] = useState(revealed - 1);
  const [draft, setDraft] = useState('');
  const input = useRef<HTMLTextAreaElement>(null);
  const feed = useRef<HTMLDivElement>(null);
  const draftKey = `folio.learn.draft.${course.id}.${unit.id}`;
  const busy = Boolean(chat.pending[target]);

  useEffect(() => {
    try {
      setDraft(localStorage.getItem(draftKey) ?? '');
    } catch {
      /* Draft only lives in memory. */
    }
  }, [draftKey]);

  // The composer follows the newest section unless the learner picked another.
  useEffect(() => setTarget(revealed - 1), [revealed]);

  const scrollTo = (selector: string) =>
    window.requestAnimationFrame(() => feed.current?.querySelector(selector)?.scrollIntoView({ behavior: 'smooth', block: 'start' }));

  // Reopening lands where the learner was; later, each new section or the recap slides into view.
  const mounted = useRef(false);
  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true;
      if (focusSection !== null) scrollTo(`[data-section="${focusSection}"]`);
      else if (recap) scrollTo('[data-recap]');
      else if (revealed > 1) scrollTo(`[data-section="${revealed - 1}"]`);
      return;
    }
    if (recap) scrollTo('[data-recap]');
    else if (revealed > 1) scrollTo(`[data-section="${revealed - 1}"]`);
  }, [revealed, recap]);

  const keepDraft = (text: string) => {
    setDraft(text);
    try {
      localStorage.setItem(draftKey, text);
    } catch {
      /* ignore */
    }
  };

  const run = async (index: number, action: TutorAction, message = '') => {
    window.requestAnimationFrame(() => feed.current?.querySelector(`[data-thread="${index}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'end' }));
    // The question moves into the conversation right away; it comes back to the box if sending fails.
    const fromBox = action === 'ask' && message === draft.trim();
    if (fromBox) {
      keepDraft('');
      if (input.current) input.current.style.height = 'auto';
    }
    const ok = await chat.send(index, action, message);
    if (!ok && fromBox) setDraft((current) => current || message);
  };

  const sendDraft = () => {
    const message = draft.trim();
    if (!message) return input.current?.focus();
    if (busy) return;
    void run(target, 'ask', message);
  };

  const askAbout = (index: number) => {
    setTarget(index);
    input.current?.focus();
  };

  const saveNote = async (index: number, messageId: string) => {
    try {
      const threadId = await threadFor({ kind: 'section', courseId: course.id, unitId: unit.id, index, revision: course.revision, label: '' });
      await api(`/help/threads/${threadId}/notebook`, { body: { message_id: messageId } });
      toast('Đã lưu vào sổ tay');
    } catch (error) {
      toast(describeError(error).title);
    }
  };

  const next = (index: number) => {
    if (index + 1 < sections.length) onReveal(index + 2);
    else onRecap();
  };

  return (
    <div className="tutor">
      <div className="tutor__feed" ref={feed}>
        <TutorMessage mood="hello">
          <p className="title-m">Chào bạn, mình là Kẹp!</p>
          <p>
            Bài “{fix(unit.title)}” có {sections.length} phần. Mình giảng từng phần một — chỗ nào chưa rõ cứ hỏi, hỏi bao nhiêu cũng được. Khi bạn thấy đã
            hiểu, mình mới sang {questionCount} câu luyện tập.
          </p>
          {unit.objective && <p className="meta">Mục tiêu: {fix(unit.objective)}</p>}
          <ol className="lesson-map" aria-label="Các phần của bài">
            {sections.map((section, index) => {
              const state = index < revealed - 1 || recap ? 'is-done' : index === revealed - 1 ? 'is-current' : '';
              return (
                <li key={index} className={state}>
                  <button
                    type="button"
                    disabled={index >= revealed}
                    onClick={() => feed.current?.querySelector(`[data-section="${index}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
                  >
                    <span className="lesson-map__dot">{state === 'is-done' ? <Icon name="check" size={13} /> : index + 1}</span>
                    {fix(section.title)}
                  </button>
                </li>
              );
            })}
          </ol>
        </TutorMessage>

        {sections.slice(0, revealed).map((section, index) => {
          const thread = chat.threads[index];
          const pending = chat.pending[index];
          const quote = chat.quotes[index];
          const problem = chat.problems[index];
          const latest = index === revealed - 1 && !recap;
          return (
            <Fragment key={index}>
              <div data-section={index} className="tutor__anchor" />
              <SectionCard section={section} index={index} total={sections.length} fragments={fragments} onAsk={() => askAbout(index)} />
              <div data-thread={index} className="tutor__thread">
                {thread && <Thread messages={thread.messages} onSave={(id) => saveNote(index, id)} />}
                {pending && (
                  <>
                    {pending.message ? (
                      <LearnerMessage>
                        <p>{pending.message}</p>
                      </LearnerMessage>
                    ) : pending.action !== 'ask' ? (
                      <LearnerMessage>
                        <p className="msg__action">{ACTION_LABEL[pending.action]}</p>
                      </LearnerMessage>
                    ) : null}
                    <Typing pending={pending} />
                  </>
                )}
                {quote && (
                  <div className="tutor__aside">
                    <CoinConfirm quote={quote.quote} what="Hỏi Kẹp" onConfirm={() => void chat.confirmQuote(index)} onCancel={() => chat.dismissQuote(index)} />
                  </div>
                )}
                {problem && (
                  <div className="tutor__aside">
                    <ProblemNotice problem={problem.problem} onRetry={problem.retry} compact />
                  </div>
                )}
              </div>
              {latest && (
                <div className="quick-replies enter">
                  <button type="button" className="btn btn--primary" onClick={() => next(index)}>
                    {index + 1 < sections.length ? `Hiểu rồi — sang phần ${index + 2}` : 'Hiểu rồi — xem tổng kết'} <Icon name="down" size={18} />
                  </button>
                  <button type="button" className="chip" disabled={Boolean(pending)} onClick={() => void run(index, 'simpler')}>
                    <Icon name="bulb" size={16} /> Giải thích dễ hơn <Price amount={chat.price} />
                  </button>
                  <button type="button" className="chip" disabled={Boolean(pending)} onClick={() => void run(index, 'ask', EXAMPLE)}>
                    <Icon name="sparkle" size={16} /> Cho ví dụ <Price amount={chat.price} />
                  </button>
                  <button type="button" className="chip" onClick={() => askAbout(index)}>
                    <Icon name="message" size={16} /> Mình chưa hiểu chỗ khác…
                  </button>
                </div>
              )}
            </Fragment>
          );
        })}

        {recap && (
          <div data-recap className="tutor__anchor">
            <TutorMessage mood="happy" wide>
              <p className="title-m">Xong {sections.length} phần rồi! Đây là sơ đồ ý chính của bài:</p>
              {ideas.length > 0 && <Mindmap title={unit.title} ideas={ideas} fix={fix} />}
              <p>
                Chỗ nào còn mơ hồ cứ hỏi tiếp ở ô bên dưới. Khi thấy đã hiểu, mình sang luyện tập {questionCount} câu — làm sai cũng không sao, câu nào cũng có
                gợi ý và lời giải.
              </p>
              <div className="quick-replies">
                <button type="button" className="btn btn--primary btn--lg" onClick={onPractice}>
                  Mình hiểu rồi — vào luyện tập <Icon name="arrowRight" size={18} />
                </button>
                <button type="button" className="chip" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}>
                  <Icon name="up" size={16} /> Đọc lại từ đầu
                </button>
              </div>
            </TutorMessage>
          </div>
        )}
      </div>

      <form
        className="composer"
        onSubmit={(event) => {
          event.preventDefault();
          sendDraft();
        }}
      >
        <div className="composer__box">
          <label className="composer__target">
            <span>Hỏi về</span>
            <select value={target} onChange={(event) => setTarget(Number(event.target.value))} aria-label="Phần bạn đang hỏi">
              {sections.slice(0, revealed).map((section, index) => (
                <option key={index} value={index}>
                  Phần {index + 1} · {fix(section.title)}
                </option>
              ))}
            </select>
          </label>
          <textarea
            ref={input}
            rows={1}
            value={draft}
            placeholder="Hỏi Kẹp về phần này…"
            aria-label="Câu hỏi cho Kẹp"
            onChange={(event) => {
              keepDraft(event.target.value);
              event.target.style.height = 'auto';
              event.target.style.height = `${Math.min(event.target.scrollHeight, 180)}px`;
            }}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                sendDraft();
              }
            }}
          />
          <button type="submit" className="btn btn--primary composer__send" disabled={!draft.trim() || busy} aria-busy={busy}>
            <span className="composer__send-label">{busy ? 'Đang trả lời…' : 'Gửi'}</span> {!busy && <Price amount={chat.price} />}
            <Icon name="send" size={16} />
          </button>
        </div>
        <p className="composer__note">
          Enter để gửi · Shift+Enter xuống dòng{chat.price > 0 && wallet ? ` · bạn còn ${wallet.available} Coin` : ''}
        </p>
      </form>
    </div>
  );
}
