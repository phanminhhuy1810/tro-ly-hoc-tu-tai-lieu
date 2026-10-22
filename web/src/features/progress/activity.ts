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
