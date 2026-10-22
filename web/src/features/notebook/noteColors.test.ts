import { describe, expect, it } from 'vitest';
import { noteColor } from './noteColors';

describe('noteColor', () => {
  it('uses the colour the learner picked', () => {
    expect(noteColor({ color: 'mint', label: 'ai' })).toBe('mint');
  });

  it('tells Kẹp, teacher and own notes apart before any colour is picked', () => {
    expect(noteColor({ color: null, label: 'ai' })).toBe('sky');
    expect(noteColor({ color: null, label: 'teacher' })).toBe('peach');
    expect(noteColor({ color: null, label: 'user' })).toBe('butter');
  });
});
