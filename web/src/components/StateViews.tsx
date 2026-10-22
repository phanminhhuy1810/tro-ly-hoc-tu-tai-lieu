import type { ReactNode } from 'react';
import type { Problem } from '../lib/copy';
import { Icon } from './Icon';
import { Mascot } from './Mascot';

export function LoadingRows({ rows = 3, label = 'Đang tải…' }: { rows?: number; label?: string }) {
  return (
    <div className="loading-rows" role="status" aria-live="polite">
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="loading-row">
          <div className="skeleton" style={{ width: 56, height: 56, borderRadius: 16 }} />
          <div style={{ display: 'grid', gap: 8, flex: 1 }}>
            <div className="skeleton" style={{ height: 16, width: `${62 - i * 9}%` }} />
            <div className="skeleton" style={{ height: 12, width: `${38 - i * 5}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}

export function ProblemNotice({ problem, onRetry, retryLabel = 'Thử lại', compact = false }: { problem: Problem; onRetry?: () => void; retryLabel?: string; compact?: boolean }) {
  return (
    <div className="notice notice--coral" role="alert">
      {!compact && <Mascot mood="oops" size={56} />}
      <div style={{ display: 'grid', gap: 6, flex: 1 }}>
        <p className="notice__title">{problem.title}</p>
        <p className="notice__body">{problem.body}</p>
        {problem.canRetry && onRetry && (
          <div>
            <button type="button" className="btn btn--secondary btn--sm" onClick={onRetry}>
              <Icon name="refresh" size={16} /> {retryLabel}
            </button>
          </div>
        )}
        {problem.technical && (
          <details>
            <summary>Chi tiết kỹ thuật</summary>
            <p>{problem.technical}</p>
          </details>
        )}
      </div>
    </div>
  );
}

export function EmptyState({ art, title, body, action }: { art: ReactNode; title: string; body: string; action?: ReactNode }) {
  return (
    <div className="state enter-fade">
      {art}
      <p className="state__title">{title}</p>
      <p className="state__body">{body}</p>
      {action}
    </div>
  );
}
