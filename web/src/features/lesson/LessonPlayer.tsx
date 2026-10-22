import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../../api/client';
import type { GradeResult, Question, SourceFragment, Unit } from '../../api/types';
import { hrefFor } from '../../app/router';
import { useApp } from '../../app/store';
import { useStudyPulse } from '../../app/usePulse';
import { Icon } from '../../components/Icon';
import { Mascot } from '../../components/Mascot';
import { EmptyState, LoadingRows, ProblemNotice } from '../../components/StateViews';
import { draftFrom, emptyDraft, type Draft } from '../../lib/answers';
import { describeError } from '../../lib/copy';
import type { Phase } from '../../lib/lessonFlow';
import { makeTextFix } from '../../lib/text';
import { HelpPanel } from './HelpPanel';
import { LearnChat } from './LearnChat';
import { CheckStep, ResultStep } from './Steps';
import { TextFixProvider } from './textFix';
import { rememberRead, saveLearnPosition, useLessonSession } from './useLessonSession';

function unitTexts(units: Unit[]): string[] {
  return units.flatMap((unit) => [
    unit.title,
    unit.objective ?? '',
    ...(unit.data?.sections ?? []).flatMap((s) => [s.title, s.text]),
    ...(unit.data?.mindmap ?? []).flatMap((s) => [s.title, s.text]),
    ...(unit.data?.cards ?? []).flatMap((c) => [c.front, c.back]),
  ]);
}

function PhaseSteps({ phase, weak, onPick }: { phase: Phase; weak: boolean; onPick: (phase: Phase) => void }) {
  const all: [Phase, string][] = weak
    ? [
        ['practice', 'Luyện tập'],
        ['result', 'Kết quả'],
      ]
    : [
        ['learn', 'Học hiểu'],
        ['practice', 'Luyện tập'],
        ['result', 'Kết quả'],
      ];
  const at = all.findIndex(([p]) => p === phase);
  return (
    <nav className="phase-steps" aria-label="Các bước của bài">
      {all.map(([value, label], i) => (
        <button
          key={value}
          type="button"
          className={`phase-step${i < at ? ' is-done' : ''}${i === at ? ' is-current' : ''}`}
          aria-current={i === at ? 'step' : undefined}
          onClick={() => onPick(value)}
        >
          <span className="phase-step__num">{i < at ? <Icon name="check" size={14} /> : i + 1}</span>
          {label}
        </button>
      ))}
    </nav>
  );
}

function QuestionDots({ order, index, feedback, onPick }: { order: string[]; index: number; feedback: Record<string, GradeResult>; onPick: (i: number) => void }) {
  return (
    <div className="q-dots" role="tablist" aria-label="Các câu luyện tập">
      {order.map((id, i) => {
        const result = feedback[id];
        const state = result ? (result.correct === false ? 'is-wrong' : result.correct === null ? 'is-self' : 'is-right') : '';
        return (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={i === index}
            className={`q-dot ${state}${i === index ? ' is-current' : ''}`}
            aria-label={`Câu ${i + 1}${result ? (result.correct === false ? ', chưa đúng' : result.correct === null ? ', tự đối chiếu' : ', đúng') : ''}`}
            onClick={() => onPick(i)}
          >
            {i + 1}
          </button>
        );
      })}
    </div>
  );
}

export function LessonPlayer({ courseId, unitId, weak }: { courseId: string; unitId: string; weak: boolean }) {
  const { wallet, toast } = useApp();
  const { data, error, reload, submit, saveDraft } = useLessonSession(courseId, unitId, weak);
  const [phase, setPhase] = useState<Phase>('learn');
  const [revealed, setRevealed] = useState(1);
  const [recap, setRecap] = useState(false);
  const [qIndex, setQIndex] = useState(0);
  const [focusSection, setFocusSection] = useState<number | null>(null);
  const [askSkip, setAskSkip] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [fragments, setFragments] = useState<Map<string, SourceFragment>>(new Map());
  const timers = useRef<Record<string, number>>({});

  const questions = useMemo(() => new Map((data?.session?.questions ?? []).map((q) => [q.id, q])), [data?.session]);
  // Study time and "đã đọc" for Tiến độ: the lesson's unit, or one unit for a mistake review across lessons
  // (time is credited only while course, unit and mode stay put).
  const pulseUnit = data?.unit?.id ?? data?.session?.questions[0]?.unit_id;
  useStudyPulse(data && pulseUnit && phase !== 'result' ? { courseId: data.course.id, unitId: pulseUnit, revision: data.course.revision, mode: phase === 'learn' ? 'learn' : 'practice' } : null);
  const fix = useMemo(() => makeTextFix(unitTexts(data ? (data.unit ? [data.unit] : data.units) : [])), [data]);

  // Position and drafts once per loaded session.
  useEffect(() => {
    if (!data) return;
    setPhase(data.start.phase);
    setRevealed(data.start.revealed);
    setRecap(data.start.recap);
    setQIndex(data.start.questionIndex);
    const initial: Record<string, Draft> = {};
    for (const q of data.session?.questions ?? []) {
      const saved = data.answered[q.id] ?? data.drafts[q.id]?.answer;
      initial[q.id] = saved === undefined ? emptyDraft(q) : draftFrom(q, saved as never);
    }
    setDrafts(initial);
  }, [data?.session?.id, data?.course.revision]);

  useEffect(() => {
    if (!data?.unit) return;
    api<SourceFragment[]>(`/courses/${courseId}/source-fragments?unit_id=${encodeURIComponent(data.unit.id)}`)
      .then((list) => setFragments(new Map(list.map((f) => [f.id, f]))))
      .catch(() => setFragments(new Map()));
  }, [courseId, data?.unit?.id]);

  const onDraft = useCallback(
    (itemId: string, draft: Draft) => {
      setDrafts((all) => ({ ...all, [itemId]: draft }));
      window.clearTimeout(timers.current[itemId]);
      timers.current[itemId] = window.setTimeout(() => void saveDraft(itemId, draft), 700);
    },
    [saveDraft],
  );

  const onSubmit = useCallback(
    async (itemId: string, draft: Draft): Promise<GradeResult> => {
      window.clearTimeout(timers.current[itemId]);
      return submit(itemId, draft);
    },
    [submit],
  );

  if (error) {
    return (
      <div className="lesson-shell">
        <div className="page">
          <a className="back" href={hrefFor({ name: 'course', courseId })}>
            <Icon name="arrowLeft" size={18} /> Lộ trình
          </a>
          <ProblemNotice problem={describeError(error)} onRetry={reload} />
        </div>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="lesson-shell">
        <div className="page" style={{ maxWidth: 720, paddingTop: 80 }}>
          <LoadingRows rows={2} label="Đang mở bài…" />
        </div>
      </div>
    );
  }

  const course = data.course;
  const courseHref = hrefFor({ name: 'course', courseId: course.id });
  if (!weak && (!data.unit || !data.unit.data)) {
    return (
      <div className="lesson-shell">
        <EmptyState
          art={<Mascot mood="hint" size={110} />}
          title="Bài này chưa được tạo"
          body="Mở lộ trình để tạo bài khi bạn sẵn sàng. Các bài đã có vẫn học được."
          action={
            <a className="btn btn--primary btn--lg" href={courseHref}>
              Về lộ trình
            </a>
          }
        />
      </div>
    );
  }
  if (!data.session && weak) {
    return (
      <div className="lesson-shell">
        <EmptyState
          art={<Mascot mood="happy" size={110} />}
          title="Chưa có câu sai để ôn"
          body={data.sessionNote ?? 'Khi bạn làm sai một câu, nó sẽ có ở đây để ôn lại.'}
          action={
            <a className="btn btn--primary btn--lg" href={courseHref}>
              Về lộ trình
            </a>
          }
        />
      </div>
    );
  }

  const unit = data.unit;
  const sections = unit?.data?.sections ?? [];
  const order = data.order;
  const currentId = order[qIndex];
  const current = currentId ? questions.get(currentId) : undefined;
  const unitIndex = unit ? course.content.units.findIndex((u) => u.id === unit.id) : null;
  const wrong: Question[] = order.filter((id) => data.feedback[id]?.correct === false).map((id) => questions.get(id)!).filter(Boolean);
  const unanswered = order.filter((id) => !data.feedback[id]).length;
  const answeredAny = order.length - unanswered > 0;

  const sectionFor = (question: Question | undefined): number | null => {
    if (!question) return null;
    const refs = new Set(question.source_refs);
    let last: number | null = null;
    sections.forEach((section, i) => {
      if (section.source_refs.some((ref) => refs.has(ref))) last = i;
    });
    return last;
  };

  const markRead = (index: number) => {
    if (!unit) return;
    rememberRead(course.id, unit.id, course.revision, index);
    void saveLearnPosition(course, unit.id, index);
  };

  const goPractice = () => {
    setAskSkip(false);
    setPhase('practice');
    window.scrollTo({ top: 0 });
  };

  const pickPhase = (next: Phase) => {
    if (next === phase) return;
    if (next === 'learn') {
      setFocusSection(null);
      setPhase('learn');
    } else if (next === 'practice') {
      if (recap || answeredAny || weak) goPractice();
      else setAskSkip(true);
    } else if (unanswered === 0) setPhase('result');
    else toast(`Còn ${unanswered} câu chưa làm — làm xong thì xem được kết quả.`);
  };

  const progress =
    phase === 'learn' ? (sections.length ? (Math.min(revealed - 1, sections.length) + (recap ? 1 : 0)) / sections.length : 1) : order.length ? (order.length - unanswered) / order.length : 1;

  return (
    <TextFixProvider value={fix}>
      <div className={`lesson-shell lesson-shell--${phase}`}>
        <header className="lesson-top">
          <a className="back back--bar" href={courseHref}>
            <Icon name="arrowLeft" size={18} />
            <span>Lộ trình</span>
          </a>
          <div className="lesson-top__title">
            <span className="eyebrow">{weak ? 'Ôn câu sai' : `Bài ${(unitIndex ?? 0) + 1} · ${course.content.title}`}</span>
            <strong>{weak ? `${order.length} câu cần ôn` : fix(unit!.title)}</strong>
          </div>
          <PhaseSteps phase={phase} weak={weak} onPick={pickPhase} />
          <span className="coin-chip" title="Coin dùng cho lượt hỏi AI">
            <Icon name="coin" size={17} />
            {wallet ? wallet.available : '—'}
          </span>
          <div className="lesson-top__bar" aria-hidden="true">
            <span style={{ width: `${Math.round(progress * 100)}%` }} />
          </div>
        </header>

        {askSkip && (
          <div className="skip-ask enter" role="dialog" aria-label="Vào luyện tập sớm">
            <Mascot mood="hint" size={56} />
            <div>
              <p className="title-m">Còn {sections.length - Math.min(revealed - 1, sections.length) - (recap ? 1 : 0)} phần chưa đọc xong</p>
              <p className="meta">Luyện tập dễ hơn khi đã đọc hết. Bạn vẫn có thể vào luyện tập ngay.</p>
            </div>
            <button type="button" className="btn btn--secondary btn--sm" onClick={() => setAskSkip(false)}>
              Đọc tiếp
            </button>
            <button type="button" className="btn btn--primary btn--sm" onClick={goPractice}>
              Vẫn vào luyện tập
            </button>
          </div>
        )}

        {phase === 'learn' && unit?.data && (
          <LearnChat
            course={course}
            unit={unit}
            revealed={revealed}
            recap={recap}
            fragments={fragments}
            questionCount={order.length}
            focusSection={focusSection}
            onReveal={(count) => {
              markRead(count - 2);
              setRevealed(count);
            }}
            onRecap={() => {
              markRead(sections.length - 1);
              setRecap(true);
            }}
            onPractice={goPractice}
          />
        )}

        {phase === 'practice' && current && data.session && (
          <div className="practice">
            <main className="practice__main" id="main">
              <QuestionDots order={order} index={qIndex} feedback={data.feedback} onPick={setQIndex} />
              <div className="lesson-card" key={current.id}>
                <CheckStep
                  question={current}
                  position={{ index: qIndex + 1, total: order.length }}
                  draft={drafts[current.id] ?? emptyDraft(current)}
                  result={data.feedback[current.id]}
                  sessionId={data.session.id}
                  course={course}
                  reviewTitle={(() => {
                    const index = sectionFor(current);
                    return index === null ? null : sections[index]?.title ?? null;
                  })()}
                  nextLabel={qIndex < order.length - 1 ? 'Câu tiếp' : 'Xem kết quả'}
                  onDraft={(d) => onDraft(current.id, d)}
                  onSubmit={(d) => onSubmit(current.id, d)}
                  onNext={() => {
                    const following = order.findIndex((id, i) => i > qIndex && !data.feedback[id]);
                    if (qIndex < order.length - 1) setQIndex(following >= 0 ? following : qIndex + 1);
                    else setPhase('result');
                    window.scrollTo({ top: 0, behavior: 'smooth' });
                  }}
                  onReview={() => {
                    const index = sectionFor(current);
                    if (index === null) return;
                    setRevealed((r) => Math.max(r, index + 1));
                    setFocusSection(index);
                    setPhase('learn');
                  }}
                />
              </div>
            </main>
            <HelpPanel
              key={current.id}
              target={{ kind: 'question', sessionId: data.session.id, itemId: current.id, label: `Câu ${qIndex + 1} · ${current.prompt}` }}
              answered={Boolean(data.feedback[current.id])}
            />
          </div>
        )}

        {phase === 'result' && (
          <div className="result-wrap">
            <div className="lesson-card">
              <ResultStep
                course={course}
                unitIndex={weak ? null : unitIndex}
                sessionId={data.session?.id ?? null}
                weak={weak}
                wrong={wrong}
                unanswered={unanswered}
                onJump={() => {
                  setQIndex(Math.max(0, order.findIndex((id) => !data.feedback[id])));
                  setPhase('practice');
                }}
              />
            </div>
          </div>
        )}
      </div>
    </TextFixProvider>
  );
}
