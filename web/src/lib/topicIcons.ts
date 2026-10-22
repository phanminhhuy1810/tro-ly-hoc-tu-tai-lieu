// Subject icons for course covers and lessons: a 3D picture from Microsoft's
// Fluent Emoji set (web/public/art/<key>.webp, MIT) on a pastel tile, picked
// from the title or chosen by the creator. Nothing is generated per course; the
// set is curated so every cover stays on topic.

const ICON_TABLE = {
  // The first names are the old drawn presets, so covers saved before keep working.
  network: 'Mạng',
  code: 'Lập trình',
  calculus: 'Hàm số, đồ thị',
  chart: 'Thống kê',
  atom: 'Vật lý',
  flask: 'Hóa học',
  psychology: 'Tâm lý, trí nhớ',
  brain: 'Thần kinh',
  globe: 'Thế giới',
  scale: 'Luật',
  pencil: 'Viết',
  book: 'Sách',
  papers: 'Tài liệu',
  cards: 'Phân loại',
  flag: 'Mục tiêu',
  ruler: 'Hình học',
  abacus: 'Tính toán',
  numbers: 'Công thức',
  dice: 'Xác suất',
  money: 'Kinh tế',
  briefcase: 'Quản trị',
  bolt: 'Điện',
  magnet: 'Từ trường',
  telescope: 'Thiên văn',
  dna: 'Sinh học',
  microscope: 'Thí nghiệm',
  leaf: 'Phát triển',
  stethoscope: 'Y học',
  map: 'Địa lý',
  scroll: 'Lịch sử',
  speech: 'Ngôn ngữ',
  chat: 'Giao tiếp',
  music: 'Âm nhạc',
  palette: 'Thiết kế',
  lock: 'Bảo mật',
  robot: 'Trí tuệ nhân tạo',
  cabinet: 'Cơ sở dữ liệu',
  gear: 'Thuật toán',
  desktop: 'Máy chủ',
  package: 'Gói tin',
  plug: 'Kết nối',
  signal: 'Không dây',
  satellite: 'Định tuyến',
  megaphone: 'Phát tin',
  handshake: 'Giao thức',
  search: 'Tra cứu',
  people: 'Xã hội',
  heart: 'Cảm xúc',
  bulb: 'Ý tưởng',
  target: 'Trọng tâm',
  puzzle: 'Ghép ý',
  rocket: 'Tăng tốc',
  compass: 'Định hướng',
  writing: 'Luyện tập',
  books: 'Kiến thức',
  graduation: 'Học tập',
  trophy: 'Về đích',
  star: 'Nổi bật',
} as const satisfies Record<string, string>;

export type TopicIcon = keyof typeof ICON_TABLE;
export const TILE_TONES = ['sky', 'butter', 'pink', 'mint', 'lilac', 'peach', 'coral', 'sage'] as const;
export type TileTone = (typeof TILE_TONES)[number];
export const TONE_LABEL: Record<TileTone, string> = {
  sky: 'Xanh dương',
  butter: 'Vàng',
  pink: 'Hồng',
  mint: 'Xanh bạc hà',
  lilac: 'Tím nhạt',
  peach: 'Cam đào',
  coral: 'San hô',
  sage: 'Xanh lá',
};

export const nameOf = (icon: TopicIcon) => ICON_TABLE[icon];
/** What the creator can pick from: every icon once (the old “brain” is the same picture as “psychology”). */
export const PICKER_ICONS = (Object.keys(ICON_TABLE) as TopicIcon[]).filter((icon) => icon !== 'brain');

const isIcon = (value: string): value is TopicIcon => Object.hasOwn(ICON_TABLE, value);
const isTone = (value: string): value is TileTone => (TILE_TONES as readonly string[]).includes(value);

export interface Cover {
  icon: TopicIcon;
  tone: TileTone;
}

/** A saved preset is `icon-tone`, e.g. `network-sky`; anything else is ignored. */
export function parseCover(preset: string | null | undefined): Cover | null {
  const match = /^([a-z]{2,20})-([a-z]{2,20})$/.exec(preset ?? '');
  return match && isIcon(match[1]) && isTone(match[2]) ? { icon: match[1], tone: match[2] } : null;
}

function hash(text: string) {
  let h = 0;
  for (const ch of text) h = (h * 31 + ch.codePointAt(0)!) >>> 0;
  return h;
}

// Order matters: the specific subject before the broad one (“Toán học: Tích phân” is calculus,
// “Kế toán” is accounting). Short Vietnamese words are matched as whole words, so “khóa” is not “hóa”.
const COURSE_RULES: [RegExp, TopicIcon, TileTone][] = [
  [/(\bip\b|ipv|subnet|mạng máy tính|network|tcp\/ip|router|mạng lan|osi\b|giao thức)/, 'network', 'sky'],
  [/(trí tuệ nhân tạo|học máy|machine learning|deep learning|\bai\b)/, 'robot', 'sky'],
  [/(cơ sở dữ liệu|database|sql)/, 'cabinet', 'lilac'],
  [/(bảo mật|an toàn thông tin|mật mã|security|crypto)/, 'lock', 'sage'],
  [/(lập trình|code|python|java|thuật toán|algorithm|cấu trúc dữ liệu|web)/, 'code', 'lilac'],
  [/(tích phân|đạo hàm|giới hạn|vi phân|calculus|integral|derivative|hàm số)/, 'calculus', 'butter'],
  [/(xác suất|probability)/, 'dice', 'peach'],
  [/(thống kê|statistic)/, 'chart', 'mint'],
  [/(kinh tế|tài chính|kế toán|marketing|econom|financ)/, 'money', 'mint'],
  [/(toán|đại số|hình học|math|algebra|geometry)/, 'ruler', 'butter'],
  [/(quản trị|kinh doanh|business|management)/, 'briefcase', 'peach'],
  [/(vật l[ýí]|physics|lượng tử|cơ học|điện học)/, 'atom', 'sky'],
  [/((?<!\p{L})(hóa|hoá) (học|sinh|hữu cơ|vô cơ|phân tích)|chemistry)/u, 'flask', 'mint'],
  [/(sinh học|biology|tế bào|di truyền|gene)/, 'dna', 'pink'],
  [/(y học|y khoa|dược|medic|nursing)/, 'stethoscope', 'coral'],
  [/(tâm l[ýí]|psychology|nhận thức|trí nhớ|hành vi|củng cố|thần kinh|neuro)/, 'psychology', 'pink'],
  [/(tiếng anh|english|ngôn ngữ|language|ngữ pháp|grammar|từ vựng|vocabulary)/, 'speech', 'peach'],
  [/(lịch sử|history)/, 'scroll', 'butter'],
  [/(địa l[ýí]|geography)/, 'map', 'mint'],
  [/(luật|pháp luật|law|triết|chính trị|philosoph)/, 'scale', 'lilac'],
  [/(âm nhạc|music)/, 'music', 'lilac'],
  [/(mỹ thuật|thiết kế|design)/, 'palette', 'pink'],
  [/(viết|văn học|ngữ văn|writing|essay)/, 'pencil', 'peach'],
];
const COURSE_FALLBACK: TopicIcon[] = ['books', 'book', 'bulb', 'graduation', 'target'];
// Several courses on one subject should not look identical: each title settles on one of three neighbouring colours.
const TONE_FAMILY: Record<TileTone, [TileTone, TileTone, TileTone]> = {
  sky: ['sky', 'lilac', 'mint'],
  butter: ['butter', 'peach', 'pink'],
  pink: ['pink', 'lilac', 'peach'],
  mint: ['mint', 'sky', 'sage'],
  lilac: ['lilac', 'sky', 'pink'],
  peach: ['peach', 'butter', 'coral'],
  coral: ['coral', 'peach', 'pink'],
  sage: ['sage', 'mint', 'butter'],
};

/** The cover a course gets until its creator picks one: by subject, else a study icon in a colour from the title. */
const plain = (text: string) => text.normalize('NFC').toLowerCase();

export function courseCover(title: string): Cover {
  const t = plain(title);
  const hit = COURSE_RULES.find(([pattern]) => pattern.test(t));
  const h = hash(t);
  if (hit) return { icon: hit[1], tone: TONE_FAMILY[hit[2]][h % 3] };
  return { icon: COURSE_FALLBACK[h % COURSE_FALLBACK.length], tone: TILE_TONES[h % TILE_TONES.length] };
}

const LESSON_RULES: [RegExp, TopicIcon][] = [
  [/(giới thiệu|tổng quan|mở đầu|nhập môn|overview|introduction)/, 'compass'],
  [/(ôn tập|tổng kết|tóm tắt|kết luận|review|summary)/, 'trophy'],
  [/(bài tập|luyện tập|ví dụ|exercise|practice|example)/, 'writing'],
  [/(subnet|mask|chia mạng|cidr|vlsm)/, 'abacus'],
  [/(classful|phân loại|phân lớp|lớp [a-e]\b)/, 'cards'],
  [/(địa chỉ|address|ipv4|ipv6|\bip\b)/, 'network'],
  [/(broadcast|multicast|quảng bá)/, 'megaphone'],
  [/(định tuyến|routing|router)/, 'satellite'],
  [/(tcp|udp|gói tin|packet|segment)/, 'package'],
  [/(giao thức|protocol|bắt tay|handshake)/, 'handshake'],
  [/(dns|tên miền|domain)/, 'search'],
  [/(wifi|không dây|wireless)/, 'signal'],
  [/(ethernet|cáp|cable|tầng vật l[ýí])/, 'plug'],
  [/(bảo mật|tấn công|mật mã|security|attack)/, 'lock'],
  [/(máy chủ|server)/, 'desktop'],
  [/(tích phân|nguyên hàm|integral)/, 'ruler'],
  [/(đạo hàm|vi phân|derivative)/, 'calculus'],
  [/(giới hạn|liên tục|limit)/, 'target'],
  [/(diện tích|thể tích|hình học|area|volume)/, 'ruler'],
  [/(xác suất|probability)/, 'dice'],
  [/(cơ sở dữ liệu|database|sql)/, 'cabinet'],
  [/(thống kê|dữ liệu|statistic|data)/, 'chart'],
  [/(công thức|phương trình|formula|equation)/, 'numbers'],
  [/(hàm số|đồ thị|function|graph)/, 'calculus'],
  [/(trí nhớ|ghi nhớ|memory)/, 'psychology'],
  [/(cảm xúc|động lực|emotion|motivation)/, 'heart'],
  [/(nhận thức|tư duy|cognition|thinking)/, 'bulb'],
  [/(học tập|củng cố|learning|conditioning)/, 'graduation'],
  [/(xã hội|nhóm|social|group)/, 'people'],
  [/(phát triển|trưởng thành|development)/, 'leaf'],
  [/(lịch sử|history)/, 'scroll'],
  [/(thuật toán|algorithm)/, 'gear'],
  [/(lập trình|vòng lặp|câu lệnh|code)/, 'code'],
  [/(định nghĩa|khái niệm|definition|concept)/, 'book'],
];
const LESSON_POOL: TopicIcon[] = ['bulb', 'target', 'puzzle', 'rocket', 'books', 'search', 'star', 'compass', 'graduation', 'flag'];

/**
 * One icon per lesson, in order: the best match for each title that the
 * course has not used yet, so the path reads at a glance. Same titles, same icons.
 */
export function lessonIcons(titles: string[]): TopicIcon[] {
  const used = new Set<TopicIcon>();
  return titles.map((title, index) => {
    const t = plain(title);
    const matches = LESSON_RULES.filter(([pattern]) => pattern.test(t)).map(([, icon]) => icon);
    const pool = LESSON_POOL.map((_, i) => LESSON_POOL[(index + i) % LESSON_POOL.length]);
    const icon = [...matches, ...pool].find((candidate) => !used.has(candidate)) ?? matches[0] ?? pool[0];
    used.add(icon);
    return icon;
  });
}
