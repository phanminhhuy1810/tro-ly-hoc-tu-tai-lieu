import { describe, expect, it } from 'vitest';
import { ApiError } from '../api/client';
import { describeError, describeJobFailure, formatElapsed, lessonWaiting, locatorLabel } from './copy';

describe('describeError speaks to the learner, keeps raw text aside', () => {
  it('turns an unreachable local model into an actionable message', () => {
    const problem = describeJobFailure({ status: 'failed', error: { code: 'CONNECTION_FAILED', message: 'httpx.ConnectError …' } });
    expect(problem.title).toBe('AI trên máy này đang tắt');
    expect(problem.body).not.toMatch(/httpx/);
    expect(problem.technical).toMatch(/httpx/);
    expect(problem.canRetry).toBe(true);
  });

  it('explains a stale version without blaming the learner', () => {
    const problem = describeError(new ApiError(409, 'Khóa học đã đổi; tải lại trước khi tạo.'));
    expect(problem.title).toMatch(/thay đổi/);
    expect(problem.body).toMatch(/vẫn còn/);
  });

  it('shows learner-facing backend messages for 422/403 as the body', () => {
    expect(describeError(new ApiError(422, 'Nhập câu hỏi cho phần đang học.')).body).toBe('Nhập câu hỏi cho phần đang học.');
  });

  it('never claims a retry fixes missing Coin', () => {
    expect(describeError(new ApiError(402, 'x', 'INSUFFICIENT_COIN')).canRetry).toBe(false);
  });

  it('falls back to a calm generic message for unknown failures', () => {
    const problem = describeJobFailure({ status: 'failed', error: { message: 'Traceback …' } });
    expect(problem.title).toBe('Lượt này chưa xong');
    expect(problem.technical).toMatch(/Traceback/);
  });
});

describe('lessonWaiting reflects reported progress only', () => {
  it('starts in the reading stage while queued', () => {
    const view = lessonWaiting({ phase: 'queued', requests: [], planned_stages: null, saved_stages: 0 });
    expect(view.headline).toMatch(/chờ/);
    expect(view.stages.map((s) => s.state)).toEqual(['active', 'waiting', 'waiting', 'waiting']);
  });

  it('marks earlier stages done once questions are being drafted', () => {
    const view = lessonWaiting({
      phase: 'receiving',
      planned_stages: 7,
      saved_stages: 2,
      requests: [
        { index: 1, schema: 'ChapterBrief', phase: 'received' },
        { index: 2, schema: 'LessonReading', phase: 'received' },
        { index: 3, schema: 'McqDraft', phase: 'received' },
        { index: 4, schema: 'ClozeDraft', phase: 'receiving' },
      ],
    });
    expect(view.headline).toMatch(/soạn câu/);
    expect(view.stages.map((s) => s.state)).toEqual(['done', 'done', 'active', 'waiting']);
    expect(view.stages[2].detail).toBe('1 câu');
    expect(view.saved).toMatch(/2\/7/);
  });

  it('uses chapter part counts when the server reports them', () => {
    const view = lessonWaiting({
      phase: 'receiving',
      planned_stages: null,
      saved_stages: 0,
      chapter_context: { read_parts: 2, total_parts: 5 },
      requests: [{ index: 1, schema: 'ChapterBrief', phase: 'receiving' }],
    });
    expect(view.stages[0].detail).toBe('2/5 phần');
  });
});

describe('small formatters', () => {
  it('labels source locations', () => {
    expect(locatorLabel({ type: 'line', line: 3 })).toBe('dòng 3');
    expect(locatorLabel({ type: 'page', page: 12 })).toBe('trang 12');
    expect(locatorLabel({ type: 'slide', slide: 4 })).toBe('slide 4');
    expect(locatorLabel(undefined)).toBe('trích đoạn');
  });

  it('formats real elapsed time, not an estimate', () => {
    expect(formatElapsed(42_000)).toBe('42 giây');
    expect(formatElapsed(125_000)).toBe('2 phút 5 giây');
  });
});
