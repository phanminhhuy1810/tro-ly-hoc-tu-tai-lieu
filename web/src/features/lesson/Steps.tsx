import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import type { Course, GradeResult, HelpReply, Question, SessionResult } from '../../api/types';
import { hrefFor } from '../../app/router';
import { useApp } from '../../app/store';
import { Icon } from '../../components/Icon';
import { Mascot } from '../../components/Mascot';
import { ProblemNotice } from '../../components/StateViews';
import { applyHint, hintEffect, hintMessage, isMalformed, missingAnswer, noHint, type Draft, type HintEffect } from '../../lib/answers';
import { describeError, type Problem } from '../../lib/copy';
import { fixedHelp } from './help';
import { FOCUS_HELP } from './HelpPanel';
import { kindLabel, QuestionView } from './QuestionView';
import { useTextFix } from './textFix';

/* Check ------------------------------------------------------------------- */
function answerText(question: Question, draft: Draft): string | null {
  if (draft.kind === 'mcq') return question.payload.options.find((o) => o.id === draft.optionId)?.text ?? null;
  if (draft.kind === 'cloze' || draft.kind === 'short_answer') return draft.text;
  return null;
}

function Feedback({
  question,
  draft,
  result,
  reviewTitle,
  onReview,
  sessionId,
  course,
}: {
  question: Question;
  draft: Draft;
  result: GradeResult;
  reviewTitle: string | null;
  onReview: () => void;
  sessionId: string;
  course: Course;
}) {
  const { toast } = useApp();
  const fix = useTextFix();
  const [saved, setSaved] = useState(false);
  const [reported, setReported] = useState(false);
  // Saved keys can be wrong (AI-made). The learner must be able to push back instead of being told they are wrong.
  const report = async () => {
    try {
      await api(`/courses/${course.id}/question-reports`, {
        body: { expected_revision: course.revision, unit_id: question.unit_id, item_id: question.id, reason: 'Người học cho rằng đáp án lưu chưa đúng hoặc mâu thuẫn với lời giải.' },
      });
      setReported(true);
      toast('Đã báo để người tạo khóa xem lại câu này');
    } catch (error) {
      toast(describeError(error).title);
    }
  };
  const mine = answerText(question, draft);
  const reference = Array.isArray(result.reference) ? null : result.reference;
  const saveCard = async () => {
    try {
      await api('/cards/from-question', { body: { session_id: sessionId, item_id: question.id } });
      setSaved(true);
      toast('Đã lưu câu này thành thẻ');
    } catch (error) {
      toast(describeError(error).title);
    }
  };
  if (result.correct === null) {
    return (
      <div className="feedback feedback--self enter" role="status">
        <p className="feedback__title">Tự đối chiếu với đáp án tham khảo</p>
        {reference && <p className="feedback__ref">{fix(reference)}</p>}
        {result.rubric.length > 0 && (
          <ul className="criteria">
            {result.rubric.map((r) => (
              <li key={r}>
                <Icon name="check" size={16} /> {r}
              </li>
            ))}
          </ul>
        )}
        <p className="meta">Câu tự luận không được chấm tự động. Đọc lại câu của bạn và xem đã có đủ các ý trên chưa.</p>
      </div>
    );
  }
  return (
    <div className={`feedback ${result.correct ? 'feedback--right' : 'feedback--wrong'} enter`} role="status">
      <div className="feedback__head">
        {result.correct ? <Mascot mood="happy" size={52} /> : null}
        <div>
          <p className="feedback__title">{result.correct ? 'Chính xác!' : 'Chưa đúng — xem lại một chút nhé'}</p>
          {!result.correct && mine && <p className="meta">Bạn trả lời: {fix(mine)}</p>}
          {!result.correct && reference && (
            <p className="feedback__ref">
              Đáp án: <strong>{fix(reference)}</strong>
            </p>
          )}
        </div>
      </div>
      <p>{fix(result.explanation)}</p>
      {!result.correct && (
        <div className="feedback__actions">
          {reviewTitle && (
            <button type="button" className="link" onClick={onReview}>
              <Icon name="arrowLeft" size={15} /> Đọc lại phần “{reviewTitle}”
            </button>
          )}
          <button type="button" className="chip" onClick={saveCard} disabled={saved}>
            <Icon name={saved ? 'check' : 'save'} size={15} /> {saved ? 'Đã lưu thành thẻ' : 'Lưu câu này thành thẻ'}
          </button>
          <button type="button" className="link link--quiet" onClick={report} disabled={reported}>
            <Icon name="flag" size={15} /> {reported ? 'Đã báo đáp án' : 'Đáp án này có vẻ sai?'}
          </button>
        </div>
      )}
    </div>
  );
}

export function CheckStep({
  question,
  position,
  draft,
  result,
  sessionId,
  course,
  reviewTitle,
  onDraft,
  onSubmit,
  onNext,
  onReview,
  nextLabel,
}: {
  question: Question;
  position: { index: number; total: number };
  draft: Draft;
  result?: GradeResult;
  sessionId: string;
  course: Course;
  reviewTitle: string | null;
  onDraft: (draft: Draft) => void;
  onSubmit: (draft: Draft) => Promise<GradeResult>;
  onNext: () => void;
  onReview: () => void;
  nextLabel: string;
}) {
  const { toast } = useApp();
  const fix = useTextFix();
  const [effect, setEffect] = useState<HintEffect>(noHint);
  const [hint, setHint] = useState<HelpReply | null>(null);
  const [solution, setSolution] = useState<HelpReply | null>(null);
  const [missing, setMissing] = useState<string | null>(null);
  const [busy, setBusy] = useState<'hint' | 'solution' | 'check' | null>(null);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [skipped, setSkipped] = useState(false);
  const malformed = isMalformed(question);
  const target = { kind: 'question' as const, sessionId, itemId: question.id, label: '' };

  useEffect(() => {
    setEffect(noHint());
    setHint(null);
    setSolution(null);
    setMissing(null);
    setProblem(null);
  }, [question.id]);

  const askHint = async () => {
    setBusy('hint');
    setProblem(null);
    try {
      const reply = await fixedHelp(target, 'hint');
      const next = hintEffect(reply);
      setEffect(next);
      setHint(reply);
      onDraft(applyHint(draft, next));
    } catch (error) {
      setProblem(describeError(error));
    } finally {
      setBusy(null);
    }
  };

  const showSolution = async () => {
    setBusy('solution');
    try {
      setSolution(await fixedHelp(target, 'explain'));
    } catch (error) {
      setProblem(describeError(error));
    } finally {
      setBusy(null);
    }
  };

  const check = async () => {
    const why = missingAnswer(question, draft);
    if (why) {
      setMissing(why);
      return;
    }
    setBusy('check');
    setProblem(null);
    try {
      await onSubmit(draft);
    } catch (error) {
      setProblem(describeError(error));
    } finally {
      setBusy(null);
    }
  };

  const report = async () => {
    try {
      await api(`/courses/${course.id}/question-reports`, {
        body: { expected_revision: course.revision, unit_id: question.unit_id, item_id: question.id, reason: 'Câu không ghép/sắp được như đề yêu cầu (người học báo từ màn học).' },
      });
      toast('Đã báo câu này cho người tạo khóa');
    } catch (error) {
      toast(describeError(error).title);
    }
  };

  return (
    <article className="step step--check">
      <p className="eyebrow">
        Câu {position.index}/{position.total} · {kindLabel(question.kind)}
      </p>
      <h2 className="question-prompt">{question.kind === 'cloze' ? 'Điền vào chỗ trống' : fix(question.prompt)}</h2>

      {malformed ? (
        <div className="notice notice--butter">
          <Icon name="flag" />
          <div style={{ display: 'grid', gap: 8 }}>
            <p className="notice__title">Câu này đang có lỗi dữ liệu nên chưa làm được</p>
            <p className="notice__body">Hai cột ghép không khớp số lượng. Bạn có thể báo để người tạo sửa, rồi đi tiếp.</p>
            <div style={{ display: 'flex', gap: 8 }}>
              <button type="button" className="btn btn--secondary btn--sm" onClick={report}>
                Báo câu lỗi
              </button>
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                onClick={() => {
                  setSkipped(true);
                  onNext();
                }}
              >
                Bỏ qua câu này
              </button>
            </div>
          </div>
        </div>
      ) : (
        <QuestionView
          question={question}
          draft={draft}
          effect={effect}
          result={result}
          locked={Boolean(result) || busy === 'check'}
          onChange={(next) => {
            setMissing(null);
            onDraft(next);
          }}
        />
      )}

      {hint && !result && (
        <p className="hint-note enter" role="status">
          <Icon name="bulb" size={16} />
          {hintMessage(effect, hint.step)}
        </p>
      )}
      {solution && !result && (
        <div className="solution enter">
          <p className="feedback__title">Lời giải đã lưu</p>
          <p>{fix(solution.text ?? '')}</p>
          {solution.reference !== undefined && !Array.isArray(solution.reference) && (
            <p className="feedback__ref">
              Đáp án: <strong>{fix(solution.reference)}</strong>
            </p>
          )}
          <p className="meta">Bạn vẫn trả lời được; câu này sẽ ghi là đã xem trợ giúp.</p>
        </div>
      )}
      {result && <Feedback question={question} draft={draft} result={result} reviewTitle={reviewTitle} onReview={onReview} sessionId={sessionId} course={course} />}
      {problem && <ProblemNotice problem={problem} compact />}

      {!malformed && (
        <footer className="step__foot">
          <div className="step__chips">
            {!result && (
              <>
                <button type="button" className="chip" onClick={askHint} disabled={busy !== null} aria-busy={busy === 'hint'}>
                  <Icon name="bulb" size={16} /> {hint ? 'Gợi ý thêm' : 'Gợi ý'}
                </button>
                {(hint || solution) && !solution && (
                  <button type="button" className="chip" onClick={showSolution} disabled={busy !== null}>
                    <Icon name="eye" size={16} /> Vẫn bí? Xem lời giải
                  </button>
                )}
              </>
            )}
            <button type="button" className="chip" onClick={() => window.dispatchEvent(new Event(FOCUS_HELP))}>
              <Icon name="message" size={16} /> Hỏi Kẹp
            </button>
          </div>
          <div className="step__cta">
            {missing && (
              <span className="missing" role="alert">
                {missing}
              </span>
            )}
            {result || skipped ? (
              <button type="button" className="btn btn--primary btn--lg" onClick={onNext} autoFocus>
                {nextLabel} <Icon name="arrowRight" size={18} />
              </button>
            ) : (
              <button type="button" className="btn btn--primary btn--lg" onClick={check} aria-busy={busy === 'check'}>
                {busy === 'check' ? 'Đang chấm…' : 'Kiểm tra'}
              </button>
            )}
          </div>
        </footer>
      )}
    </article>
  );
}

/* Result ------------------------------------------------------------------ */
function SaveWrongCards({ wrong, sessionId }: { wrong: Question[]; sessionId: string }) {
  const { toast } = useApp();
  const fix = useTextFix();
  const [picked, setPicked] = useState<Set<string>>(() => new Set(wrong.map((q) => q.id)));
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState(false);
  const save = async () => {
    setSaving(true);
    let count = 0;
    for (const id of picked) {
      try {
        await api('/cards/from-question', { body: { session_id: sessionId, item_id: id } });
        count += 1;
      } catch {
        /* Keep going; the toast reports what was saved. */
      }
    }
    setSaving(false);
    setDone(true);
    toast(`Đã lưu ${count} thẻ để ôn lại`);
  };
  if (done) return null;
  return (
    <section className="save-cards">
      <p className="title-m">Lưu câu chưa đúng thành thẻ?</p>
      <p className="meta">Thẻ giúp bạn ôn lại đúng chỗ còn vướng. Bỏ chọn câu bạn không cần.</p>
      {wrong.map((q) => (
        <label key={q.id} className="check-row">
          <input
            type="checkbox"
            checked={picked.has(q.id)}
            onChange={() =>
              setPicked((set) => {
                const next = new Set(set);
                if (next.has(q.id)) next.delete(q.id);
                else next.add(q.id);
                return next;
              })
            }
          />
          <span>{fix(q.prompt)}</span>
        </label>
      ))}
      <div>
        <button type="button" className="btn btn--secondary btn--sm" onClick={save} disabled={!picked.size || saving} aria-busy={saving}>
          <Icon name="save" size={16} /> Lưu {picked.size} thẻ
        </button>
      </div>
    </section>
  );
}

export function ResultStep({
  course,
  unitIndex,
  sessionId,
  weak,
  wrong,
  unanswered,
  onJump,
}: {
  course: Course;
  unitIndex: number | null;
  sessionId: string | null;
  weak: boolean;
  wrong: Question[];
  unanswered: number;
  onJump: () => void;
}) {
  const { refreshWallet } = useApp();
  const wrongCount = wrong.length;
  const [result, setResult] = useState<SessionResult | null>(null);
  const [next, setNext] = useState<{ href: string; label: string } | null>(null);
  const [problem, setProblem] = useState<Problem | null>(null);

  useEffect(() => {
    if (!sessionId || unanswered > 0) return;
    let alive = true;
    (async () => {
      const value = await api<SessionResult>(`/sessions/${sessionId}/complete`, { method: 'POST' });
      if (!alive) return;
      setResult(value);
      refreshWallet();
      if (unitIndex === null) return;
      const fresh = await api<Course>(`/courses/${course.id}`);
      const following = fresh.content.units[unitIndex + 1];
      if (following && following.unlocked !== false) {
        sessionStorage.setItem('folio.justUnlocked', following.id);
        setNext(
          following.data
            ? { href: hrefFor({ name: 'lesson', courseId: course.id, unitId: following.id, mode: 'learn' }), label: `Học bài ${unitIndex + 2}` }
            : { href: hrefFor({ name: 'course', courseId: course.id }), label: `Tạo bài ${unitIndex + 2}` },
        );
      }
    })().catch((error) => alive && setProblem(describeError(error)));
    return () => {
      alive = false;
    };
  }, [sessionId, unanswered, unitIndex, course.id, refreshWallet]);

  if (unanswered > 0) {
    return (
      <article className="step step--result">
        <Mascot mood="hint" size={96} />
        <h2 className="display-title">Còn {unanswered} câu chưa trả lời</h2>
        <p className="body-l">Trả lời hết các câu thì lượt luyện mới được ghi lại và bài sau mới mở.</p>
        <button type="button" className="btn btn--primary btn--lg" onClick={onJump}>
          Làm câu còn thiếu
        </button>
      </article>
    );
  }

  const coin = (result?.rewards ?? []).filter((r) => !r.replayed).reduce((sum, r) => sum + (r.amount ?? 0), 0);
  const back = hrefFor({ name: 'course', courseId: course.id });
  return (
    <article className="step step--result">
      <Mascot mood="happy" size={112} pettable />
      <p className="eyebrow">{weak ? 'Xong lượt ôn' : unitIndex !== null ? `Xong bài ${unitIndex + 1}` : 'Xong'}</p>
      {problem && <ProblemNotice problem={problem} compact />}
      {!result && !problem && <div className="skeleton" style={{ height: 40, width: 260 }} />}
      {result && (
        <>
          <h2 className="display-title result__score">
            {result.score}/{result.fixed_total} câu đúng
          </h2>
          <p className="body-l">
            {result.self_review_count ? `${result.self_review_count} câu tự luận để bạn tự đối chiếu. ` : ''}
            {coin > 0 ? `+${coin} Coin cho lượt luyện này.` : ''}
          </p>
        </>
      )}
      <div className="result__actions">
        {next ? (
          <a className="btn btn--primary btn--lg" href={next.href}>
            {next.label} <Icon name="arrowRight" size={18} />
          </a>
        ) : (
          <a className="btn btn--primary btn--lg" href={back}>
            Về lộ trình <Icon name="arrowRight" size={18} />
          </a>
        )}
        {next && (
          <a className="btn btn--secondary btn--lg" href={back}>
            Về lộ trình
          </a>
        )}
        {wrongCount > 0 && !weak && (
          <a className="btn btn--secondary btn--lg" href={hrefFor({ name: 'lesson', courseId: course.id, unitId: course.content.units[unitIndex ?? 0]?.id ?? 'tat-ca', mode: 'weak' })}>
            Ôn {wrongCount} câu sai
          </a>
        )}
      </div>
      {wrong.length > 0 && sessionId && <SaveWrongCards wrong={wrong} sessionId={sessionId} />}
    </article>
  );
}
