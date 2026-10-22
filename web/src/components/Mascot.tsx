// "Kẹp" — a soft ginger cat in thick black nerd glasses (flat on top, gently
// rounded below), after the sketch Huy picked: a round pear-shaped body,
// half-lidded "obviously" eyes, whiskers past the cheeks and a tail that grows
// from behind and curls up at the side. Few expressions, used only where a face helps:
// greeting, hint, waiting, success, and when something failed.

export type Mood = 'hello' | 'hint' | 'think' | 'happy' | 'oops';

const INK = '#2b2f36';
const FRAME = '#14161a';
const FUR = '#ffd8ad';
const STRIPE = '#f3a660';
const BELLY = '#fff3e4';
const PINK = '#f6a7ba';

const BODY =
  'M60 105C46 105 32.5 105 28 99.5C24.4 94.6 24.2 87.5 24.6 80C25.4 64 27.2 50 29.6 37L31.4 15.6Q32 9.8 36.2 13.4L48 23.8Q60 19.2 72 23.8L83.8 13.4Q88 9.8 88.6 15.6L90.4 37C92.8 50 94.6 64 95.4 80C95.8 87.5 95.6 94.6 92 99.5C87.5 105 74 105 60 105Z';
// Lenses: a flat, square top and a gently rounded bottom, like classic nerd frames.
const LENSES = 'M33 37H56V49Q56 56 49 56H40Q33 56 33 49ZM64 37H87V49Q87 56 80 56H71Q64 56 64 49Z';
// The tail grows from behind the body: its root is hidden, it sweeps out to the left and curls up.
const TAIL = 'M46 100C30 106 14 102 11 89C9.6 81 12.4 74.6 18.5 72';
const line = { stroke: INK, fill: 'none', strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };

/** A limb or the tail: an outlined tube in fur colour with a round end. */
function Tube({ d, width = 8 }: { d: string; width?: number }) {
  return (
    <g>
      <path d={d} stroke={INK} strokeWidth={width + 4.4} fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <path d={d} stroke={FUR} strokeWidth={width} fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </g>
  );
}

function Eyes({ mood }: { mood: Mood }) {
  switch (mood) {
    case 'happy':
      return <path d="M38.5 49.5q6-6.5 12 0M69.5 49.5q6-6.5 12 0" {...line} strokeWidth={2.4} />;
    case 'oops':
      return (
        <g>
          <circle cx="44.5" cy="47" r="3.6" fill={INK} />
          <circle cx="75.5" cy="47" r="3.6" fill={INK} />
          <circle cx="45.7" cy="45.8" r="1.1" fill="#fff" />
          <circle cx="76.7" cy="45.8" r="1.1" fill="#fff" />
        </g>
      );
    case 'think':
      return (
        <g fill={INK}>
          <circle cx="48" cy="44" r="3" />
          <circle cx="79" cy="44" r="3" />
        </g>
      );
    default:
      // Half-lidded: a flat lid with the pupil hanging under it.
      return (
        <g>
          <path d="M38 45.5h13M69 45.5h13" {...line} strokeWidth={2.4} />
          <circle cx="44.5" cy="48.3" r="2.9" fill={INK} />
          <circle cx="75.5" cy="48.3" r="2.9" fill={INK} />
          <circle cx="45.4" cy="47.5" r=".8" fill="#fff" />
          <circle cx="76.4" cy="47.5" r=".8" fill="#fff" />
        </g>
      );
  }
}

function Mouth({ mood }: { mood: Mood }) {
  switch (mood) {
    case 'happy':
      return (
        <g>
          <path d="M55.5 62q4.5 6.5 9 0z" fill={INK} stroke={INK} strokeWidth="1.6" strokeLinejoin="round" />
          <path d="M58 64.6q2-1.2 4 0" stroke={PINK} strokeWidth="1.8" strokeLinecap="round" fill="none" />
        </g>
      );
    case 'oops':
      return <path d="M55.5 63.5q2.25-2.2 4.5 0t4.5 0" {...line} strokeWidth={1.9} />;
    case 'think':
      return <path d="M57.5 62.5h5" {...line} strokeWidth={1.9} />;
    default:
      return <path d="M60 59.6v1.4M56 61.6q2 2.2 4 0q2 2.2 4 0" {...line} strokeWidth={1.9} />;
  }
}

function Paws({ mood }: { mood: Mood }) {
  switch (mood) {
    case 'hello':
      return (
        <g className="mascot__wave">
          <Tube d="M90 78C97 75 100.5 68 100 60" />
        </g>
      );
    case 'hint':
      return <Tube d="M90 76C96 70 97.5 62 97 53" />;
    case 'happy':
      return (
        <g>
          <Tube d="M30 78C23 75 19.5 68 20 60" />
          <Tube d="M90 78C97 75 100.5 68 100 60" />
        </g>
      );
    case 'think':
      return <Tube d="M84 92C80 82 76 75 69 71.5" />;
    default:
      return null;
  }
}

function Extras({ mood }: { mood: Mood }) {
  switch (mood) {
    case 'hello':
      // The little "attitude" strokes from the sketch.
      return (
        <g className="mascot__extra" stroke={INK} strokeWidth="2.2" strokeLinecap="round">
          <path d="M21.5 11l2 6M14 21l6 2.4M98.5 16l-5 3.6M102.5 27.5l-6 .4" />
        </g>
      );
    case 'hint':
      return (
        <g className="mascot__extra">
          <path d="M104 8a8 8 0 0 0-4.6 14.5c.7.5 1 1.3 1 2.1V27h7.2v-2.4c0-.8.3-1.6 1-2.1A8 8 0 0 0 104 8z" fill="#f7dd72" stroke={INK} strokeWidth="2" strokeLinejoin="round" />
          <path d="M101 31h6" stroke={INK} strokeWidth="2" strokeLinecap="round" />
        </g>
      );
    case 'think':
      return (
        <g className="mascot__extra">
          <circle cx="98" cy="30" r="2.4" fill="#fff" stroke={INK} strokeWidth="1.8" />
          <circle cx="105" cy="21.5" r="3.4" fill="#fff" stroke={INK} strokeWidth="1.8" />
          <circle cx="112.5" cy="11" r="4.6" fill="#fff" stroke={INK} strokeWidth="1.8" />
        </g>
      );
    case 'happy':
      return (
        <g className="mascot__extra" fill="#f7cf3c" stroke={INK} strokeWidth="1.6" strokeLinejoin="round">
          <path d="M11 25l2 4.8 4.8 2-4.8 2L11 38.6l-2-4.8-4.8-2 4.8-2z" />
          <path d="M108 32l1.5 3.6 3.6 1.5-3.6 1.5-1.5 3.6-1.5-3.6-3.6-1.5 3.6-1.5z" />
        </g>
      );
    case 'oops':
      return (
        <g className="mascot__extra">
          <path d="M97 20c2.8 4.2 4.2 6.8 4.2 8.8a4.2 4.2 0 0 1-8.4 0c0-2 1.4-4.6 4.2-8.8z" fill="#a9c1e3" stroke={INK} strokeWidth="1.8" />
        </g>
      );
    default:
      return null;
  }
}

/** The cat itself (no shadow or signs), shared with the logo. */
export function CatDrawing({ mood = 'hello' }: { mood?: Mood }) {
  return (
    <g>
      <Tube d={TAIL} width={10} />
      <path d="M6.6 85.4l9.6-.2M8.8 94.6l8.6-3.4" stroke={STRIPE} strokeWidth="2.4" strokeLinecap="round" />
      <path d={BODY} fill={FUR} stroke={INK} strokeWidth="2.4" strokeLinejoin="round" />
      <path d="M34.1 18.5L36.4 15.9L44.6 23.2L35 27.6ZM85.9 18.5L83.6 15.9L75.4 23.2L85 27.6Z" fill={PINK} opacity=".9" />
      <path d="M54.5 26.5v4.5M60 25.5v5.5M65.5 26.5v4.5M26.5 70h5M26 77h4.5M93.5 70h-5M94 77h-4.5" stroke={STRIPE} strokeWidth="2.4" strokeLinecap="round" />
      <ellipse cx="60" cy="88" rx="17" ry="14" fill={BELLY} />
      <path d="M51.5 92v12.5M68.5 92v12.5" stroke={INK} strokeWidth="2.2" strokeLinecap="round" />
      <path d="M30 58.5l-12-1.6M30 62.5l-11 1.8M90 58.5l12-1.6M90 62.5l11 1.8" stroke={INK} strokeWidth="1.8" strokeLinecap="round" />
      <ellipse cx="36.5" cy="61.5" rx="4.2" ry="2.6" fill={PINK} opacity=".55" />
      <ellipse cx="83.5" cy="61.5" rx="4.2" ry="2.6" fill={PINK} opacity=".55" />
      {/* Thick black glasses: pale lenses behind the eyes, frames on top. */}
      <path d={LENSES} fill="#fff" fillOpacity=".6" />
      <Eyes mood={mood} />
      <path d={LENSES} fill="none" stroke={FRAME} strokeWidth="3.6" strokeLinejoin="round" />
      <path d="M56 39.5h8M33 39.5l-4.5-1.4M87 39.5l4.5-1.4" stroke={FRAME} strokeWidth="3.4" fill="none" strokeLinecap="round" />
      <path d="M36.8 41.2l3.4-.1M67.8 41.2l3.4-.1" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" />
      <path d="M57.6 57.4h4.8l-2.4 2.9z" fill={PINK} stroke={INK} strokeWidth="1.5" strokeLinejoin="round" />
      <Mouth mood={mood} />
      <Paws mood={mood} />
    </g>
  );
}

/** `face` crops to the head for small round avatars. */
export function Mascot({ mood = 'hello', size = 96, bob = false, face = false, title }: { mood?: Mood; size?: number; bob?: boolean; face?: boolean; title?: string }) {
  return (
    <svg
      className={`mascot mascot--${mood}${bob ? ' mascot--bob' : ''}`}
      width={size}
      height={size}
      viewBox={face ? '17 6 86 86' : '0 0 120 120'}
      role={title ? 'img' : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
    >
      {!face && <ellipse cx="60" cy="111" rx="30" ry="3.6" fill="rgba(35,38,43,.1)" />}
      <g className="mascot__body">
        <CatDrawing mood={mood} />
      </g>
      <Extras mood={mood} />
    </svg>
  );
}
