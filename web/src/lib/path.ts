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
}

/** Consecutive lessons with the same chapter name form one section of the path. */
export function chapterGroups(nodes: PathNode[]): ChapterGroup[] {
  const groups: ChapterGroup[] = [];
  for (const node of nodes) {
    const title = node.unit.chapter?.trim() ?? '';
    const last = groups[groups.length - 1];
    if (last && last.title === title) last.nodes.push(node);
    else groups.push({ title, nodes: [node] });
  }
  return groups;
}
