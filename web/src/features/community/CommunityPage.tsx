import { useState, type FormEvent } from 'react';
import { api, ApiError, ensureSession } from '../../api/client';
import type { CommunityCourse, Course } from '../../api/types';
import { hrefFor, navigate } from '../../app/router';
import { useApp, useLoad } from '../../app/store';
import { Icon } from '../../components/Icon';
import { Spot } from '../../components/Spot';
import { EmptyState, LoadingRows, ProblemNotice } from '../../components/StateViews';
import { creatorLabel, ratingText } from '../../lib/community';
import { describeError } from '../../lib/copy';
import { fold } from '../../lib/text';
import { CourseCover } from '../course/covers';
import { TogetherTabs } from '../together/TogetherTabs';

/** Join a shared course with the code its creator sent. */
function InviteForm({ initial }: { initial?: string }) {
  const { toast } = useApp();
  const [code, setCode] = useState(initial ?? '');
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const join = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setProblem(null);
    try {
      await ensureSession();
      const result = await api<{ course_id: string }>('/community/join', { body: { code: code.trim() } });
      toast('Đã vào khóa — tiến trình, sổ tay và chat của bạn là riêng');
      navigate({ name: 'course', courseId: result.course_id });
    } catch (error) {
      setProblem(error instanceof ApiError && error.status === 404 ? 'Mã mời không đúng hoặc người tạo đã thu hồi.' : describeError(error).title);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="panel-card invite-form" onSubmit={(event) => void join(event)}>
      <h2 className="title-m">Có mã mời?</h2>
      <p className="meta">Khóa chia sẻ riêng không hiện trong danh sách; nhập mã người tạo gửi cho bạn.</p>
      <input
        className="field"
        value={code}
        placeholder="Dán mã mời"
        aria-label="Mã mời"
        autoComplete="off"
        spellCheck={false}
        onChange={(event) => setCode(event.target.value)}
      />
      {problem && (
        <p className="missing" role="alert">
          {problem}
        </p>
      )}
      <button type="submit" className="btn btn--primary" disabled={busy || code.trim().length < 8} aria-busy={busy}>
        Vào khóa <Icon name="arrowRight" size={18} />
      </button>
    </form>
  );
}

/**
 * Khóa cộng đồng: public courses anyone here can preview and join. Joining
 * keeps progress, notebook and chat per person; nobody edits the creator's
 * content, and original files stay with the creator unless shared separately.
 */
export function CommunityPage({ code }: { code?: string }) {
  const [query, setQuery] = useState('');
  const state = useLoad(async () => {
    await ensureSession();
    const [items, mine] = await Promise.all([api<CommunityCourse[]>('/community'), api<Course[]>('/courses')]);
    return { items, roles: new Map(mine.map((course) => [course.id, course.access_role])) };
  }, []);

  const q = fold(query.trim());
  const items = (state.data?.items ?? []).filter((course) => !q || fold(`${course.title} ${creatorLabel(course.creator_name)}`).includes(q));

  return (
    <div className="page together">
      <header className="page-head">
        <div>
          <p className="eyebrow">Học cùng người khác</p>
          <h1 className="page-title">Cùng học</h1>
        </div>
        <TogetherTabs active="community" />
      </header>

      <div className="together-grid">
        <section aria-labelledby="community-title">
          {/* Opened from an invite link: joining is the point of the visit, so the code comes first. */}
          {code && <InviteForm initial={code} />}
          <div className="library__bar">
            <h2 id="community-title" className="title-m">
              Khóa công khai
            </h2>
            <label className="search">
              <Icon name="search" size={18} />
              <input className="field" value={query} placeholder="Tìm môn, tên khóa, người tạo…" aria-label="Tìm khóa cộng đồng" onChange={(e) => setQuery(e.target.value)} />
            </label>
          </div>

          {state.loading && !state.data && <LoadingRows rows={3} label="Đang tải khóa cộng đồng…" />}
          {state.error != null && <ProblemNotice problem={describeError(state.error)} onRetry={state.reload} />}

          {state.data &&
            (items.length === 0 ? (
              <EmptyState
                art={<Spot glyph="globe" tone="sky" size={110} />}
                title={query ? 'Không có khóa trùng tên' : 'Chưa có khóa công khai'}
                body="Khi bạn hoặc người khác đăng khóa công khai, khóa sẽ hiện ở đây để xem trước và tham gia."
                action={
                  <a className="btn btn--secondary" href={hrefFor({ name: 'library' })}>
                    Chia sẻ một khóa của bạn
                  </a>
                }
              />
            ) : (
              <ul className="community-list">
                {items.map((course) => {
                  const role = state.data!.roles.get(course.id);
                  const ready = course.units.filter((unit) => unit.generated).length;
                  const creator = creatorLabel(course.creator_name);
                  return (
                    <li key={course.id}>
                      <a className="community-card" href={hrefFor({ name: 'community', courseId: course.id })}>
                        <CourseCover courseId={course.id} title={course.title} size={64} />
                        <span className="community-card__text">
                          <strong>{course.title}</strong>
                          <span className="meta">
                            {creator ? `của ${creator} · ` : ''}
                            {ready}/{course.units.length} bài đã có nội dung
                          </span>
                          <span className="community-card__stats">
                            <span>
                              <Icon name="heart" size={15} /> {course.likes}
                            </span>
                            <span>{ratingText(course.rating, course.rating_count)}</span>
                          </span>
                        </span>
                        {role === 'learner' && <span className="tag tag--sage">Đang học</span>}
                        {role === 'creator' && <span className="tag">Khóa của bạn</span>}
                      </a>
                    </li>
                  );
                })}
              </ul>
            ))}
        </section>

        <aside className="together-aside">
          {!code && <InviteForm />}
          <section className="panel-card">
            <h2 className="title-m">Chia sẻ khóa của bạn</h2>
            <p className="meta">
              Mở khóa trong Thư viện rồi chọn “Chia sẻ khóa”: giữ riêng, gửi mã mời hoặc đăng công khai. Bạn xem trước những gì được chia sẻ trước khi áp dụng.
            </p>
            <a className="btn btn--secondary btn--sm" href={hrefFor({ name: 'library' })}>
              Mở Thư viện <Icon name="arrowRight" size={16} />
            </a>
          </section>
        </aside>
      </div>
    </div>
  );
}
