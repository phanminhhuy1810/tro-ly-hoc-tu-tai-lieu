// "Kẹp" — a cheeky ginger cat in big nerd glasses and a bow tie, after the
// sketch Huy picked: monoline ink, flat warm colours, half-lidded eyes that
// say "obviously". Few expressions, used only where a face helps: greeting,
// hint, waiting, success, and when something failed.

export type Mood = 'hello' | 'hint' | 'think' | 'happy' | 'oops';

const INK = '#23262b';
const FUR = '#ffcf94';
const STRIPE = '#e98d3c';
const BELLY = '#fff3e2';
const PINK = '#f59bb0';
const TIE = '#3b6fe8';

const line = { stroke: INK, strokeWidth: 2.6, fill: 'none', strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };

/** A limb as an outlined tube in fur colour, ending in a round paw. */
function Paw({ d, x, y }: { d: string; x: number; y: number }) {
  return (
    <g>
      <path d={d} stroke={INK} strokeWidth="11" fill="none" strokeLinecap="round" />
      <path d={d} stroke={FUR} strokeWidth="6" fill="none" strokeLinecap="round" />
      <circle cx={x} cy={y} r="5.2" fill={FUR} stroke={INK} strokeWidth="2.4" />
    </g>
  );
}

function Eyes({ mood }: { mood: Mood }) {
  switch (mood) {
    case 'happy':
      return <path d="M41.5 48q5.5-6 11 0M67.5 48q5.5-6 11 0" {...line} />;
    case 'think':
      return (
        <g fill={INK}>
          <circle cx="51" cy="42.5" r="2.7" />
          <circle cx="77" cy="42.5" r="2.7" />
        </g>
      );
    case 'oops':
      return (
        <g>
          <circle cx="47" cy="45" r="3.6" fill={INK} />
          <circle cx="73" cy="45" r="3.6" fill={INK} />
          <circle cx="48.2" cy="43.8" r="1.1" fill="#fff" />
          <circle cx="74.2" cy="43.8" r="1.1" fill="#fff" />
        </g>
      );
    default:
      // Half-lidded: a flat lid with the pupil hanging under it.
      return (
        <g>
          <path d="M41 44.5h12M67 44.5h12" {...line} />
          <circle cx="47.5" cy="47.2" r="2.6" fill={INK} />
          <circle cx="73.5" cy="47.2" r="2.6" fill={INK} />
        </g>
      );
  }
}

function Mouth({ mood }: { mood: Mood }) {
  switch (mood) {
    case 'happy':
      return (
        <g>
          <path d="M54.5 60.5q5.5 8 11 0z" fill={INK} stroke={INK} strokeWidth="2" strokeLinejoin="round" />
          <path d="M57.5 63.5q2.5-1.6 5 0" stroke={PINK} strokeWidth="2.2" strokeLinecap="round" fill="none" />
        </g>
      );
    case 'think':
      return <path d="M56.5 61.5h7" {...line} />;
    case 'oops':
      return <path d="M54.5 62q2.75-2.6 5.5 0t5.5 0" {...line} />;
    default:
      // A one-sided smirk: the cat knows the answer.
      return <path d="M60 57.5v2.2M55 60.5q2.5 2.2 5 -.8q3.5 2.6 7.5-2" {...line} />;
  }
}

function Extras({ mood }: { mood: Mood }) {
  switch (mood) {
    case 'hello':
      // The little "attitude" strokes from the sketch.
      return (
        <g className="mascot__extra" stroke={INK} strokeWidth="2.4" strokeLinecap="round">
          <path d="M24 8l2 7M16 18l7 3M97 13l-6 4M101 25l-7 1" />
        </g>
      );
    case 'hint':
      return (
        <g className="mascot__extra">
          <path d="M103 9a8 8 0 0 0-4.6 14.5c.7.5 1 1.3 1 2.1V28h7.2v-2.4c0-.8.3-1.6 1-2.1A8 8 0 0 0 103 9z" fill="#f7dd72" stroke={INK} strokeWidth="2.2" strokeLinejoin="round" />
          <path d="M100 32h6" stroke={INK} strokeWidth="2.2" strokeLinecap="round" />
          <path d="M93 6l-3-3M113 6l3-3M115 17h4" stroke={INK} strokeWidth="2" strokeLinecap="round" />
        </g>
      );
    case 'think':
      return (
        <g className="mascot__extra">
          <circle cx="96" cy="30" r="2.6" fill="#fff" stroke={INK} strokeWidth="2" />
          <circle cx="103.5" cy="21" r="3.6" fill="#fff" stroke={INK} strokeWidth="2" />
          <circle cx="112" cy="10" r="5" fill="#fff" stroke={INK} strokeWidth="2" />
        </g>
      );
    case 'happy':
      return (
        <g className="mascot__extra" fill="#f7cf3c" stroke={INK} strokeWidth="1.8" strokeLinejoin="round">
          <path d="M12 26l2.2 5.3 5.3 2.2-5.3 2.2L12 41l-2.2-5.3-5.3-2.2 5.3-2.2z" />
          <path d="M108 34l1.6 3.9 3.9 1.6-3.9 1.6-1.6 3.9-1.6-3.9-3.9-1.6 3.9-1.6z" />
        </g>
      );
    case 'oops':
      return (
        <g className="mascot__extra">
          <path d="M96 22c3 4.5 4.5 7.3 4.5 9.4a4.5 4.5 0 0 1-9 0c0-2.1 1.5-4.9 4.5-9.4z" fill="#a9c1e3" stroke={INK} strokeWidth="2" />
        </g>
      );
    default:
      return null;
  }
}

function Paws({ mood }: { mood: Mood }) {
  if (mood === 'happy') {
    return (
      <g>
        <Paw d="M34 74Q24 68 21 57" x={21} y={55} />
        <Paw d="M86 74Q96 68 99 57" x={99} y={55} />
      </g>
    );
  }
  if (mood === 'think') return <Paw d="M84 86Q80 74 73 70" x={72} y={69} />;
  if (mood === 'hello') {
    return (
      <g className="mascot__wave">
        <Paw d="M86 76Q96 70 99 58" x={99} y={56} />
      </g>
    );
  }
  if (mood === 'hint') return <Paw d="M86 74Q95 64 96 50" x={96} y={48} />;
  return null;
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
      <ellipse cx="58" cy="111" rx="30" ry="4" fill="rgba(35,38,43,.1)" />
      <g className="mascot__body">
        {/* Tail first, so the body sits on it. */}
        <path d="M40 104C22 107 10 96 13 82C15 72 25 69 29 76" stroke={INK} strokeWidth="13" fill="none" strokeLinecap="round" />
        <path d="M40 104C22 107 10 96 13 82C15 72 25 69 29 76" stroke={FUR} strokeWidth="7.5" fill="none" strokeLinecap="round" />
        <path d="M16.5 90.5l5.5-3M13.5 81.5l6 .5" stroke={STRIPE} strokeWidth="2.6" strokeLinecap="round" />
        <path d="M44 106Q32 106 32 94V32L40 9L51 24Q61 21 71 23L84 11L88 32V94Q88 106 76 106Z" fill={FUR} stroke={INK} strokeWidth="2.8" strokeLinejoin="round" />
        <path d="M36 27l4-11 6 8.5zM76 22l7-6 1.6 10.5z" fill={PINK} />
        <path d="M55 26.5v5M60 25.5v6M65 26.5v5" stroke={STRIPE} strokeWidth="2.6" strokeLinecap="round" />
        <path d="M33 70l6 2M33 79l5 1M87 70l-6 2M87 79l-5 1" stroke={STRIPE} strokeWidth="2.6" strokeLinecap="round" />
        <path d="M47 104V84q0-9 13-9t13 9v20z" fill={BELLY} />
        <path d="M52 88v17M68 88v17" {...line} />
        {/* Whiskers reach past the face like in the sketch. */}
        <path d="M36 55.5l-12-2M36 60l-11 1.5M84 55.5l12-2M84 60l11 1.5" stroke={INK} strokeWidth="2.2" strokeLinecap="round" />
        <ellipse cx="40.5" cy="58.5" rx="4" ry="2.4" fill={PINK} opacity=".45" />
        <ellipse cx="79.5" cy="58.5" rx="4" ry="2.4" fill={PINK} opacity=".45" />
        {/* The nerd glasses: pale lenses behind the eyes, frames, bridge and temples on top. */}
        <rect x="37.5" y="37" width="20" height="16" rx="5" fill="rgba(255, 255, 255, .55)" />
        <rect x="62.5" y="37" width="20" height="16" rx="5" fill="rgba(255, 255, 255, .55)" />
        <Eyes mood={mood} />
        <g>
          <rect x="37.5" y="37" width="20" height="16" rx="5" fill="none" stroke={INK} strokeWidth="2.8" />
          <rect x="62.5" y="37" width="20" height="16" rx="5" fill="none" stroke={INK} strokeWidth="2.8" />
          <path d="M57.5 43q2.5-2.6 5 0M37.5 42l-5-1.5M82.5 42l5-1.5" {...line} strokeWidth={2.8} />
          <path d="M40.5 40.5l3.5-.2" stroke="#fff" strokeWidth="2" strokeLinecap="round" opacity=".9" />
          <path d="M65.5 40.5l3.5-.2" stroke="#fff" strokeWidth="2" strokeLinecap="round" opacity=".9" />
        </g>
        {mood === 'hint' && <path d="M64 31.5q8-5 17-1" {...line} />}
        <path d="M57.3 54.3h5.4L60 57.5z" fill={PINK} stroke={INK} strokeWidth="1.8" strokeLinejoin="round" />
        <Mouth mood={mood} />
        {/* Bow tie. */}
        <path d="M60 69.5L50 64v11zM60 69.5L70 64v11z" fill={TIE} stroke={INK} strokeWidth="2.4" strokeLinejoin="round" />
        <circle cx="60" cy="69.5" r="3" fill={TIE} stroke={INK} strokeWidth="2.2" />
        <Paws mood={mood} />
      </g>
      <Extras mood={mood} />
    </svg>
  );
}
