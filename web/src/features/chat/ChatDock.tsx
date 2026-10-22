import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../../api/client';
import { acceptShownPrice } from '../../api/consent';
import { observeJob, startAi, type AiStart } from '../../api/jobs';
import type { ChatMessage, CoinQuote, Course } from '../../api/types';
import { useApp, type ChatContext } from '../../app/store';
import { BotBubble, MyBubble, TypingBubble } from '../../components/ChatBubbles';
import { CoinConfirm } from '../../components/CoinConfirm';
import { Icon } from '../../components/Icon';
import { Mascot } from '../../components/Mascot';
import { RichText } from '../../components/RichText';
import { ProblemNotice } from '../../components/StateViews';
import { describeError, describeJobFailure, type Problem } from '../../lib/copy';
import { stripRefLabels } from '../../lib/text';

const draftKey = (courseId: string) => `folio.chat.draft.${courseId}`;

// Starters fill the box rather than send, so nothing is spent until the learner presses Gửi.
const STARTERS = [
  { label: 'Tóm tắt bài này', text: 'Tóm tắt giúp mình các ý chính của bài này.' },
  { label: 'Giải thích một thuật ngữ', text: 'Giải thích giúp mình thuật ngữ: ' },
  { label: 'Cho ví dụ dễ hiểu', text: 'Cho mình một ví dụ cụ thể, dễ hình dung về nội dung bài này.' },
];

function loadDraft(courseId: string) {
  try {
    return localStorage.getItem(draftKey(courseId)) ?? '';
  } catch {
    return '';
  }
}

function keepDraft(courseId: string, text: string) {
  try {
    localStorage.setItem(draftKey(courseId), text);
  } catch {
    /* Draft lives in memory only. */
  }
}

/** Pick a course to talk about when the page has no lesson context (e.g. Home). */
function ContextPicker({ onPick }: { onPick: (ctx: ChatContext) => void }) {
  const [courses, setCourses] = useState<Course[] | null>(null);
  useEffect(() => {
    api<Course[]>('/courses')
      .then(setCourses)
      .catch(() => setCourses([]));
  }, []);
  const usable = (courses ?? []).filter((c) => c.content.units.some((u) => u.data));
  return (
    <div className="chat-pick">
      <p className="title-m">Bạn muốn hỏi về khóa nào?</p>
      <p className="meta">Trợ lý trả lời dựa trên nguồn của bài bạn chọn.</p>
      {courses === null && <div className="skeleton" style={{ height: 44 }} />}
      {courses && usable.length === 0 && <p className="meta">Chưa có bài nào để hỏi. Tạo một bài trước nhé.</p>}
      {usable.map((course) => {
        const unit = course.content.units.find((u) => u.data)!;
        return (
          <button
            key={course.id}
            type="button"
            className="chat-pick__item"
            onClick={() => onPick({ courseId: course.id, courseTitle: course.content.title, unitId: unit.id, unitTitle: unit.title })}
          >
            <strong>{course.content.title}</strong>
            <span className="meta">{unit.title}</span>
          </button>
        );
      })}
    </div>
  );
}

/**
 * General chat: closed by default, opens as a small panel, the learner chooses
 * to expand. Size changes never reset history or the draft.
 */
export function ChatDock() {
  const { chatSize, setChatSize, chatContext, refreshWallet, priceOf } = useApp();
  const price = priceOf('chat');
  const [picked, setPicked] = useState<ChatContext | null>(null);
  const context = chatContext ?? picked;
  const [messages, setMessages] = useState<ChatMessage[] | null>(null);
  const [draft, setDraft] = useState('');
  const [attach, setAttach] = useState(false);
  const [pending, setPending] = useState(false);
  const [quote, setQuote] = useState<{ quote: CoinQuote; confirm: () => Promise<AiStart<unknown>> } | null>(null);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [loadProblem, setLoadProblem] = useState<Problem | null>(null);
  const list = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const launcher = useRef<HTMLButtonElement>(null);
  const open = chatSize !== 'closed';
  const courseId = context?.courseId;

  const loadHistory = useCallback(async () => {
    if (!courseId) return;
    try {
      setMessages(await api<ChatMessage[]>(`/courses/${courseId}/chat`));
      setLoadProblem(null);
    } catch (error) {
      setLoadProblem(describeError(error));
    }
  }, [courseId]);

  useEffect(() => {
    if (!open || !courseId) return;
    setMessages(null);
    setDraft(loadDraft(courseId));
    void loadHistory();
  }, [open, courseId, loadHistory]);

  const attachable = context?.question ?? context?.card;
  useEffect(() => {
    if (!attachable) setAttach(false);
  }, [context?.question?.itemId, context?.card?.id]);

  useEffect(() => {
    list.current?.scrollTo({ top: list.current.scrollHeight });
  }, [messages, pending, quote, problem, chatSize]);

  useEffect(() => {
    if (open) input.current?.focus();
  }, [open, chatSize]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || event.defaultPrevented) return;
      if (document.querySelector('.help-panel')?.contains(document.activeElement)) return;
      setChatSize(chatSize === 'large' ? 'small' : 'closed');
      if (chatSize === 'small') launcher.current?.focus();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, chatSize, setChatSize]);

  const settle = async (start: AiStart<unknown>) => {
    if (start.kind === 'quote') {
      setPending(false);
      setQuote({ quote: start.quote, confirm: start.confirm });
      return;
    }
    if (start.kind === 'job') {
      setPending(true);
      const job = await observeJob(start.jobId);
      refreshWallet();
      if (job.status !== 'succeeded') {
        setProblem(describeJobFailure(job));
        await loadHistory();
        setPending(false);
        return;
      }
    }
    await loadHistory();
    setDraft('');
    if (courseId) keepDraft(courseId, '');
    setPending(false);
  };

  const start = (text: string) => {
    setDraft(text);
    if (courseId) keepDraft(courseId, text);
    window.requestAnimationFrame(() => {
      input.current?.focus();
      input.current?.setSelectionRange(text.length, text.length);
    });
  };

  const send = async () => {
    const message = draft.trim();
    if (!context || !message) return;
    setProblem(null);
    setQuote(null);
    setPending(true);
    const body: Record<string, unknown> = { unit_id: context.unitId, message };
    if (attach && context.question) {
      body.session_id = context.question.sessionId;
      body.item_id = context.question.itemId;
    } else if (attach && context.card) {
      body.card_id = context.card.id;
    }
    try {
      // The send button shows the price, so pressing it accepts a quote up to that amount.
      await settle(await acceptShownPrice(await startAi(`/courses/${context.courseId}/chat`, body), price));
    } catch (error) {
      setPending(false);
      setProblem(describeError(error));
    }
  };

  if (!open) {
    return (
      <button ref={launcher} type="button" className="chat-launcher" aria-label="Mở hỏi chung" onClick={() => setChatSize('small')}>
        <Mascot mood="hello" size={46} />
        <span className="chat-launcher__label">Hỏi chung</span>
      </button>
    );
  }

  const panel = (
    <section className={`chat chat--${chatSize}`} role="dialog" aria-modal={chatSize === 'large'} aria-label="Hỏi chung">
      <header className="chat__head">
        <div className="chat__who">
          <span className="chat__avatar" aria-hidden="true">
            <Mascot mood="hello" size={40} face />
          </span>
          <div>
            <p className="chat__title">Hỏi chung</p>
            <p className="meta">{context ? `Về: ${context.unitTitle}` : 'Chưa chọn bài'}</p>
          </div>
        </div>
        <div className="chat__tools">
          {context && !chatContext && (
            <button type="button" className="icon-btn" aria-label="Chọn khóa khác" onClick={() => setPicked(null)}>
              <Icon name="layers" />
            </button>
          )}
          <button
            type="button"
            className="icon-btn"
            aria-label={chatSize === 'large' ? 'Thu nhỏ' : 'Phóng to'}
            onClick={() => setChatSize(chatSize === 'large' ? 'small' : 'large')}
          >
            <Icon name={chatSize === 'large' ? 'collapse' : 'expand'} />
          </button>
          <button
            type="button"
            className="icon-btn"
            aria-label="Đóng hỏi chung"
            onClick={() => {
              setChatSize('closed');
              window.setTimeout(() => launcher.current?.focus(), 0);
            }}
          >
            <Icon name="x" />
          </button>
        </div>
      </header>

      {!context ? (
        <ContextPicker onPick={setPicked} />
      ) : (
        <>
          <div className="chat__list" ref={list}>
            {loadProblem && <ProblemNotice problem={loadProblem} onRetry={loadHistory} compact />}
            {messages === null && !loadProblem && <div className="skeleton" style={{ height: 60 }} />}
            {messages && messages.length === 0 && (
              <div className="chat-welcome">
                <Mascot mood="hello" size={68} bob />
                <p className="chat-welcome__title">Chào bạn, mình là Kẹp!</p>
                <p className="chat-welcome__text">Hỏi thuật ngữ hay ý chung của bài, mình trả lời theo tài liệu của bạn. Câu đang làm thì có nút hỏi riêng ngay trong bài.</p>
                <div className="chat-welcome__starters">
                  {STARTERS.map((item) => (
                    <button key={item.label} type="button" className="chip" onClick={() => start(item.text)}>
                      {item.label}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {messages?.map((m) =>
              m.role === 'assistant' ? (
                <BotBubble key={m.id}>
                  <RichText text={stripRefLabels(m.text)} />
                </BotBubble>
              ) : (
                <MyBubble key={m.id}>
                  <p>{m.text}</p>
                </MyBubble>
              ),
            )}
            {pending && <TypingBubble />}
            {quote && (
              <CoinConfirm
                quote={quote.quote}
                what="Hỏi AI"
                onCancel={() => setQuote(null)}
                onConfirm={async () => {
                  const current = quote;
                  setQuote(null);
                  setPending(true);
                  try {
                    await settle(await current.confirm());
                  } catch (error) {
                    setPending(false);
                    setProblem(describeError(error));
                  }
                }}
              />
            )}
            {problem && <ProblemNotice problem={problem} onRetry={send} compact />}
          </div>
          {attachable && (
            <div className="chat__attach">
              <button type="button" className="chip" aria-pressed={attach} onClick={() => setAttach((v) => !v)}>
                <Icon name={attach ? 'check' : 'plus'} size={15} /> {attach ? `Đã gắn ${attachable.label}` : `Gắn ${attachable.label}`}
              </button>
            </div>
          )}
          <form
            className="chat__composer"
            onSubmit={(event) => {
              event.preventDefault();
              void send();
            }}
          >
            <textarea
              ref={input}
              className="chat__input"
              rows={chatSize === 'large' ? 2 : 1}
              value={draft}
              placeholder="Hỏi một thuật ngữ hoặc ý bạn muốn rõ hơn…"
              aria-label="Tin nhắn"
              onChange={(event) => {
                setDraft(event.target.value);
                if (courseId) keepDraft(courseId, event.target.value);
              }}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault();
                  void send();
                }
              }}
            />
            <button type="submit" className="btn btn--primary chat__send" disabled={pending || !draft.trim()} aria-label={price > 0 ? `Gửi, ${price} Coin` : 'Gửi'}>
              {price > 0 && <span className="price">{price} Coin</span>}
              <Icon name="send" size={18} />
            </button>
          </form>
        </>
      )}
    </section>
  );

  if (chatSize === 'large') {
    return (
      <div className="chat-scrim" onMouseDown={(event) => event.target === event.currentTarget && setChatSize('small')}>
        <div className="chat-large">
          <aside className="chat-large__context">
            <p className="eyebrow">Bạn đang học</p>
            <p className="title-m">{context?.courseTitle ?? '—'}</p>
            <p className="meta">{context?.unitTitle}</p>
            {attachable && <p className="tag tag--butter">{attachable.label}</p>}
            <button type="button" className="btn btn--secondary btn--sm" onClick={() => setChatSize('small')}>
              <Icon name="arrowLeft" size={16} /> Quay lại bài
            </button>
          </aside>
          {panel}
        </div>
      </div>
    );
  }
  return panel;
}
