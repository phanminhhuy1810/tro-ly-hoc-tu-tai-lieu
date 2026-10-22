import type { GradeResult, RoomPhase, RoomPlayer, RoomSnapshot } from '../api/types';

// Quiz rooms run on the server: phase, deadline and score come from snapshots.
// These helpers only turn a snapshot into what the screen shows.

/** People type codes with spaces, dashes or lower case; the server compares upper-case letters and digits. */
export function normalizeCode(text: string): string {
  return text.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 10);
}

/** “ABCD2345” → “ABCD 2345”, easier to read aloud. */
export function formatCode(code: string): string {
  return code.replace(/(.{4})(?=.)/g, '$1 ');
}

/** How far the server clock is ahead of this device, taken when a snapshot arrives. */
export function clockOffset(serverTime: string, receivedAt: number): number {
  return Date.parse(serverTime) - receivedAt;
}

/** Whole seconds left before a server deadline, never negative. */
export function secondsLeft(deadline: string | null, offsetMs: number, now: number): number {
  if (!deadline) return 0;
  return Math.max(0, Math.ceil((Date.parse(deadline) - (now + offsetMs)) / 1000));
}

export function isTerminal(phase: RoomPhase): boolean {
  return phase === 'finished' || phase === 'cancelled';
}

export function onlinePlayers(board: RoomPlayer[]): number {
  return board.filter((player) => player.state === 'joined' && player.connected).length;
}

/** The server starts a room only for its host, from the lobby, with two people connected. */
export function canStart(snapshot: RoomSnapshot): boolean {
  return snapshot.me.is_host && snapshot.phase === 'lobby' && onlinePlayers(snapshot.scoreboard) >= 2;
}

export const PHASE_LABEL: Record<RoomPhase, string> = {
  lobby: 'Đang chờ',
  question_open: 'Đang làm câu',
  question_closed: 'Xem đáp án',
  finished: 'Đã xong',
  cancelled: 'Đã dừng',
};

const END_REASON: Record<string, string> = {
  all_questions_closed: 'Đã đi hết các câu.',
  host_closed_room: 'Chủ phòng đã đóng phòng.',
  host_left: 'Chủ phòng đã rời nên phòng dừng lại.',
  host_disconnected: 'Chủ phòng mất kết nối quá lâu nên phòng dừng lại.',
  room_expired: 'Phòng đã hết thời gian mở.',
  question_needs_review: 'Một câu vừa bị báo cần xem lại nên phòng dừng để không chấm sai.',
};

export function endReason(reason: string | null): string {
  return (reason && END_REASON[reason]) || 'Phòng đã kết thúc.';
}

/** A closed question's solution in the shape the practice feedback already uses. */
export function revealed(snapshot: RoomSnapshot): GradeResult | undefined {
  if (!snapshot.solution) return undefined;
  return {
    correct: snapshot.own_result ? snapshot.own_result.correct : null,
    reference: snapshot.solution.answer,
    explanation: snapshot.solution.explanation,
    rubric: [],
    source_refs: snapshot.solution.source_refs,
    grading: 'fixed',
  };
}

function hash(text: string, seed: number, factor: number): string {
  let value = seed;
  for (let i = 0; i < text.length; i += 1) value = (Math.imul(value, factor) + text.charCodeAt(i)) >>> 0;
  return value.toString(36);
}

/**
 * Idempotency key for one answer: resending the same answer after a lost
 * response replays safely, a different answer is a different intent.
 */
export function answerKey(roomId: string, questionId: string, answer: unknown): string {
  const text = `${roomId}|${questionId}|${JSON.stringify(answer)}`;
  return `room-answer-${hash(text, 5381, 33)}${hash(text, 2166136261, 16777619)}`;
}
