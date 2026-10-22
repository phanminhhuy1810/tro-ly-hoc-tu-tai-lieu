import { describe, expect, it } from 'vitest';
import { courseCover, lessonIcons, parseCover, PICKER_ICONS } from './topicIcons';

describe('subject icons', () => {
  it('picks the specific subject before the broad one', () => {
    expect(courseCover('Toán học: Tích phân cơ bản').icon).toBe('calculus');
    expect(courseCover('IPv4 và subnet · nguồn kiểm thử tự soạn').icon).toBe('network');
    expect(['sky', 'lilac', 'mint']).toContain(courseCover('Địa chỉ IP và Chia Subnet').tone);
    expect(courseCover('Tâm lý học đại cương').icon).toBe('psychology');
    expect(courseCover('Kế toán tài chính').icon).toBe('money');
    expect(courseCover('Hoá học hữu cơ').icon).toBe('flask');
    // “Khóa học” (a course) and “Văn hóa” are not chemistry.
    expect(courseCover('Khóa học kỹ năng mềm').icon).not.toBe('flask');
    expect(courseCover('Văn hóa Việt Nam').icon).not.toBe('flask');
  });

  it('gives an unknown subject a steady study icon', () => {
    const cover = courseCover('Khóa không rõ môn');
    expect(courseCover('Khóa không rõ môn')).toEqual(cover);
    expect(['books', 'book', 'bulb', 'graduation', 'target']).toContain(cover.icon);
  });

  it('reads saved presets, old drawn ones included, and ignores anything else', () => {
    expect(parseCover('network-sage')).toEqual({ icon: 'network', tone: 'sage' });
    expect(parseCover('rocket-lilac')).toEqual({ icon: 'rocket', tone: 'lilac' });
    for (const bad of ['rocket-purple', 'constructor-sky', '../etc-sky', '', null]) expect(parseCover(bad)).toBeNull();
    expect(PICKER_ICONS).not.toContain('brain');
  });

  it('gives each lesson of a course its own icon, matching the title when it can', () => {
    const icons = lessonIcons(['Giới thiệu địa chỉ IP', 'Phân loại Classful', 'Chia subnet với mask /26', 'Địa chỉ broadcast', 'Ôn tập chương']);
    expect(icons).toEqual(['compass', 'cards', 'abacus', 'network', 'trophy']);
    expect(lessonIcons(['Bài 1', 'Bài 2', 'Bài 3'])).toEqual(lessonIcons(['Bài 1', 'Bài 2', 'Bài 3']));
    expect(new Set(lessonIcons(['Bài 1', 'Bài 2', 'Bài 3'])).size).toBe(3);
  });
});
