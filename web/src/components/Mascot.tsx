// "Kẹp" — a small page with a bookmark ribbon. Monoline ink + flat sage/butter,
// the same hand as the spot illustrations. Few expressions, used only where a
// face helps: greeting, hint, waiting, success, and when something failed.

export type Mood = 'hello' | 'hint' | 'think' | 'happy' | 'oops';

const INK = '#23262b';

function Face({ mood }: { mood: Mood }) {
  switch (mood) {
    case 'happy':
      return (
        <g>
          <path d="M47 57q4.5-5.5 9 0M65 57q4.5-5.5 9 0" stroke={INK} strokeWidth="2.6" fill="none" strokeLinecap="round" />
          <path d="M54 64q7 10 14 0z" fill={INK} stroke={INK} strokeWidth="2" strokeLinejoin="round" />
          <path d="M58 67.5q3-2 6 0" stroke="#e2896d" strokeWidth="2.4" strokeLinecap="round" fill="none" />
        </g>
      );
    case 'think':
      return (
        <g>
          <circle cx="54.5" cy="54" r="3.6" fill={INK} />
          <circle cx="72.5" cy="54" r="3.6" fill={INK} />
          <path d="M57 68h8" stroke={INK} strokeWidth="2.4" strokeLinecap="round" />
        </g>
      );
    case 'hint':
      return (
        <g>
          <path d="M46 48.5q5-4.5 10-1.5" stroke={INK} strokeWidth="2.3" fill="none" strokeLinecap="round" />
          <path d="M66 49h9" stroke={INK} strokeWidth="2.3" strokeLinecap="round" />
          <circle cx="51.5" cy="56" r="3.6" fill={INK} />
          <circle cx="70" cy="56" r="3.6" fill={INK} />
          <path d="M56 66.5q5.5 3.5 11-1" stroke={INK} strokeWidth="2.4" fill="none" strokeLinecap="round" />
        </g>
      );
    case 'oops':
      return (
        <g>
          <path d="M46 49.5l7.5 2.5M75.5 49.5 68 52" stroke={INK} strokeWidth="2.3" strokeLinecap="round" />
          <circle cx="51.5" cy="57" r="3.4" fill={INK} />
          <circle cx="70" cy="57" r="3.4" fill={INK} />
          <path d="M55 68.5q3-3 6 0t6 0" stroke={INK} strokeWidth="2.4" fill="none" strokeLinecap="round" />
        </g>
      );
    default:
      return (
        <g>
          <circle cx="51.5" cy="56" r="3.6" fill={INK} />
          <circle cx="70" cy="56" r="3.6" fill={INK} />
          <path d="M55.5 65q5.5 6 11 0" stroke={INK} strokeWidth="2.6" fill="none" strokeLinecap="round" />
        </g>
      );
  }
}

function Extras({ mood }: { mood: Mood }) {
  switch (mood) {
    case 'hint':
      return (
        <g className="mascot__extra">
          <path d="M98 14a8 8 0 0 0-4.6 14.5c.7.5 1 1.3 1 2.1V33h7.2v-2.4c0-.8.3-1.6 1-2.1A8 8 0 0 0 98 14z" fill="#f7dd72" stroke={INK} strokeWidth="2.2" strokeLinejoin="round" />
          <path d="M95 37h6" stroke={INK} strokeWidth="2.2" strokeLinecap="round" />
          <path d="M88 10l-3-3M108 10l3-3M110 22h4" stroke={INK} strokeWidth="2" strokeLinecap="round" />
        </g>
      );
    case 'think':
      return (
        <g className="mascot__extra">
          <circle cx="93" cy="31" r="2.6" fill="#fff" stroke={INK} strokeWidth="2" />
          <circle cx="100.5" cy="23" r="3.6" fill="#fff" stroke={INK} strokeWidth="2" />
          <circle cx="110" cy="13" r="5" fill="#fff" stroke={INK} strokeWidth="2" />
        </g>
      );
    case 'happy':
      return (
        <g className="mascot__extra" fill="#e3bd38" stroke={INK} strokeWidth="1.8" strokeLinejoin="round">
          <path d="M18 30l2.2 5.3 5.3 2.2-5.3 2.2L18 45l-2.2-5.3-5.3-2.2 5.3-2.2z" />
          <path d="M104 40l1.6 3.9 3.9 1.6-3.9 1.6-1.6 3.9-1.6-3.9-3.9-1.6 3.9-1.6z" />
        </g>
      );
    case 'oops':
      return (
        <g className="mascot__extra">
          <path d="M92 34c3 4.5 4.5 7.3 4.5 9.4a4.5 4.5 0 0 1-9 0c0-2.1 1.5-4.9 4.5-9.4z" fill="#a9c1e3" stroke={INK} strokeWidth="2" />
        </g>
      );
    default:
      return null;
  }
}

function Arms({ mood }: { mood: Mood }) {
  const stroke = { stroke: INK, strokeWidth: 2.8, fill: 'none', strokeLinecap: 'round' as const };
  if (mood === 'happy') {
    return (
      <g>
        <path d="M30 66q-10-6-10-18" {...stroke} />
        <path d="M90 66q10-6 10-18" {...stroke} />
      </g>
    );
  }
  if (mood === 'think') {
    return (
      <g>
        <path d="M30 74q-6 2-4 8" {...stroke} />
        <path d="M90 76q-2-6-14-6" {...stroke} />
      </g>
    );
  }
  return (
    <g>
      <path d="M30 72q-9 2-10-5" {...stroke} />
      <g className={mood === 'hello' ? 'mascot__wave' : undefined}>
        <path d={mood === 'hint' ? 'M90 66q8-4 6-16' : 'M90 70q9-2 11-12'} {...stroke} />
      </g>
    </g>
  );
}

export function Mascot({ mood = 'hello', size = 96, bob = false, title }: { mood?: Mood; size?: number; bob?: boolean; title?: string }) {
  return (
    <svg
      className={`mascot mascot--${mood}${bob ? ' mascot--bob' : ''}`}
      width={size}
      height={size}
      viewBox="0 0 120 120"
      role={title ? 'img' : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
    >
      <ellipse cx="60" cy="109" rx="25" ry="4" fill="rgba(35,38,43,.1)" />
      <g className="mascot__body">
        <Arms mood={mood} />
        <path d="M38 18h36l16 16v58a8 8 0 0 1-8 8H38a8 8 0 0 1-8-8V26a8 8 0 0 1 8-8z" fill="#e3edd4" stroke={INK} strokeWidth="2.6" strokeLinejoin="round" />
        <path d="M74 18v11a5 5 0 0 0 5 5h11" fill="#cadcb2" stroke={INK} strokeWidth="2.6" strokeLinejoin="round" />
        <path d="M41 85h24M41 91h15" stroke="#92b06c" strokeWidth="2.4" strokeLinecap="round" opacity=".75" />
        <path d="M40 12h9v28l-4.5-3.5L40 40z" fill="#f7dd72" stroke={INK} strokeWidth="2.2" strokeLinejoin="round" />
        <ellipse cx="45" cy="66" rx="4.6" ry="3" fill="#e2896d" opacity=".42" />
        <ellipse cx="77" cy="66" rx="4.6" ry="3" fill="#e2896d" opacity=".42" />
        <Face mood={mood} />
      </g>
      <Extras mood={mood} />
    </svg>
  );
}
