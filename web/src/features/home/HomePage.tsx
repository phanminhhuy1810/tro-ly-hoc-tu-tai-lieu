import { useEffect } from 'react';
import { api, ensureSession } from '../../api/client';
import type { Course, ResumeEntry } from '../../api/types';
import { hrefFor } from '../../app/router';
import { useApp, useLoad } from '../../app/store';
import { Icon } from '../../components/Icon';
import { Mascot } from '../../components/Mascot';
import { PageHeader } from '../../components/PageHeader';
import { Spot } from '../../components/Spot';
import { CourseCover } from '../course/covers';
import { EmptyState, LoadingRows, ProblemNotice } from '../../components/StateViews';
import { describeError } from '../../lib/copy';
import { courseSummary, pathNodes } from '../../lib/path';
import type { Dashboard, Missions } from '../progress/activity';

const CREATE_HREF = hrefFor({ name: 'create' });

function today() {
  return new Intl.DateTimeFormat('vi-VN', { weekday: 'long', day: 'numeric', month: 'long' }).format(new Date());
}

function greeting() {
  const hour = new Date().getHours();
  if (hour < 11) return 'Chào buổi sáng';
  if (hour < 14) return 'Chào buổi trưa';
  if (hour < 18) return 'Chào buổi chiều';
  return 'Chào buổi tối';
}

interface Next {
  course: Course;
  unitIndex: number;
  unitTitle: string;
  href: string;
  action: string;
  note: string;
}

/**
 * Where "Học tiếp" should take the learner: the most recently used course that
 * has a lesson ready now; only if none is ready, the next lesson to create.
 */
function nextStep(courses: Course[], resume: ResumeEntry[]): Next | null {
  const recent = [...resume].sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  const ordered = [
    ...recent.map((r) => ({ course: courses.find((c) => c.id === r.course_id), entry: r as ResumeEntry | undefined })),
    ...courses.map((course) => ({ course, entry: undefined })),
  ];
  const candidates = ordered.flatMap(({ course, entry }) => {
    const current = course && pathNodes(course, entry?.position.unit_id).find((n) => n.isCurrent);
    return course && current ? [{ course, entry, current }] : [];
  });
  const pick = candidates.find((c) => c.current.state === 'ready') ?? candidates[0];
  if (pick) {
    const { course, entry, current } = pick;
    const ready = current.state === 'ready';
    const midway = entry && entry.position.unit_id === current.unit.id;
    return {
      course,
      unitIndex: current.index,
      unitTitle: current.unit.title,
      href: ready ? hrefFor({ name: 'lesson', courseId: course.id, unitId: current.unit.id, mode: 'learn' }) : hrefFor({ name: 'course', courseId: course.id }),
      action: ready ? (midway ? 'Học tiếp' : 'Bắt đầu bài') : 'Tạo bài này',
      note: ready
        ? midway
          ? entry?.position.mode === 'cards'
            ? 'Bạn đang ôn thẻ của bài này.'
            : 'Bạn đang làm dở bài này — phần đã làm vẫn còn.'
          : 'Bài kế tiếp trong lộ trình của bạn.'
        : 'Bài kế tiếp chưa được tạo. Mở lộ trình để tạo khi bạn sẵn sàng.',
    };
  }
  return null;
}

export function HomePage() {
  const { refreshWallet, wallet } = useApp();
  const state = useLoad(async () => {
    await ensureSession();
    const [courses, resume] = await Promise.all([api<Course[]>('/courses'), api<ResumeEntry[]>('/resume')]);
    return { courses, resume };
  }, []);
  // Streak and missions are a nudge, not the page: if they fail to load the strip just stays hidden.
  const pulse = useLoad(async () => {
    await ensureSession();
    const [dashboard, missions] = await Promise.all([api<Dashboard>('/dashboard'), api<Missions>('/missions')]);
    return { streak: dashboard.weekly_streak.current, done: missions.daily.filter((m) => m.completed).length, total: missions.daily.length };
  }, []);
  useEffect(refreshWallet, [refreshWallet]);

  const next = state.data ? nextStep(state.data.courses, state.data.resume) : null;

  return (
    <div className="page home">
      <PageHeader
        title="Học tiếp"
        tone="sage"
        note={`${greeting()}! Hôm nay là ${today()} — học một chút là lửa lại cháy thêm một ngày.`}
        art={<Mascot mood="hello" size={86} />}
        actions={
          <a className="btn btn--secondary" href={CREATE_HREF}>
            <Icon name="plus" size={18} /> Tạo khóa từ tài liệu
          </a>
        }
      />

      {state.loading && !state.data && <LoadingRows rows={3} label="Đang mở các khóa đã lưu…" />}
      {state.error != null && <ProblemNotice problem={describeError(state.error)} onRetry={state.reload} />}

      {state.data && state.data.courses.length === 0 && (
        <EmptyState
          art={<Spot glyph="papers" tone="butter" size={120} badge />}
          title="Chưa có khóa nào"
          body="Chọn slide, giáo trình hoặc ghi chú của bạn — mình đọc rồi đề xuất lộ trình để bạn duyệt trước khi tạo bài."
          action={
            <a className="btn btn--primary btn--lg" href={CREATE_HREF}>
              Chọn tài liệu
            </a>
          }
        />
      )}

      {next && (
        <section className="resume enter" aria-label="Bài đang học">
          <Mascot mood="hello" size={92} />
          <div className="resume__body">
            <p className="eyebrow">{next.course.content.title}</p>
            <h2 className="display-title">
              Bài {next.unitIndex + 1}: {next.unitTitle}
            </h2>
            <p className="resume__note">{next.note}</p>
          </div>
          <a className="btn btn--primary btn--lg" href={next.href}>
            {next.action} <Icon name="arrowRight" size={18} />
          </a>
        </section>
      )}

      {pulse.data && state.data && state.data.courses.length > 0 && (
        <a className="today-strip enter" href={hrefFor({ name: 'progress' })}>
          <span className="today-strip__item">
            <Icon name="fire" size={18} /> <strong>{pulse.data.streak}</strong> ngày học liên tiếp
          </span>
          <span className="today-strip__item">
            <Icon name="flag" size={18} /> Nhiệm vụ hôm nay{' '}
            <strong>
              {pulse.data.done}/{pulse.data.total}
            </strong>
          </span>
          {wallet && (
            <span className="today-strip__item">
              <Icon name="coin" size={18} /> <strong>{wallet.available}</strong> Coin
            </span>
          )}
          <span className="today-strip__more">
            Xem tiến độ <Icon name="arrowRight" size={16} />
          </span>
        </a>
      )}

      {state.data && state.data.courses.length > 0 && (
        <section className="course-list" aria-labelledby="course-list-title">
          <div className="section-head">
            <h2 id="course-list-title" className="title-m">
              Khóa của bạn
            </h2>
            <span className="meta">{state.data.courses.length} khóa</span>
          </div>
          <ul>
            {state.data.courses.map((course) => {
              const s = courseSummary(course);
              const parts = [`${s.done}/${s.total} bài xong`];
              if (s.notGenerated) parts.push(`${s.notGenerated} bài chưa tạo`);
              return (
                <li key={course.id}>
                  <a className="course-row" href={hrefFor({ name: 'course', courseId: course.id })}>
                    <CourseCover courseId={course.id} title={course.content.title} size={60} />
                    <span className="course-row__text">
                      <span className="course-row__title">{course.content.title}</span>
                      <span className="meta">{parts.join(' · ')}</span>
                      <span className="progress-bar" aria-hidden="true">
                        <span style={{ width: `${s.total ? Math.round((s.done / s.total) * 100) : 0}%` }} />
                      </span>
                    </span>
                    <span className="btn btn--secondary btn--sm course-row__cta" aria-hidden="true">
                      Mở <Icon name="arrowRight" size={16} />
                    </span>
                  </a>
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </div>
  );
}
