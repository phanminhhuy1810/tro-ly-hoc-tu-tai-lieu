import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../../api/client';
import { observeJob, startAi, type AiStart } from '../../api/jobs';
import type { CoinQuote, Course, Job, Unit } from '../../api/types';
import { describeError, describeJobFailure, type Problem } from '../../lib/copy';

export type Generation =
  | { phase: 'idle' }
  | { phase: 'asking'; unit: Unit; busy?: boolean; problem?: Problem }
  | { phase: 'quote'; unit: Unit; quote: CoinQuote; confirm: () => Promise<AiStart<unknown>>; busy?: boolean }
  | { phase: 'running'; unit: Unit; jobId: string; job: Job | null; startedAt: number }
  | { phase: 'continue'; unit: Unit; jobId: string; job: Job }
  | { phase: 'failed'; unit: Unit; problem: Problem; jobId?: string };

interface Stored {
  jobId: string;
  unitId: string;
  startedAt: number;
}

const storeKey = (courseId: string) => `folio.job.${courseId}`;

function readStored(courseId: string): Stored | null {
  try {
    const raw = localStorage.getItem(storeKey(courseId));
    return raw ? (JSON.parse(raw) as Stored) : null;
  } catch {
    return null;
  }
}

function writeStored(courseId: string, value: Stored | null) {
  try {
    if (value) localStorage.setItem(storeKey(courseId), JSON.stringify(value));
    else localStorage.removeItem(storeKey(courseId));
  } catch {
    /* The job still runs; only reconnect-after-reload is lost. */
  }
}

/**
 * Lesson generation for one course: ask → (Coin quote) → job → watch.
 * Re-opening the page watches the same job instead of starting a new one.
 */
export function useGeneration(course: Course | undefined, onDone: (unitTitle: string) => void) {
  const [state, setState] = useState<Generation>({ phase: 'idle' });
  const abort = useRef<AbortController | null>(null);

  const watch = useCallback(
    (unit: Unit, jobId: string, startedAt: number) => {
      if (!course) return;
      abort.current?.abort();
      const controller = new AbortController();
      abort.current = controller;
      setState({ phase: 'running', unit, jobId, job: null, startedAt });
      writeStored(course.id, { jobId, unitId: unit.id, startedAt });
      observeJob(jobId, {
        signal: controller.signal,
        onUpdate: (job) => setState((s) => (s.phase === 'running' && s.jobId === jobId ? { ...s, job } : s)),
      })
        .then((job) => {
          if (job.status === 'succeeded') {
            if (job.result && (job.result as { continuation_required?: boolean }).continuation_required) {
              setState({ phase: 'continue', unit, jobId, job });
              return;
            }
            writeStored(course.id, null);
            setState({ phase: 'idle' });
            onDone(unit.title);
          } else {
            writeStored(course.id, null);
            setState({ phase: 'failed', unit, problem: describeJobFailure(job), jobId });
          }
        })
        .catch((error) => {
          if ((error as Error)?.name === 'AbortError') return;
          setState({ phase: 'failed', unit, problem: describeError(error), jobId });
        });
    },
    [course, onDone],
  );

  // Reconnect to a job started earlier (reload, navigation, another tab).
  useEffect(() => {
    if (!course) return;
    const saved = readStored(course.id);
    const unit = saved && course.content.units.find((u) => u.id === saved.unitId);
    if (saved && unit) {
      api<Job>('/jobs/' + saved.jobId)
        .then((job) => {
          if (job.status === 'queued' || job.status === 'running') watch(unit, saved.jobId, saved.startedAt);
          else writeStored(course.id, null);
        })
        .catch(() => writeStored(course.id, null));
    }
    return () => abort.current?.abort();
    // Only on course identity; `watch` changes with onDone.
  }, [course?.id]);

  const handle = useCallback(
    (unit: Unit, start: AiStart<unknown>) => {
      if (start.kind === 'quote') setState({ phase: 'quote', unit, quote: start.quote, confirm: start.confirm });
      else if (start.kind === 'job') watch(unit, start.jobId, Date.now());
      else {
        setState({ phase: 'idle' });
        onDone(unit.title);
      }
    },
    [watch, onDone],
  );

  const begin = useCallback(
    async (unit: Unit, resumeJobId?: string) => {
      if (!course) return;
      setState({ phase: 'asking', unit, busy: true });
      try {
        const body: Record<string, unknown> = { expected_revision: course.revision, unit_id: unit.id };
        if (resumeJobId) body.resume_job_id = resumeJobId;
        handle(unit, await startAi(`/courses/${course.id}/generate`, body));
      } catch (error) {
        setState({ phase: 'asking', unit, problem: describeError(error) });
      }
    },
    [course, handle],
  );

  const confirm = useCallback(async () => {
    if (state.phase !== 'quote') return;
    const { unit } = state;
    setState({ ...state, busy: true });
    try {
      handle(unit, await state.confirm());
    } catch (error) {
      setState({ phase: 'asking', unit, problem: describeError(error) });
    }
  }, [state, handle]);

  const cancelJob = useCallback(async () => {
    if (state.phase !== 'running') return;
    try {
      await api(`/jobs/${state.jobId}/cancel`, { method: 'POST' });
    } catch {
      /* The watcher reports the final state either way. */
    }
  }, [state]);

  return {
    state,
    ask: (unit: Unit) => setState({ phase: 'asking', unit }),
    begin,
    confirm,
    cancelJob,
    close: () => setState({ phase: 'idle' }),
  };
}
