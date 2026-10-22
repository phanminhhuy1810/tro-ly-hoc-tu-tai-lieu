import type { Note, NoteColor } from '../../api/types';

export const NOTE_COLORS: { value: NoteColor; name: string }[] = [
  { value: 'butter', name: 'Vàng bơ' },
  { value: 'peach', name: 'Cam đào' },
  { value: 'pink', name: 'Hồng' },
  { value: 'lilac', name: 'Tím nhạt' },
  { value: 'sky', name: 'Xanh trời' },
  { value: 'mint', name: 'Bạc hà' },
  { value: 'white', name: 'Trắng' },
];

/** A note without a chosen colour still reads at a glance: Kẹp's answers blue, a teacher's peach, yours butter. */
export function noteColor(note: Pick<Note, 'color' | 'label'>): NoteColor {
  if (note.color) return note.color;
  if (note.label === 'ai') return 'sky';
  if (note.label === 'teacher') return 'peach';
  return 'butter';
}
