import { useCallback, useEffect, useRef, useState } from 'react';
import { askAi, settleAi, type AiOutcome } from '../../api/consent';
import { observeJob, type AiStart } from '../../api/jobs';
import type { CoinQuote, Course, HelpThread, Unit } from '../../api/types';
import { useApp } from '../../app/store';
import { describeError, describeJobFailure, type Problem } from '../../lib/copy';
import { readThread, threadFor, type HelpTarget } from './help';

export type TutorAction = 'ask' | 'explain' | 'simpler' | 'detail';

export interface Pending {
  action: TutorAction;
  message: string;
  since: number;
}

export interface QuoteState {
  quote: CoinQuote;
  confirm: () => Promise<AiStart<unknown>>;
  action: TutorAction;
  message: string;
}

type ByIndex<T> = Record<number, T | undefined>;

/**
 * The learn chat keeps one saved help thread per reading section (the backend
 * pins the section and its sources), so questions asked here come back when
 * the learner reopens the lesson, on any device.
 */
export function useSectionChat(course: Course, unit: Unit, revealed: number) {
  const { priceOf, refreshWallet } = useApp();
  const [threads, setThreads] = useState<ByIndex<HelpThread>>({});
  const [pending, setPending] = useState<ByIndex<Pending>>({});
  const [problems, setProblems] = useState<ByIndex<{ problem: Problem; retry?: () => void }>>({});
  const [quotes, setQuotes] = useState<ByIndex<QuoteState>>({});
  const loaded = useRef(new Set<number>());

  const target = useCallback(
    (index: number): HelpTarget => ({
      kind: 'section',
      courseId: course.id,
      unitId: unit.id,
      index,
      revision: course.revision,
      label: unit.data?.sections[index]?.title ?? '',
    }),
    [course.id, course.revision, unit],
  );

  const refresh = useCallback(async (index: number, threadId: string) => {
    const thread = await readThread(threadId);
    setThreads((all) => ({ ...all, [index]: thread }));
    return thread;
  }, []);

  // History of the sections on screen, loaded once each; an answer still being
  // written (e.g. after a reload) is picked up and shown when it lands.
  useEffect(() => {
    let alive = true;
    (async () => {
      for (let index = 0; index < revealed; index += 1) {
        if (loaded.current.has(index)) continue;
        loaded.current.add(index);
        try {
          const id = await threadFor(target(index));
          const thread = await refresh(index, id);
          if (!alive) return;
          const job = thread.pending_jobs[0];
          if (job) {
            setPending((all) => ({ ...all, [index]: { action: 'ask', message: '', since: Date.now() } }));
            observeJob(job)
              .then(() => refresh(index, id))
              .finally(() => alive && setPending((all) => ({ ...all, [index]: undefined })));
          }
        } catch {
          // No history is fine; asking reports a real problem if one exists.
          loaded.current.delete(index);
        }
      }
    })();
    return () => {
      alive = false;
    };
  }, [revealed, target, refresh]);

  const finish = useCallback(
    async (index: number, threadId: string, outcome: AiOutcome<unknown>, action: TutorAction, message: string, retry: () => void) => {
      refreshWallet();
      if (outcome.kind === 'quote') {
        setQuotes((all) => ({ ...all, [index]: { quote: outcome.quote, confirm: outcome.confirm, action, message } }));
      } else if (outcome.kind === 'failed') {
        setProblems((all) => ({ ...all, [index]: { problem: describeJobFailure(outcome.job), retry } }));
      }
      await refresh(index, threadId).catch(() => undefined);
      setPending((all) => ({ ...all, [index]: undefined }));
    },
    [refresh, refreshWallet],
  );

  const send = useCallback(
    async (index: number, action: TutorAction, message = ''): Promise<boolean> => {
      const retry = () => void send(index, action, message);
      setProblems((all) => ({ ...all, [index]: undefined }));
      setQuotes((all) => ({ ...all, [index]: undefined }));
      setPending((all) => ({ ...all, [index]: { action, message, since: Date.now() } }));
      try {
        const threadId = await threadFor(target(index));
        const outcome = await askAi(`/help/threads/${threadId}/actions`, { action, message }, priceOf('inline_help'));
        await finish(index, threadId, outcome, action, message, retry);
        return outcome.kind === 'done';
      } catch (error) {
        setPending((all) => ({ ...all, [index]: undefined }));
        setProblems((all) => ({ ...all, [index]: { problem: describeError(error), retry } }));
        return false;
      }
    },
    [target, priceOf, finish],
  );

  const confirmQuote = useCallback(
    async (index: number) => {
      const current = quotes[index];
      if (!current) return;
      setQuotes((all) => ({ ...all, [index]: undefined }));
      setPending((all) => ({ ...all, [index]: { action: current.action, message: current.message, since: Date.now() } }));
      const retry = () => void send(index, current.action, current.message);
      try {
        const threadId = await threadFor(target(index));
        await finish(index, threadId, await settleAi(await current.confirm()), current.action, current.message, retry);
      } catch (error) {
        setPending((all) => ({ ...all, [index]: undefined }));
        setProblems((all) => ({ ...all, [index]: { problem: describeError(error), retry } }));
      }
    },
    [quotes, target, finish, send],
  );

  const dismissQuote = useCallback((index: number) => setQuotes((all) => ({ ...all, [index]: undefined })), []);

  return { threads, pending, problems, quotes, send, confirmQuote, dismissQuote, price: priceOf('inline_help') };
}
