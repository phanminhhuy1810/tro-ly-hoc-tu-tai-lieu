import { useEffect, useRef, useState } from 'react';
import { api, ensureSession } from '../../api/client';
import type { Course, Lifecycle, SourceSummary } from '../../api/types';
import { hrefFor, navigate } from '../../app/router';
import { useApp, useLoad } from '../../app/store';
import { Icon } from '../../components/Icon';
import { Spot } from '../../components/Spot';
import { EmptyState, LoadingRows, ProblemNotice } from '../../components/StateViews';
import { describeError } from '../../lib/copy';
import { courseSummary } from '../../lib/path';
import { fold } from '../../lib/text';
import { CourseCover } from '../course/covers';

type Tab = 'courses' | 'sources' | 'trash';
type Kind = 'course' | 'source';
const PLURAL: Record<Kind, string> = { course: 'courses', source: 'sources' };

function size(bytes: number) {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${bytes} B`;
}

function day(iso: string | null | undefined) {
  return iso ? new Intl.DateTimeFormat('vi-VN', { day: 'numeric', month: 'numeric', year: 'numeric' }).format(new Date(iso)) : '';
}

/** Trash is recoverable: nothing is purged, history and personal notes stay. The dialog says what changes. */
function TrashDialog({
  target,
  courseTitles,
  onClose,
  onDone,
}: {
  target: { kind: Kind; id: string } | null;
  courseTitles: Map<string, string>;
  onClose: () => void;
  onDone: () => void;
}) {
  const { toast } = useApp();
  const dialog = useRef<HTMLDialogElement>(null);
  const [details, setDetails] = useState<Lifecycle | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const el = dialog.current;
    if (!el) return;
    if (target && !el.open) el.showModal();
    if (!target && el.open) el.close();
    setDetails(null);
    if (target) {
      api<Lifecycle>(`/${PLURAL[target.kind]}/${target.id}/lifecycle`)
        .then(setDetails)
        .catch((error) => {
          toast(describeError(error).title);
          onClose();
        });
    }
  }, [target]);

  const confirm = async () => {
    if (!target || !details) return;
    setBusy(true);
    try {
      await api(`/${PLURAL[target.kind]}/${target.id}`, { method: 'DELETE', body: { expected_revision: details.revision, expected_lifecycle_version: details.lifecycle_version } });
      toast('Đã chuyển vào thùng rác — khôi phục được bất cứ lúc nào');
      onDone();
    } catch (error) {
      toast(describeError(error).title);
    } finally {
      setBusy(false);
    }
  };

  return (
    <dialog
      ref={dialog}
      className="dialog"
      aria-labelledby="trash-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <div className="dialog__inner">
        <h2 id="trash-title" className="title-l">
          Chuyển “{details?.title ?? '…'}” vào thùng rác?
        </h2>
        {!details ? (
          <div className="skeleton" style={{ height: 60 }} />
        ) : details.blockers.length ? (
          <div className="notice notice--butter">
            <Icon name="flag" />
            <div>
              <p className="notice__title">Chưa xóa được</p>
              <ul className="plain-list">
                {details.blockers.map((b) =>
                  b.type === 'course' && courseTitles.has(b.id) ? (
                    <li key={b.id}>
                      Khóa “{courseTitles.get(b.id)}” đang dùng tài liệu này. Chuyển khóa đó vào thùng rác trước.
                    </li>
                  ) : (
                    <li key={b.id}>{b.reason}</li>
                  ),
                )}
              </ul>
            </div>
          </div>
        ) : (
          <ul className="plain-list">
            <li>Không xóa vĩnh viễn: mở Thùng rác để khôi phục.</li>
            <li>Lịch sử học, thẻ và ghi chú riêng của bạn được giữ.</li>
            {details.effects.jobs_to_cancel > 0 && <li>{details.effects.jobs_to_cancel} việc AI đang chạy sẽ dừng.</li>}
            {details.effects.sessions_to_cancel > 0 && <li>{details.effects.sessions_to_cancel} lượt luyện đang dở sẽ đóng.</li>}
            {details.effects.sharing_revoked && <li>Chia sẻ khóa (nếu có) sẽ tắt.</li>}
          </ul>
        )}
        <div className="dialog__actions">
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            Thôi
          </button>
          <button type="button" className="btn btn--danger" disabled={!details || !details.can_delete || busy} aria-busy={busy} onClick={() => void confirm()}>
            <Icon name="trash" size={16} /> Chuyển vào thùng rác
          </button>
        </div>
      </div>
    </dialog>
  );
}

export function LibraryPage() {
  const { toast } = useApp();
  const [tab, setTab] = useState<Tab>('courses');
  const [query, setQuery] = useState('');
  const [trashing, setTrashing] = useState<{ kind: Kind; id: string } | null>(null);
  const state = useLoad(async () => {
    await ensureSession();
    const [courses, sources, trash] = await Promise.all([
      api<Course[]>('/courses'),
      api<{ items: SourceSummary[]; total: number }>('/source-library?limit=100'),
      api<{ items: Lifecycle[] }>('/trash?limit=100'),
    ]);
    return { courses, sources: sources.items, trash: trash.items };
  }, []);

  const restore = async (item: Lifecycle) => {
    try {
      await api(`/${PLURAL[item.type]}/${item.id}/restore`, { method: 'POST', body: { expected_revision: item.revision, expected_lifecycle_version: item.lifecycle_version } });
      toast(`Đã khôi phục “${item.title}”`);
      state.reload();
    } catch (error) {
      toast(describeError(error).title);
    }
  };

  const makeCourse = (sourceId: string) => {
    try {
      localStorage.setItem('folio.create.v1', JSON.stringify({ sourceId, goal: '', notes: '' }));
    } catch {
      /* The create page then starts at step 1. */
    }
    navigate({ name: 'create' });
  };

  const q = fold(query.trim());
  const courses = (state.data?.courses ?? []).filter((c) => !q || fold(c.content.title).includes(q));
  const sources = (state.data?.sources ?? []).filter((s) => !q || fold(s.metadata.name).includes(q));
  const trash = (state.data?.trash ?? []).filter((t) => !q || fold(t.title).includes(q));

  return (
    <div className="page library">
      <header className="page-head">
        <div>
          <p className="eyebrow">Khóa học, tài liệu và thùng rác</p>
          <h1 className="page-title">Thư viện</h1>
        </div>
        <a className="btn btn--primary" href={hrefFor({ name: 'create' })}>
          <Icon name="plus" size={18} /> Tạo khóa mới
        </a>
      </header>

      <div className="library__bar">
        <div className="segmented segmented--fit" role="radiogroup" aria-label="Mục">
          <button type="button" role="radio" aria-checked={tab === 'courses'} onClick={() => setTab('courses')}>
            Khóa học {state.data ? `(${state.data.courses.length})` : ''}
          </button>
          <button type="button" role="radio" aria-checked={tab === 'sources'} onClick={() => setTab('sources')}>
            Tài liệu {state.data ? `(${state.data.sources.length})` : ''}
          </button>
          <button type="button" role="radio" aria-checked={tab === 'trash'} onClick={() => setTab('trash')}>
            Thùng rác {state.data?.trash.length ? `(${state.data.trash.length})` : ''}
          </button>
        </div>
        <label className="search">
          <Icon name="search" size={18} />
          <input className="field" value={query} placeholder="Tìm theo tên…" aria-label="Tìm trong thư viện" onChange={(e) => setQuery(e.target.value)} />
        </label>
      </div>

      {state.loading && !state.data && <LoadingRows rows={3} label="Đang mở thư viện…" />}
      {state.error != null && <ProblemNotice problem={describeError(state.error)} onRetry={state.reload} />}

      {state.data && tab === 'courses' && (
        courses.length === 0 ? (
          <EmptyState
            art={<Spot glyph="book" tone="sky" size={110} />}
            title={query ? 'Không có khóa trùng tên' : 'Chưa có khóa nào'}
            body="Tải slide, giáo trình hoặc ghi chú — Kẹp đọc hết rồi đề xuất lộ trình để bạn sửa trước khi tạo."
            action={
              <a className="btn btn--primary btn--lg" href={hrefFor({ name: 'create' })}>
                Tạo khóa mới
              </a>
            }
          />
        ) : (
          <ul className="library-list">
            {courses.map((course) => {
              const s = courseSummary(course);
              return (
                <li key={course.id} className="library-row">
                  <CourseCover courseId={course.id} title={course.content.title} size={56} />
                  <a className="library-row__text" href={hrefFor({ name: 'course', courseId: course.id })}>
                    <strong>{course.content.title}</strong>
                    <span className="meta">
                      {s.done}/{s.total} bài xong{s.notGenerated ? ` · ${s.notGenerated} bài chưa tạo` : ''}
                      {course.access_role === 'learner' ? ' · khóa được chia sẻ' : ''}
                    </span>
                    <span className="progress-bar" aria-hidden="true">
                      <span style={{ width: `${s.total ? Math.round((s.done / s.total) * 100) : 0}%` }} />
                    </span>
                  </a>
                  <span className="library-row__actions">
                    <a className="btn btn--secondary btn--sm" href={hrefFor({ name: 'cards', courseId: course.id })}>
                      Flashcard
                    </a>
                    <a className="btn btn--secondary btn--sm" href={hrefFor({ name: 'practice', courseId: course.id })}>
                      Ôn luyện
                    </a>
                    {course.access_role !== 'learner' && (
                      <button type="button" className="icon-btn" aria-label={`Chuyển ${course.content.title} vào thùng rác`} onClick={() => setTrashing({ kind: 'course', id: course.id })}>
                        <Icon name="trash" size={18} />
                      </button>
                    )}
                  </span>
                </li>
              );
            })}
          </ul>
        )
      )}

      {state.data && tab === 'sources' && (
        sources.length === 0 ? (
          <EmptyState art={<Spot glyph="papers" tone="butter" size={110} />} title={query ? 'Không có tài liệu trùng tên' : 'Chưa có tài liệu'} body="Tài liệu bạn tải lên khi tạo khóa sẽ nằm ở đây để dùng lại." />
        ) : (
          <ul className="library-list">
            {sources.map((source) => (
              <li key={source.id} className="library-row">
                <span className="library-row__icon">
                  <Icon name="file" size={22} />
                </span>
                <div className="library-row__text">
                  <strong>{source.metadata.name}</strong>
                  <span className="meta">
                    {size(source.metadata.bytes)} · tải ngày {day(source.created_at)}
                    {source.warning_count ? ` · ${source.warning_count} lưu ý khi đối chiếu` : ''}
                  </span>
                  <span>
                    <span className={source.reviewed ? 'tag tag--sage' : 'tag tag--butter'}>{source.reviewed ? 'đã kiểm tra bản đọc' : 'chưa kiểm tra bản đọc'}</span>
                  </span>
                </div>
                <span className="library-row__actions">
                  <button type="button" className="btn btn--secondary btn--sm" onClick={() => makeCourse(source.id)}>
                    <Icon name="sparkle" size={16} /> Tạo khóa
                  </button>
                  <a className="btn btn--ghost btn--sm" href={`/api/sources/${encodeURIComponent(source.id)}/original`} target="_blank" rel="noreferrer">
                    File gốc
                  </a>
                  <button type="button" className="icon-btn" aria-label={`Chuyển ${source.metadata.name} vào thùng rác`} onClick={() => setTrashing({ kind: 'source', id: source.id })}>
                    <Icon name="trash" size={18} />
                  </button>
                </span>
              </li>
            ))}
          </ul>
        )
      )}

      {state.data && tab === 'trash' && (
        trash.length === 0 ? (
          <EmptyState art={<Spot glyph="cards" tone="sage" size={110} />} title="Thùng rác trống" body="Khóa hoặc tài liệu bạn xóa sẽ nằm ở đây và khôi phục được; không có gì bị xóa vĩnh viễn." />
        ) : (
          <ul className="library-list">
            {trash.map((item) => (
              <li key={`${item.type}:${item.id}`} className="library-row">
                <span className="library-row__icon">
                  <Icon name={item.type === 'course' ? 'bookOpen' : 'file'} size={22} />
                </span>
                <div className="library-row__text">
                  <strong>{item.title}</strong>
                  <span className="meta">
                    {item.type === 'course' ? 'Khóa học' : 'Tài liệu'} · xóa ngày {day(item.deleted_at)}
                    {item.blockers.length ? ` · ${item.blockers[0].reason}` : ''}
                  </span>
                </div>
                <span className="library-row__actions">
                  <button type="button" className="btn btn--secondary btn--sm" disabled={!item.can_restore} onClick={() => void restore(item)}>
                    <Icon name="refresh" size={16} /> Khôi phục
                  </button>
                </span>
              </li>
            ))}
          </ul>
        )
      )}

      <TrashDialog
        target={trashing}
        courseTitles={new Map((state.data?.courses ?? []).map((c) => [c.id, c.content.title]))}
        onClose={() => setTrashing(null)}
        onDone={() => {
          setTrashing(null);
          state.reload();
        }}
      />
    </div>
  );
}
