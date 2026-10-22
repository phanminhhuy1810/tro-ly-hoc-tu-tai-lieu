import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api, ensureSession } from '../../api/client';
import type { Course, Progress, StudyCard } from '../../api/types';
import { hrefFor, navigate } from '../../app/router';
import { useApp, useLoad } from '../../app/store';
import { CoinConfirm } from '../../components/CoinConfirm';
import { Icon } from '../../components/Icon';
import { EmojiTile } from '../../components/EmojiTile';
import { LoadingRows, ProblemNotice } from '../../components/StateViews';
import { describeError } from '../../lib/copy';
import { chapterGroups, courseSummary, pathNodes, type PathNode } from '../../lib/path';
import { readUpTo } from '../lesson/useLessonSession';
import { CourseCover } from './covers';
import { CoverPicker } from './CoverPicker';
import { JobCard } from './JobCard';
import { MemoryCard } from './MemoryCard';
import { ProgressPath } from './ProgressPath';
import { useGeneration } from './useGeneration';

const STATE_ICON = { done: 'check', ready: 'bookOpen', not_generated: 'sparkle', locked: 'lock' } as const;

export function CoursePage({ courseId }: { courseId: string }) {
  const { toast, refreshWallet, setChatContext } = useApp();
  const [fresh, setFresh] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [coverOpen, setCoverOpen] = useState(false);
  const state = useLoad(async () => {
    await ensureSession();
    const [course, progress, cards] = await Promise.all([
      api<Course>(`/courses/${courseId}`),
      api<Progress>(`/courses/${courseId}/progress`).catch(() => null),
      api<StudyCard[]>(`/cards?course_id=${encodeURIComponent(courseId)}`).catch(() => [] as StudyCard[]),
    ]);
    return { course, progress, cards };
  }, [courseId]);
  const course = state.data?.course;

  const { reload } = state;
  const onDone = useCallback(
    (unitTitle: string) => {
      toast(`Bài “${unitTitle}” đã sẵn sàng`);
      refreshWallet();
      reload();
    },
    [toast, refreshWallet, reload],
  );
  const generation = useGeneration(course, onDone);
  const dialog = useRef<HTMLDialogElement>(null);
  const dialogOpen = generation.state.phase === 'asking' || generation.state.phase === 'quote';

  useEffect(() => {
    const el = dialog.current;
    if (!el) return;
    if (dialogOpen && !el.open) el.showModal();
    if (!dialogOpen && el.open) el.close();
  }, [dialogOpen]);

  useEffect(() => {
    if (!course) return;
    const current = pathNodes(course, state.data?.progress?.unit_id).find((n) => n.isCurrent);
    const unit = current?.unit.data ? current.unit : course.content.units.find((u) => u.data);
    if (unit) setChatContext({ courseId: course.id, courseTitle: course.content.title, unitId: unit.id, unitTitle: unit.title });
    // Highlight a unit that just became available (e.g. after finishing a lesson).
    const unlocked = sessionStorage.getItem('folio.justUnlocked');
    if (unlocked) {
      setFresh(unlocked);
      sessionStorage.removeItem('folio.justUnlocked');
    }
  }, [course, state.data?.progress?.unit_id, setChatContext]);

  const nodes = useMemo(() => (course ? pathNodes(course, state.data?.progress?.unit_id) : []), [course, state.data?.progress?.unit_id]);

  if (state.loading && !course) {
    return (
      <div className="page">
        <LoadingRows rows={4} label="Đang mở lộ trình…" />
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

  const summary = courseSummary(course);
  const cards = state.data?.cards ?? [];
  const unknownCards = cards.filter((c) => !c.memory?.remembered).length;
  const studied = course.content.units.some((u) => u.data && u.completed);
  const g = generation.state;
  const unitNumber = (id: string) => course.content.units.findIndex((u) => u.id === id) + 1;
  const creator = course.access_role !== 'learner';
  const groups = chapterGroups(nodes);

  const generate = (node: PathNode) => {
    if (g.phase === 'running') toast('Đang tạo một bài khác. Đợi bài đó xong nhé.');
    else generation.ask(node.unit);
  };
  const review = (node: PathNode | null) =>
    navigate({ name: 'lesson', courseId: course.id, unitId: node ? node.unit.id : 'tat-ca', mode: 'weak' });
  const focusNode = (unitId: string) => {
    setSelected(unitId);
    window.requestAnimationFrame(() =>
      document.querySelector('.path-pop')?.closest('.path-step')?.scrollIntoView({ behavior: 'smooth', block: 'center' }),
    );
  };

  return (
    <div className="page course">
      <a className="back" href="#/">
        <Icon name="arrowLeft" size={18} /> Học tiếp
      </a>
      <header className="course-head page-banner--sky">
        <button type="button" className="course-cover" disabled={!creator} onClick={() => setCoverOpen(true)} aria-label="Đổi ảnh bìa">
          <CourseCover courseId={course.id} title={course.content.title} size={96} />
          {creator && (
            <span className="course-cover__edit" aria-hidden="true">
              <Icon name="image" size={15} />
            </span>
          )}
        </button>
        <div className="course-head__text">
          <p className="eyebrow">{creator ? 'Khóa của bạn' : 'Khóa được chia sẻ'}</p>
          <h1 className="page-title">{course.content.title}</h1>
          <p className="meta">
            {summary.total} bài · {summary.done} bài đã xong
            {summary.notGenerated ? ` · ${summary.notGenerated} bài chưa tạo` : ''}
            {course.content.unlock_policy === 'locked' ? ' · mở dần theo lượt luyện' : ' · học tự do'}
          </p>
          <span className="progress-bar course-head__bar" aria-hidden="true">
            <span style={{ width: `${summary.total ? Math.round((summary.done / summary.total) * 100) : 0}%` }} />
          </span>
        </div>
      </header>

      <div className="course-grid">
        <section aria-label="Lộ trình">
          <JobCard
            state={g}
            onCancel={generation.cancelJob}
            onRetry={() => (g.phase === 'failed' ? generation.begin(g.unit) : undefined)}
            onContinue={() => (g.phase === 'continue' ? generation.begin(g.unit, g.jobId) : undefined)}
            onDismiss={generation.close}
          />
          <ProgressPath
            nodes={nodes}
            courseTitle={course.content.title}
            generatingUnitId={g.phase === 'running' ? g.unit.id : null}
            readFraction={(node) => {
              const sections = node.unit.data?.sections.length ?? 0;
              return sections ? Math.min(1, (readUpTo(course.id, node.unit.id, course.revision) + 1) / sections) : 0;
            }}
            reviewable={studied}
            justUnlocked={fresh}
            selected={selected}
            onSelect={setSelected}
            onOpen={(node) => navigate({ name: 'lesson', courseId: course.id, unitId: node.unit.id, mode: 'learn' })}
            onGenerate={generate}
            onReview={review}
          />
        </section>

        <aside className="course-aside" aria-label="Mục lục và cách học khác">
          <section className="toc">
            <h2 className="title-m">Mục lục</h2>
            {groups.map((group, i) => (
              <div key={i} className="toc__group">
                {group.title && <p className="eyebrow">{group.title}</p>}
                <ol>
                  {group.nodes.map((node) => (
                    <li key={node.unit.id}>
                      <button type="button" className={`toc__item toc__item--${node.state}${node.isCurrent ? ' is-current' : ''}`} onClick={() => focusNode(node.unit.id)}>
                        <span className="toc__icon">
                          <Icon name={STATE_ICON[node.state]} size={14} />
                        </span>
                        <span className="toc__title">
                          {node.index + 1}. {node.unit.title}
                        </span>
                      </button>
                    </li>
                  ))}
                </ol>
              </div>
            ))}
          </section>

          <MemoryCard courseId={course.id} />

          <section className="modes" aria-label="Cách học khác">
            <h2 className="title-m">Cách học khác</h2>
            <a className="mode-card" href={hrefFor({ name: 'cards', courseId: course.id })}>
              <EmojiTile icon="cards" tone="butter" size={50} />
              <span>
                <strong>Flashcard</strong>
                <span className="meta">{cards.length ? `${cards.length} thẻ · ${unknownCards} chưa nhớ` : 'Thẻ có sau khi tạo bài'}</span>
              </span>
              <Icon name="arrowRight" size={18} />
            </a>
            <a className="mode-card" href={hrefFor({ name: 'practice', courseId: course.id })}>
              <EmojiTile icon="target" tone="sky" size={50} />
              <span>
                <strong>Ôn luyện</strong>
                <span className="meta">Luyện hoặc kiểm tra theo phạm vi bài</span>
              </span>
              <Icon name="arrowRight" size={18} />
            </a>
            {studied ? (
              <a className="mode-card" href={hrefFor({ name: 'lesson', courseId: course.id, unitId: 'tat-ca', mode: 'weak' })}>
                <EmojiTile icon="flag" tone="coral" size={50} />
                <span>
                  <strong>Ôn câu sai</strong>
                  <span className="meta">Từ các bài đã luyện</span>
                </span>
                <Icon name="arrowRight" size={18} />
              </a>
            ) : (
              <div className="mode-card mode-card--muted">
                <EmojiTile icon="flag" tone="coral" size={50} />
                <span>
                  <strong>Ôn câu sai</strong>
                  <span className="meta">Có sau khi bạn luyện xong bài đầu tiên.</span>
                </span>
              </div>
            )}
          </section>

          <section className="modes" aria-label="Cùng học">
            <h2 className="title-m">Cùng học</h2>
            <a className="mode-card" href={hrefFor({ name: 'rooms', courseId: course.id })}>
              <EmojiTile icon="trophy" tone="peach" size={50} />
              <span>
                <strong>Phòng đố vui</strong>
                <span className="meta">Thi cùng bạn bè bằng bộ câu của khóa</span>
              </span>
              <Icon name="arrowRight" size={18} />
            </a>
            {creator && (
              <a className="mode-card" href={hrefFor({ name: 'share', courseId: course.id })}>
                <EmojiTile icon="people" tone="mint" size={50} />
                <span>
                  <strong>Chia sẻ khóa</strong>
                  <span className="meta">Giữ riêng, gửi mã mời hoặc đăng công khai</span>
                </span>
                <Icon name="arrowRight" size={18} />
              </a>
            )}
          </section>
        </aside>
      </div>

      {creator && <CoverPicker courseId={course.id} title={course.content.title} open={coverOpen} onClose={() => setCoverOpen(false)} />}

      <dialog
        ref={dialog}
        className="dialog"
        onCancel={(event) => {
          event.preventDefault();
          generation.close();
        }}
        aria-labelledby="gen-title"
      >
        {(g.phase === 'asking' || g.phase === 'quote') && (
          <div className="dialog__inner">
            <p className="eyebrow">Bài {unitNumber(g.unit.id)}</p>
            <h2 id="gen-title" className="title-l">
              Tạo bài “{g.unit.title}”
            </h2>
            <p className="notice__body">
              AI đọc toàn bộ phạm vi khóa trước (một lần cho cả khóa), rồi viết giải thích, ví dụ và câu luyện tập cho bài này. Trên máy này một bài thường mất
              vài phút. Bạn có thể rời trang — phần nào xong được lưu ngay.
            </p>
            {g.phase === 'asking' && g.problem && <ProblemNotice problem={g.problem} compact />}
            {g.phase === 'quote' ? (
              <CoinConfirm quote={g.quote} what="Tạo bài này" busy={g.busy} onConfirm={generation.confirm} onCancel={generation.close} />
            ) : (
              <div className="dialog__actions">
                <button type="button" className="btn btn--ghost" onClick={generation.close}>
                  Để sau
                </button>
                <button type="button" className="btn btn--primary" aria-busy={g.busy} disabled={g.busy} onClick={() => generation.begin(g.unit)}>
                  {g.busy ? 'Đang gửi…' : 'Bắt đầu tạo'}
                </button>
              </div>
            )}
          </div>
        )}
      </dialog>
    </div>
  );
}
