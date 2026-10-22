import { useCallback, useEffect, useRef, useState } from 'react';
import { api, ApiError, ensureSession, newKey } from '../../api/client';
import type { Course, GradeResult, PracticeSession, Progress, Unit } from '../../api/types';
import { toAnswer, type Draft } from '../../lib/answers';
import { practiceOrder, startPoint, type StartPoint } from '../../lib/lessonFlow';

export interface LessonData {
  course: Course;
  units: Unit[];
  unit: Unit | null;
  session: PracticeSession | null;
  /** Why there is no practice session (e.g. no wrong answers to review yet). */
  sessionNote: string | null;
  /** Question ids in practice order. */
  order: string[];
  start: StartPoint;
  feedback: Record<string, GradeResult>;
  answered: Record<string, unknown>;
  drafts: Record<string, { answer: unknown; version: number }>;
}

const readKey = (courseId: string, unitId: string, revision: number) => `folio.read.${courseId}.${unitId}.${revision}`;

export function readUpTo(courseId: string, unitId: string, revision: number): number {
  try {
    return Number(localStorage.getItem(readKey(courseId, unitId, revision)) ?? -1);
  } catch {
    return -1;
  }
}

export function rememberRead(courseId: string, unitId: string, revision: number, index: number) {
  try {
    if (index > readUpTo(courseId, unitId, revision)) localStorage.setItem(readKey(courseId, unitId, revision), String(index));
  } catch {
    /* Position still saved on the server via progress. */
  }
}

/** Best-effort learn position on the server, so "Học tiếp" can bring the learner back. */
export async function saveLearnPosition(course: Course, unitId: string, sectionIndex: number) {
  try {
    const current = await api<Progress>(`/courses/${course.id}/progress`);
    await api(`/courses/${course.id}/progress`, {
      method: 'PUT',
      body: { expected_version: current.version, expected_revision: course.revision, mode: 'learn', unit_id: unitId, section_index: sectionIndex },
    });
  } catch {
    /* Another tab moved first; the local position still works. */
  }
}

async function openSession(course: Course, unitIds: string[], weak: boolean, key: string, progress: Progress | null): Promise<{ session: PracticeSession | null; note: string | null }> {
  if (!weak) {
    // Reuse the learner's open attempt for this exact lesson and version.
    const saved = progress?.mode_positions?.practice;
    if (saved?.session_id && saved.unit_id === unitIds[0]) {
      const existing = await api<PracticeSession>(`/sessions/${saved.session_id}`).catch(() => null);
      if (existing && existing.status === 'open' && existing.revision === course.revision && existing.scope.unit_ids.join() === unitIds.join()) {
        return { session: existing, note: null };
      }
    }
  }
  try {
    const created = await api<PracticeSession>(`/courses/${course.id}/sessions`, {
      body: { expected_revision: course.revision, unit_ids: unitIds, mode: weak ? 'practice' : 'learn', exercise: weak ? 'weak' : 'practice' },
      idempotencyKey: key,
    });
    // The create response has no answers/drafts yet; read the full state once.
    const full = await api<PracticeSession>(`/sessions/${created.id}`);
    return { session: full, note: null };
  } catch (error) {
    if (error instanceof ApiError && (error.status === 409 || error.status === 422)) return { session: null, note: error.message };
    throw error;
  }
}

export function useLessonSession(courseId: string, unitParam: string, weak: boolean) {
  const [data, setData] = useState<LessonData | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [tick, setTick] = useState(0);
  const key = useRef(newKey('session'));

  useEffect(() => {
    let alive = true;
    setError(null);
    (async () => {
      await ensureSession();
      const course = await api<Course>(`/courses/${courseId}`);
      const ready = course.content.units.filter((u) => u.data && u.unlocked !== false);
      const unit = unitParam === 'tat-ca' ? null : course.content.units.find((u) => u.id === unitParam) ?? null;
      if (!weak && (!unit || !unit.data)) {
        const start: StartPoint = { phase: 'learn', revealed: 1, recap: false, questionIndex: 0 };
        return { course, units: ready, unit, session: null, sessionNote: null, order: [], start, feedback: {}, answered: {}, drafts: {} };
      }
      const unitIds = weak ? (unit ? [unit.id] : ready.map((u) => u.id)) : [unit!.id];
      const progress = await api<Progress>(`/courses/${course.id}/progress`).catch(() => null);
      const { session, note } = await openSession(course, unitIds, weak, key.current, progress);
      const questions = session?.questions ?? [];
      const order = practiceOrder(weak ? null : unit?.data ?? null, questions);
      const feedback: Record<string, GradeResult> = {};
      const answered: Record<string, unknown> = {};
      for (const [itemId, value] of Object.entries(session?.answers ?? {})) {
        answered[itemId] = value.answer;
        if (value.feedback) feedback[itemId] = value.feedback;
      }
      const drafts = Object.fromEntries(Object.entries(session?.drafts ?? {}).map(([id, d]) => [id, { answer: d.answer, version: d.version }]));
      const sections = weak ? 0 : unit?.data?.sections.length ?? 0;
      // Reading position: this device, or the one saved on the server from another device.
      const learn = progress?.mode_positions?.learn;
      const serverRead = learn && learn.unit_id === unit?.id && learn.expected_revision === course.revision ? learn.section_index ?? -1 : -1;
      const read = unit ? Math.max(readUpTo(course.id, unit.id, course.revision), serverRead) : -1;
      const start = startPoint(sections, read, order, new Set(Object.keys(answered)));
      return { course, units: ready, unit, session, sessionNote: note, order, start, feedback, answered, drafts } satisfies LessonData;
    })()
      .then((value) => alive && setData(value))
      .catch((err) => alive && setError(err));
    return () => {
      alive = false;
    };
  }, [courseId, unitParam, weak, tick]);

  const submit = useCallback(
    async (itemId: string, draft: Draft): Promise<GradeResult> => {
      if (!data?.session) throw new Error('Chưa có lượt luyện.');
      const answer = toAnswer(draft);
      try {
        const result = await api<GradeResult>(`/sessions/${data.session.id}/answers`, { body: { item_id: itemId, answer } });
        setData((d) => (d ? { ...d, feedback: { ...d.feedback, [itemId]: result }, answered: { ...d.answered, [itemId]: answer } } : d));
        return result;
      } catch (error) {
        if (error instanceof ApiError && error.status === 409) {
          // Already graded in another tab: show that saved result instead of re-grading.
          const fresh = await api<PracticeSession>(`/sessions/${data.session.id}`);
          const saved = fresh.answers?.[itemId];
          if (saved?.feedback) {
            setData((d) => (d ? { ...d, feedback: { ...d.feedback, [itemId]: saved.feedback! }, answered: { ...d.answered, [itemId]: saved.answer } } : d));
            return saved.feedback;
          }
        }
        throw error;
      }
    },
    [data?.session],
  );

  const versions = useRef<Record<string, number>>({});
  useEffect(() => {
    versions.current = Object.fromEntries(Object.entries(data?.drafts ?? {}).map(([id, d]) => [id, d.version]));
  }, [data?.drafts]);

  /** Save an unsent answer so leaving and coming back keeps it. Never grades. */
  const saveDraft = useCallback(
    async (itemId: string, draft: Draft) => {
      const session = data?.session;
      if (!session || data?.feedback[itemId]) return;
      const put = (expected: number) =>
        api<{ version: number }>(`/sessions/${session.id}/draft`, { method: 'PUT', body: { item_id: itemId, answer: toAnswer(draft), expected_version: expected } });
      try {
        const saved = await put(versions.current[itemId] ?? 0);
        versions.current[itemId] = saved.version;
      } catch (error) {
        if (error instanceof ApiError && error.status === 409) {
          const fresh = await api<PracticeSession>(`/sessions/${session.id}`).catch(() => null);
          const version = fresh?.drafts?.[itemId]?.version;
          if (version !== undefined && !fresh?.answers?.[itemId]) {
            const saved = await put(version).catch(() => null);
            if (saved) versions.current[itemId] = saved.version;
          }
        }
      }
    },
    [data?.session, data?.feedback],
  );

  return { data, error, reload: () => setTick((t) => t + 1), submit, saveDraft };
}
