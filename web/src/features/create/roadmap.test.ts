import { describe, expect, it } from 'vitest';
import { canMerge, lessonCount, memoryNotes, mergeWithPrevious, moveLesson, planRequest, removeLesson, roadmapFrom, splitLesson, type PlanChoices } from './roadmap';

const blueprint = {
  subject: 'Mạng máy tính',
  chapters: [
    { title: 'IPv4', lessons: [{ title: 'Địa chỉ', objective: 'Biết 32 bit', source_refs: ['f1', 'f2'] }, { title: 'Lớp A/B/C', objective: 'Phân lớp', source_refs: ['f3'] }] },
    { title: 'Subnet', lessons: [{ title: 'Mask', objective: 'Tính mask', source_refs: ['f4', 'f5', 'f6'] }] },
  ],
};

const titles = (r: ReturnType<typeof roadmapFrom>) => r.chapters.map((c) => [c.title, c.lessons.map((l) => l.title)]);

const choices: PlanChoices = {
  sourceId: 's',
  revision: 2,
  subject: 'Mạng',
  goal: 'Ôn thi',
  language: 'vi',
  rules: ['Giữ thuật ngữ'],
  extraRules: 'Thêm ví dụ tính\n',
  focus: ['Subnet'],
  terms: ['prefix'],
  notes: '',
  questionTypes: ['mcq', 'cloze', 'matching'],
  questionCount: 2,
  unlockPolicy: 'locked',
};

describe('roadmap editing', () => {
  it('moves a lesson within and across chapters', () => {
    const r = roadmapFrom(blueprint);
    const second = r.chapters[0].lessons[1].key;
    expect(titles(moveLesson(r, second, -1))).toEqual([
      ['IPv4', ['Lớp A/B/C', 'Địa chỉ']],
      ['Subnet', ['Mask']],
    ]);
    expect(titles(moveLesson(r, second, 1))).toEqual([
      ['IPv4', ['Địa chỉ']],
      ['Subnet', ['Lớp A/B/C', 'Mask']],
    ]);
  });

  it('merges only while the lesson still fits, splits in half and removes on purpose', () => {
    const r = roadmapFrom(blueprint);
    const [first, second] = r.chapters[0].lessons;
    expect(canMerge(r, first.key)).toBe(false);
    expect(canMerge(r, second.key, 2)).toBe(false);
    const merged = mergeWithPrevious(r, second.key);
    expect(merged.chapters[0].lessons.map((l) => l.refs)).toEqual([['f1', 'f2', 'f3']]);
    const split = splitLesson(r, r.chapters[1].lessons[0].key);
    expect(split.chapters[1].lessons.map((l) => [l.title, l.refs])).toEqual([
      ['Mask', ['f4', 'f5']],
      ['Mask (tiếp)', ['f6']],
    ]);
    const parts = roadmapFrom({ subject: 'x', chapters: [{ title: 'A', lessons: [{ title: 'Mask (phần 1)', objective: 'o', source_refs: ['a'] }, { title: 'Mask (phần 2)', objective: 'o', source_refs: ['b'] }] }] });
    expect(mergeWithPrevious(parts, parts.chapters[0].lessons[1].key).chapters[0].lessons[0].title).toBe('Mask');
    const removed = removeLesson(r, second.key);
    expect(lessonCount(removed)).toBe(2);
    expect(removed.skipped).toEqual(['f3']);
  });
});

describe('planRequest', () => {
  it('sends every kept excerpt once, the skipped ones explicitly, and valid counts', () => {
    const body = planRequest(roadmapFrom(blueprint), choices);
    expect(body.preferences.fragment_ids).toEqual(['f1', 'f2', 'f3', 'f4', 'f5', 'f6']);
    expect(body.lessons.map((l) => l.chapter)).toEqual(['IPv4', 'IPv4', 'Subnet']);
    expect(body.preferences.instructions).toBe('Giữ thuật ngữ\nThêm ví dụ tính');
    expect(body.preferences.question_count).toBe(3);
    expect(body.preferences).not.toHaveProperty('chapter_priorities');
    expect(memoryNotes(choices, ['Làm lại ví dụ'])).toBe('Phần mình muốn tập trung: Subnet.\nCách ôn Byte gợi ý: Làm lại ví dụ.');
    const r = roadmapFrom(blueprint);
    const trimmed = planRequest(removeLesson(r, r.chapters[0].lessons[1].key), choices);
    expect(trimmed.preferences.fragment_ids).toEqual(['f1', 'f2', 'f4', 'f5', 'f6']);
    expect(trimmed.preferences.excluded_fragment_ids).toEqual(['f3']);
  });
});
