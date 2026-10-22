import { useEffect, useRef, type CSSProperties, type ReactNode } from 'react';
import { api, ensureSession } from '../../api/client';
import type { Wallet } from '../../api/types';
import { hrefFor } from '../../app/router';
import { useApp, useLoad } from '../../app/store';
import { Art, ArtBadge, type ArtName } from '../../components/Art';
import { CountUp } from '../../components/CountUp';
import { Flame } from '../../components/Flame';
import { Icon } from '../../components/Icon';
import { PageHeader } from '../../components/PageHeader';
import { LoadingRows, ProblemNotice } from '../../components/StateViews';
import { describeError } from '../../lib/copy';
import { activityLevel, describeDay, monthLabels, recentWeeks, studyMinutes, type Dashboard, type Missions } from './activity';

interface Achievements {
  earned: { code: string; earned_at: string }[];
  next: string[];
}
interface CheckIn {
  checked_today: boolean;
  current_streak: number;
  total_days: number;
  week: { date: string; checked: boolean }[];
}

const ACHIEVEMENTS: { code: string; title: string; how: string; art: ArtName; tone: string }[] = [
  { code: 'first_session', title: 'Lượt luyện đầu tiên', how: 'Nộp một lượt luyện bất kỳ.', art: 'glowing', tone: 'butter' },
  { code: 'study_day_3', title: '3 ngày không nghỉ', how: 'Có ngày học trọn vẹn 3 ngày liền.', art: 'fire', tone: 'peach' },
  { code: 'study_day_7', title: 'Tuần lửa', how: 'Có ngày học trọn vẹn 7 ngày liền.', art: 'medal', tone: 'pink' },
  { code: 'five_units', title: 'Năm bài xong', how: 'Hoàn thành 5 bài học.', art: 'books', tone: 'sky' },
  { code: 'course_complete', title: 'Về đích một khóa', how: 'Học xong mọi bài của một khóa.', art: 'trophy', tone: 'mint' },
];
const WEEKDAYS = ['T2', '', 'T4', '', 'T6', '', 'CN'];
const WEEK_SHORT = ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN'];
const LEVEL_NAME = ['Chưa học', 'Có mở bài hoặc ôn thẻ', 'Nộp 1 lượt', 'Nộp từ 2 lượt'];

function day(iso: string) {
  return new Intl.DateTimeFormat('vi-VN', { day: 'numeric', month: 'numeric', year: 'numeric' }).format(new Date(iso));
}

function Tile({ art, color, value, label, hint, href }: { art: ArtName; color: string; value: ReactNode; label: string; hint?: string; href?: string }) {
  const body = (
    <>
      <span className="tile__icon">
        <Art name={art} size={34} />
      </span>
      <span className="tile__text">
        <span className="tile__value">{value}</span>
        <span className="tile__label">{label}</span>
        {hint && (
          <span className="tile__hint">
            {hint} <Icon name="arrowRight" size={14} />
          </span>
        )}
      </span>
    </>
  );
  return href ? (
    <a className={`tile tile--${color}`} href={href}>
      {body}
    </a>
  ) : (
    <div className={`tile tile--${color}`}>{body}</div>
  );
}

/** The flame card: today's check-in happens by itself when you study, so this only shows and cheers. */
function StreakCard({ checkIn }: { checkIn: CheckIn }) {
  const lit = checkIn.checked_today;
  const today = new Date();
  const todayIso = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
  return (
    <section className={lit ? 'streak-card is-lit' : 'streak-card'} aria-label="Chuỗi ngày học">
      <div className="streak-card__flame">
        <Flame size={112} lit={lit || checkIn.current_streak > 0} />
      </div>
      <div className="streak-card__text">
        <p className="streak-card__count">
          <span>
            <CountUp value={checkIn.current_streak} />
          </span>{' '}
          ngày liền
        </p>
        <p className="streak-card__note">
          {lit
            ? 'Hôm nay đã điểm danh — tự động khi bạn học. Giữ lửa ngày mai nhé!'
            : checkIn.current_streak > 0
              ? 'Học một chút hôm nay (đọc bài, ôn vài thẻ) là lửa cháy tiếp.'
              : 'Học một chút là tự điểm danh — mở bài hoặc ôn vài thẻ để nhóm lửa.'}
        </p>
        <ol className="streak-week" aria-label="Tuần này">
          {checkIn.week.map((d, i) => (
            <li key={d.date} className={`${d.checked ? 'is-on' : ''} ${d.date === todayIso ? 'is-today' : ''}`.trim() || undefined}>
              <span className="streak-week__dot">{d.checked ? <Flame size={20} still /> : null}</span>
              <span className="streak-week__day">{WEEK_SHORT[i]}</span>
            </li>
          ))}
        </ol>
        {!lit && (
          <a className="btn btn--primary btn--sm streak-card__go" href="#/">
            Học tiếp để giữ lửa <Icon name="arrowRight" size={16} />
          </a>
        )}
      </div>
      <p className="streak-card__total">
        Tổng <strong>{checkIn.total_days}</strong> ngày đã điểm danh
      </p>
    </section>
  );
}

/** Contribution-style graph after codex-resets.com: chunky rounded cells, months on top, a springy hover. */
function ActivityGraph({ dashboard }: { dashboard: Dashboard }) {
  const weeks = recentWeeks(dashboard.timeline, 26);
  const months = monthLabels(weeks);
  const scroller = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // Newest weeks are on the right; start there on narrow screens.
    scroller.current?.scrollTo({ left: scroller.current.scrollWidth });
  }, []);
  return (
    <section className="graph-card" aria-labelledby="graph-title">
      <div className="graph-card__head">
        <h2 id="graph-title" className="title-m">
          Lịch học nửa năm qua
        </h2>
        <ul className="graph-legend" aria-label="Chú thích">
          {LEVEL_NAME.map((name, level) => (
            <li key={level}>
              <span className={`graph-cell level-${level}`} aria-hidden="true" /> {name}
            </li>
          ))}
        </ul>
      </div>
      <div className="graph-scroll" ref={scroller}>
        <div className="graph" style={{ '--weeks': weeks.length } as CSSProperties}>
          <span className="graph__corner" aria-hidden="true" />
          {months.map((label, w) => (
            <span key={`m${w}`} className="graph__month" style={{ gridColumn: w + 2 }}>
              {label}
            </span>
          ))}
          {WEEKDAYS.map((label, d) => (
            <span key={`d${d}`} className="graph__weekday" style={{ gridRow: d + 2 }}>
              {label}
            </span>
          ))}
          {weeks.map((week, w) =>
            week.map((value, d) =>
              value ? (
                <span
                  key={`${w}-${d}`}
                  className={`graph-cell level-${activityLevel(value)}`}
                  style={{ gridColumn: w + 2, gridRow: d + 2, '--w': w } as CSSProperties}
                  title={describeDay(value)}
                  tabIndex={-1}
                />
              ) : null,
            ),
          )}
        </div>
      </div>
      <p className="meta">Thời gian học là ước tính từ lúc trang học đang mở; ngày “trọn vẹn” là ngày bạn nộp một lượt luyện hoặc ôn đủ 5 thẻ.</p>
    </section>
  );
}

/** Tiến độ: streak, numbers, the study calendar, today's missions, each course and achievements. */
export function ProgressPage() {
  const { wallet } = useApp();
  const state = useLoad(async () => {
    await ensureSession();
    const [dashboard, missions, achievements, checkIn, walletNow] = await Promise.all([
      api<Dashboard>('/dashboard'),
      api<Missions>('/missions'),
      api<Achievements>('/achievements'),
      api<CheckIn>('/activity/check-in'),
      api<Wallet>('/wallet'),
    ]);
    return { dashboard, missions, achievements, checkIn, walletNow };
  }, []);

  if (state.loading && !state.data) {
    return (
      <div className="page">
        <LoadingRows rows={3} label="Đang gom lại hành trình của bạn…" />
      </div>
    );
  }
  if (state.error != null || !state.data) {
    return (
      <div className="page">
        <ProblemNotice problem={describeError(state.error)} onRetry={state.reload} />
      </div>
    );
  }

  const { dashboard, missions, achievements, checkIn, walletNow } = state.data;
  const done = dashboard.learning_progress.reduce((n, c) => n + c.completed, 0);
  const minutes = studyMinutes(dashboard.timeline);
  const earnedAt = (code: string) => achievements.earned.find((a) => a.code === code || a.code.startsWith(code + ':'))?.earned_at;
  const missionsDone = missions.daily.filter((m) => m.completed).length;

  return (
    <div className="page progress-page">
      <PageHeader
        title="Tiến độ"
        tone="peach"
        note="Bạn đã đi được bao xa — mỗi ngày học một chút là lửa lại cháy thêm một ngày."
        art={<ArtBadge name="calculus" size={92} />}
      />

      <div className="progress-hero">
        <StreakCard checkIn={checkIn} />
        <div className="tiles" aria-label="Con số chính">
          <Tile art="books" color="butter" value={<CountUp value={done} />} label="Bài đã học xong" />
          <Tile art="hourglass" color="pink" value={minutes >= 60 ? `${Math.floor(minutes / 60)}g ${minutes % 60}p` : `${minutes}p`} label="Thời gian học năm nay" />
          <Tile art="calendar" color="sky" value={<CountUp value={dashboard.weekly_streak.active_days} />} label="Ngày học trọn vẹn" />
          <Tile art="coin" color="mint" value={<CountUp value={(walletNow ?? wallet)?.available ?? 0} />} label="Coin đang có" hint="Xem lịch sử" href={hrefFor({ name: 'settings', section: 'coin' })} />
        </div>
      </div>

      <ActivityGraph dashboard={dashboard} />

      <div className="progress-pair">
        <section className="panel-card">
          <div className="panel-card__head">
            <h2 className="title-m">Nhiệm vụ hôm nay</h2>
            <span className={missionsDone === missions.daily.length ? 'tag tag--sage' : 'tag'}>
              {missionsDone}/{missions.daily.length}
            </span>
          </div>
          <ul className="missions">
            {missions.daily.map((m, i) => (
              <li key={m.code} className={m.completed ? 'mission is-done' : 'mission'} style={{ '--i': i } as CSSProperties}>
                <span className="mission__icon">
                  <Icon name={m.completed ? 'check' : m.code === 'cards' ? 'layers' : m.code === 'weak' ? 'flag' : 'star'} size={18} />
                </span>
                <div className="mission__text">
                  <strong>{m.title}</strong>
                  <span className="progress-bar" aria-hidden="true">
                    <span style={{ width: `${Math.round((m.progress / m.target) * 100)}%` }} />
                  </span>
                  <span className="meta">
                    {m.progress}/{m.target}
                    {m.coin_awarded ? ` · +${m.coin_awarded} Coin` : ''}
                    {m.suggest_initial_practice ? ' · cần có câu sai trước' : ''}
                  </span>
                </div>
              </li>
            ))}
          </ul>
          <p className="meta">Nhiệm vụ chỉ để thêm động lực, không khóa bài nào.</p>
        </section>

        <section className="panel-card">
          <h2 className="title-m">Từng khóa</h2>
          {dashboard.learning_progress.length === 0 && <p className="meta">Chưa có khóa nào.</p>}
          <ul className="course-progress">
            {dashboard.learning_progress.map((c) => (
              <li key={c.course_id}>
                <a href={hrefFor({ name: 'course', courseId: c.course_id })}>
                  <span className="course-progress__top">
                    <strong>{c.title}</strong>
                    <span className="course-progress__pct">{c.percent}%</span>
                  </span>
                  <span className="progress-bar" aria-hidden="true">
                    <span style={{ width: `${c.percent}%` }} />
                  </span>
                  <span className="meta">
                    {c.completed}/{c.total} bài
                  </span>
                </a>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <section className="achievements" aria-labelledby="achievements-title">
        <h2 id="achievements-title" className="title-m">
          Thành tựu
        </h2>
        <ul className="achievement-grid">
          {ACHIEVEMENTS.map((a, i) => {
            const at = earnedAt(a.code);
            return (
              <li key={a.code} className={`achievement achievement--${a.tone}${at ? ' is-earned' : ''}`} style={{ '--i': i } as CSSProperties}>
                <span className="achievement__icon">
                  <Art name={a.art} size={36} />
                  {!at && (
                    <span className="achievement__lock" aria-label="Chưa đạt">
                      <Icon name="lock" size={12} />
                    </span>
                  )}
                </span>
                <strong>{a.title}</strong>
                <span className="achievement__how">{a.how}</span>
                <span className={at ? 'tag tag--sage' : 'tag'}>{at ? `Đạt ngày ${day(at)}` : 'Chưa đạt'}</span>
              </li>
            );
          })}
        </ul>
      </section>
    </div>
  );
}
