import { ApiError } from '../../api/client';
import { describeError } from '../../lib/copy';

// Small per-device memory for quiz rooms. The join code is shown once by the
// server when the room is created, so the host's device keeps it to display
// in the lobby; the nickname is just a convenience.

const NICKNAME_KEY = 'folio.room.nickname';
const codeKey = (roomId: string) => `folio.room.code.${roomId}`;

function read(key: string): string {
  try {
    return localStorage.getItem(key) ?? '';
  } catch {
    return '';
  }
}

function write(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* Private mode: the value lives for this page only. */
  }
}

export const loadNickname = () => read(NICKNAME_KEY);
export const saveNickname = (name: string) => write(NICKNAME_KEY, name.trim());
export const loadRoomCode = (roomId: string) => read(codeKey(roomId)) || null;
export const saveRoomCode = (roomId: string, code: string) => write(codeKey(roomId), code);

/** Room errors from the server are written for players (“Phòng đã đủ người.”); show them as they are. */
export function roomProblem(error: unknown): string {
  if (error instanceof ApiError && error.status >= 400 && error.status < 500) return error.message;
  return describeError(error).title;
}
