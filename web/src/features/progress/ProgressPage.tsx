import { useState } from 'react';
import { api, ensureSession } from '../../api/client';
import type { Wallet } from '../../api/types';
import { hrefFor } from '../../app/router';
import { useApp, useLoad } from '../../app/store';
import { Icon, type IconName } from '../../components/Icon';
import { Spot, type Glyph, type Tone } from '../../components/Spot';
import { LoadingRows, ProblemNotice } from '../../components/StateViews';
import { describeError } from '../../lib/copy';
import { activityLevel, recentWeeks, studyMinutes, type Dashboard, type Missions } from './activity';

interface Achievements {
  earned: { code: string; earned_at: string }[];
  next: string[];
}
interface CheckIn {
  checked_today: boolean;
  current_streak: number;
  total_days: number;
  week: { date: string; checked: boolean }[];
  newly_checked?: boolean;
}
interface Ledger {
  ledger: { amount: number; reason: string; category: string | null; created_at: string }[];
}

const ACHIEVEMENTS: Record<string, { title: string; icon: IconName }> = {
  first_session: { title: 'Lượt luyện đầu tiên', icon: 'star' },
  study_day_3: { title: 'Học 3 ngày liền', icon: 'fire' },
  study_day_7: { title: 'Học 7 ngày liền', icon: 'fire' },
  five_units: { title: 'Xong 5 bài', icon: 'bookOpen' },
  course_complete: { title: 'Hoàn thành một khóa', icon: 'trophy' },
};
const CATEGORY: Record<string, string> = {
  onboarding: 'Coin khởi đầu',
  ai_spend: 'Hỏi/tạo bằng AI',
  learning: 'Học và ôn',
  mission: 'Nhiệm vụ ngày',
  achievement: 'Thành tựu',
  community: 'Cộng đồng',
};
const WEEKDAYS = ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN'];

function Stat({ glyph, tone, value, label }: { glyph: Glyph; tone: Tone; value: string; label: string }) {
  return (
    <div className="stat">
      <Spot glyph={glyph} tone={tone} size={70} />
      <div>
        <p className="stat__value">{value}</p>
        <p className="meta">{label}</p>
      </div>
    </div>
  );
}

/** Tiến độ: what the server recorded — rounds, card reviews, estimated study time — plus missions and Coin. */
export function ProgressPage() {
  const { toast, wallet, refreshWallet } = useApp();
  const state = useLoad(async () => {
    await ensureSession();
    const [dashboard, missions, achievements, checkIn, ledger, walletNow] = await Promise.all([
      api<Dashboard>('/dashboard'),
      api<Missions>('/missions'),
      api<Achievements>('/achievements'),
      api<CheckIn>('/activity/check-in'),
      api<Ledger>('/wallet/history'),
      api<Wallet>('/wallet'),
    ]);
    return { dashboard, missions, achievements, checkIn, ledger, walletNow };
  }, []);
  const [checking, setChecking] = useState(false);

  const checkIn = async () => {
    setChecking(true);
    try {
      const value = await api<CheckIn>('/activity/check-in', { body: {} });
      toast(value.newly_checked ? `Đã điểm danh · chuỗi ${value.current_streak} ngày` : 'Hôm nay bạn đã điểm danh rồi');
      refreshWallet();
      state.reload();
    } catch (error) {
      toast(describeError(error).title);
    } finally {
      setChecking(false);
    }
  };

  if (state.loading && !state.data) {
    return (
      <div className="page">
        <LoadingRows rows={3} label="Đang tổng hợp tiến độ…" />
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

  const { dashboard, missions, achievements, checkIn: today, ledger, walletNow } = state.data;
  const done = dashboard.learning_progress.reduce((n, c) => n + c.completed, 0);
  const minutes = studyMinutes(dashboard.timeline);
  const weeks = recentWeeks(dashboard.timeline, 18);
  const earned = new Set(achievements.earned.map((a) => a.code));

  return (
    <div className="page progress-page">
      <header className="page-head">
        <div>
          <p className="eyebrow">Ghi nhận từ các lượt học trên máy chủ</p>
          <h1 className="page-title">Tiến độ</h1>
        </div>
        <button type="button" className={today.checked_today ? 'btn btn--secondary' : 'btn btn--primary'} disabled={today.checked_today || checking} aria-busy={checking} onClick={() => void checkIn()}>
          <Icon name={today.checked_today ? 'check' : 'calendar'} size={18} /> {today.checked_today ? 'Đã điểm danh hôm nay' : 'Điểm danh hôm nay'}
        </button>
      </header>

      <section className="stats" aria-label="Tổng quan">
        <Stat glyph="book" tone="sky" value={`${done} bài`} label="đã hoàn thành" />
        <Stat glyph="chart" tone="butter" value={minutes >= 60 ? `${Math.floor(minutes / 60)} giờ ${minutes % 60} phút` : `${minutes} phút`} label="học trong năm (ước tính)" />
        <Stat glyph="flag" tone="coral" value={`${dashboard.weekly_streak.current} ngày`} label={`chuỗi học liên tiếp · dài nhất ${dashboard.weekly_streak.longest}`} />
        <Stat glyph="cards" tone="sage" value={`${(walletNow ?? wallet)?.available ?? 0} Coin`} label="hiện có · dùng để hỏi Kẹp" />
      </section>

      <div className="progress-grid">
        <section className="panel-card">
          <h2 className="title-m">Nhiệm vụ hôm nay</h2>
          <ul className="missions">
            {missions.daily.map((m) => (
              <li key={m.code} className={m.completed ? 'mission is-done' : 'mission'}>
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
          <h2 className="title-m">Hoạt động 18 tuần gần đây</h2>
          <div className="heatmap" role="img" aria-label="Lịch hoạt động: ô càng đậm là ngày học càng nhiều">
            <div className="heatmap__days">
              {WEEKDAYS.map((d) => (
                <span key={d}>{d}</span>
              ))}
            </div>
            <div className="heatmap__grid">
              {weeks.map((week, w) => (
                <div key={w} className="heatmap__week">
                  {week.map((day, d) => (
                    <span key={d} className={`heatmap__cell level-${day ? activityLevel(day) : 'none'}`} title={day ? `${day.date}: ${day.rounds} lượt, ${day.card_reviews} thẻ, ${Math.round(day.seconds / 60)} phút` : ''} />
                  ))}
                </div>
              ))}
            </div>
          </div>
          <p className="meta">
            Điểm danh: {today.total_days} ngày · chuỗi {today.current_streak} ngày. Thời gian là ước tính từ lúc trang học đang mở.
          </p>
        </section>

        <section className="panel-card">
          <h2 className="title-m">Theo khóa</h2>
          {dashboard.learning_progress.length === 0 && <p className="meta">Chưa có khóa nào.</p>}
          <ul className="course-progress">
            {dashboard.learning_progress.map((c) => (
              <li key={c.course_id}>
                <a href={hrefFor({ name: 'course', courseId: c.course_id })}>
                  <strong>{c.title}</strong>
                  <span className="meta">
                    {c.completed}/{c.total} bài · {c.percent}%
                  </span>
                  <span className="progress-bar" aria-hidden="true">
                    <span style={{ width: `${c.percent}%` }} />
                  </span>
                </a>
              </li>
            ))}
          </ul>
        </section>

        <section className="panel-card">
          <h2 className="title-m">Thành tựu</h2>
          <ul className="badges">
            {Object.entries(ACHIEVEMENTS).map(([code, a]) => (
              <li key={code} className={earned.has(code) ? 'badge is-earned' : 'badge'}>
                <span className="badge__icon">
                  <Icon name={a.icon} size={22} />
                </span>
                <span>{a.title}</span>
              </li>
            ))}
          </ul>
        </section>

        <section className="panel-card panel-card--wide">
          <h2 className="title-m">Coin gần đây</h2>
          <p className="meta">Coin là điểm thưởng trong app để dùng lượt hỏi/tạo bằng AI; không nạp tiền thật.</p>
          <ul className="ledger">
            {ledger.ledger.slice(0, 12).map((row, i) => (
              <li key={i}>
                <span className={row.amount >= 0 ? 'ledger__amount is-plus' : 'ledger__amount'}>
                  {row.amount >= 0 ? `+${row.amount}` : row.amount}
                </span>
                <span>{CATEGORY[row.category ?? ''] ?? row.reason}</span>
                <span className="meta">{new Intl.DateTimeFormat('vi-VN', { day: 'numeric', month: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(row.created_at))}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
