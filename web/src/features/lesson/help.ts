import { api } from '../../api/client';
import type { HelpActionResponse, HelpReply, HelpThread } from '../../api/types';

export type HelpTarget =
  | { kind: 'question'; sessionId: string; itemId: string; label: string }
  | { kind: 'section'; courseId: string; unitId: string; index: number; revision: number; label: string };

const threads = new Map<string, Promise<string>>();

function targetKey(target: HelpTarget) {
  return target.kind === 'question' ? `q:${target.sessionId}:${target.itemId}` : `s:${target.courseId}:${target.unitId}:${target.index}:${target.revision}`;
}

/** One help thread per question/section; the backend returns the same id when it exists. */
export function threadFor(target: HelpTarget): Promise<string> {
  const key = targetKey(target);
  let pending = threads.get(key);
  if (!pending) {
    pending =
      target.kind === 'question'
        ? api<{ thread_id: string }>(`/sessions/${target.sessionId}/items/${encodeURIComponent(target.itemId)}/help`, { method: 'POST' }).then((r) => r.thread_id)
        : api<{ thread_id: string }>(`/courses/${target.courseId}/units/${target.unitId}/sections/${target.index}/help`, {
            body: { expected_revision: target.revision },
          }).then((r) => r.thread_id);
    threads.set(key, pending);
    pending.catch(() => threads.delete(key));
  }
  return pending;
}

export function readThread(threadId: string) {
  return api<HelpThread>(`/help/threads/${threadId}`);
}

/** Hint / reveal / explain for a question come from the saved solution: no AI, no Coin. */
export async function fixedHelp(target: Extract<HelpTarget, { kind: 'question' }>, action: 'hint' | 'reveal' | 'explain'): Promise<HelpReply> {
  const threadId = await threadFor(target);
  const response = await api<HelpActionResponse>(`/help/threads/${threadId}/actions`, { body: { action, message: '' } });
  return response.reply ?? {};
}
