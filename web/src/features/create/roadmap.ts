// Editable roadmap built from the AI's whole-document proposal. Every excerpt
// stays in exactly one lesson unless the learner removes a lesson on purpose
// (its excerpts are then listed as skipped, never dropped silently).

export interface DraftLesson {
  key: string;
  title: string;
  objective: string;
  refs: string[];
}

export interface DraftChapter {
  key: string;
  title: string;
  lessons: DraftLesson[];
}

export interface Roadmap {
  title: string;
  chapters: DraftChapter[];
  /** Excerpts of lessons the learner removed. */
  skipped: string[];
}

export interface BlueprintValue {
  subject: string;
  goal: string;
  summary: string;
  chapters: { title: string; lessons: { title: string; objective: string; source_refs: string[] }[] }[];
  focus: string[];
  study_tips: string[];
  rules: string[];
  language: 'vi' | 'en' | 'source';
  language_note: string;
  terms_to_keep: string[];
  scope_fragment_ids: string[];
  extraction_revision: number;
  coverage?: { selected_fragments: number; assigned_fragments: number; placed_by_server: number; lessons_split_to_fit: number };
}

let counter = 0;
const key = (prefix: string) => `${prefix}-${(counter += 1)}`;

export function roadmapFrom(blueprint: Pick<BlueprintValue, 'subject' | 'chapters'>): Roadmap {
  return {
    title: blueprint.subject,
    skipped: [],
    chapters: blueprint.chapters.map((chapter) => ({
      key: key('c'),
      title: chapter.title,
      lessons: chapter.lessons.map((lesson) => ({ key: key('l'), title: lesson.title, objective: lesson.objective, refs: [...lesson.source_refs] })),
    })),
  };
}

export function lessonCount(roadmap: Roadmap) {
  return roadmap.chapters.reduce((n, c) => n + c.lessons.length, 0);
}

function flat(roadmap: Roadmap) {
  return roadmap.chapters.flatMap((chapter, c) => chapter.lessons.map((lesson, l) => ({ lesson, c, l })));
}

function rebuild(roadmap: Roadmap, chapters: DraftChapter[], skipped = roadmap.skipped): Roadmap {
  return { ...roadmap, chapters: chapters.filter((chapter) => chapter.lessons.length > 0), skipped };
}

export function updateLesson(roadmap: Roadmap, lessonKey: string, patch: Partial<Pick<DraftLesson, 'title' | 'objective'>>): Roadmap {
  return { ...roadmap, chapters: roadmap.chapters.map((c) => ({ ...c, lessons: c.lessons.map((l) => (l.key === lessonKey ? { ...l, ...patch } : l)) })) };
}

export function renameChapter(roadmap: Roadmap, chapterKey: string, title: string): Roadmap {
  return { ...roadmap, chapters: roadmap.chapters.map((c) => (c.key === chapterKey ? { ...c, title } : c)) };
}

/** Move a lesson one place up or down; at a chapter edge it crosses into the neighbouring chapter. */
export function moveLesson(roadmap: Roadmap, lessonKey: string, direction: -1 | 1): Roadmap {
  const chapters = roadmap.chapters.map((c) => ({ ...c, lessons: [...c.lessons] }));
  const c = chapters.findIndex((chapter) => chapter.lessons.some((l) => l.key === lessonKey));
  if (c < 0) return roadmap;
  const l = chapters[c].lessons.findIndex((lesson) => lesson.key === lessonKey);
  const [lesson] = chapters[c].lessons.splice(l, 1);
  const target = l + direction;
  if (target >= 0 && target <= chapters[c].lessons.length && !(direction === 1 && l === chapters[c].lessons.length)) {
    chapters[c].lessons.splice(target, 0, lesson);
  } else if (direction === -1 && c > 0) {
    chapters[c - 1].lessons.push(lesson);
  } else if (direction === 1 && c < chapters.length - 1) {
    chapters[c + 1].lessons.unshift(lesson);
  } else {
    return roadmap;
  }
  return rebuild(roadmap, chapters);
}

export function moveToChapter(roadmap: Roadmap, lessonKey: string, chapterKey: string): Roadmap {
  const lesson = flat(roadmap).find((x) => x.lesson.key === lessonKey)?.lesson;
  if (!lesson) return roadmap;
  const chapters = roadmap.chapters.map((c) => ({ ...c, lessons: c.lessons.filter((l) => l.key !== lessonKey) }));
  const target = chapters.find((c) => c.key === chapterKey);
  if (!target) return roadmap;
  target.lessons.push(lesson);
  return rebuild(roadmap, chapters);
}

export function addChapter(roadmap: Roadmap, lessonKey: string, title = 'Chương mới'): Roadmap {
  const chapters = roadmap.chapters.map((c) => ({ ...c, lessons: [...c.lessons] }));
  const c = chapters.findIndex((chapter) => chapter.lessons.some((l) => l.key === lessonKey));
  if (c < 0) return roadmap;
  const l = chapters[c].lessons.findIndex((lesson) => lesson.key === lessonKey);
  // The chosen lesson and those after it in the same chapter start the new chapter.
  const moved = chapters[c].lessons.splice(l);
  chapters.splice(c + 1, 0, { key: key('c'), title, lessons: moved });
  return rebuild(roadmap, chapters);
}

/** Merge a lesson into the one before it (same or previous chapter); a lesson holds at most 12 excerpts. */
export function mergeWithPrevious(roadmap: Roadmap, lessonKey: string, maxRefs = 12): Roadmap {
  const all = flat(roadmap);
  const at = all.findIndex((x) => x.lesson.key === lessonKey);
  if (at <= 0 || all[at - 1].lesson.refs.length + all[at].lesson.refs.length > maxRefs) return roadmap;
  const previous = all[at - 1].lesson;
  // Re-joining two parts of one split lesson gives back its plain title.
  const base = (title: string) => title.replace(/\s*\((?:phần \d+|tiếp)\)$/u, '');
  const title = base(previous.title) === base(all[at].lesson.title) ? base(previous.title) : previous.title;
  const chapters = roadmap.chapters.map((c) => ({
    ...c,
    lessons: c.lessons
      .filter((l) => l.key !== lessonKey)
      .map((l) => (l.key === previous.key ? { ...l, title, refs: [...l.refs, ...all[at].lesson.refs] } : l)),
  }));
  return rebuild(roadmap, chapters);
}

export function canMerge(roadmap: Roadmap, lessonKey: string, maxRefs = 12): boolean {
  const all = flat(roadmap);
  const at = all.findIndex((x) => x.lesson.key === lessonKey);
  return at > 0 && all[at - 1].lesson.refs.length + all[at].lesson.refs.length <= maxRefs;
}

/** Split a lesson's excerpts into two halves (the second keeps the title with "(tiếp)"). */
export function splitLesson(roadmap: Roadmap, lessonKey: string): Roadmap {
  const chapters = roadmap.chapters.map((c) => {
    const index = c.lessons.findIndex((l) => l.key === lessonKey);
    if (index < 0 || c.lessons[index].refs.length < 2) return c;
    const lesson = c.lessons[index];
    const half = Math.ceil(lesson.refs.length / 2);
    const lessons = [...c.lessons];
    lessons.splice(index, 1, { ...lesson, refs: lesson.refs.slice(0, half) }, { key: key('l'), title: `${lesson.title} (tiếp)`, objective: lesson.objective, refs: lesson.refs.slice(half) });
    return { ...c, lessons };
  });
  return rebuild(roadmap, chapters);
}

export function removeLesson(roadmap: Roadmap, lessonKey: string): Roadmap {
  const lesson = flat(roadmap).find((x) => x.lesson.key === lessonKey)?.lesson;
  if (!lesson || lessonCount(roadmap) <= 1) return roadmap;
  const chapters = roadmap.chapters.map((c) => ({ ...c, lessons: c.lessons.filter((l) => l.key !== lessonKey) }));
  return rebuild(roadmap, chapters, [...roadmap.skipped, ...lesson.refs]);
}

export interface PlanChoices {
  sourceId: string;
  revision: number;
  subject: string;
  goal: string;
  language: 'vi' | 'en' | 'source';
  rules: string[];
  extraRules: string;
  focus: string[];
  terms: string[];
  notes: string;
  questionTypes: string[];
  questionCount: number;
  unlockPolicy: 'locked' | 'open';
}

/**
 * Body for POST /plans/from-blueprint. Focus areas are course-wide review
 * advice, so they go to the course memory (used when the learner asks), not
 * into every lesson's generation prompt — a 12B model otherwise pulls later
 * topics into the first lesson.
 */
export function planRequest(roadmap: Roadmap, choices: PlanChoices) {
  const lessons = roadmap.chapters.flatMap((chapter) =>
    chapter.lessons.map((lesson) => ({
      title: lesson.title.trim(),
      objective: lesson.objective.trim() || lesson.title.trim(),
      source_refs: lesson.refs,
      chapter: chapter.title.trim().slice(0, 120),
    })),
  );
  const instructions = [...choices.rules, ...choices.extraRules.split('\n')].map((r) => r.trim()).filter(Boolean).join('\n').slice(0, 2000);
  const types = choices.questionTypes.length ? choices.questionTypes : ['mcq'];
  return {
    title: roadmap.title.trim() || choices.subject.trim(),
    lessons,
    preferences: {
      source_id: choices.sourceId,
      subject: choices.subject.trim(),
      goal: choices.goal.trim(),
      instructions,
      language: choices.language,
      fragment_ids: lessons.flatMap((l) => l.source_refs),
      excluded_fragment_ids: roadmap.skipped,
      unlock_policy: choices.unlockPolicy,
      initial_mode: 'learn',
      expected_extraction_revision: choices.revision,
      question_types: types,
      question_count: Math.max(types.length, Math.min(8, choices.questionCount)),
      terms_to_keep: choices.terms.map((t) => t.slice(0, 100)).filter(Boolean).slice(0, 30),
      user_notes: choices.notes.slice(0, 2000),
    },
  };
}

/** Notes saved to "Kẹp nhớ gì về bạn" right after the course is created. */
export function memoryNotes(choices: Pick<PlanChoices, 'focus'>, tips: string[]): string {
  const lines = [];
  if (choices.focus.length) lines.push(`Phần mình muốn tập trung: ${choices.focus.join('; ')}.`);
  if (tips.length) lines.push(`Cách ôn Kẹp gợi ý: ${tips.join('; ')}.`);
  return lines.join('\n').slice(0, 1500);
}
