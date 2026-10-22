import { useEffect, useRef } from 'react';
import { api, ApiError } from '../api/client';

export interface PulseTarget {
  courseId: string;
  unitId: string;
  revision: number;
  mode: 'learn' | 'cards' | 'practice';
}

/**
 * Study-time heartbeat for Tiến độ and daily missions. One beat every 25 s
 * while the tab is visible; the server credits at most 30 s per beat, never
 * counts a closed tab and keeps one lease per account, so two tabs cannot
 * double the time. A learn beat also marks the lesson as read.
 */
export function useStudyPulse(target: PulseTarget | null) {
  const lease = useRef<{ id: string; sequence: number } | null>(null);
  const key = target ? `${target.courseId}|${target.unitId}|${target.revision}|${target.mode}` : '';

  useEffect(() => {
    if (!target) return;
    let stopped = false;
    const beat = async () => {
      if (document.visibilityState !== 'visible') return;
      const body = {
        course_id: target.courseId,
        unit_id: target.unitId,
        expected_revision: target.revision,
        mode: target.mode,
        ...(lease.current ? { lease_id: lease.current.id, expected_sequence: lease.current.sequence } : {}),
      };
      try {
        const result = await api<{ lease_id: string; sequence: number }>('/activity/ping', { body });
        if (!stopped) lease.current = { id: result.lease_id, sequence: result.sequence };
      } catch (error) {
        // Another tab took over or the course changed: start a fresh lease on the next beat.
        if (error instanceof ApiError && error.status === 409) lease.current = null;
      }
    };
    void beat();
    const timer = window.setInterval(() => void beat(), 25_000);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
    // The key captures every field of the target.
  }, [key]);
}
