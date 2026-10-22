export interface DayActivity {
  date: string;
  rounds: number;
  card_reviews: number;
  seconds: number;
  qualified: boolean;
}

/** GET /dashboard */
export interface Dashboard {
  timeline: DayActivity[];
  weekly_streak: { current: number; longest: number; active_days: number; week: { date: string; completed: boolean }[] };
  learning_progress: { course_id: string; title: string; completed: number; total: number; percent: number; next_unit_id: string | null }[];
}

/** GET /missions */
export interface Missions {
  daily: { code: string; title: string; progress: number; target: number; completed: boolean; coin_awarded: number; suggest_initial_practice?: boolean }[];
}

/** Estimated study minutes in the dashboard year. */
export function studyMinutes(timeline: DayActivity[]): number {
  return Math.round(timeline.reduce((n, d) => n + d.seconds, 0) / 60);
}

/** 0 = nothing, 1 = opened/reviewed, 2 = one round, 3 = two or more rounds. */
export function activityLevel(day: DayActivity): number {
  if (day.rounds >= 2) return 3;
  if (day.rounds >= 1 || day.qualified) return 2;
  return day.seconds > 0 || day.card_reviews > 0 ? 1 : 0;
}

/**
 * The last `count` Monday-first weeks up to `today` (inclusive). Days after
 * today, or outside the timeline year, are null so the grid keeps its shape.
 */
export function recentWeeks(timeline: DayActivity[], count: number, today = new Date()): (DayActivity | null)[][] {
  const byDate = new Map(timeline.map((d) => [d.date, d]));
  const iso = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
  const end = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const monday = new Date(end);
  monday.setDate(end.getDate() - ((end.getDay() + 6) % 7));
  const start = new Date(monday);
  start.setDate(monday.getDate() - 7 * (count - 1));
  const weeks: (DayActivity | null)[][] = [];
  for (let w = 0; w < count; w += 1) {
    const week: (DayActivity | null)[] = [];
    for (let d = 0; d < 7; d += 1) {
      const date = new Date(start);
      date.setDate(start.getDate() + w * 7 + d);
      week.push(date > end ? null : byDate.get(iso(date)) ?? { date: iso(date), rounds: 0, card_reviews: 0, seconds: 0, qualified: false });
    }
    weeks.push(week);
  }
  return weeks;
}

/** “Thg 6” above the first week column of each month, like a contribution graph. */
export function monthLabels(weeks: (DayActivity | null)[][]): string[] {
  let previous = -1;
  const labels = weeks.map((week) => {
    const first = week.find(Boolean);
    if (!first) return '';
    const month = Number(first.date.slice(5, 7));
    if (month === previous) return '';
    previous = month;
    return `Thg ${month}`;
  });
  // A label needs about three columns: drop one the next month would run into (usually a partial first month).
  let next = Infinity;
  for (let w = labels.length - 1; w >= 0; w -= 1) {
    if (!labels[w]) continue;
    if (next - w < 3) labels[w] = '';
    else next = w;
  }
  return labels;
}

const WEEKDAY_NAME = ['Chủ nhật', 'Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7'];

/** Tooltip for one day of the graph, in plain words. */
export function describeDay(day: DayActivity): string {
  const [year, month, date] = day.date.split('-').map(Number);
  const head = `${WEEKDAY_NAME[new Date(year, month - 1, date).getDay()]}, ${date}/${month}`;
  const parts: string[] = [];
  if (day.rounds) parts.push(`${day.rounds} lượt luyện`);
  if (day.card_reviews) parts.push(`${day.card_reviews} thẻ`);
  if (day.seconds >= 60) parts.push(`${Math.round(day.seconds / 60)} phút`);
  return parts.length ? `${head}: ${parts.join(' · ')}` : `${head}: chưa học`;
}
