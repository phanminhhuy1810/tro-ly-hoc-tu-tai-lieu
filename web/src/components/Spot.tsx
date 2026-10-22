// Small ink-sketch spot illustrations on a soft starburst, after the TAITOR
// reference: tiny, purposeful, one hand. Course covers use them as presets
// (picked from the course title, or chosen by the creator), never generated images.

const INK = '#23262b';

export const GLYPHS = [
  'network',
  'code',
  'calculus',
  'chart',
  'atom',
  'flask',
  'psychology',
  'brain',
  'globe',
  'scale',
  'pencil',
  'book',
  'papers',
  'cards',
  'flag',
] as const;
export type Glyph = (typeof GLYPHS)[number];
export const TONE_NAMES = ['sage', 'butter', 'coral', 'sky'] as const;
export type Tone = (typeof TONE_NAMES)[number];

const TONES: Record<Tone, string> = {
  sage: '#e3edd4',
  butter: '#fcf0b8',
  coral: '#f8dccf',
  sky: '#dfe8f5',
};

function starburst(cx: number, cy: number, outer: number, inner: number, points = 12): string {
  const parts: string[] = [];
  for (let i = 0; i < points * 2; i += 1) {
    const r = i % 2 === 0 ? outer : inner;
    const a = (Math.PI * i) / points - Math.PI / 2;
    parts.push(`${(cx + r * Math.cos(a)).toFixed(2)},${(cy + r * Math.sin(a)).toFixed(2)}`);
  }
  return parts.join(' ');
}

function GlyphPaths({ glyph }: { glyph: Glyph }) {
  const s = { stroke: INK, strokeWidth: 2.4, fill: 'none', strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };
  switch (glyph) {
    case 'network':
      return (
        <g>
          <path d="M30 32 50 32M30 32 40 52M50 32 40 52" {...s} />
          <circle cx="30" cy="32" r="6" fill="#fff" stroke={INK} strokeWidth="2.4" />
          <circle cx="50" cy="32" r="6" fill="#fff" stroke={INK} strokeWidth="2.4" />
          <circle cx="40" cy="52" r="6" fill="#f7dd72" stroke={INK} strokeWidth="2.4" />
        </g>
      );
    case 'code':
      return (
        <g>
          <rect x="21" y="25" width="38" height="30" rx="5" {...s} fill="#fff" />
          <path d="M33 34l-6 6 6 6M47 34l6 6-6 6M42.5 32l-5 16" {...s} />
        </g>
      );
    case 'calculus':
      return (
        <g>
          <path d="M45 22c-4-3-8 0-8 5v26c0 5-4 8-8 5" {...s} />
          <path d="M44 50q4-14 9-6t9-8" {...s} stroke="#5f803e" />
        </g>
      );
    case 'chart':
      return (
        <g>
          <path d="M24 57h34M25 57V24" {...s} />
          <rect x="30" y="42" width="7" height="15" rx="1.5" fill="#f7dd72" stroke={INK} strokeWidth="2.2" />
          <rect x="40" y="34" width="7" height="23" rx="1.5" fill="#fff" stroke={INK} strokeWidth="2.2" />
          <rect x="50" y="27" width="7" height="30" rx="1.5" fill="#92b06c" stroke={INK} strokeWidth="2.2" />
        </g>
      );
    case 'atom':
      return (
        <g>
          <ellipse cx="40" cy="40" rx="18" ry="7" {...s} />
          <ellipse cx="40" cy="40" rx="18" ry="7" {...s} transform="rotate(60 40 40)" />
          <ellipse cx="40" cy="40" rx="18" ry="7" {...s} transform="rotate(120 40 40)" />
          <circle cx="40" cy="40" r="4" fill="#f7dd72" stroke={INK} strokeWidth="2.2" />
        </g>
      );
    case 'flask':
      return (
        <g>
          <path d="M34.5 23h11M36.5 23v12.5L26 52.5a3.5 3.5 0 0 0 3 5.5h22a3.5 3.5 0 0 0 3-5.5L43.5 35.5V23" {...s} fill="#fff" />
          <path d="M30 47h20l3.4 6.3a2 2 0 0 1-1.8 2.7H28.4a2 2 0 0 1-1.8-2.7z" fill="#92b06c" stroke={INK} strokeWidth="2" strokeLinejoin="round" />
          <circle cx="39" cy="41" r="1.8" fill={INK} />
        </g>
      );
    case 'psychology':
      return (
        <g>
          <path d="M33 58v-7c-6-5-5-19 7-21 10-2 17 6 15 15l4 6h-4v5h-8v2" {...s} />
          <path d="M40 38c2-3 7-3 8 1 1 3-3 4-2 7" {...s} stroke="#b5563a" />
        </g>
      );
    case 'brain':
      return (
        <g>
          <path d="M39 25c-4-3-11-1-11 5-5 1-6 7-3 10-3 4 0 10 5 10 1 5 7 6 9 3z" {...s} fill="#f8dccf" />
          <path d="M41 25c4-3 11-1 11 5 5 1 6 7 3 10 3 4 0 10-5 10-1 5-7 6-9 3z" {...s} fill="#fff" />
          <path d="M33 35c2 1 3 3 2 5M47 35c-2 1-3 3-2 5M40 26v27" {...s} />
        </g>
      );
    case 'globe':
      return (
        <g>
          <circle cx="40" cy="40" r="16" {...s} fill="#fff" />
          <ellipse cx="40" cy="40" rx="7" ry="16" {...s} />
          <path d="M25 34h30M25 46h30" {...s} />
          <path d="M51 27l3-3" {...s} stroke="#5f803e" />
        </g>
      );
    case 'scale':
      return (
        <g>
          <path d="M40 24v31M31 56h18M24 30h32" {...s} />
          <path d="M24 30l-6 12h12zM56 30l-6 12h12z" {...s} fill="#fff" />
          <path d="M18 42a6 3 0 0 0 12 0M50 42a6 3 0 0 0 12 0" {...s} fill="#f7dd72" />
          <circle cx="40" cy="24" r="2.6" fill={INK} />
        </g>
      );
    case 'pencil':
      return (
        <g>
          <path d="M27 55l3-11 20-20 8 8-20 20z" {...s} fill="#f7dd72" />
          <path d="M45 29l8 8M30 44l6 6" {...s} />
          <path d="M27 55l3-11 8 8z" fill="#fff" stroke={INK} strokeWidth="2.2" strokeLinejoin="round" />
        </g>
      );
    case 'papers':
      return (
        <g>
          <path d="M27 26h20l7 7v24H27z" {...s} fill="#fff" />
          <path d="M23 31v30h24" {...s} />
          <path d="M47 26v7h7M33 41h12M33 47h8" {...s} />
          <circle cx="56" cy="56" r="7" fill="#f7dd72" stroke={INK} strokeWidth="2.2" />
          <path d="M56 52.5v7M52.5 56h7" {...s} strokeWidth={2} />
        </g>
      );
    case 'flag':
      return (
        <g>
          <path d="M30 60V22" {...s} />
          <path d="M30 24h22l-5 7 5 7H30" {...s} fill="#f7dd72" />
          <path d="M24 60h14" {...s} />
        </g>
      );
    case 'cards':
      return (
        <g>
          <rect x="24" y="28" width="26" height="30" rx="4" {...s} fill="#fff" transform="rotate(-8 37 43)" />
          <rect x="32" y="24" width="26" height="30" rx="4" {...s} fill="#fff" transform="rotate(6 45 39)" />
          <path d="M40 36h10M40 42h7" {...s} transform="rotate(6 45 39)" />
        </g>
      );
    default:
      return (
        <g>
          <path d="M22 30c7-4 12-4 18 0 6-4 11-4 18 0v26c-7-4-12-4-18 0-6-4-11-4-18 0z" {...s} fill="#fff" />
          <path d="M40 30v26M27 37h7M27 43h7M46 37h7" {...s} />
        </g>
      );
  }
}

export function Spot({ glyph, tone = 'sage', size = 72, label }: { glyph: Glyph; tone?: Tone; size?: number; label?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 80 80" role={label ? 'img' : undefined} aria-label={label} aria-hidden={label ? undefined : true}>
      <polygon points={starburst(40, 40, 37, 32)} fill={TONES[tone]} />
      <GlyphPaths glyph={glyph} />
    </svg>
  );
}

const KEYWORDS: [RegExp, Glyph, Tone][] = [
  [/(ip\b|ipv|subnet|mạng|network|tcp|router|lan\b|giao thức|tầng)/, 'network', 'sage'],
  [/(lập trình|code|python|java|thuật toán|algorithm|cấu trúc dữ liệu|web|sql)/, 'code', 'sky'],
  [/(tích phân|đạo hàm|giới hạn|calculus|integral|derivative|hàm số|toán|đại số|xác suất)/, 'calculus', 'butter'],
  [/(thống kê|kinh tế|tài chính|kế toán|marketing|statistic|econom)/, 'chart', 'butter'],
  [/(vật lý|physics|lượng tử|điện|cơ học)/, 'atom', 'sky'],
  [/(hóa|chemistry|sinh học|biology|tế bào)/, 'flask', 'sage'],
  [/(tâm lý|psychology|nhận thức|trí nhớ|hành vi|củng cố)/, 'psychology', 'coral'],
  [/(thần kinh|não|neuro)/, 'brain', 'coral'],
  [/(tiếng anh|english|ngôn ngữ|language|địa lý|lịch sử|history)/, 'globe', 'sky'],
  [/(luật|pháp luật|law|triết|chính trị)/, 'scale', 'coral'],
  [/(viết|văn|writing|essay)/, 'pencil', 'butter'],
];

export function coverFor(title: string): { glyph: Glyph; tone: Tone } {
  const t = title.toLowerCase();
  const hit = KEYWORDS.find(([pattern]) => pattern.test(t));
  return hit ? { glyph: hit[1], tone: hit[2] } : { glyph: 'book', tone: 'sky' };
}

export function parsePreset(preset: string | null | undefined): { glyph: Glyph; tone: Tone } | null {
  const [glyph, tone] = (preset ?? '').split('-');
  return (GLYPHS as readonly string[]).includes(glyph) && (TONE_NAMES as readonly string[]).includes(tone) ? { glyph: glyph as Glyph, tone: tone as Tone } : null;
}
