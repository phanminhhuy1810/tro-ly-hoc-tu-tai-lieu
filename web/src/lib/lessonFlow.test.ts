import { describe, expect, it } from 'vitest';
import { practiceOrder, startPoint } from './lessonFlow';

const sections = [
  { title: 'IPv4 và mask', text: '', source_refs: ['s:1'] },
  { title: 'Prefix /26', text: '', source_refs: ['s:2'] },
  { title: 'Ví dụ .70/26', text: '', source_refs: ['s:3'] },
];

describe('practiceOrder', () => {
  it('orders questions by the last section they rely on, loose ones last', () => {
    const order = practiceOrder({ sections }, [
      { id: 'q-late', source_refs: ['s:2', 's:3'] },
      { id: 'q-loose', source_refs: ['s:9'] },
      { id: 'q-early', source_refs: ['s:1'] },
    ]);
    expect(order).toEqual(['q-early', 'q-late', 'q-loose']);
  });

  it('keeps bank order among questions on the same section and works without sections', () => {
    expect(practiceOrder({ sections }, [{ id: 'b', source_refs: ['s:1'] }, { id: 'a', source_refs: ['s:1'] }])).toEqual(['b', 'a']);
    expect(practiceOrder(null, [{ id: 'x', source_refs: [] }, { id: 'y', source_refs: [] }])).toEqual(['x', 'y']);
  });
});

describe('startPoint', () => {
  const order = ['q1', 'q2'];

  it('starts a new lesson in the learn chat with the first section', () => {
    expect(startPoint(3, -1, order, new Set())).toEqual({ phase: 'learn', revealed: 1, recap: false, questionIndex: 0 });
  });

  it('shows the sections already read plus the next one', () => {
    expect(startPoint(3, 0, order, new Set())).toMatchObject({ phase: 'learn', revealed: 2, recap: false });
  });

  it('offers the recap once every section is read', () => {
    expect(startPoint(3, 2, order, new Set())).toMatchObject({ phase: 'learn', revealed: 3, recap: true });
  });

  it('resumes practice at the first unanswered question', () => {
    expect(startPoint(3, -1, order, new Set(['q1']))).toMatchObject({ phase: 'practice', questionIndex: 1 });
  });

  it('opens the result when every question is answered, and practice when there is nothing to read', () => {
    expect(startPoint(3, 2, order, new Set(['q1', 'q2'])).phase).toBe('result');
    expect(startPoint(0, -1, order, new Set()).phase).toBe('practice');
  });
});
