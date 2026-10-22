import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api, ApiError, ensureSession } from '../../api/client';
import type { Course, GradeResult, PracticeSession, Question, SessionResult } from '../../api/types';
import { hrefFor } from '../../app/router';
import { useApp } from '../../app/store';
import { useStudyPulse } from '../../app/usePulse';
import { Icon } from '../../components/Icon';
import { Mascot } from '../../components/Mascot';
import { LoadingRows, ProblemNotice } from '../../components/StateViews';
import { draftFrom, emptyDraft, missingAnswer, noHint, toAnswer, type Draft } from '../../lib/answers';
import { describeError, type Problem } from '../../lib/copy';
import { makeTextFix } from '../../lib/text';
import { HelpPanel } from '../lesson/HelpPanel';
import { kindLabel, QuestionView } from '../lesson/QuestionView';
import { CheckStep } from '../lesson/Steps';
import { TextFixProvider, useTextFix } from '../lesson/textFix';

interface Loaded {
  course: Course;
  session: PracticeSession;
}

function Dots({ questions, index, done, feedback, onPick }: { questions: Question[]; index: number; done: Set<string>; feedback: Record<string, GradeResult>; onPick: (i: number) => void }) {
  return (
    <div className="q-dots" role="tablist" aria-label="Các câu">
      {questions.map((q, i) => {
        const result = feedback[q.id];
        const state = result ? (result.correct === false ? 'is-wrong' : result.correct === null ? 'is-self' : 'is-right') : done.has(q.id) ? 'is-saved' : '';
        return (
          <button key={q.id} type="button" role="tab" aria-selected={i === index} className={`q-dot ${state}${i === index ? ' is-current' : ''}`} onClick={() => onPick(i)}>
            {i + 1}
          </button>
        );
      })}
    </div>
  );
}

/** Test question: the answer is saved (and can be changed) but graded only when the test is submitted. */
function ExamStep({ question, position, draft, saved, onDraft, onSave }: { question: Question; position: string; draft: Draft; saved: boolean; onDraft: (d: Draft) => void; onSave: () => Promise<void> }) {
  const fix = useTextFix();
  const [busy, setBusy] = useState(false);
  const [missing, setMissing] = useState<string | null>(null);
  const save = async () => {
    const why = missingAnswer(question, draft);
    if (why) return setMissing(why);
    setBusy(true);
    try {
      await onSave();
    } finally {
      setBusy(false);
    }
  };
  return (
    <article className="step step--check">
      <p className="eyebrow">
        {position} · {kindLabel(question.kind)}
      </p>
      <h2 className="question-prompt">{question.kind === 'cloze' ? 'Điền vào chỗ trống' : fix(question.prompt)}</h2>
      <QuestionView
        question={question}
        draft={draft}
        effect={noHint()}
        onChange={(next) => {
          setMissing(null);
          onDraft(next);
        }}
      />
      <footer className="step__foot">
        <span className={saved ? 'tag tag--sage' : 'meta'}>{saved ? 'Đã lưu đáp án — vẫn đổi được trước khi nộp' : 'Chưa lưu đáp án'}</span>
        <div className="step__cta">
          {missing && (
            <span className="missing" role="alert">
              {missing}
            </span>
          )}
          <button type="button" className={saved ? 'btn btn--secondary btn--lg' : 'btn btn--primary btn--lg'} onClick={() => void save()} aria-busy={busy} disabled={busy}>
            {saved ? 'Lưu lại' : 'Lưu đáp án'} <Icon name="arrowRight" size={18} />
          </button>
        </div>
      </footer>
    </article>
  );
}

/** Every question with the learner's answer and the saved solution, after a round ends. */
function Review({ questions, session }: { questions: Question[]; session: PracticeSession }) {
  const fix = useTextFix();
  return (
    <ol className="review-list">
      {questions.map((q, i) => {
        const saved = session.answers?.[q.id];
        const result = saved?.feedback ?? undefined;
        const draft = saved ? draftFrom(q, saved.answer) : emptyDraft(q);
        const reference = result && !Array.isArray(result.reference) ? result.reference : null;
        return (
          <li key={q.id} className={`review-item${result?.correct === false ? ' is-wrong' : result?.correct ? ' is-right' : ''}`}>
            <p className="eyebrow">
              Câu {i + 1} · {kindLabel(q.kind)} · {result?.correct === null ? 'tự đối chiếu' : result?.correct ? 'đúng' : 'chưa đúng'}
            </p>
            <p className="review-item__prompt">{q.kind === 'cloze' ? 'Điền vào chỗ trống' : fix(q.prompt)}</p>
            <QuestionView question={q} draft={draft} effect={noHint()} result={result} locked onChange={() => undefined} />
            {reference && result?.correct !== true && (
              <p className="feedback__ref">
                Đáp án: <strong>{fix(reference)}</strong>
              </p>
            )}
            {result?.explanation && <p className="meta review-item__why">{fix(result.explanation)}</p>}
          </li>
        );
      })}
    </ol>
  );
}

export function PracticeRunner({ courseId, sessionId }: { courseId: string; sessionId: string }) {
  const { refreshWallet, toast, wallet } = useApp();
  const [data, setData] = useState<Loaded | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [index, setIndex] = useState(0);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [saved, setSaved] = useState<Set<string>>(new Set());
  const [feedback, setFeedback] = useState<Record<string, GradeResult>>({});
  const [result, setResult] = useState<SessionResult | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);
  const versions = useRef<Record<string, number>>({});
  const timers = useRef<Record<string, number>>({});

  const load = useCallback(async () => {
    await ensureSession();
    const [course, session] = await Promise.all([api<Course>(`/courses/${courseId}`), api<PracticeSession>(`/sessions/${sessionId}`)]);
    const answered = new Set(Object.keys(session.answers ?? {}));
    const graded: Record<string, GradeResult> = {};
    const initial: Record<string, Draft> = {};
    for (const q of session.questions) {
      const value = session.answers?.[q.id];
      if (value?.feedback) graded[q.id] = value.feedback;
      const stored = value?.answer ?? session.drafts?.[q.id]?.answer;
      initial[q.id] = stored === undefined ? emptyDraft(q) : draftFrom(q, stored as never);
      versions.current[q.id] = session.drafts?.[q.id]?.version ?? 0;
    }
    setDrafts(initial);
    setSaved(answered);
    setFeedback(graded);
    setResult(session.result ?? null);
    setIndex(Math.max(0, session.questions.findIndex((q) => !answered.has(q.id))));
    setData({ course, session });
  }, [courseId, sessionId]);

  useEffect(() => {
    load().catch(setError);
  }, [load]);

  const questions = data?.session.questions ?? [];
  const current = questions[index];
  const exam = Boolean(data?.session.exam);
  const status = data?.session.status;
  const fix = useMemo(
    () => makeTextFix((data?.course.content.units ?? []).flatMap((u) => [...(u.data?.sections ?? []).flatMap((s) => [s.title, s.text]), ...(u.data?.cards ?? []).flatMap((c) => [c.front, c.back])])),
    [data?.course],
  );
  // The server credits time only while course, unit and mode stay put, against the course as it is now
  // (the session keeps the revision it was built from), so one unit stands for the whole round.
  const pulseUnit = data?.session.questions[0]?.unit_id;
  useStudyPulse(data && pulseUnit && status === 'open' ? { courseId: data.course.id, unitId: pulseUnit, revision: data.course.revision, mode: 'practice' } : null);

  const onDraft = (itemId: string, draft: Draft) => {
    setDrafts((all) => ({ ...all, [itemId]: draft }));
    if (!data || feedback[itemId] || (!exam && saved.has(itemId))) return;
    window.clearTimeout(timers.current[itemId]);
    timers.current[itemId] = window.setTimeout(async () => {
      try {
        const out = await api<{ version: number }>(`/sessions/${data.session.id}/draft`, { method: 'PUT', body: { item_id: itemId, answer: toAnswer(draft), expected_version: versions.current[itemId] ?? 0 } });
        versions.current[itemId] = out.version;
      } catch {
        /* Draft saving is best effort; the answer itself is sent on Kiểm tra/Lưu. */
      }
    }, 700);
  };

  const submit = async (itemId: string, draft: Draft): Promise<GradeResult> => {
    if (!data) throw new Error('Chưa có lượt.');
    window.clearTimeout(timers.current[itemId]);
    const graded = await api<GradeResult>(`/sessions/${data.session.id}/answers`, { body: { item_id: itemId, answer: toAnswer(draft) } });
    setFeedback((all) => ({ ...all, [itemId]: graded }));
    setSaved((all) => new Set(all).add(itemId));
    return graded;
  };

  const saveExamAnswer = async (itemId: string) => {
    if (!data) return;
    window.clearTimeout(timers.current[itemId]);
    try {
      await api(`/sessions/${data.session.id}/answers`, { body: { item_id: itemId, answer: toAnswer(drafts[itemId]) } });
      const next = new Set(saved).add(itemId);
      setSaved(next);
      const following = questions.findIndex((q, i) => i > index && !next.has(q.id));
      const firstOpen = questions.findIndex((q) => !next.has(q.id));
      if (following >= 0) setIndex(following);
      else if (firstOpen >= 0) setIndex(firstOpen);
    } catch (error) {
      toast(describeError(error).title);
    }
  };

  const finish = async () => {
    if (!data) return;
    setSubmitting(true);
    setProblem(null);
    try {
      await api<SessionResult>(`/sessions/${data.session.id}/complete`, { method: 'POST' });
      refreshWallet();
      await load();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (error) {
      setProblem(describeError(error));
    } finally {
      setSubmitting(false);
    }
  };

  const cancel = async () => {
    if (!data || !window.confirm('Hủy lượt kiểm tra này? Các đáp án đã lưu sẽ không được chấm.')) return;
    try {
      await api(`/sessions/${data.session.id}/cancel`, { method: 'POST' });
      await load();
    } catch (error) {
      toast(error instanceof ApiError ? error.message : describeError(error).title);
    }
  };

  const back = hrefFor({ name: 'practice', courseId });
  if (error) {
    return (
      <div className="lesson-shell">
        <div className="page" style={{ paddingTop: 40 }}>
          <a className="back" href={back}>
            <Icon name="arrowLeft" size={18} /> Ôn luyện
          </a>
          <ProblemNotice problem={describeError(error)} onRetry={() => void load().catch(setError)} />
        </div>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="lesson-shell">
        <div className="page" style={{ maxWidth: 720, paddingTop: 80 }}>
          <LoadingRows rows={2} label="Đang mở lượt…" />
        </div>
      </div>
    );
  }

  const answeredCount = questions.filter((q) => saved.has(q.id)).length;
  const allAnswered = answeredCount === questions.length;
  const done = status === 'completed';

  return (
    <TextFixProvider value={fix}>
      <div className={`lesson-shell lesson-shell--${done ? 'result' : 'practice'}`}>
        <header className="lesson-top">
          <a className="back back--bar" href={back}>
            <Icon name="arrowLeft" size={18} />
            <span>Ôn luyện</span>
          </a>
          <div className="lesson-top__title">
            <span className="eyebrow">
              {exam ? 'Kiểm tra' : 'Luyện tập'} · {data.course.content.title}
            </span>
            <strong>
              {done ? 'Kết quả' : `${answeredCount}/${questions.length} câu đã ${exam ? 'lưu' : 'làm'}`}
            </strong>
          </div>
          {exam && status === 'open' ? (
            <button type="button" className="btn btn--ghost btn--sm" onClick={() => void cancel()}>
              Hủy lượt
            </button>
          ) : (
            <span />
          )}
          <span className="coin-chip" title="Coin dùng cho lượt hỏi AI">
            <Icon name="coin" size={17} />
            {wallet ? wallet.available : '—'}
          </span>
          <div className="lesson-top__bar" aria-hidden="true">
            <span style={{ width: `${questions.length ? Math.round((answeredCount / questions.length) * 100) : 0}%` }} />
          </div>
        </header>

        {status === 'cancelled' && (
          <div className="result-wrap">
            <div className="lesson-card step--result step">
              <Mascot mood="oops" size={96} />
              <p className="display-title">Lượt này đã hủy</p>
              <a className="btn btn--primary btn--lg" href={back}>
                Bắt đầu lượt khác
              </a>
            </div>
          </div>
        )}

        {done && (
          <div className="result-wrap">
            <section className="lesson-card step step--result">
              <Mascot mood="happy" size={100} />
              <p className="eyebrow">{exam ? 'Đã nộp bài kiểm tra' : 'Xong lượt luyện'}</p>
              {result && (
                <>
                  <h2 className="display-title result__score">
                    {result.score}/{result.fixed_total} câu đúng
                  </h2>
                  <p className="body-l">
                    {result.self_review_count ? `${result.self_review_count} câu tự luận để bạn tự đối chiếu. ` : ''}
                    {(result.rewards ?? []).filter((r) => !r.replayed).reduce((n, r) => n + (r.amount ?? 0), 0) > 0
                      ? `+${(result.rewards ?? []).filter((r) => !r.replayed).reduce((n, r) => n + (r.amount ?? 0), 0)} Coin.`
                      : ''}
                  </p>
                </>
              )}
              <div className="result__actions">
                <a className="btn btn--primary btn--lg" href={back}>
                  Lượt mới <Icon name="arrowRight" size={18} />
                </a>
                <a className="btn btn--secondary btn--lg" href={hrefFor({ name: 'course', courseId })}>
                  Về lộ trình
                </a>
              </div>
            </section>
            <h2 className="title-m review-title">Xem lại từng câu</h2>
            <Review questions={questions} session={data.session} />
          </div>
        )}

        {status === 'open' && current && (
          <div className={exam ? 'practice practice--exam' : 'practice'}>
            <main className="practice__main" id="main">
              <Dots questions={questions} index={index} done={saved} feedback={feedback} onPick={setIndex} />
              <div className="lesson-card" key={current.id}>
                {exam ? (
                  <ExamStep
                    question={current}
                    position={`Câu ${index + 1}/${questions.length}`}
                    draft={drafts[current.id] ?? emptyDraft(current)}
                    saved={saved.has(current.id)}
                    onDraft={(d) => onDraft(current.id, d)}
                    onSave={() => saveExamAnswer(current.id)}
                  />
                ) : (
                  <CheckStep
                    question={current}
                    position={{ index: index + 1, total: questions.length }}
                    draft={drafts[current.id] ?? emptyDraft(current)}
                    result={feedback[current.id]}
                    sessionId={data.session.id}
                    course={data.course}
                    reviewTitle={null}
                    nextLabel={index < questions.length - 1 ? 'Câu tiếp' : 'Xem tổng kết'}
                    onDraft={(d) => onDraft(current.id, d)}
                    onSubmit={(d) => submit(current.id, d)}
                    onNext={() => {
                      const following = questions.findIndex((q, i) => i > index && !feedback[q.id]);
                      if (following >= 0) setIndex(following);
                      else if (index < questions.length - 1) setIndex(index + 1);
                      window.scrollTo({ top: 0, behavior: 'smooth' });
                    }}
                    onReview={() => undefined}
                  />
                )}
              </div>
              <div className="submit-bar">
                <span className="meta">
                  {allAnswered ? 'Đã trả lời hết — nộp để xem kết quả.' : `Còn ${questions.length - answeredCount} câu chưa ${exam ? 'lưu' : 'làm'}.`}
                </span>
                {problem && <ProblemNotice problem={problem} compact />}
                <button type="button" className="btn btn--primary" disabled={!allAnswered || submitting} aria-busy={submitting} onClick={() => void finish()}>
                  {exam ? 'Nộp bài' : 'Nộp lượt'} <Icon name="check" size={18} />
                </button>
              </div>
            </main>
            {!exam && (
              <HelpPanel
                key={current.id}
                target={{ kind: 'question', sessionId: data.session.id, itemId: current.id, label: `Câu ${index + 1} · ${current.prompt}` }}
                answered={Boolean(feedback[current.id])}
              />
            )}
          </div>
        )}
      </div>
    </TextFixProvider>
  );
}
