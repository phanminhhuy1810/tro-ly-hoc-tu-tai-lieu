import { api, ApiError, newKey } from './client';
import type { CoinQuote, Job } from './types';

const TERMINAL = new Set(['succeeded', 'failed', 'cancelled']);

export interface ObserveOptions {
  onUpdate?: (job: Job) => void;
  timeoutMs?: number;
  pollMs?: number;
  signal?: AbortSignal;
  EventSourceClass?: typeof EventSource | null;
  fetchJob?: (jobId: string) => Promise<Job>;
}

/**
 * Watch an accepted job until it ends. Observation never submits or retries AI
 * work: a lost stream falls back to GET polling of the same job id.
 */
export function observeJob(jobId: string, options: ObserveOptions = {}): Promise<Job> {
  const {
    onUpdate = () => {},
    timeoutMs = 210_000,
    pollMs = 1200,
    signal,
    EventSourceClass = typeof EventSource === 'undefined' ? null : EventSource,
    fetchJob = (id: string) => api<Job>('/jobs/' + encodeURIComponent(id)),
  } = options;

  return new Promise<Job>((resolve, reject) => {
    let stream: EventSource | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let done = false;
    let polling = false;
    let fallback = !EventSourceClass;
    let lastVersion = -1;
    let lastStatus = '';

    const close = () => {
      stream?.close();
      clearTimeout(timer);
      clearTimeout(deadline);
      signal?.removeEventListener('abort', onAbort);
    };
    const fail = (error: Error) => {
      if (done) return;
      done = true;
      close();
      reject(error);
    };
    const accept = (job: Job) => {
      if (done || job.id !== jobId) return;
      const version = job.progress?.version ?? 0;
      if (version < lastVersion) return;
      if (version !== lastVersion || job.status !== lastStatus) {
        lastVersion = version;
        lastStatus = job.status;
        onUpdate(job);
      }
      if (job.feedback_deferred) {
        fail(new ApiError(403, 'Kết thúc lượt kiểm tra trước khi xem phản hồi.', 'FEEDBACK_DEFERRED'));
        return;
      }
      if (TERMINAL.has(job.status)) {
        done = true;
        close();
        resolve(job);
      }
    };
    const poll = async () => {
      if (done || polling) return;
      polling = true;
      try {
        accept(await fetchJob(jobId));
      } catch (error) {
        fail(error as Error);
      } finally {
        polling = false;
        if (!done && fallback) timer = setTimeout(poll, pollMs);
      }
    };
    const onAbort = () => fail(new DOMException('Đã ngừng theo dõi.', 'AbortError'));
    const deadline = setTimeout(
      () => fail(new ApiError(0, 'Việc tạo vẫn chạy ở máy chủ. Mở lại để tiếp tục theo dõi.', 'OBSERVATION_TIMEOUT')),
      timeoutMs,
    );
    signal?.addEventListener('abort', onAbort);

    if (EventSourceClass) {
      try {
        stream = new EventSourceClass('/api/jobs/' + encodeURIComponent(jobId) + '/events');
        stream.addEventListener('snapshot', (event) => {
          try {
            accept(JSON.parse((event as MessageEvent<string>).data) as Job);
          } catch (error) {
            fail(error as Error);
          }
        });
        stream.addEventListener('session_expired', () =>
          fail(new ApiError(401, 'Phiên đã hết hạn; phần đã lưu vẫn còn.', 'SESSION_EXPIRED')),
        );
        stream.onerror = () => {
          stream?.close();
          fallback = true;
          clearTimeout(timer);
          if (!done) void poll();
        };
      } catch {
        fallback = true;
      }
    }
    void poll();
  });
}

export type AiStart<T> =
  | { kind: 'done'; value: T }
  | { kind: 'job'; jobId: string }
  | { kind: 'quote'; quote: CoinQuote; confirm: () => Promise<AiStart<T>> };

/**
 * One AI intent = one Idempotency-Key. If the backend asks for Coin
 * confirmation, `confirm` re-sends the same body and key with the quote id;
 * nothing is charged or queued before that.
 */
export async function startAi<T>(path: string, body: unknown, key = newKey('ai'), quoteId?: string): Promise<AiStart<T>> {
  try {
    const value = await api<T & { job_id?: string }>(path, { body, idempotencyKey: key, quoteId });
    if (value && typeof value === 'object' && typeof value.job_id === 'string') return { kind: 'job', jobId: value.job_id };
    return { kind: 'done', value };
  } catch (error) {
    if (error instanceof ApiError && error.status === 402 && error.code === 'COIN_CONFIRMATION_REQUIRED') {
      const quote = error.detail as CoinQuote;
      return { kind: 'quote', quote, confirm: () => startAi<T>(path, body, key, quote.quote_id) };
    }
    throw error;
  }
}
