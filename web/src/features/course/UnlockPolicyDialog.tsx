import { useEffect, useRef, useState } from 'react';
import { api } from '../../api/client';
import type { Course } from '../../api/types';
import { Icon } from '../../components/Icon';
import { ProblemNotice } from '../../components/StateViews';
import { describeError } from '../../lib/copy';

// The creator picks how lessons open (rule 10): one by one after a practice
// round, or all at once to learn in any order. It can change any time; like
// every course edit it is a preview the creator confirms, then a new revision.
// Lessons, sources and results stay as they are.

export function UnlockPolicyDialog({ course, open, onClose, onChanged }: { course: Course; open: boolean; onClose: () => void; onChanged: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<unknown>(null);
  const next = course.content.unlock_policy === 'open' ? 'locked' : 'open';

  useEffect(() => {
    const el = dialog.current;
    if (!el) return;
    if (open && !el.open) {
      setProblem(null);
      el.showModal();
    }
    if (!open && el.open) el.close();
  }, [open]);

  const apply = async () => {
    setBusy(true);
    setProblem(null);
    try {
      const preview = await api<{ proposal_id: string }>(`/courses/${course.id}/unlock-policy-preview`, {
        body: { expected_revision: course.revision, unlock_policy: next },
      });
      await api(`/proposals/${preview.proposal_id}/apply`, { body: { expected_revision: course.revision } });
      onChanged();
    } catch (error) {
      setProblem(error);
    } finally {
      setBusy(false);
    }
  };

  return (
    <dialog
      ref={dialog}
      className="dialog"
      aria-labelledby="order-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <div className="dialog__inner">
        <p className="eyebrow">Thứ tự học</p>
        <h2 id="order-title" className="title-l">
          {next === 'open' ? 'Mở mọi bài để học tự do?' : 'Chuyển về mở dần từng bài?'}
        </h2>
        {next === 'open' ? (
          <p className="notice__body">
            Mọi bài trong khóa mở ngay, bạn học bài nào trước cũng được. Lộ trình vẫn gợi ý thứ tự; bài đã học và kết quả giữ nguyên.
          </p>
        ) : (
          <p className="notice__body">
            Bài sau chỉ mở khi luyện xong một lượt bài trước, không cần điểm tối thiểu. Bài chưa tới lượt sẽ khóa lại; kết quả đã học giữ nguyên.
          </p>
        )}
        {problem != null && <ProblemNotice problem={describeError(problem)} compact />}
        <div className="dialog__actions">
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            Thôi
          </button>
          <button type="button" className="btn btn--primary" aria-busy={busy} disabled={busy} onClick={() => void apply()}>
            <Icon name={next === 'open' ? 'unlock' : 'lock'} size={18} /> {busy ? 'Đang đổi…' : next === 'open' ? 'Mở mọi bài' : 'Mở dần từng bài'}
          </button>
        </div>
      </div>
    </dialog>
  );
}
