import { describe, expect, it } from 'vitest';
import { makeTextFix, respace, tidyBullets, vocabularyFrom } from './text';

// Real case: a cloze prompt quoted from a slide whose PDF text lost its spaces.
const PROMPT = '“§Địachỉlogic •do ngườidùngấnđịnh •VD: ____”';
const LESSON = ['Địa chỉ IP là một loại địa chỉ logic, do người dùng ấn định trong mạng máy tính.', 'Địa chỉ vật lý do nhà sản xuất ấn định.'];

describe('respace', () => {
  it('splits glued words into words the same lesson uses', () => {
    const words = vocabularyFrom(LESSON);
    expect(respace('Địachỉlogic', words)).toBe('Địa chỉ logic');
    expect(respace('ngườidùngấnđịnh', words)).toBe('người dùng ấn định');
  });

  it('keeps case, English terms and words it cannot fully explain', () => {
    const words = vocabularyFrom(LESSON);
    expect(respace('Subnetmask', words)).toBe('Subnetmask');
    expect(respace('nghiêngngả', words)).toBe('nghiêngngả');
    expect(respace('Địachỉ', new Set())).toBe('Địachỉ');
  });
});

describe('tidyBullets', () => {
  it('turns slide bullets into readable bullets', () => {
    expect(tidyBullets('§định danh\nqPhân loại:\n•do người dùng')).toBe('• định danh\n• Phân loại:\n• do người dùng');
  });

  it('keeps real words and section references', () => {
    expect(tidyBullets('quy tắc chia mạng')).toBe('quy tắc chia mạng');
    expect(tidyBullets('Xem § 5 của quy chế')).toBe('Xem § 5 của quy chế');
  });
});

describe('makeTextFix', () => {
  it('repairs the reported cloze prompt for display', () => {
    expect(makeTextFix(LESSON)(PROMPT)).toBe('“Địa chỉ logic • do người dùng ấn định • VD: ____”');
  });
});
