import { useEffect, useState } from 'react';
import { Icon } from '../../components/Icon';
import { Mascot } from '../../components/Mascot';
import { ProblemNotice } from '../../components/StateViews';
import { formatElapsed, lessonWaiting } from '../../lib/copy';
import type { Generation } from './useGeneration';

function Elapsed({ since }: { since: number }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);
  return <span>{formatElapsed(now - since)}</span>;
}

/** Waiting/failed state of a lesson job. Shows only what the server reports. */
export function JobCard({
  state,
  onCancel,
  onRetry,
  onContinue,
  onDismiss,
}: {
  state: Generation;
  onCancel: () => void;
  onRetry: () => void;
  onContinue: () => void;
  onDismiss: () => void;
}) {
  if (state.phase === 'running') {
    const view = lessonWaiting(state.job?.progress);
    return (
      <section className="job-card enter" aria-live="polite" aria-busy="true">
        <Mascot mood="think" size={84} bob />
        <div className="job-card__body">
          <p className="eyebrow">Đang tạo bài: {state.unit.title}</p>
          <p className="title-m">{view.headline}</p>
          <ol className="stages">
            {view.stages.map((stage) => (
              <li key={stage.key} className={`stage stage--${stage.state}`}>
                <span className="stage__dot" aria-hidden="true">
                  {stage.state === 'done' ? <Icon name="check" size={14} /> : null}
                </span>
                <span>{stage.label}</span>
                {stage.detail && <span className="meta">· {stage.detail}</span>}
              </li>
            ))}
          </ol>
          <p className="meta">
            {view.saved} Đã chạy <Elapsed since={state.startedAt} />.
          </p>
        </div>
        <button type="button" className="btn btn--ghost btn--sm" onClick={onCancel}>
          <Icon name="stop" size={16} /> Dừng
        </button>
      </section>
    );
  }
  if (state.phase === 'continue') {
    const chapter = state.job.progress?.chapter_context;
    return (
      <section className="job-card enter">
        <Mascot mood="hint" size={84} />
        <div className="job-card__body">
          <p className="title-m">Đã đọc được một phần chương, chưa đủ để viết bài</p>
          <p className="notice__body">
            {chapter?.total_parts ? `Đã đọc ${chapter.read_parts ?? 0}/${chapter.total_parts} phần. ` : ''}
            Phần đã đọc được lưu lại; bấm tiếp tục để đọc nốt rồi mới viết bài và câu hỏi.
          </p>
          <div style={{ display: 'flex', gap: 8 }}>
            <button type="button" className="btn btn--primary btn--sm" onClick={onContinue}>
              Tiếp tục đọc
            </button>
            <button type="button" className="btn btn--ghost btn--sm" onClick={onDismiss}>
              Để sau
            </button>
          </div>
        </div>
      </section>
    );
  }
  if (state.phase === 'failed') {
    return (
      <section className="job-card job-card--failed enter">
        <div style={{ flex: 1 }}>
          <ProblemNotice problem={state.problem} onRetry={onRetry} />
        </div>
        <button type="button" className="icon-btn" aria-label="Đóng thông báo" onClick={onDismiss}>
          <Icon name="x" />
        </button>
      </section>
    );
  }
  return null;
}
