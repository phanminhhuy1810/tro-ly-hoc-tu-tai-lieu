import type { Course, Unit } from '../api/types';

export type NodeState = 'done' | 'ready' | 'not_generated' | 'locked';

export interface PathNode {
  unit: Unit;
  index: number;
  state: NodeState;
  /** The one place the learner should go next. */
  isCurrent: boolean;
}

export function nodeState(unit: Unit): NodeState {
  if (unit.unlocked === false) return 'locked';
  if (unit.completed) return 'done';
  if (!unit.data) return 'not_generated';
  return 'ready';
}

/**
 * Progress path for a course. "Current" is the learner's saved unit when it is
 * still open, otherwise the first open unit that is not finished.
 */
export function pathNodes(course: Pick<Course, 'content'>, savedUnitId?: string | null): PathNode[] {
  const nodes = course.content.units.map((unit, index) => ({ unit, index, state: nodeState(unit), isCurrent: false }));
  const open = (node: PathNode) => node.state === 'ready' || node.state === 'not_generated';
  const saved = nodes.find((node) => node.unit.id === savedUnitId && open(node));
  const current = saved ?? nodes.find(open);
  if (current) current.isCurrent = true;
  return nodes;
}

export function courseSummary(course: Pick<Course, 'content'>) {
  const units = course.content.units;
  const done = units.filter((u) => u.completed).length;
  const ready = units.filter((u) => u.data && !u.completed && u.unlocked !== false).length;
  const notGenerated = units.filter((u) => !u.data).length;
  return { total: units.length, done, ready, notGenerated };
}

export interface ChapterGroup {
  title: string;
  nodes: PathNode[];
  /** Set when a very long chapter (or a course without chapters) was cut into parts of the path. */
  part?: number;
}

const LONG_CHAPTER = 10;
const PART_SIZE = 8;

/** Consecutive lessons with the same chapter name form one section of the path. */
export function chapterGroups(nodes: PathNode[]): ChapterGroup[] {
  const groups: ChapterGroup[] = [];
  for (const node of nodes) {
    const title = node.unit.chapter?.trim() ?? '';
    const last = groups[groups.length - 1];
    if (last && last.title === title) last.nodes.push(node);
    else groups.push({ title, nodes: [node] });
  }
  // One endless chapter (e.g. 154 lessons cut by page) reads better as parts of eight lessons.
  return groups.flatMap((group) => {
    if (group.nodes.length <= LONG_CHAPTER) return [group];
    const parts: ChapterGroup[] = [];
    for (let i = 0; i < group.nodes.length; i += PART_SIZE) {
      const part = parts.length + 1;
      const first = group.nodes[i].index + 1;
      const last = group.nodes[Math.min(i + PART_SIZE, group.nodes.length) - 1].index + 1;
      parts.push({ title: `${group.title ? `${group.title} · ` : ''}Bài ${first}–${last}`, nodes: group.nodes.slice(i, i + PART_SIZE), part });
    }
    return parts;
  });
}
