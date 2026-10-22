import { useCallback, useEffect, useState } from 'react';
import { api, ApiError, newKey } from '../../api/client';
import { askAi, settleAi, type AiOutcome } from '../../api/consent';
import type { AiStart } from '../../api/jobs';
import type { CoinQuote, GradeResult, RoomPlayer, RoomResultQuestion, RoomResults, RoomSnapshot } from '../../api/types';
import { hrefFor, navigate } from '../../app/router';
import { useApp, useLoad } from '../../app/store';
import { CoinConfirm } from '../../components/CoinConfirm';
import { Icon } from '../../components/Icon';
import { Mascot } from '../../components/Mascot';
import { RichText } from '../../components/RichText';
import { EmptyState, LoadingRows, ProblemNotice } from '../../components/StateViews';
import { draftFrom, missingAnswer, noHint, toAnswer, type Draft } from '../../lib/answers';
import { appLink, copyText } from '../../lib/clipboard';
import { describeError, describeJobFailure, locatorLabel, type Problem } from '../../lib/copy';
import { answerKey, canStart, endReason, formatCode, isTerminal, onlinePlayers, revealed, secondsLeft } from '../../lib/rooms';
import { stripRefLabels } from '../../lib/text';
import { kindLabel, QuestionView } from '../lesson/QuestionView';
import { loadRoomCode, roomProblem, saveRoomCode } from './roomStore';
import { useNow, useRoom } from './useRoom';

type Action = 'start' | 'next' | 'close-question' | 'close' | 'leave' | 'invite';
type Act = (action: Action) => void;

const noChange = () => undefined;

function Players({ board, meId, scores }: { board: RoomPlayer[]; meId: string; scores: boolean }) {
  return (
    <ol className="room-players">
      {board.map((player) => (
        <li key={player.member_id} className={`${player.member_id === meId ? 'is-me' : ''} ${player.state === 'left' ? 'is-left' : ''}`.trim() || undefined}>
          {scores && <span className="room-players__rank">{player.rank}</span>}
          <span className="room-players__avatar" aria-hidden="true">
            {player.nickname.slice(0, 1).toUpperCase()}
          </span>
          <span className="room-players__name">
            {player.nickname}
            {player.member_id === meId && <span className="meta"> (bạn)</span>}
            {player.is_host && <span className="tag">chủ phòng</span>}
            {player.state === 'left' && <span className="tag">đã rời</span>}
          </span>
          <span className={player.connected ? 'room-dot is-on' : 'room-dot'} title={player.connected ? 'Đang kết nối' : 'Mất kết nối'} />
          {scores && <strong className="room-players__score">{player.score}</strong>}
        </li>
      ))}
    </ol>
  );
}

function Lobby({ roomId, snapshot, busy, act }: { roomId: string; snapshot: RoomSnapshot; busy: Action | null; act: Act }) {
  const { toast } = useApp();
  const code = loadRoomCode(roomId);
  const host = snapshot.me.is_host;
  const joined = snapshot.scoreboard.filter((player) => player.state === 'joined').length;
  const copy = async (text: string, what: string) => toast((await copyText(text)) ? `Đã chép ${what}` : 'Trình duyệt chưa cho chép — đọc mã cho mọi người nhé');

  return (
    <div className="room-lobby">
      <section className="room-hero enter">
        {host && code ? (
          <>
            <p className="eyebrow">Mã phòng — gửi hoặc đọc cho mọi người</p>
            <p className="room-code">{formatCode(code)}</p>
            <div className="room-hero__actions">
              <button type="button" className="btn btn--secondary btn--sm" onClick={() => void copy(code, 'mã phòng')}>
                <Icon name="copy" size={16} /> Chép mã
              </button>
              <button type="button" className="btn btn--secondary btn--sm" onClick={() => void copy(appLink(hrefFor({ name: 'rooms', code })), 'đường dẫn vào phòng')}>
                <Icon name="link" size={16} /> Chép đường dẫn
              </button>
              <button type="button" className="btn btn--ghost btn--sm" disabled={busy !== null} onClick={() => act('invite')}>
                <Icon name="refresh" size={16} /> Đổi mã
              </button>
            </div>
          </>
        ) : host ? (
          <>
            <p className="eyebrow">Mã phòng</p>
            <p className="meta">Mã chỉ hiện trên máy đã tạo phòng. Tạo mã mới để mời thêm người; mã cũ sẽ hết hiệu lực.</p>
            <button type="button" className="btn btn--secondary" disabled={busy !== null} onClick={() => act('invite')}>
              <Icon name="refresh" size={18} /> Tạo mã mới
            </button>
          </>
        ) : (
          <>
            <Mascot mood="happy" size={96} bob />
            <p className="display-title">Bạn đã vào phòng!</p>
            <p className="meta">Chờ chủ phòng bắt đầu. Mọi người làm cùng lúc, máy chủ giữ đồng hồ và chấm điểm.</p>
          </>
        )}
        <p className="meta room-hero__facts">
          {snapshot.question_count} câu · {snapshot.seconds_per_question} giây mỗi câu · đúng +{snapshot.policy.points_per_correct} điểm, không tính tốc độ
        </p>
      </section>

      <section className="panel-card">
        <h2 className="title-m">
          Trong phòng ({joined}/{snapshot.policy.max_players})
        </h2>
        <Players board={snapshot.scoreboard} meId={snapshot.me.member_id} scores={false} />
        {host ? (
          <div className="room-actions">
            <button type="button" className="btn btn--primary btn--lg" disabled={!canStart(snapshot) || busy !== null} aria-busy={busy === 'start'} onClick={() => act('start')}>
              <Icon name="play" size={18} /> Bắt đầu
            </button>
            {!canStart(snapshot) && <p className="meta">Cần ít nhất 2 người đang kết nối ({onlinePlayers(snapshot.scoreboard)}/2).</p>}
          </div>
        ) : (
          <p className="meta">Bài làm trong phòng không đổi tiến trình học hay Coin của bạn.</p>
        )}
      </section>
    </div>
  );
}

function Timer({ left, total }: { left: number; total: number }) {
  return (
    <div className="room-timer" role="timer" aria-label={`Còn ${left} giây`}>
      <span className="room-timer__bar">
        <span style={{ width: `${total ? Math.min(100, (left / total) * 100) : 0}%` }} />
      </span>
      <strong className={left <= 5 ? 'room-timer__left is-low' : 'room-timer__left'}>{left}s</strong>
    </div>
  );
}

function QuestionStage({ roomId, snapshot, left, busy, act, onSent }: { roomId: string; snapshot: RoomSnapshot; left: number; busy: Action | null; act: Act; onSent: () => void }) {
  const { toast } = useApp();
  const question = snapshot.question!;
  const submitted = snapshot.own_answer != null;
  const [draft, setDraft] = useState<Draft>(() => draftFrom(question, snapshot.own_answer));
  const [missing, setMissing] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  const send = async () => {
    const why = missingAnswer(question, draft);
    if (why) return setMissing(why);
    const answer = toAnswer(draft);
    setSending(true);
    try {
      await api(`/rooms/${encodeURIComponent(roomId)}/answers`, {
        body: { event_index: snapshot.question_event_index, question_id: question.id, answer },
        idempotencyKey: answerKey(roomId, question.id, answer),
      });
    } catch (error) {
      toast(roomProblem(error));
    } finally {
      setSending(false);
      onSent();
    }
  };

  return (
    <article className="lesson-card step step--check room-question">
      <Timer left={left} total={snapshot.seconds_per_question} />
      <p className="eyebrow">
        Câu {snapshot.question_index + 1}/{snapshot.question_count} · {kindLabel(question.kind)}
      </p>
      <h2 className="question-prompt">{question.kind === 'cloze' ? 'Điền vào chỗ trống' : question.prompt}</h2>
      <QuestionView
        question={question}
        draft={draft}
        effect={noHint()}
        locked={submitted || sending || left === 0}
        onChange={(next) => {
          setMissing(null);
          setDraft(next);
        }}
      />
      <footer className="step__foot">
        {submitted ? (
          <span className="tag tag--sage">
            <Icon name="check" size={14} /> Đã gửi — chờ mọi người hoặc hết giờ
          </span>
        ) : (
          <span className="meta">Chỉ gửi được một lần.</span>
        )}
        <div className="step__cta">
          {missing && (
            <span className="missing" role="alert">
              {missing}
            </span>
          )}
          {snapshot.me.is_host && (
            <button type="button" className="btn btn--ghost btn--sm" disabled={busy !== null} onClick={() => act('close-question')}>
              Đóng câu ngay
            </button>
          )}
          {!submitted && (
            <button type="button" className="btn btn--primary btn--lg" disabled={sending || left === 0} aria-busy={sending} onClick={() => void send()}>
              Gửi đáp án <Icon name="send" size={18} />
            </button>
          )}
        </div>
      </footer>
    </article>
  );
}

function RevealStage({ snapshot, left, busy, act }: { snapshot: RoomSnapshot; left: number; busy: Action | null; act: Act }) {
  const question = snapshot.question!;
  const result = revealed(snapshot);
  const own = snapshot.own_result;
  const last = snapshot.question_index + 1 >= snapshot.question_count;
  return (
    <article className="lesson-card step step--check room-question">
      <div className={`room-verdict enter ${own ? (own.correct ? 'is-right' : 'is-wrong') : 'is-none'}`}>
        <Icon name={own?.correct ? 'check' : own ? 'x' : 'clock'} size={22} />
        <strong>{own ? (own.correct ? `Chính xác! +${own.points} điểm` : 'Chưa đúng câu này') : 'Bạn chưa kịp trả lời'}</strong>
      </div>
      <p className="eyebrow">
        Câu {snapshot.question_index + 1}/{snapshot.question_count} · {kindLabel(question.kind)}
      </p>
      <h2 className="question-prompt">{question.kind === 'cloze' ? 'Điền vào chỗ trống' : question.prompt}</h2>
      <QuestionView question={question} draft={draftFrom(question, snapshot.own_answer)} result={result} locked effect={noHint()} onChange={noChange} />
      {result?.explanation && (
        <div className="room-explain">
          <p className="eyebrow">Giải thích</p>
          <RichText text={result.explanation} />
        </div>
      )}
      {snapshot.reference_warning && <p className="notice notice--butter">Câu này đang bị báo cần xem lại: {snapshot.reference_warning}</p>}
      <footer className="step__foot">
        <span className="meta">{last ? `Bảng điểm sau ${left} giây` : `Câu tiếp theo sau ${left} giây`}</span>
        {snapshot.me.is_host && (
          <button type="button" className="btn btn--primary" disabled={busy !== null} aria-busy={busy === 'next'} onClick={() => act('next')}>
            {last ? 'Xem bảng điểm' : 'Câu tiếp'} <Icon name="arrowRight" size={18} />
          </button>
        )}
      </footer>
    </article>
  );
}

interface HelpMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  needs_more_source?: boolean;
}

/** Kẹp explains a room question only after the room has ended; each person's thread is private. */
function RoomHelp({ roomId, questionId }: { roomId: string; questionId: string }) {
  const { priceOf, refreshWallet } = useApp();
  const price = priceOf('chat');
  const path = `/rooms/${encodeURIComponent(roomId)}/questions/${encodeURIComponent(questionId)}/chat`;
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<HelpMessage[] | null>(null);
  const [draft, setDraft] = useState('');
  const [pending, setPending] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [quote, setQuote] = useState<{ quote: CoinQuote; confirm: () => Promise<AiStart<unknown>> } | null>(null);

  const load = useCallback(async () => {
    try {
      setMessages(await api<HelpMessage[]>(path));
    } catch (error) {
      setProblem(describeError(error));
    }
  }, [path]);

  useEffect(() => {
    if (open && messages === null) void load();
  }, [open, messages, load]);

  const settle = async (outcome: AiOutcome<unknown>) => {
    refreshWallet();
    if (outcome.kind === 'quote') setQuote({ quote: outcome.quote, confirm: outcome.confirm });
    else if (outcome.kind === 'failed') setProblem(describeJobFailure(outcome.job));
    else setDraft('');
    await load();
  };

  const send = async (message: string) => {
    setPending(true);
    setProblem(null);
    try {
      await settle(await askAi(path, { question_id: questionId, message }, price));
    } catch (error) {
      setProblem(describeError(error));
    } finally {
      setPending(false);
    }
  };

  if (!open) {
    return (
      <button type="button" className="chip" onClick={() => setOpen(true)}>
        <Icon name="message" size={16} /> Hỏi Kẹp về câu này
      </button>
    );
  }
  return (
    <div className="room-help enter">
      {messages === null && !problem && <div className="skeleton" style={{ height: 44 }} />}
      {messages?.map((message) =>
        message.role === 'user' ? (
          <div key={message.id} className="bubble bubble--me">
            {message.text}
          </div>
        ) : (
          <div key={message.id} className="bubble bubble--bot">
            <span className="bubble__who">Kẹp · trợ lý AI</span>
            <RichText text={stripRefLabels(message.text)} />
            {message.needs_more_source && <p className="meta">Nguồn của câu chưa đủ để trả lời chắc chắn.</p>}
          </div>
        ),
      )}
      {pending && (
        <div className="bubble bubble--bot bubble--pending" role="status">
          <Mascot mood="think" size={36} bob />
          <span>Kẹp đang đọc câu và nguồn…</span>
        </div>
      )}
      {quote && (
        <CoinConfirm
          quote={quote.quote}
          what="Hỏi Kẹp"
          onCancel={() => setQuote(null)}
          onConfirm={async () => {
            const current = quote;
            setQuote(null);
            setPending(true);
            try {
              await settle(await settleAi(await current.confirm()));
            } catch (error) {
              setProblem(describeError(error));
            } finally {
              setPending(false);
            }
          }}
        />
      )}
      {problem && <ProblemNotice problem={problem} compact />}
      {messages && messages.length === 0 && !pending && (
        <div className="quick-replies">
          <button type="button" className="chip" disabled={pending} onClick={() => void send('Vì sao đáp án đúng là như vậy?')}>
            Vì sao đáp án đúng?
          </button>
          <button type="button" className="chip" disabled={pending} onClick={() => void send('Mình sai ở đâu, giải thích dễ hiểu giúp mình.')}>
            Mình sai ở đâu?
          </button>
        </div>
      )}
      <form
        className="room-help__form"
        onSubmit={(event) => {
          event.preventDefault();
          if (draft.trim()) void send(draft.trim());
        }}
      >
        <input className="field" value={draft} maxLength={2000} placeholder="Hỏi thêm về câu này…" aria-label="Câu hỏi cho Kẹp" onChange={(event) => setDraft(event.target.value)} />
        <button type="submit" className="btn btn--primary btn--sm" disabled={pending || !draft.trim()} aria-label={price > 0 ? `Gửi, ${price} Coin` : 'Gửi'}>
          {price > 0 && <span className="price">{price} Coin</span>}
          <Icon name="send" size={16} />
        </button>
      </form>
    </div>
  );
}

function ReviewItem({ roomId, question, index, help }: { roomId: string; question: RoomResultQuestion; index: number; help: boolean }) {
  const answered = question.own_answer != null;
  const result: GradeResult = {
    correct: answered ? question.correct : null,
    reference: question.solution.answer,
    explanation: question.solution.explanation,
    rubric: [],
    source_refs: question.solution.source_refs,
    grading: 'fixed',
  };
  return (
    <li className={`review-item ${question.correct ? 'is-right' : 'is-wrong'}`}>
      <p className="eyebrow">
        Câu {index + 1} · {kindLabel(question.kind)} · {!answered ? 'bạn chưa trả lời' : question.correct ? `đúng, +${question.points} điểm` : 'chưa đúng'}
      </p>
      <p className="review-item__prompt">{question.kind === 'cloze' ? 'Điền vào chỗ trống' : question.prompt}</p>
      <QuestionView question={question} draft={draftFrom(question, question.own_answer)} result={result} locked effect={noHint()} onChange={noChange} />
      {question.solution.explanation && <RichText className="room-explain" text={question.solution.explanation} />}
      {question.reference_warning && <p className="notice notice--butter">Câu này đang bị báo cần xem lại: {question.reference_warning}</p>}
      {question.sources.length > 0 && (
        <details className="room-sources">
          <summary>
            <Icon name="file" size={16} /> Nguồn của câu ({question.sources.length})
          </summary>
          <ul>
            {question.sources.map((fragment) => (
              <li key={fragment.id}>
                <span className="tag">{locatorLabel(fragment.locator)}</span> {fragment.text}
              </li>
            ))}
          </ul>
        </details>
      )}
      {help && <RoomHelp roomId={roomId} questionId={question.id} />}
    </li>
  );
}

function Podium({ board }: { board: RoomPlayer[] }) {
  const top = board.slice(0, 3);
  if (top.length < 2) return null;
  // Second, first, third — the classic podium order.
  const order = [top[1], top[0], top[2]].filter(Boolean);
  return (
    <ol className="room-podium" aria-label="Ba người dẫn đầu">
      {order.map((player) => (
        <li key={player.member_id} className={`room-podium__step rank-${player.rank}`}>
          <span className="room-players__avatar">{player.nickname.slice(0, 1).toUpperCase()}</span>
          <strong>{player.nickname}</strong>
          <span className="meta">{player.score} điểm</span>
          <span className="room-podium__block">{player.rank}</span>
        </li>
      ))}
    </ol>
  );
}

function RoomEnd({ roomId, snapshot }: { roomId: string; snapshot: RoomSnapshot }) {
  const results = useLoad(() => api<RoomResults>(`/rooms/${encodeURIComponent(roomId)}/results`), [roomId]);
  const board = results.data?.scoreboard ?? snapshot.scoreboard;
  const me = board.find((player) => player.member_id === snapshot.me.member_id);
  const finished = snapshot.phase === 'finished';
  return (
    <div className="room-end">
      <section className="room-hero enter">
        <Mascot mood={finished ? 'happy' : 'oops'} size={100} />
        <p className="display-title">{finished ? 'Xong phòng!' : 'Phòng đã dừng'}</p>
        <p className="meta">
          {endReason(snapshot.end_reason)}
          {me && snapshot.closed_count > 0 ? ` Bạn được ${me.score} điểm, hạng ${me.rank}.` : ''}
        </p>
        <Podium board={board} />
      </section>

      <section className="panel-card">
        <h2 className="title-m">Bảng điểm</h2>
        <Players board={board} meId={snapshot.me.member_id} scores />
      </section>

      <section>
        <h2 className="title-m review-title">Xem lại từng câu</h2>
        {results.loading && !results.data && <LoadingRows rows={2} label="Đang mở bài làm của bạn…" />}
        {results.error != null && <ProblemNotice problem={describeError(results.error)} onRetry={results.reload} />}
        {results.data && results.data.questions.length === 0 && <p className="meta">Phòng dừng trước khi có câu nào được chấm.</p>}
        {results.data && results.data.questions.length > 0 && (
          <ol className="review-list">
            {results.data.questions.map((question, index) => (
              <ReviewItem key={question.id} roomId={roomId} question={question} index={index} help={snapshot.ai_help_available} />
            ))}
          </ol>
        )}
      </section>

      <div className="result__actions">
        <a className="btn btn--primary btn--lg" href={hrefFor({ name: 'rooms' })}>
          Về phòng đố vui <Icon name="arrowRight" size={18} />
        </a>
      </div>
    </div>
  );
}

/**
 * One quiz room, live. Everything that decides the game — phase, deadline,
 * correctness, score — comes from the server; this screen shows the latest
 * snapshot, sends answers once, and lets the host move the room along.
 */
export function RoomPage({ roomId }: { roomId: string }) {
  const { toast } = useApp();
  const { snapshot, error, offset, refresh } = useRoom(roomId);
  const [busy, setBusy] = useState<Action | null>(null);
  const [confirmEnd, setConfirmEnd] = useState(false);
  const counting = snapshot?.phase === 'question_open' || snapshot?.phase === 'question_closed';
  const now = useNow(counting);

  const act: Act = (action) => {
    if (!snapshot || busy) return;
    // Ending the room (or the host leaving, which ends it too) asks once more.
    if ((action === 'close' || (action === 'leave' && snapshot.me.is_host)) && !confirmEnd) {
      setConfirmEnd(true);
      return;
    }
    setConfirmEnd(false);
    setBusy(action);
    void api<{ join_code?: string }>(`/rooms/${encodeURIComponent(roomId)}/${action}`, {
      body: { expected_event_index: snapshot.event_index },
      idempotencyKey: newKey(`room-${action}`),
    })
      .then((result) => {
        if (result.join_code) saveRoomCode(roomId, result.join_code);
        if (action === 'leave' && !snapshot.me.is_host) navigate({ name: 'rooms' });
      })
      .catch((cause) => toast(roomProblem(cause)))
      .finally(() => {
        setBusy(null);
        void refresh();
      });
  };

  const back = (
    <a className="back back--bar" href={hrefFor({ name: 'rooms' })}>
      <Icon name="arrowLeft" size={18} />
      <span>Phòng đố vui</span>
    </a>
  );

  if (!snapshot) {
    const missing = error instanceof ApiError && error.status === 404;
    return (
      <div className="lesson-shell">
        <div className="page" style={{ paddingTop: 40 }}>
          {back}
          {error == null ? (
            <LoadingRows rows={2} label="Đang vào phòng…" />
          ) : missing ? (
            <EmptyState art={<Mascot mood="oops" size={110} />} title="Bạn chưa ở trong phòng này" body="Vào phòng bằng mã chủ phòng gửi cho bạn." action={<a className="btn btn--primary" href={hrefFor({ name: 'rooms' })}>Nhập mã phòng</a>} />
          ) : (
            <ProblemNotice problem={describeError(error)} onRetry={() => void refresh()} />
          )}
        </div>
      </div>
    );
  }

  const left = secondsLeft(snapshot.deadline, offset.current, now);
  const me = snapshot.scoreboard.find((player) => player.member_id === snapshot.me.member_id);
  const ended = isTerminal(snapshot.phase);
  const playing = snapshot.phase === 'question_open' || snapshot.phase === 'question_closed';
  const heading =
    snapshot.phase === 'lobby'
      ? 'Sảnh chờ'
      : playing
        ? `Câu ${snapshot.question_index + 1}/${snapshot.question_count}`
        : snapshot.phase === 'finished'
          ? 'Bảng điểm'
          : 'Phòng đã dừng';

  return (
    <div className={`lesson-shell room-shell room-shell--${snapshot.phase}`}>
      <header className="lesson-top">
        {back}
        <div className="lesson-top__title">
          <span className="eyebrow">Phòng đố vui · {snapshot.title}</span>
          <strong>{heading}</strong>
        </div>
        {!ended && snapshot.me.state === 'joined' && (
          <div className="room-top__tools">
            {confirmEnd ? (
              <>
                <span className="meta">{snapshot.me.is_host ? 'Phòng sẽ dừng với mọi người.' : ''}</span>
                <button type="button" className="btn btn--danger btn--sm" onClick={() => act(snapshot.me.is_host ? 'close' : 'leave')}>
                  {snapshot.me.is_host ? 'Đóng phòng' : 'Rời phòng'}
                </button>
                <button type="button" className="btn btn--ghost btn--sm" onClick={() => setConfirmEnd(false)}>
                  Thôi
                </button>
              </>
            ) : (
              <button type="button" className="btn btn--ghost btn--sm" disabled={busy !== null} onClick={() => act(snapshot.me.is_host ? 'close' : 'leave')}>
                <Icon name="exit" size={16} /> {snapshot.me.is_host ? 'Đóng phòng' : 'Rời phòng'}
              </button>
            )}
          </div>
        )}
        <span className="coin-chip" title="Điểm của bạn trong phòng">
          <Icon name="trophy" size={17} />
          {me?.score ?? 0}
        </span>
        <div className="lesson-top__bar" aria-hidden="true">
          <span style={{ width: `${snapshot.question_count ? Math.round((snapshot.closed_count / snapshot.question_count) * 100) : 0}%` }} />
        </div>
      </header>

      {error != null && !ended && (
        <p className="notice notice--butter room-reconnect" role="status">
          Mất kết nối với phòng, đang thử lại… Đáp án đã gửi vẫn được giữ.
        </p>
      )}

      <main className="room-main" id="main">
        {snapshot.phase === 'lobby' && <Lobby roomId={roomId} snapshot={snapshot} busy={busy} act={act} />}
        {playing && snapshot.question && (
          <div className="room-play">
            {snapshot.phase === 'question_open' ? (
              <QuestionStage key={snapshot.question.id} roomId={roomId} snapshot={snapshot} left={left} busy={busy} act={act} onSent={() => void refresh()} />
            ) : (
              <RevealStage key={`${snapshot.question.id}-reveal`} snapshot={snapshot} left={left} busy={busy} act={act} />
            )}
            <aside className="panel-card room-board">
              <h2 className="title-m">Bảng điểm</h2>
              <Players board={snapshot.scoreboard} meId={snapshot.me.member_id} scores />
              <p className="meta">Điểm cộng khi mỗi câu đóng lại.</p>
            </aside>
          </div>
        )}
        {ended && <RoomEnd roomId={roomId} snapshot={snapshot} />}
      </main>
    </div>
  );
}
