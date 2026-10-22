import { useEffect, useMemo, useRef, useState } from 'react';
import { api, ApiError, ensureSession, newKey } from '../../api/client';
import type { Course, HistoryEntry, PracticeSession, QuestionKind } from '../../api/types';
import { hrefFor, navigate } from '../../app/router';
import { useLoad } from '../../app/store';
import { Icon } from '../../components/Icon';
import { PageHeader } from '../../components/PageHeader';
import { Mascot } from '../../components/Mascot';
import { ArtBadge } from '../../components/Art';
import { EmptyState, LoadingRows, ProblemNotice } from '../../components/StateViews';
import { describeError, type Problem } from '../../lib/copy';
import { availableCount, defaultCount, kindsIn, practiceUnits } from '../../lib/practice';
import { kindLabel } from '../lesson/QuestionView';

function when(iso: string) {
  return new Intl.DateTimeFormat('vi-VN', { day: 'numeric', month: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(iso));
}

/**
 * Ôn luyện: practise or test across any open lessons. Practice shows feedback
 * and help per question; a test grades only on submit and allows no help.
 * Both use the same history as lessons.
 */
export function PracticePage({ courseId }: { courseId: string }) {
  const state = useLoad(async () => {
    await ensureSession();
    const [course, history] = await Promise.all([api<Course>(`/courses/${courseId}`), api<HistoryEntry[]>(`/courses/${courseId}/history`).catch(() => [])]);
    return { course, history };
  }, [courseId]);
  const course = state.data?.course;
  const units = useMemo(() => practiceUnits(course?.content.units ?? []), [course]);
  const [unitIds, setUnitIds] = useState<string[]>([]);
  const [kinds, setKinds] = useState<QuestionKind[]>([]);
  const [count, setCount] = useState(10);
  const [exam, setExam] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);
  const key = useRef(newKey('practice'));

  useEffect(() => {
    const ids = units.map((u) => u.id);
    setUnitIds(ids);
    setKinds(kindsIn(units, ids));
  }, [units]);

  const present = kindsIn(units, unitIds);
  const chosenKinds = kinds.filter((k) => present.includes(k));
  const available = availableCount(units, unitIds, chosenKinds);
  useEffect(() => setCount(defaultCount(available)), [available]);

  const toggleUnit = (id: string) => setUnitIds((all) => (all.includes(id) ? all.filter((x) => x !== id) : [...all, id]));
  const toggleKind = (kind: QuestionKind) => setKinds((all) => (all.includes(kind) ? all.filter((x) => x !== kind) : [...all, kind]));

  const start = async () => {
    if (!course) return;
    setBusy(true);
    setProblem(null);
    try {
      const session = await api<PracticeSession>(`/courses/${course.id}/sessions`, {
        body: {
          expected_revision: course.revision,
          unit_ids: unitIds,
          mode: 'practice',
          exercise: exam ? 'test' : 'practice',
          question_types: chosenKinds.length === present.length ? [] : chosenKinds,
          question_count: Math.min(count, available),
        },
        idempotencyKey: key.current,
      });
      key.current = newKey('practice');
      navigate({ name: 'practice', courseId: course.id, sessionId: session.id });
    } catch (error) {
      setProblem(error instanceof ApiError && (error.status === 409 || error.status === 422) ? { title: 'Chưa bắt đầu được lượt này', body: error.message, canRetry: false } : describeError(error));
    } finally {
      setBusy(false);
    }
  };

  if (state.loading && !state.data) {
    return (
      <div className="page">
        <LoadingRows rows={3} label="Đang mở Ôn luyện…" />
      </div>
    );
  }
  if (state.error != null || !course) {
    return (
      <div className="page">
        <a className="back" href="#/">
          <Icon name="arrowLeft" size={18} /> Học tiếp
        </a>
        <ProblemNotice problem={describeError(state.error)} onRetry={state.reload} />
      </div>
    );
  }

  const history = state.data?.history ?? [];
  const open = history.find((h) => h.status === 'open');
  const finished = history.filter((h) => h.status === 'completed' && h.result);

  return (
    <div className="page practice-page">
      <a className="back" href={hrefFor({ name: 'course', courseId: course.id })}>
        <Icon name="arrowLeft" size={18} /> Lộ trình
      </a>
      <PageHeader
        title="Ôn luyện"
        tone="sky"
        note={`${course.content.title} — chọn bài và dạng câu, luyện có Kẹp gợi ý hoặc tự kiểm tra.`}
        art={<ArtBadge name="target" size={84} />}
        actions={
          <a className="btn btn--secondary" href={hrefFor({ name: 'lesson', courseId: course.id, unitId: 'tat-ca', mode: 'weak' })}>
            <Icon name="flag" size={18} /> Ôn câu sai
          </a>
        }
      />

      {units.length === 0 ? (
        <EmptyState
          art={<ArtBadge name="target" size={110} />}
          title="Chưa có bài nào để luyện"
          body="Tạo và học bài đầu tiên trên lộ trình; câu hỏi của bài sẽ có ở đây."
          action={
            <a className="btn btn--primary btn--lg" href={hrefFor({ name: 'course', courseId: course.id })}>
              Về lộ trình
            </a>
          }
        />
      ) : (
        <div className="practice-grid">
          <section className="practice-setup">
            {open && (
              <div className="notice notice--butter">
                <Icon name="clock" />
                <div style={{ display: 'grid', gap: 8, flex: 1 }}>
                  <p className="notice__title">Bạn còn một lượt đang làm dở</p>
                  <div>
                    <a className="btn btn--primary btn--sm" href={hrefFor({ name: 'practice', courseId: course.id, sessionId: open.id })}>
                      Làm tiếp <Icon name="arrowRight" size={16} />
                    </a>
                  </div>
                </div>
              </div>
            )}

            <div className="segmented practice-mode" role="radiogroup" aria-label="Kiểu lượt">
              <button type="button" role="radio" aria-checked={!exam} onClick={() => setExam(false)}>
                <strong>Luyện tập</strong>
                <span>Chấm từng câu, có gợi ý và hỏi Kẹp</span>
              </button>
              <button type="button" role="radio" aria-checked={exam} onClick={() => setExam(true)}>
                <strong>Kiểm tra</strong>
                <span>Chấm khi nộp bài, không trợ giúp</span>
              </button>
            </div>

            <fieldset className="practice-units">
              <legend className="eyebrow">Phạm vi ({unitIds.length}/{units.length} bài)</legend>
              <div className="practice-units__tools">
                <button type="button" className="link link--quiet" onClick={() => setUnitIds(units.map((u) => u.id))}>
                  Chọn tất cả
                </button>
                <button type="button" className="link link--quiet" onClick={() => setUnitIds([])}>
                  Bỏ chọn
                </button>
              </div>
              {units.map((unit) => (
                <label key={unit.id} className="check-row practice-unit">
                  <input type="checkbox" checked={unitIds.includes(unit.id)} onChange={() => toggleUnit(unit.id)} />
                  <span>
                    {unit.title}
                    <span className="meta"> · {unit.data?.questions.length ?? 0} câu</span>
                  </span>
                </label>
              ))}
            </fieldset>

            <div>
              <p className="eyebrow">Dạng câu</p>
              <div className="chips">
                {present.map((kind) => (
                  <button key={kind} type="button" className="chip" aria-pressed={kinds.includes(kind)} onClick={() => toggleKind(kind)}>
                    {kinds.includes(kind) && <Icon name="check" size={14} />} {kindLabel(kind)}
                  </button>
                ))}
              </div>
            </div>

            <label className="count-row">
              <span>Số câu</span>
              <input type="range" min={1} max={Math.max(1, available)} value={Math.min(count, Math.max(1, available))} disabled={!available} aria-label="Số câu" onChange={(e) => setCount(Number(e.target.value))} />
              <strong>
                {available ? Math.min(count, available) : 0}/{available}
              </strong>
            </label>

            {problem && <ProblemNotice problem={problem} compact />}
            <button type="button" className="btn btn--primary btn--lg btn--block" disabled={busy || !available || !unitIds.length} aria-busy={busy} onClick={() => void start()}>
              {exam ? 'Bắt đầu kiểm tra' : 'Bắt đầu luyện tập'} <Icon name="arrowRight" size={18} />
            </button>
            <p className="meta">Câu lấy từ bộ đã tạo của các bài, không tạo thêm. Câu đang chờ xem lại đáp án được tạm giữ lại.</p>
          </section>

          <aside className="practice-history" aria-label="Lịch sử">
            <h2 className="title-m">Lịch sử</h2>
            {finished.length === 0 && !open ? (
              <div className="practice-history__empty">
                <Mascot mood="hint" size={64} />
                <p className="meta">Chưa có lượt nào. Lượt luyện sau mỗi bài học cũng được ghi ở đây.</p>
              </div>
            ) : (
              <ol>
                {history.slice(0, 20).map((entry) => (
                  <li key={entry.id}>
                    <a className="history-row" href={hrefFor({ name: 'practice', courseId: course.id, sessionId: entry.id })}>
                      <span className={`history-row__score${entry.status === 'open' ? ' is-open' : ''}`}>
                        {entry.status === 'completed' && entry.result ? `${entry.result.score}/${entry.result.fixed_total}` : entry.status === 'open' ? 'Dở' : '—'}
                      </span>
                      <span className="history-row__text">
                        <strong>{entry.status === 'open' ? 'Đang làm' : entry.status === 'cancelled' ? 'Đã hủy' : 'Đã nộp'}</strong>
                        <span className="meta">{when(entry.created_at)}</span>
                      </span>
                      <Icon name="arrowRight" size={16} />
                    </a>
                  </li>
                ))}
              </ol>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}
