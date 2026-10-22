// Thin fetch wrapper for the local backend. Every mutation stays same-origin;
// the backend owns grading, Coin and permissions, so nothing here decides them.

export class ApiError extends Error {
  readonly status: number;
  readonly code: string | undefined;
  readonly detail: unknown;

  constructor(status: number, message: string, code?: string, detail?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  body?: unknown;
  idempotencyKey?: string;
  quoteId?: string;
  signal?: AbortSignal;
}

let sessionPromise: Promise<void> | null = null;

/** Establish (or keep) the anonymous local profile cookie once per page. */
export function ensureSession(): Promise<void> {
  sessionPromise ??= fetch('/api/session', { method: 'POST', credentials: 'same-origin' }).then((r) => {
    if (!r.ok) throw new ApiError(r.status, 'Chưa mở được không gian học trên máy này.');
  });
  sessionPromise.catch(() => {
    sessionPromise = null;
  });
  return sessionPromise;
}

export function newKey(prefix: string): string {
  const random = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${random}`;
}

function errorFrom(status: number, payload: unknown): ApiError {
  const detail = (payload as { detail?: unknown } | null)?.detail ?? payload;
  if (typeof detail === 'string') return new ApiError(status, detail, undefined, detail);
  if (detail && typeof detail === 'object') {
    const record = detail as { code?: string; message?: string; detail?: string };
    const message = record.message ?? record.detail ?? 'Yêu cầu chưa thực hiện được.';
    return new ApiError(status, message, record.code, detail);
  }
  return new ApiError(status, 'Yêu cầu chưa thực hiện được.');
}

export async function api<T>(path: string, options: RequestOptions = {}, retried = false): Promise<T> {
  const headers: Record<string, string> = {};
  if (options.body !== undefined) headers['Content-Type'] = 'application/json';
  if (options.idempotencyKey) headers['Idempotency-Key'] = options.idempotencyKey;
  if (options.quoteId) headers['Coin-Quote-Id'] = options.quoteId;
  let response: Response;
  try {
    response = await fetch('/api' + path, {
      method: options.method ?? (options.body === undefined ? 'GET' : 'POST'),
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      credentials: 'same-origin',
      signal: options.signal,
    });
  } catch (cause) {
    if ((cause as Error)?.name === 'AbortError') throw cause;
    throw new ApiError(0, 'Không kết nối được máy chủ học trên máy này.', 'NETWORK');
  }
  if (response.status === 401 && !retried) {
    sessionPromise = null;
    await ensureSession();
    return api<T>(path, options, true);
  }
  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }
  if (!response.ok) throw errorFrom(response.status, payload);
  return payload as T;
}
