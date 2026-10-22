import { useState, type FormEvent } from 'react';
import { api, ApiError, ensureSession } from '../../api/client';
import type { CommunityCourse } from '../../api/types';
import { hrefFor } from '../../app/router';
import { useApp, useLoad } from '../../app/store';
import { Icon } from '../../components/Icon';
import { Mascot } from '../../components/Mascot';
import { EmptyState, LoadingRows, ProblemNotice } from '../../components/StateViews';
import { creatorLabel, ratingText } from '../../lib/community';
import { describeError } from '../../lib/copy';
import { CourseCover } from '../course/covers';

/** A learner's note about a wrong question or unclear lesson; it goes to the creator and never edits the course. */
function ReportForm({ course }: { course: CommunityCourse }) {
  const { toast } = useApp();
  const [unitId, setUnitId] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);

  const send = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    try {
      await api(`/community/${encodeURIComponent(course.id)}/reports`, { body: { reason: reason.trim(), unit_id: unitId || null } });
      toast('Đã gửi cho người tạo — nội dung khóa không tự đổi');
      setReason('');
      setOpen(false);
    } catch (error) {
      toast(describeError(error).title);
    } finally {
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <button type="button" className="btn btn--ghost btn--sm" onClick={() => setOpen(true)}>
        <Icon name="flag" size={16} /> Báo lỗi nội dung
      </button>
    );
  }
  return (
    <form className="report-form enter" onSubmit={(event) => void send(event)}>
      <label>
        <span className="eyebrow">Bài có lỗi (không bắt buộc)</span>
        <select className="field" value={unitId} onChange={(event) => setUnitId(event.target.value)}>
          <option value="">Cả khóa</option>
          {course.units.map((unit, i) => (
            <option key={unit.id} value={unit.id}>
              Bài {i + 1}: {unit.title}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span className="eyebrow">Lỗi gì?</span>
        <textarea className="field" rows={3} maxLength={2000} value={reason} placeholder="Ví dụ: câu 2 bài 1 có đáp án sai so với slide 17" onChange={(event) => setReason(event.target.value)} />
      </label>
      <div className="dialog__actions">
        <button type="button" className="btn btn--ghost" onClick={() => setOpen(false)}>
          Thôi
        </button>
        <button type="submit" className="btn btn--secondary" disabled={busy || !reason.trim()} aria-busy={busy}>
          Gửi báo lỗi
        </button>
      </div>
    </form>
  );
}

function Stars({ value, disabled, onPick }: { value: number | null; disabled: boolean; onPick: (rating: number) => void }) {
  return (
    <div className="stars" role="radiogroup" aria-label="Đánh giá khóa">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          role="radio"
          aria-checked={value === n}
          aria-label={`${n} sao`}
          className={value != null && n <= value ? 'is-on' : undefined}
          disabled={disabled}
          onClick={() => onPick(n)}
        >
          ★
        </button>
      ))}
    </div>
  );
}

/**
 * Preview of a public course: what is inside, who made it and what others
 * think. Joining starts the learner's own progress; likes and ratings are for
 * people who joined, and the creator cannot rate their own course.
 */
export function CommunityCoursePage({ courseId }: { courseId: string }) {
  const { toast } = useApp();
  const state = useLoad(async () => {
    await ensureSession();
    return api<CommunityCourse>(`/community/${encodeURIComponent(courseId)}`);
  }, [courseId]);
  const [busy, setBusy] = useState(false);

  const back = (
    <a className="back" href={hrefFor({ name: 'community' })}>
      <Icon name="arrowLeft" size={18} /> Cộng đồng
    </a>
  );

  if (state.loading && !state.data) {
    return (
      <div className="page">
        {back}
        <LoadingRows rows={2} label="Đang mở khóa…" />
      </div>
    );
  }
  if (state.error != null || !state.data) {
    const gone = state.error instanceof ApiError && state.error.status === 404;
    return (
      <div className="page">
        {back}
        {gone ? (
          <EmptyState art={<Mascot mood="oops" size={110} />} title="Khóa này không còn công khai" body="Người tạo có thể đã chuyển khóa về riêng tư hoặc chỉ chia sẻ bằng mã mời." />
        ) : (
          <ProblemNotice problem={describeError(state.error)} onRetry={state.reload} />
        )}
      </div>
    );
  }

  const course = state.data;
  const role = course.me?.role ?? null;
  const ready = course.units.filter((unit) => unit.generated).length;

  const enroll = async () => {
    setBusy(true);
    try {
      await api(`/courses/${encodeURIComponent(course.id)}/enroll`, { method: 'POST' });
      toast('Đã tham gia — tiến trình, sổ tay và chat của bạn là riêng');
      state.reload();
    } catch (error) {
      toast(describeError(error).title);
    } finally {
      setBusy(false);
    }
  };

  const feedback = async (liked: boolean, rating: number | null) => {
    setBusy(true);
    try {
      await api(`/community/${encodeURIComponent(course.id)}/feedback`, { method: 'PUT', body: { liked, rating } });
      state.reload();
    } catch (error) {
      toast(describeError(error).title);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page community-course">
      {back}
      <header className="course-head">
        <CourseCover courseId={course.id} title={course.title} size={96} />
        <div className="course-head__text">
          <p className="eyebrow">Khóa cộng đồng{creatorLabel(course.creator_name) ? ` · của ${creatorLabel(course.creator_name)}` : ''}</p>
          <h1 className="page-title">{course.title}</h1>
          <p className="meta community-card__stats">
            <span>
              <Icon name="heart" size={15} /> {course.likes} lượt thích
            </span>
            <span>{ratingText(course.rating, course.rating_count)}</span>
            <span>
              {ready}/{course.units.length} bài đã có nội dung
            </span>
          </p>
        </div>
      </header>

      <div className="together-grid">
        <section className="panel-card">
          <h2 className="title-m">Trong khóa có gì</h2>
          <ol className="unit-list">
            {course.units.map((unit, i) => (
              <li key={unit.id}>
                <span className="unit-list__num">{i + 1}</span>
                <span className="unit-list__title">{unit.title}</span>
                <span className={unit.generated ? 'tag tag--sage' : 'tag'}>{unit.generated ? 'đã có bài' : 'chưa tạo'}</span>
              </li>
            ))}
          </ol>
          <p className="meta">
            Vào học bạn có bài giảng, thẻ và bộ câu luyện của người tạo. File gốc của tài liệu không đi kèm, trừ khi người tạo chọn chia sẻ riêng.
          </p>
        </section>

        <aside className="together-aside">
          <section className="panel-card join-card">
            {role === 'creator' ? (
              <>
                <h2 className="title-m">Đây là khóa của bạn</h2>
                <p className="meta">Người khác thấy trang này khi tìm trong Cộng đồng. Bạn không tự thả tim hay đánh giá khóa của mình.</p>
                <a className="btn btn--secondary" href={hrefFor({ name: 'share', courseId: course.id })}>
                  <Icon name="share" size={18} /> Cài đặt chia sẻ
                </a>
              </>
            ) : role === 'learner' ? (
              <>
                <h2 className="title-m">Bạn đang học khóa này</h2>
                <a className="btn btn--primary btn--block" href={hrefFor({ name: 'course', courseId: course.id })}>
                  Vào học <Icon name="arrowRight" size={18} />
                </a>
                <div className="feedback">
                  <button type="button" className={course.me?.liked ? 'chip is-on' : 'chip'} aria-pressed={course.me?.liked ?? false} disabled={busy} onClick={() => void feedback(!course.me?.liked, course.me?.rating ?? null)}>
                    <Icon name="heart" size={16} /> {course.me?.liked ? 'Đã thích' : 'Thích khóa này'}
                  </button>
                  <Stars value={course.me?.rating ?? null} disabled={busy} onPick={(rating) => void feedback(course.me?.liked ?? false, rating)} />
                </div>
                <ReportForm course={course} />
              </>
            ) : (
              <>
                <h2 className="title-m">Tham gia để học</h2>
                <p className="meta">Tiến trình, sổ tay và chat của bạn là riêng; người tạo không xem được.</p>
                <button type="button" className="btn btn--primary btn--block" disabled={busy || ready === 0} aria-busy={busy} onClick={() => void enroll()}>
                  Tham gia khóa <Icon name="arrowRight" size={18} />
                </button>
              </>
            )}
          </section>
        </aside>
      </div>
    </div>
  );
}
