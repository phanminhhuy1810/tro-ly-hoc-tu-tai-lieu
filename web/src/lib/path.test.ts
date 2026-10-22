import { describe, expect, it } from 'vitest';
import type { Unit, UnitData } from '../api/types';
import { chapterGroups, courseSummary, pathNodes } from './path';

const data = { title: '', sections: [], questions: [], cards: [], mindmap: [] } as UnitData;
const unit = (id: string, extra: Partial<Unit>): Unit => ({ id, title: id, source_refs: [], data: null, ...extra });

describe('pathNodes', () => {
  const course = {
    content: {
      title: 'Mạng',
      unlock_policy: 'locked',
      units: [
        unit('u1', { data, completed: true, unlocked: true }),
        unit('u2', { data, unlocked: true }),
        unit('u3', { unlocked: true }),
        unit('u4', { unlocked: false }),
      ],
    },
  };

  it('labels done, ready, not generated and locked units', () => {
    expect(pathNodes(course).map((n) => n.state)).toEqual(['done', 'ready', 'not_generated', 'locked']);
  });

  it('points to the first open unit by default', () => {
    expect(pathNodes(course).filter((n) => n.isCurrent).map((n) => n.unit.id)).toEqual(['u2']);
  });

  it('prefers the saved position while that unit is still open', () => {
    expect(pathNodes(course, 'u3').find((n) => n.isCurrent)?.unit.id).toBe('u3');
    expect(pathNodes(course, 'u1').find((n) => n.isCurrent)?.unit.id).toBe('u2');
  });

  it('marks nothing current when every unit is finished or locked', () => {
    const finished = { content: { ...course.content, units: [unit('a', { data, completed: true }), unit('b', { unlocked: false })] } };
    expect(pathNodes(finished).some((n) => n.isCurrent)).toBe(false);
  });

  it('summarises counts for course rows', () => {
    expect(courseSummary(course)).toEqual({ total: 4, done: 1, ready: 1, notGenerated: 2 });
  });
});

describe('chapterGroups', () => {
  it('groups consecutive lessons by chapter and keeps older courses as one group', () => {
    const course = {
      content: {
        title: 'Mạng',
        unlock_policy: 'open',
        units: [unit('a', { chapter: 'IPv4' }), unit('b', { chapter: 'IPv4' }), unit('c', { chapter: 'Subnet' }), unit('d', {})],
      },
    };
    expect(chapterGroups(pathNodes(course)).map((g) => [g.title, g.nodes.map((n) => n.unit.id)])).toEqual([
      ['IPv4', ['a', 'b']],
      ['Subnet', ['c']],
      ['', ['d']],
    ]);
    const old = { content: { ...course.content, units: [unit('x', {}), unit('y', {})] } };
    expect(chapterGroups(pathNodes(old))).toHaveLength(1);
  });
});
