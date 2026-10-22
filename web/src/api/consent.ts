import { observeJob, startAi, type AiStart } from './jobs';
import type { CoinQuote, Job } from './types';

export type AiOutcome<T> =
  | { kind: 'done'; value: T | null; job?: Job }
  | { kind: 'failed'; job: Job }
  | { kind: 'quote'; quote: CoinQuote; confirm: () => Promise<AiStart<T>> };

export interface Watch {
  onJob?: (jobId: string) => void;
  onUpdate?: (job: Job) => void;
}

/** Carry an accepted (or cached) AI request to its end. */
export async function settleAi<T>(start: AiStart<T>, watch: Watch = {}): Promise<AiOutcome<T>> {
  if (start.kind === 'quote') return start;
  if (start.kind === 'done') return { kind: 'done', value: start.value };
  watch.onJob?.(start.jobId);
  const job = await observeJob(start.jobId, { onUpdate: watch.onUpdate });
  if (job.status !== 'succeeded') return { kind: 'failed', job };
  return { kind: 'done', value: job.result as T, job };
}

/**
 * Send an AI request from a button that already shows its Coin price
 * ("Gửi · 1 Coin"). Pressing it is the confirmation, so a quote for at most
 * that price is accepted straight away. A higher price or missing Coin goes
 * back to the screen to decide; nothing is held before that.
 */
export async function askAi<T>(path: string, body: unknown, shownPrice: number, watch: Watch = {}): Promise<AiOutcome<T>> {
  let start = await startAi<T>(path, body);
  if (start.kind === 'quote' && !start.quote.insufficient_coin && start.quote.amount <= shownPrice) start = await start.confirm();
  return settleAi(start, watch);
}
