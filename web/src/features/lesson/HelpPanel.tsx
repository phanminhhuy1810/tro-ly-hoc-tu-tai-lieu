import { useCallback, useEffect, useRef, useState } from 'react';
import { api, ApiError } from '../../api/client';
import { askAi, settleAi, type AiOutcome } from '../../api/consent';
import type { AiStart } from '../../api/jobs';
import type { CoinQuote, HelpMessage, HelpThread } from '../../api/types';
import { useApp } from '../../app/store';
import { CoinConfirm } from '../../components/CoinConfirm';
import { Icon } from '../../components/Icon';
import { Mascot } from '../../components/Mascot';
import { RichText } from '../../components/RichText';
import { ProblemNotice } from '../../components/StateViews';
import { describeError, describeJobFailure, locatorLabel, type Problem } from '../../lib/copy';
import { stripRefLabels } from '../../lib/text';
import { readThread, threadFor, type HelpTarget } from './help';
import { useTextFix } from './textFix';

type AiAction = 'ask' | 'explain' | 'simpler' | 'detail';

/** Ask the docked chat to take focus (e.g. from "Hỏi về câu này" on the question). */
export const FOCUS_HELP = 'folio:focus-help';

const ACTION_LABEL: Record<string, string> = {
  hint: 'Gợi ý',
  reveal: 'Xem đáp án',
  explain: 'Xem lời giải',
  ask: 'Câu hỏi',
  simpler: 'Giải thích dễ hiểu hơn',
  detail: 'Nói chi tiết hơn',
};

const QUICK_BEFORE = [
  { label: 'Đề này hỏi gì?', message: 'Giải thích giúp mình đề này đang hỏi gì, chưa nói đáp án.' },
  { label: 'Gợi ý cách nghĩ', message: 'Gợi ý cho mình bước suy nghĩ đầu tiên, chưa nói đáp án.' },
];
const QUICK_AFTER = [
  { label: 'Vì sao đáp án là vậy?', message: 'Giải thích vì sao đáp án là như vậy, từng bước.' },
  { label: 'Mình sai ở đâu?', message: 'Câu trả lời của mình sai ở đâu và nên nghĩ thế nào cho đúng?' },
];

function referenceText(message: HelpMessage): string | null {
  const ref = message.content.reference;
  if (ref === undefined || ref === null) return null;
  return Array.isArray(ref) ? ref.join(', ') : String(ref);
}

function Bubble({ message, onSimpler, onDetail, onSave, busy }: { message: HelpMessage; onSimpler: () => void; onDetail: () => void; onSave: () => void; busy: boolean }) {
  const fix = useTextFix();
  if (message.role === 'user') {
    const text = message.action === 'ask' ? message.content.text : ACTION_LABEL[message.action] ?? message.action;
    return <div className="bubble bubble--me">{text}</div>;
  }
  const ref = referenceText(message);
  const ai = message.content.ai_generated;
  return (
    <div className="bubble bubble--bot">
      <span className="bubble__who">{ai ? 'Kẹp · trợ lý AI' : message.action === 'hint' ? 'Gợi ý có sẵn · không tốn Coin' : 'Lời giải đã lưu'}</span>
      {message.content.text && <RichText text={stripRefLabels(message.content.text)} fix={fix} />}
      {ref && message.action !== 'hint' && (
        <p className="bubble__ref">
          <strong>Đáp án tham khảo:</strong> {fix(ref)}
        </p>
      )}
      {message.content.needs_more_source && <p className="meta">Nguồn hiện có chưa đủ để trả lời chắc chắn.</p>}
      {ai && (
        <div className="bubble__actions">
          <button type="button" className="chip" disabled={busy} onClick={onSimpler}>
            Dễ hiểu hơn
          </button>
          <button type="button" className="chip" disabled={busy} onClick={onDetail}>
            Chi tiết hơn
          </button>
          <button type="button" className="chip" onClick={onSave}>
            <Icon name="save" size={15} /> Lưu vào sổ tay
          </button>
        </div>
      )}
    </div>
  );
}

/**
 * Chat beside the question during practice. It reads the same question, the
 * learner's draft or answer and the question's sources, keeps its own draft,
 * and only calls AI for free-form questions.
 */
export function HelpPanel({ target, answered = false, onClose }: { target: HelpTarget; answered?: boolean; onClose?: () => void }) {
  const fix = useTextFix();
  const { toast, refreshWallet, priceOf } = useApp();
  const price = priceOf('inline_help');
  const [thread, setThread] = useState<HelpThread | null>(null);
  const [loadProblem, setLoadProblem] = useState<Problem | null>(null);
  const [draft, setDraft] = useState('');
  const [pending, setPending] = useState<{ action: AiAction; message: string } | null>(null);
  const [quote, setQuote] = useState<{ quote: CoinQuote; confirm: () => Promise<AiStart<unknown>>; action: AiAction; message: string } | null>(null);
  const [problem, setProblem] = useState<Problem | null>(null);
  const lastRequest = useRef<{ action: AiAction; message: string } | null>(null);
  const draftVersion = useRef(0);
  const saveTimer = useRef<number | undefined>(undefined);
  const body = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const threadId = thread?.id;

  const refresh = useCallback(async (id: string) => {
    const value = await readThread(id);
    setThread(value);
    return value;
  }, []);

  useEffect(() => {
    let alive = true;
    setThread(null);
    setLoadProblem(null);
    threadFor(target)
      .then((id) => readThread(id))
      .then((value) => {
        if (!alive) return;
        setThread(value);
        setDraft(value.draft.text);
        draftVersion.current = value.draft.version;
      })
      .catch((error) => alive && setLoadProblem(describeError(error)));
    return () => {
      alive = false;
    };
  }, [target]);

  useEffect(() => {
    body.current?.scrollTo({ top: body.current.scrollHeight, behavior: 'smooth' });
  }, [thread?.messages.length, pending, quote, problem]);

  useEffect(() => {
    const focus = () => input.current?.focus();
    window.addEventListener(FOCUS_HELP, focus);
    return () => window.removeEventListener(FOCUS_HELP, focus);
  }, []);

  const settle = useCallback(
    async (outcome: AiOutcome<unknown>, action: AiAction, message: string, id: string) => {
      refreshWallet();
      if (outcome.kind === 'quote') {
        setQuote({ quote: outcome.quote, confirm: outcome.confirm, action, message });
      } else if (outcome.kind === 'failed') {
        setProblem(describeJobFailure(outcome.job));
      } else if (action === 'ask' && message === draft.trim()) {
        setDraft('');
      }
      await refresh(id).catch(() => undefined);
      setPending(null);
    },
    [refresh, refreshWallet, draft],
  );

  const run = useCallback(
    async (action: AiAction, message = '') => {
      if (!threadId) return;
      lastRequest.current = { action, message };
      setProblem(null);
      setQuote(null);
      setPending({ action, message });
      try {
        await settle(await askAi(`/help/threads/${threadId}/actions`, { action, message }, price), action, message, threadId);
      } catch (error) {
        setPending(null);
        setProblem(describeError(error));
      }
    },
    [threadId, settle, price],
  );

  const retry = () => {
    if (lastRequest.current) void run(lastRequest.current.action, lastRequest.current.message);
  };

  const onDraft = (text: string) => {
    setDraft(text);
    window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(async () => {
      if (!threadId) return;
      try {
        const saved = await api<{ version: number }>(`/help/threads/${threadId}/draft`, { method: 'PUT', body: { text, expected_version: draftVersion.current } });
        draftVersion.current = saved.version;
      } catch (error) {
        if (error instanceof ApiError && error.status === 409 && threadId) {
          const fresh = await readThread(threadId).catch(() => null);
          if (fresh) draftVersion.current = fresh.draft.version;
        }
      }
    }, 700);
  };

  const send = () => {
    const message = draft.trim();
    if (!message) {
      input.current?.focus();
      return;
    }
    void run('ask', message);
  };

  const saveNote = async (messageId: string) => {
    if (!threadId) return;
    try {
      await api(`/help/threads/${threadId}/notebook`, { body: { message_id: messageId } });
      toast('Đã lưu vào sổ tay');
    } catch (error) {
      toast(describeError(error).title);
    }
  };

  const quick = answered ? QUICK_AFTER : QUICK_BEFORE;

  return (
    <aside className="help-panel" aria-label="Hỏi Kẹp về câu này">
      <header className="help-panel__head">
        <Mascot mood="hint" size={44} />
        <div style={{ minWidth: 0, flex: 1 }}>
          <p className="help-panel__title">Hỏi Kẹp về câu này</p>
          <p className="help-panel__target">{fix(target.label)}</p>
        </div>
        {onClose && (
          <button type="button" className="icon-btn" aria-label="Đóng" onClick={onClose}>
            <Icon name="x" />
          </button>
        )}
      </header>

      <div className="help-panel__body" ref={body}>
        {loadProblem && <ProblemNotice problem={loadProblem} compact />}
        {!thread && !loadProblem && <div className="skeleton" style={{ height: 80 }} />}
        {thread && thread.messages.length === 0 && !pending && (
          <div className="help-empty">
            <p>Kẹt ở đâu cứ hỏi. Mình thấy câu bạn đang làm, nháp của bạn và nguồn của câu — không cần chép lại đề.</p>
          </div>
        )}
        {thread?.reference_warning && (
          <div className="notice notice--butter">
            <Icon name="flag" />
            <p className="notice__body">Đáp án lưu của câu này đang cần xem lại: {thread.reference_warning.reason}</p>
          </div>
        )}
        {thread?.messages.map((message) => (
          <Bubble
            key={message.id}
            message={message}
            busy={pending !== null}
            onSimpler={() => run('simpler')}
            onDetail={() => run('detail')}
            onSave={() => saveNote(message.id)}
          />
        ))}
        {pending && (
          <>
            {pending.message && <div className="bubble bubble--me">{pending.message}</div>}
            <div className="bubble bubble--bot bubble--pending" role="status">
              <Mascot mood="think" size={40} bob />
              <span>Đang soạn câu trả lời…</span>
            </div>
          </>
        )}
        {quote && (
          <CoinConfirm
            quote={quote.quote}
            what="Hỏi Kẹp"
            onCancel={() => setQuote(null)}
            onConfirm={async () => {
              const current = quote;
              if (!threadId) return;
              setQuote(null);
              setPending({ action: current.action, message: current.message });
              try {
                await settle(await settleAi(await current.confirm()), current.action, current.message, threadId);
              } catch (error) {
                setPending(null);
                setProblem(describeError(error));
              }
            }}
          />
        )}
        {problem && <ProblemNotice problem={problem} onRetry={retry} compact />}
      </div>

      {thread && thread.source_excerpts.length > 0 && (
        <details className="help-panel__sources">
          <summary>
            <Icon name="file" size={16} /> Nguồn của câu này ({thread.source_excerpts.length})
          </summary>
          <ul>
            {thread.source_excerpts.map((fragment) => (
              <li key={fragment.id}>
                <span className="tag">{locatorLabel(fragment.locator)}</span> {fix(fragment.text)}
              </li>
            ))}
          </ul>
        </details>
      )}

      <div className="help-panel__quick">
        {quick.map((item) => (
          <button key={item.label} type="button" className="chip" disabled={!thread || pending !== null} onClick={() => void run('ask', item.message)}>
            {item.label}
          </button>
        ))}
      </div>
      <form
        className="help-panel__composer"
        onSubmit={(event) => {
          event.preventDefault();
          send();
        }}
      >
        <textarea
          ref={input}
          className="field"
          rows={2}
          value={draft}
          placeholder="Ví dụ: vì sao lại trừ 2 địa chỉ?"
          aria-label="Câu hỏi của bạn"
          disabled={!thread}
          onChange={(event) => onDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              send();
            }
          }}
        />
        <button type="submit" className="btn btn--primary btn--sm" disabled={!thread || pending !== null} aria-label="Gửi câu hỏi">
          {price > 0 && <span className="price">{price}</span>}
          <Icon name="send" size={16} />
        </button>
      </form>
    </aside>
  );
}
