import { useState } from 'react';
import { api, ensureSession } from '../../api/client';
import type { Course, CourseReport, PublicationPreview, PublicationState, Visibility } from '../../api/types';
import { hrefFor } from '../../app/router';
import { useApp, useLoad } from '../../app/store';
import { Icon, type IconName } from '../../components/Icon';
import { LoadingRows, ProblemNotice } from '../../components/StateViews';
import { appLink, copyText } from '../../lib/clipboard';
import { materialLabel, ratingText, VISIBILITY } from '../../lib/community';
import { describeError } from '../../lib/copy';

const ICON: Record<Visibility, IconName> = { private: 'lock', shared: 'link', public: 'globe' };
const ORDER: Visibility[] = ['private', 'shared', 'public'];

function day(iso: string) {
  return new Intl.DateTimeFormat('vi-VN', { day: 'numeric', month: 'numeric', year: 'numeric' }).format(new Date(iso));
}

/** One fresh invite code; older codes keep working until the course goes back to private. */
function InviteCard({ courseId }: { courseId: string }) {
  const { toast } = useApp();
  const [code, setCode] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const create = async () => {
    setBusy(true);
    try {
      setCode((await api<{ code: string }>(`/courses/${encodeURIComponent(courseId)}/invite`, { method: 'POST' })).code);
    } catch (error) {
      toast(describeError(error).title);
    } finally {
      setBusy(false);
    }
  };
  const copy = async (text: string, what: string) => toast((await copyText(text)) ? `Đã chép ${what}` : 'Trình duyệt chưa cho chép — bôi đen để chép tay nhé');

  return (
    <section className="panel-card">
      <h2 className="title-m">Mã mời</h2>
      <p className="meta">Ai có mã đều vào học được, nên chỉ gửi cho người bạn muốn. Mã cũ vẫn dùng được tới khi bạn chuyển khóa về “Chỉ mình tôi”.</p>
      {code ? (
        <div className="invite-code">
          <code>{code}</code>
          <div className="invite-code__actions">
            <button type="button" className="btn btn--secondary btn--sm" onClick={() => void copy(code, 'mã mời')}>
              <Icon name="copy" size={16} /> Chép mã
            </button>
            <button type="button" className="btn btn--secondary btn--sm" onClick={() => void copy(appLink(hrefFor({ name: 'community', code })), 'đường dẫn mời')}>
              <Icon name="link" size={16} /> Chép đường dẫn
            </button>
          </div>
        </div>
      ) : (
        <button type="button" className="btn btn--secondary" disabled={busy} aria-busy={busy} onClick={() => void create()}>
          <Icon name="plus" size={18} /> Tạo mã mời
        </button>
      )}
    </section>
  );
}

/**
 * Chia sẻ khóa: the creator picks private, invite-only or public, sees exactly
 * what is shared and what stays private, and only then applies it. Original
 * files are a separate choice from the lesson material.
 */
export function SharePage({ courseId }: { courseId: string }) {
  const { toast } = useApp();
  const state = useLoad(async () => {
    await ensureSession();
    const id = encodeURIComponent(courseId);
    const course = await api<Course>(`/courses/${id}`);
    if (course.access_role === 'learner') return { course, publication: null, reports: [] as CourseReport[] };
    const [publication, reports] = await Promise.all([api<PublicationState>(`/courses/${id}/publication`), api<CourseReport[]>(`/courses/${id}/reports`)]);
    return { course, publication, reports };
  }, [courseId]);
  const [picked, setPicked] = useState<Visibility | null>(null);
  const [original, setOriginal] = useState<boolean | null>(null);
  const [preview, setPreview] = useState<PublicationPreview | null>(null);
  const [busy, setBusy] = useState(false);

  const back = (
    <a className="back" href={hrefFor({ name: 'course', courseId })}>
      <Icon name="arrowLeft" size={18} /> Lộ trình
    </a>
  );
  if (state.loading && !state.data) {
    return (
      <div className="page">
        {back}
        <LoadingRows rows={2} label="Đang mở cài đặt chia sẻ…" />
      </div>
    );
  }
  if (state.error != null || !state.data) {
    return (
      <div className="page">
        {back}
        <ProblemNotice problem={describeError(state.error)} onRetry={state.reload} />
      </div>
    );
  }

  const { course, publication, reports } = state.data;
  if (!publication) {
    return (
      <div className="page">
        {back}
        <div className="notice notice--butter">
          <Icon name="lock" />
          <div>
            <p className="notice__title">Khóa này do người khác tạo</p>
            <p className="notice__body">Chỉ người tạo đổi được quyền chia sẻ. Bạn vẫn học, ôn và hỏi Kẹp bằng tiến trình riêng của mình.</p>
          </div>
        </div>
      </div>
    );
  }

  const current = publication.visibility;
  const chosen = picked ?? current;
  const shareOriginal = chosen !== 'private' && (original ?? publication.originals.length > 0);
  const changed = chosen !== current || shareOriginal !== publication.originals.length > 0;
  const hasLesson = course.content.units.some((unit) => unit.data);
  const unitIndex = (id: string | null) => course.content.units.findIndex((unit) => unit.id === id);

  const review = async () => {
    setBusy(true);
    try {
      setPreview(
        await api<PublicationPreview>(`/courses/${encodeURIComponent(course.id)}/publication-preview`, {
          body: { expected_revision: course.revision, visibility: chosen, share_original: shareOriginal },
        }),
      );
    } catch (error) {
      toast(describeError(error).title);
    } finally {
      setBusy(false);
    }
  };

  const apply = async () => {
    if (!preview) return;
    setBusy(true);
    try {
      const result = await api<{ visibility: Visibility; revoked_members: number }>(`/publications/${encodeURIComponent(preview.publication_id)}/apply`, {
        body: { expected_revision: course.revision },
      });
      toast(
        result.revoked_members > 0
          ? `Đã chuyển về riêng tư; ${result.revoked_members} người không còn vào được`
          : `Đã áp dụng: ${VISIBILITY[result.visibility].title}`,
      );
      setPreview(null);
      setPicked(null);
      setOriginal(null);
      state.reload();
    } catch (error) {
      toast(describeError(error).title);
      setPreview(null);
      state.reload();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page share-page">
      {back}
      <header className="page-head">
        <div>
          <p className="eyebrow">{course.content.title}</p>
          <h1 className="page-title">Chia sẻ khóa</h1>
        </div>
      </header>

      <div className="together-grid">
        <div className="share-main">
          <section className="panel-card">
            <h2 className="title-m">Ai được vào học?</h2>
            <div className="visibility-options" role="radiogroup" aria-label="Quyền xem khóa">
              {ORDER.map((value) => (
                <button
                  key={value}
                  type="button"
                  role="radio"
                  aria-checked={chosen === value}
                  className="visibility-option"
                  disabled={busy || (value !== 'private' && !hasLesson)}
                  onClick={() => {
                    setPicked(value);
                    setPreview(null);
                  }}
                >
                  <span className="visibility-option__icon">
                    <Icon name={ICON[value]} size={20} />
                  </span>
                  <span>
                    <strong>
                      {VISIBILITY[value].title}
                      {value === current && <span className="tag tag--sage">đang dùng</span>}
                    </strong>
                    <span className="meta">{VISIBILITY[value].body}</span>
                  </span>
                </button>
              ))}
            </div>
            {!hasLesson && <p className="meta">Tạo và xem lại ít nhất một bài trước khi chia sẻ.</p>}
            <label className={chosen === 'private' ? 'check-row is-disabled' : 'check-row'}>
              <input
                type="checkbox"
                checked={shareOriginal}
                disabled={chosen === 'private' || busy}
                onChange={(event) => {
                  setOriginal(event.target.checked);
                  setPreview(null);
                }}
              />
              <span>
                Cho người học tải cả file tài liệu gốc
                <span className="meta"> — tách riêng với quyền đọc bài; mặc định chỉ chia sẻ các trích đoạn bài dùng.</span>
              </span>
            </label>
            {!preview && (
              <div>
                <button type="button" className="btn btn--primary" disabled={busy || !changed} aria-busy={busy} onClick={() => void review()}>
                  {changed ? 'Xem trước thay đổi' : 'Chưa có thay đổi'}
                </button>
              </div>
            )}
          </section>

          {preview && (
            <section className="panel-card share-preview enter" aria-label="Xem trước khi áp dụng">
              <h2 className="title-m">Xem trước: {VISIBILITY[preview.preview.visibility].title}</h2>
              {preview.preview.visibility !== 'private' && (
                <div className="share-columns">
                  <div>
                    <p className="eyebrow">Người học thấy</p>
                    <ul className="tick-list">
                      {preview.preview.shared_material.map((code) => (
                        <li key={code}>
                          <Icon name="check" size={16} /> {materialLabel(code)}
                        </li>
                      ))}
                      {preview.preview.originals.map((name) => (
                        <li key={name}>
                          <Icon name="file" size={16} /> File gốc: {name}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <p className="eyebrow">Vẫn là của riêng từng người</p>
                    <ul className="tick-list tick-list--muted">
                      {preview.preview.private_material_excluded.map((code) => (
                        <li key={code}>
                          <Icon name="lock" size={16} /> {materialLabel(code)}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}
              <p className="notice notice--butter">{preview.preview.warning}</p>
              <div className="dialog__actions">
                <button type="button" className="btn btn--ghost" disabled={busy} onClick={() => setPreview(null)}>
                  Sửa lại
                </button>
                <button type="button" className="btn btn--primary" disabled={busy} aria-busy={busy} onClick={() => void apply()}>
                  Áp dụng
                </button>
              </div>
            </section>
          )}

          {current !== 'private' && <InviteCard courseId={course.id} />}
        </div>

        <aside className="together-aside">
          <section className="panel-card share-status">
            <h2 className="title-m">Hiện tại</h2>
            <p className="share-status__now">
              <Icon name={ICON[current]} size={20} /> {VISIBILITY[current].title}
            </p>
            <ul className="prices">
              <li>
                <span>Người đang học</span>
                <strong>{publication.active_members}</strong>
              </li>
              <li>
                <span>Lượt thích</span>
                <strong>{publication.likes}</strong>
              </li>
              <li>
                <span>Đánh giá</span>
                <strong>{ratingText(publication.rating, publication.rating_count)}</strong>
              </li>
              <li>
                <span>File gốc chia sẻ</span>
                <strong>{publication.originals.length ? publication.originals.join(', ') : 'không'}</strong>
              </li>
            </ul>
            {current === 'public' && (
              <a className="btn btn--ghost btn--sm" href={hrefFor({ name: 'community', courseId: course.id })}>
                Xem trang cộng đồng <Icon name="arrowRight" size={16} />
              </a>
            )}
            <p className="meta">Đăng khóa không được thưởng Coin; Coin chỉ đến khi người khác thích hoặc đánh giá tốt.</p>
          </section>

          <section className="panel-card">
            <h2 className="title-m">Báo lỗi từ người học {reports.length ? `(${reports.length})` : ''}</h2>
            {reports.length === 0 ? (
              <p className="meta">Chưa có báo lỗi nào.</p>
            ) : (
              <ul className="report-list">
                {reports.map((report) => {
                  const index = unitIndex(report.unit_id);
                  return (
                    <li key={report.id}>
                      <p>{report.reason}</p>
                      <span className="meta">
                        {index >= 0 ? `Bài ${index + 1}: ${course.content.units[index].title}` : 'Cả khóa'} · {day(report.created_at)}
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
            <p className="meta">Báo lỗi không tự sửa nội dung; mở bài để sửa nếu bạn thấy đúng là lỗi.</p>
          </section>
        </aside>
      </div>
    </div>
  );
}
