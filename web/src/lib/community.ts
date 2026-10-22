import type { Visibility } from '../api/types';

const MATERIAL: Record<string, string> = {
  lesson: 'Bài giảng đã tạo',
  cards: 'Thẻ ghi nhớ của bài',
  practice_bank: 'Bộ câu luyện tập',
  selected_source_excerpts: 'Các trích đoạn nguồn mà bài dùng',
  learner_progress: 'Tiến trình học của từng người',
  notebook: 'Sổ tay',
  chat: 'Các cuộc chat với Kẹp',
  creator_preferences_and_notes: 'Ghi chú và tùy chọn khi bạn tạo khóa',
  answer_keys_before_submission: 'Đáp án trước khi người học nộp bài',
};

/** Plain words for the material codes in a publication preview. */
export function materialLabel(code: string): string {
  return MATERIAL[code] ?? code;
}

export const VISIBILITY: Record<Visibility, { title: string; body: string }> = {
  private: {
    title: 'Chỉ mình tôi',
    body: 'Không ai khác mở được khóa. Người đã tham gia mất quyền vào, nhưng vẫn giữ lịch sử và ghi chú riêng của họ.',
  },
  shared: {
    title: 'Chia sẻ bằng mã mời',
    body: 'Chỉ người có mã mời vào học được. Khóa không hiện ở trang Cộng đồng.',
  },
  public: {
    title: 'Công khai trong Cộng đồng',
    body: 'Ai dùng app cũng tìm thấy, xem trước và tham gia được; họ có thể thả tim, đánh giá và báo lỗi.',
  },
};

/** “4,5 ★ · 12 lượt”, or a plain note when nobody has rated yet. */
export function ratingText(rating: number | null, count: number): string {
  if (rating == null || count === 0) return 'Chưa có đánh giá';
  return `${rating.toFixed(1).replace('.', ',')} ★ · ${count} lượt`;
}

/** Every anonymous local profile is named “Người học local”, which tells a learner nothing; show no name then. */
export function creatorLabel(name: string | null | undefined): string {
  return name && name !== 'Người học local' ? name : '';
}
