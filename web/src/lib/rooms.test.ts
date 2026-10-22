import { describe, expect, it } from 'vitest';
import type { RoomPlayer, RoomSnapshot } from '../api/types';
import { answerKey, canStart, endReason, formatCode, normalizeCode, revealed, secondsLeft } from './rooms';

const player = (over: Partial<RoomPlayer>): RoomPlayer => ({
  member_id: 'm',
  nickname: 'A',
  state: 'joined',
  is_host: false,
  score: 0,
  answered_closed_questions: 0,
  connected: true,
  rank: 1,
  ...over,
});

const snapshot = (over: Partial<RoomSnapshot>): RoomSnapshot =>
  ({ phase: 'lobby', me: { member_id: 'h', state: 'joined', is_host: true }, scoreboard: [], solution: null, own_result: null, ...over }) as RoomSnapshot;

describe('room codes', () => {
  it('accepts codes typed with spaces, dashes and lower case', () => {
    expect(normalizeCode(' abcd-23 45 ')).toBe('ABCD2345');
    expect(formatCode('ABCD2345')).toBe('ABCD 2345');
  });
});

describe('secondsLeft', () => {
  it('counts down on the server clock, not the device clock', () => {
    const deadline = '2026-10-22T10:00:30Z';
    const deviceNow = Date.parse('2026-10-22T10:00:00Z');
    expect(secondsLeft(deadline, 0, deviceNow)).toBe(30);
    // Device runs 5 s behind the server: 5 s fewer remain.
    expect(secondsLeft(deadline, 5000, deviceNow)).toBe(25);
    expect(secondsLeft(deadline, 0, deviceNow + 60_000)).toBe(0);
    expect(secondsLeft(null, 0, deviceNow)).toBe(0);
  });
});

describe('canStart', () => {
  it('needs the host in the lobby with two connected people', () => {
    const two = [player({ is_host: true }), player({ member_id: 'b' })];
    expect(canStart(snapshot({ scoreboard: two }))).toBe(true);
    expect(canStart(snapshot({ scoreboard: [two[0], player({ member_id: 'b', connected: false })] }))).toBe(false);
    expect(canStart(snapshot({ scoreboard: two, me: { member_id: 'b', state: 'joined', is_host: false } }))).toBe(false);
    expect(canStart(snapshot({ scoreboard: two, phase: 'question_open' }))).toBe(false);
  });
});

describe('revealed', () => {
  it('shows nothing before the server closes the question', () => {
    expect(revealed(snapshot({}))).toBeUndefined();
  });

  it('maps the closed solution and own result to practice feedback', () => {
    const value = revealed(
      snapshot({ solution: { answer: 'B', explanation: 'vì…', source_refs: ['s1'] }, own_result: { correct: false, points: 0 } }),
    );
    expect(value).toMatchObject({ correct: false, reference: 'B', explanation: 'vì…', grading: 'fixed' });
    expect(revealed(snapshot({ solution: { answer: [1, 0], explanation: '', source_refs: [] } }))?.correct).toBeNull();
  });
});

describe('answerKey', () => {
  it('is stable for the same answer and changes with the answer', () => {
    const a = answerKey('room', 'q1', 'option-0');
    expect(answerKey('room', 'q1', 'option-0')).toBe(a);
    expect(answerKey('room', 'q1', 'option-1')).not.toBe(a);
    expect(answerKey('room', 'q2', 'option-0')).not.toBe(a);
    expect(a.length).toBeLessThanOrEqual(128);
  });
});

describe('endReason', () => {
  it('explains why a room stopped and falls back for unknown codes', () => {
    expect(endReason('host_disconnected')).toContain('mất kết nối');
    expect(endReason('something_new')).toBe('Phòng đã kết thúc.');
    expect(endReason(null)).toBe('Phòng đã kết thúc.');
  });
});
