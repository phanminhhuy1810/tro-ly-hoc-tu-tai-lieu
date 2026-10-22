import { describe, expect, it } from 'vitest';
import { activityLevel, recentWeeks, studyMinutes, type DayActivity } from './activity';

const day = (date: string, extra: Partial<DayActivity> = {}): DayActivity => ({ date, rounds: 0, card_reviews: 0, seconds: 0, qualified: false, ...extra });

describe('activity summary', () => {
  it('turns seconds into minutes and rounds into intensity', () => {
    expect(studyMinutes([day('2026-10-20', { seconds: 600 }), day('2026-10-21', { seconds: 90 })])).toBe(12);
    expect([activityLevel(day('d')), activityLevel(day('d', { seconds: 30 })), activityLevel(day('d', { rounds: 1 })), activityLevel(day('d', { rounds: 3 }))]).toEqual([0, 1, 2, 3]);
  });

  it('builds Monday-first weeks ending today and leaves future days empty', () => {
    // 2026-10-22 is a Thursday.
    const weeks = recentWeeks([day('2026-10-20', { rounds: 1 })], 2, new Date(2026, 9, 22));
    expect(weeks).toHaveLength(2);
    expect(weeks[1].map((d) => d?.date ?? null)).toEqual(['2026-10-19', '2026-10-20', '2026-10-21', '2026-10-22', null, null, null]);
    expect(weeks[1][1]?.rounds).toBe(1);
    expect(weeks[0][0]?.date).toBe('2026-10-12');
  });
});
