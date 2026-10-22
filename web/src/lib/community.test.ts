import { describe, expect, it } from 'vitest';
import { creatorLabel, materialLabel, ratingText } from './community';

describe('community copy', () => {
  it('formats ratings the Vietnamese way and says when there are none', () => {
    expect(ratingText(4.5, 12)).toBe('4,5 ★ · 12 lượt');
    expect(ratingText(null, 0)).toBe('Chưa có đánh giá');
    expect(ratingText(5, 0)).toBe('Chưa có đánh giá');
  });

  it('names shared material and keeps unknown codes visible', () => {
    expect(materialLabel('practice_bank')).toBe('Bộ câu luyện tập');
    expect(materialLabel('new_material')).toBe('new_material');
  });

  it('hides the placeholder name of anonymous local profiles', () => {
    expect(creatorLabel('Người học local')).toBe('');
    expect(creatorLabel('Huy')).toBe('Huy');
    expect(creatorLabel(null)).toBe('');
  });
});
