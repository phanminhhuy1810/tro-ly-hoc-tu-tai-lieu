// "Kẹp" — a soft ginger cat in thick black nerd glasses (flat on top, gently
// rounded below), after the sketch Huy picked: a round pear-shaped body,
// half-lidded "obviously" eyes, whiskers past the cheeks and a tail that grows
// from behind and curls up at the side. Ten expressions, ready-made scenes for
// the course path, and a little life: it blinks, swishes its tail, breathes,
// and reacts with a hop and a new face when tapped (where it is `pettable`).
// Page pictures are Kẹp scenes too (books, notepad, chart…), drawn here by
// hand rather than generated, so every page shares one look; MascotDuo adds a
// grey classmate for the pages about learning with others.

import { useId, useRef, useState, type CSSProperties } from 'react';

export type Mood = 'hello' | 'hint' | 'think' | 'happy' | 'oops' | 'wink' | 'love' | 'surprised' | 'sad' | 'smug';
/** Ready-made scenes: the cats along the course path, then the page pictures. */
export type Pose =
  | 'book'
  | 'mug'
  | 'laptop'
  | 'flag'
  | 'sleep'
  | 'books'
  | 'pencil'
  | 'chart'
  | 'gear'
  | 'target'
  | 'search'
  | 'wand'
  | 'box'
  | 'upload'
  | 'plane';
export const POSES: Pose[] = ['book', 'mug', 'laptop', 'flag', 'sleep'];
export const PAGE_POSES: Pose[] = ['books', 'pencil', 'chart', 'gear', 'target', 'search', 'wand', 'box', 'upload', 'plane'];

const INK = '#2b2f36';
const FRAME = '#14161a';
const FUR = '#ffd8ad';
const STRIPE = '#f3a660';
const BELLY = '#fff3e4';
const PINK = '#f6a7ba';
const METAL = '#c4ccd9';

/** Kẹp is ginger; the classmate in MascotDuo is grey. */
const COATS = {
  ginger: { fur: FUR, stripe: STRIPE, belly: BELLY },
  grey: { fur: '#dfe3ea', stripe: '#a3abbb', belly: '#f6f7fa' },
};
type Coat = keyof typeof COATS;

const BODY =
  'M60 105C46 105 32.5 105 28 99.5C24.4 94.6 24.2 87.5 24.6 80C25.4 64 27.2 50 29.6 37L31.4 15.6Q32 9.8 36.2 13.4L48 23.8Q60 19.2 72 23.8L83.8 13.4Q88 9.8 88.6 15.6L90.4 37C92.8 50 94.6 64 95.4 80C95.8 87.5 95.6 94.6 92 99.5C87.5 105 74 105 60 105Z';
// Lenses: a flat, square top and a gently rounded bottom, like classic nerd frames.
const LENSES = 'M33 37H56V49Q56 56 49 56H40Q33 56 33 49ZM64 37H87V49Q87 56 80 56H71Q64 56 64 49Z';
// The tail grows from behind the body: its root is hidden, it sweeps out to the left and curls up.
const TAIL = 'M46 100C30 106 14 102 11 89C9.6 81 12.4 74.6 18.5 72';
const line = { stroke: INK, fill: 'none', strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };

/** A limb or the tail: an outlined tube in fur colour with a round end. */
function Tube({ d, width = 8, fur = FUR }: { d: string; width?: number; fur?: string }) {
  return (
    <g>
      <path d={d} stroke={INK} strokeWidth={width + 4.4} fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <path d={d} stroke={fur} strokeWidth={width} fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </g>
  );
}

/** A paw resting on something the cat holds. */
function Paw({ x, y, fur }: { x: number; y: number; fur: string }) {
  return <circle cx={x} cy={y} r="4.6" fill={fur} stroke={INK} strokeWidth="2.2" />;
}

/** Points of a star or a cog: alternating outer and inner radii around a centre. */
function ring(cx: number, cy: number, outer: number, inner: number, points: number, spread = 0.5): string {
  const out: string[] = [];
  const step = (Math.PI * 2) / points;
  for (let i = 0; i < points; i += 1) {
    const a = i * step - Math.PI / 2;
    const corners: [number, number][] =
      spread === 0.5
        ? [
            [outer, a],
            [inner, a + step / 2],
          ]
        : [
            [inner, a - step / 2 + step * (0.5 - spread) * 0.5],
            [outer, a - step * spread * 0.35],
            [outer, a + step * spread * 0.35],
            [inner, a + step / 2 - step * (0.5 - spread) * 0.5],
          ];
    for (const [r, angle] of corners) out.push(`${(cx + r * Math.cos(angle)).toFixed(2)},${(cy + r * Math.sin(angle)).toFixed(2)}`);
  }
  return out.join(' ');
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
    case 'wink':
      return (
        <g>
          <path d="M38 45.5h13" {...line} strokeWidth={2.4} />
          <circle cx="44.5" cy="48.3" r="2.9" fill={INK} />
          <circle cx="45.4" cy="47.5" r=".8" fill="#fff" />
          <path d="M69.5 48.5q6-5.5 12 0" {...line} strokeWidth={2.4} />
        </g>
      );
    case 'love':
      return (
        <g fill="#ff6b8b" stroke={INK} strokeWidth="1.2" strokeLinejoin="round">
          <path d="M44.5 52l-4.6-4.6a2.7 2.7 0 0 1 4.6-3.4 2.7 2.7 0 0 1 4.6 3.4z" />
          <path d="M75.5 52l-4.6-4.6a2.7 2.7 0 0 1 4.6-3.4 2.7 2.7 0 0 1 4.6 3.4z" />
        </g>
      );
    case 'surprised':
      return (
        <g>
          <circle cx="44.5" cy="47" r="4.3" fill={INK} />
          <circle cx="75.5" cy="47" r="4.3" fill={INK} />
          <circle cx="45.9" cy="45.6" r="1.3" fill="#fff" />
          <circle cx="76.9" cy="45.6" r="1.3" fill="#fff" />
        </g>
      );
    case 'sad':
      return (
        <g>
          <path d="M38 46.5L51 44M69 44L82 46.5" {...line} strokeWidth={2.4} />
          <circle cx="44.5" cy="49.4" r="2.8" fill={INK} />
          <circle cx="75.5" cy="49.4" r="2.8" fill={INK} />
        </g>
      );
    case 'smug':
      // Half-lidded and looking sideways: the cheekiest face.
      return (
        <g>
          <path d="M38 45.5h13M69 45.5h13" {...line} strokeWidth={2.4} />
          <circle cx="48.2" cy="48.3" r="2.9" fill={INK} />
          <circle cx="79.2" cy="48.3" r="2.9" fill={INK} />
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
    case 'love':
      return <path d="M60 59.6v1.4M55.5 61.5q4.5 5.5 9 0" {...line} strokeWidth={1.9} />;
    case 'surprised':
      return <ellipse cx="60" cy="63.6" rx="2.4" ry="2.9" fill={INK} />;
    case 'sad':
      return <path d="M56 64.5q4-3.6 8 0" {...line} strokeWidth={1.9} />;
    case 'smug':
      return <path d="M60 59.6v1.4M56 62.4q2.6 1.2 4-.8q2.6 1.4 6.5-2.4" {...line} strokeWidth={1.9} />;
    default:
      return <path d="M60 59.6v1.4M56 61.6q2 2.2 4 0q2 2.2 4 0" {...line} strokeWidth={1.9} />;
  }
}

function Paws({ mood, fur }: { mood: Mood; fur: string }) {
  switch (mood) {
    case 'hello':
      return (
        <g className="mascot__wave">
          <Tube d="M90 78C97 75 100.5 68 100 60" fur={fur} />
        </g>
      );
    case 'hint':
      return <Tube d="M90 76C96 70 97.5 62 97 53" fur={fur} />;
    case 'happy':
      return (
        <g>
          <Tube d="M30 78C23 75 19.5 68 20 60" fur={fur} />
          <Tube d="M90 78C97 75 100.5 68 100 60" fur={fur} />
        </g>
      );
    case 'think':
      return <Tube d="M84 92C80 82 76 75 69 71.5" fur={fur} />;
    case 'surprised':
      return (
        <g>
          <Tube d="M31 80C25 76 23 70 24 64" fur={fur} />
          <Tube d="M89 80C95 76 97 70 96 64" fur={fur} />
        </g>
      );
    case 'wink':
      return (
        <g className="mascot__wave">
          <Tube d="M90 78C97 75 100.5 68 100 60" fur={fur} />
        </g>
      );
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
    case 'wink':
      return (
        <g className="mascot__extra" fill="#f7cf3c" stroke={INK} strokeWidth="1.5" strokeLinejoin="round">
          <path d="M98 30l1.6 3.9 3.9 1.6-3.9 1.6-1.6 3.9-1.6-3.9-3.9-1.6 3.9-1.6z" />
        </g>
      );
    case 'love':
      return (
        <g className="mascot__extra mascot__hearts" fill="#ff8fab" stroke={INK} strokeWidth="1.5" strokeLinejoin="round">
          <path d="M101 26l-5-5a3 3 0 0 1 5-3.6 3 3 0 0 1 5 3.6z" />
          <path d="M111 40l-3.6-3.6a2.2 2.2 0 0 1 3.6-2.6 2.2 2.2 0 0 1 3.6 2.6z" />
        </g>
      );
    case 'surprised':
      return (
        <g className="mascot__extra" stroke={INK} strokeLinecap="round">
          <path d="M99 13v11" strokeWidth="3.2" />
          <circle cx="99" cy="30" r="1.9" fill={INK} stroke="none" />
          <path d="M38 33q6.5-3.5 13 0M69 33q6.5-3.5 13 0" strokeWidth="2.2" fill="none" />
        </g>
      );
    case 'sad':
      return (
        <g className="mascot__extra mascot__tear">
          <path d="M84 56c2 3 3 4.8 3 6.2a3 3 0 0 1-6 0c0-1.4 1-3.2 3-6.2z" fill="#a9c1e3" stroke={INK} strokeWidth="1.5" />
        </g>
      );
    case 'smug':
      return (
        <g className="mascot__extra" stroke={INK} strokeWidth="2.2" strokeLinecap="round" fill="none">
          <path d="M68.5 33q7-4.5 14-1.5" />
        </g>
      );
    default:
      return null;
  }
}

// The raised right arm that holds up a wand, a magnifier, a wrench or a plane.
const RAISED = 'M90 76C96 70 97.5 62 97 53';

/** What the paws hold in each scene; drawn in front of the body. */
function PoseProps({ pose, fur = FUR }: { pose: Pose; fur?: string }) {
  switch (pose) {
    case 'book':
      return (
        <g>
          <path d="M35 80Q48 75.5 60 81.5Q72 75.5 85 80V98.5Q72 94 60 100Q48 94 35 98.5Z" fill="#7fa7ff" stroke={INK} strokeWidth="2.2" strokeLinejoin="round" />
          <path d="M38 79Q49 75 60 80V96.5Q49 92 38 95.5ZM60 80Q71 75 82 79V95.5Q71 92 60 96.5Z" fill="#fff" stroke={INK} strokeWidth="2.2" strokeLinejoin="round" />
          <path d="M43 82.5q6-2 13 .5M43 87q6-2 13 .5M64 83q6-2.5 13-.5M64 87.5q6-2.5 13-.5" stroke="#b9bfca" strokeWidth="1.6" strokeLinecap="round" fill="none" />
          <circle cx="36.5" cy="88" r="4.6" fill={FUR} stroke={INK} strokeWidth="2.2" />
          <circle cx="83.5" cy="88" r="4.6" fill={FUR} stroke={INK} strokeWidth="2.2" />
        </g>
      );
    case 'mug':
      return (
        <g>
          <path d="M55 70q-2-3 0-6t0-6M62 70q-2-3 0-6t0-6" stroke="#b9bfca" strokeWidth="2" strokeLinecap="round" fill="none" className="mascot__steam" />
          <path d="M70 80.5q8 0 8 6.5t-8 6.5" stroke={INK} strokeWidth="2.4" fill="none" strokeLinecap="round" />
          <path d="M48 76h22v15.5q0 6-6 6H54q-6 0-6-6Z" fill="#fff4c9" stroke={INK} strokeWidth="2.4" strokeLinejoin="round" />
          <path d="M53 84.5h12" stroke="#f3a660" strokeWidth="2.4" strokeLinecap="round" />
          <circle cx="47" cy="88" r="4.6" fill={FUR} stroke={INK} strokeWidth="2.2" />
          <circle cx="71" cy="90.5" r="4.6" fill={FUR} stroke={INK} strokeWidth="2.2" />
        </g>
      );
    case 'laptop':
      return (
        <g>
          <path d="M38 74.5h44q2.5 0 2.5 2.5V96H35.5V77q0-2.5 2.5-2.5Z" fill="#dfe5ef" stroke={INK} strokeWidth="2.4" strokeLinejoin="round" />
          <path d="M31 96h58q0 5-5 5H36q-5 0-5-5Z" fill="#c4ccd9" stroke={INK} strokeWidth="2.4" strokeLinejoin="round" />
          <path d="M60 81.5l1.8 3.7 4 .6-2.9 2.8.7 4-3.6-1.9-3.6 1.9.7-4-2.9-2.8 4-.6Z" fill="#f7dd72" stroke={INK} strokeWidth="1.4" strokeLinejoin="round" />
          <circle cx="40" cy="96" r="4.6" fill={FUR} stroke={INK} strokeWidth="2.2" />
          <circle cx="80" cy="96" r="4.6" fill={FUR} stroke={INK} strokeWidth="2.2" />
        </g>
      );
    case 'flag':
      return (
        <g>
          <path d="M97 54V18" stroke={INK} strokeWidth="2.6" strokeLinecap="round" />
          <path d="M97.5 19L114 25L97.5 31Z" fill="#ff8f7a" stroke={INK} strokeWidth="2.2" strokeLinejoin="round" className="mascot__flag" />
          <Tube d={RAISED} fur={fur} />
        </g>
      );
    case 'books':
      return (
        <g>
          <g transform="rotate(2.5 60 76)">
            <rect x="40" y="70.5" width="40" height="10" rx="2.5" fill="#92b06c" stroke={INK} strokeWidth="2.2" />
            <path d="M46 70.5v10M74 70.5v10" stroke={INK} strokeWidth="1.6" />
          </g>
          <g transform="rotate(-3 60 86)">
            <rect x="36" y="80.5" width="47" height="11" rx="2.5" fill="#ff8f7a" stroke={INK} strokeWidth="2.2" />
            <path d="M42 86h15" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" />
          </g>
          <rect x="33" y="91.5" width="54" height="11.5" rx="2.5" fill="#7fa7ff" stroke={INK} strokeWidth="2.2" />
          <path d="M39.5 97.2h24M74 94v6.5" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" />
          <Paw x={34.5} y={87} fur={fur} />
          <Paw x={85.5} y={87} fur={fur} />
        </g>
      );
    case 'pencil':
      return (
        <g>
          <g transform="rotate(-5 58 88)">
            <rect x="39" y="73" width="38" height="31" rx="3.5" fill="#fffdf3" stroke={INK} strokeWidth="2.2" />
            <rect x="39" y="73" width="38" height="7" rx="3" fill="#f7dd72" stroke={INK} strokeWidth="2.2" />
            <path d="M45 87h20M45 92.5h24M45 98h14" stroke="#b9bfca" strokeWidth="1.8" strokeLinecap="round" />
          </g>
          <g transform="translate(90 60) rotate(118)">
            <path d="M0 0h6v7H0z" fill={PINK} stroke={INK} strokeWidth="1.8" strokeLinejoin="round" />
            <path d="M6 0h3.5v7H6z" fill={METAL} stroke={INK} strokeWidth="1.8" />
            <path d="M9.5 0h17v7h-17z" fill="#f7cf3c" stroke={INK} strokeWidth="1.8" />
            <path d="M26.5 0l7.5 3.5-7.5 3.5z" fill="#ffe2b8" stroke={INK} strokeWidth="1.8" strokeLinejoin="round" />
            <path d="M31.4 2.3l2.6 1.2-2.6 1.2z" fill={INK} />
          </g>
          <Paw x={41} y={94} fur={fur} />
          <Paw x={79} y={73.5} fur={fur} />
        </g>
      );
    case 'chart':
      return (
        <g>
          <rect x="37" y="71" width="46" height="32" rx="4.5" fill="#fff" stroke={INK} strokeWidth="2.4" />
          <path d="M43.5 97h33" stroke={INK} strokeWidth="2" strokeLinecap="round" />
          <rect x="45.5" y="87" width="7" height="10" rx="1.5" fill="#92b06c" stroke={INK} strokeWidth="1.8" />
          <rect x="56.5" y="82" width="7" height="15" rx="1.5" fill="#f7dd72" stroke={INK} strokeWidth="1.8" />
          <rect x="67.5" y="76" width="7" height="21" rx="1.5" fill="#ff8f7a" stroke={INK} strokeWidth="1.8" />
          <Paw x={37.5} y={88} fur={fur} />
          <Paw x={82.5} y={88} fur={fur} />
        </g>
      );
    case 'gear':
      return (
        <g>
          <g className="mascot__gear">
            <polygon points={ring(17, 31, 13, 9.4, 8, 0.32)} fill={METAL} stroke={INK} strokeWidth="2.2" strokeLinejoin="round" />
            <circle cx="17" cy="31" r="3.6" fill="#fff" stroke={INK} strokeWidth="2" />
          </g>
          <g transform="translate(97 61) rotate(14)">
            <path d="M0 0V-21" stroke={INK} strokeWidth="7.4" strokeLinecap="round" />
            <path d="M0 0V-21" stroke={METAL} strokeWidth="3.2" strokeLinecap="round" />
            <path d="M-3.2-19.5L-7.5-23.5V-32L-3.2-36.5V-30.5H3.2V-36.5L7.5-32V-23.5L3.2-19.5Z" fill={METAL} stroke={INK} strokeWidth="2.2" strokeLinejoin="round" />
          </g>
          <Tube d={RAISED} fur={fur} />
        </g>
      );
    case 'target':
      return (
        <g>
          <circle cx="60" cy="87" r="16.5" fill="#fff" stroke={INK} strokeWidth="2.4" />
          <circle cx="60" cy="87" r="11" fill="#ff8f7a" stroke={INK} strokeWidth="2" />
          <circle cx="60" cy="87" r="5.6" fill="#fff" stroke={INK} strokeWidth="2" />
          <circle cx="60" cy="87" r="2.1" fill="#ff8f7a" />
          <path d="M61 86L77.5 71.5" stroke={INK} strokeWidth="2.4" strokeLinecap="round" />
          <path d="M77.5 71.5l7.5-1.8-2 7.4zM76 70l2-6.8 4.2 4.8" fill="#7fa7ff" stroke={INK} strokeWidth="1.6" strokeLinejoin="round" />
          <Paw x={43.5} y={92} fur={fur} />
          <Paw x={76.5} y={93} fur={fur} />
        </g>
      );
    case 'search':
      return (
        <g>
          <path d="M96.5 48.5L94 58" stroke={INK} strokeWidth="5.4" strokeLinecap="round" />
          <circle cx="99" cy="37" r="11" fill="#dff1ff" fillOpacity=".8" stroke={INK} strokeWidth="3.4" />
          <path d="M92.6 34.5a7 7 0 0 1 5-5.4" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" fill="none" />
          <Tube d={RAISED} fur={fur} />
        </g>
      );
    case 'wand':
      return (
        <g>
          <path d="M96 57L102.5 33" stroke={INK} strokeWidth="3.8" strokeLinecap="round" />
          <polygon points={ring(104, 25, 11, 4.8, 5)} fill="#f7cf3c" stroke={INK} strokeWidth="2.2" strokeLinejoin="round" />
          <g className="mascot__twinkle" fill="#fff" stroke={INK} strokeWidth="1.5" strokeLinejoin="round">
            <polygon points={ring(85, 17, 4.6, 1.6, 4)} />
            <polygon points={ring(114, 44, 3.6, 1.3, 4)} />
          </g>
          <Tube d={RAISED} fur={fur} />
        </g>
      );
    case 'box':
      return (
        <g>
          <path d="M26 80L14.5 70.5L36 71.5L41 80Z" fill="#e9c08a" stroke={INK} strokeWidth="2.2" strokeLinejoin="round" />
          <path d="M94 80L105.5 70.5L84 71.5L79 80Z" fill="#e9c08a" stroke={INK} strokeWidth="2.2" strokeLinejoin="round" />
          <rect x="24.5" y="79" width="71" height="29" rx="2.5" fill="#d9a466" stroke={INK} strokeWidth="2.4" />
          <path d="M53 79v11.5h14V79" fill="#f3d9a8" stroke={INK} strokeWidth="2" strokeLinejoin="round" />
          <Paw x={43} y={80} fur={fur} />
          <Paw x={77} y={80} fur={fur} />
        </g>
      );
    case 'upload':
      return (
        <g>
          <path d="M41 70h24l11 11v24H41Z" fill="#fff" stroke={INK} strokeWidth="2.4" strokeLinejoin="round" />
          <path d="M65 70v11h11" fill="#e8ecf3" stroke={INK} strokeWidth="2.2" strokeLinejoin="round" />
          <path d="M47 88h20M47 93.5h23M47 99h13" stroke="#b9bfca" strokeWidth="1.8" strokeLinecap="round" />
          <circle cx="80" cy="69" r="8.5" fill="#92b06c" stroke={INK} strokeWidth="2.2" />
          <path d="M80 73.5v-9M76.2 68l3.8-3.8 3.8 3.8" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" fill="none" />
          <Paw x={42} y={91} fur={fur} />
          <Paw x={76} y={97} fur={fur} />
        </g>
      );
    case 'plane':
      return (
        <g>
          <path d="M80 30h-7M82 37h-9" stroke="#b9bfca" strokeWidth="2.2" strokeLinecap="round" />
          <g className="mascot__glide">
            <path d="M85 35L117 21L98 45Z" fill="#fff" stroke={INK} strokeWidth="2.2" strokeLinejoin="round" />
            <path d="M98 45L117 21L102 51Z" fill="#dfe5ef" stroke={INK} strokeWidth="2.2" strokeLinejoin="round" />
          </g>
          <Tube d={RAISED} fur={fur} />
        </g>
      );
    default:
      return null;
  }
}

/** The cat itself (no shadow or signs), shared with the logo. */
export function CatDrawing({ mood = 'hello', pose, coat = 'ginger', glasses = true }: { mood?: Mood; pose?: Pose; coat?: Coat; glasses?: boolean }) {
  const { fur, stripe, belly } = COATS[coat];
  return (
    <g className="mascot__breath">
      <g className="mascot__tail">
        <Tube d={TAIL} width={10} fur={fur} />
        <path d="M6.6 85.4l9.6-.2M8.8 94.6l8.6-3.4" stroke={stripe} strokeWidth="2.4" strokeLinecap="round" />
      </g>
      <path d={BODY} fill={fur} stroke={INK} strokeWidth="2.4" strokeLinejoin="round" />
      <path d="M34.1 18.5L36.4 15.9L44.6 23.2L35 27.6ZM85.9 18.5L83.6 15.9L75.4 23.2L85 27.6Z" fill={PINK} opacity=".9" />
      <path d="M54.5 26.5v4.5M60 25.5v5.5M65.5 26.5v4.5M26.5 70h5M26 77h4.5M93.5 70h-5M94 77h-4.5" stroke={stripe} strokeWidth="2.4" strokeLinecap="round" />
      <ellipse cx="60" cy="88" rx="17" ry="14" fill={belly} />
      <path d="M51.5 92v12.5M68.5 92v12.5" stroke={INK} strokeWidth="2.2" strokeLinecap="round" />
      <path d="M30 58.5l-12-1.6M30 62.5l-11 1.8M90 58.5l12-1.6M90 62.5l11 1.8" stroke={INK} strokeWidth="1.8" strokeLinecap="round" />
      <ellipse cx="36.5" cy="61.5" rx="4.2" ry="2.6" fill={PINK} opacity=".55" />
      <ellipse cx="83.5" cy="61.5" rx="4.2" ry="2.6" fill={PINK} opacity=".55" />
      {/* Thick black glasses: pale lenses behind the eyes, frames on top. */}
      {glasses && <path d={LENSES} fill="#fff" fillOpacity=".6" />}
      {pose === 'sleep' ? (
        <path d="M38.5 47q6 4.5 12 0M69.5 47q6 4.5 12 0" {...line} strokeWidth={2.4} />
      ) : (
        <g className="mascot__eyes">
          <Eyes mood={mood} />
        </g>
      )}
      {glasses && (
        <g>
          <path d={LENSES} fill="none" stroke={FRAME} strokeWidth="3.6" strokeLinejoin="round" />
          <path d="M56 39.5h8M33 39.5l-4.5-1.4M87 39.5l4.5-1.4" stroke={FRAME} strokeWidth="3.4" fill="none" strokeLinecap="round" />
          <path d="M36.8 41.2l3.4-.1M67.8 41.2l3.4-.1" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" />
        </g>
      )}
      <path d="M57.6 57.4h4.8l-2.4 2.9z" fill={PINK} stroke={INK} strokeWidth="1.5" strokeLinejoin="round" />
      <Mouth mood={pose === 'sleep' ? 'think' : mood} />
      {pose ? <PoseProps pose={pose} fur={fur} /> : <Paws mood={mood} fur={fur} />}
    </g>
  );
}

const REACTIONS: Mood[] = ['love', 'wink', 'surprised', 'happy', 'smug'];

/**
 * `face` crops to the head for small round avatars; `pose` picks a ready-made
 * scene for the path; `pettable` lets a tap make the cat hop and pull a face.
 */
export function Mascot({
  mood = 'hello',
  size = 96,
  bob = false,
  face = false,
  pose,
  pettable = false,
  title,
}: {
  mood?: Mood;
  size?: number;
  bob?: boolean;
  face?: boolean;
  pose?: Pose;
  pettable?: boolean;
  title?: string;
}) {
  const id = useId();
  const [reaction, setReaction] = useState<{ mood: Mood; n: number } | null>(null);
  const taps = useRef(0);
  const timer = useRef<number>(undefined);
  // Each cat blinks and swishes on its own beat.
  let h = 0;
  for (const ch of id) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  const style = { '--mascot-delay': `-${(h % 37) / 10}s` } as CSSProperties;

  const pet = () => {
    const n = taps.current++;
    setReaction({ mood: REACTIONS[n % REACTIONS.length], n });
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setReaction(null), 1600);
  };
  const shown = reaction?.mood ?? mood;
  const classes = ['mascot', `mascot--${shown}`, bob && 'mascot--bob', pettable && 'is-pettable', reaction && (reaction.n % 2 ? 'is-petted-b' : 'is-petted-a')];
  return (
    <svg
      className={classes.filter(Boolean).join(' ')}
      style={style}
      width={size}
      height={size}
      viewBox={face ? '17 6 86 86' : '0 0 120 120'}
      role={title ? 'img' : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
      onClick={pettable ? pet : undefined}
    >
      {!face && <ellipse cx="60" cy="111" rx="30" ry="3.6" fill="rgba(35,38,43,.1)" />}
      <g className="mascot__body">
        <CatDrawing mood={shown} pose={reaction ? undefined : pose} />
      </g>
      {pose === 'sleep' && !reaction ? (
        <g className="mascot__extra mascot__zzz" fill="none" stroke={INK} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M94 26h7l-7 8h7M104 13h9l-9 10h9" />
        </g>
      ) : (
        (!pose || reaction) && <Extras mood={shown} />
      )}
    </svg>
  );
}

/**
 * Kẹp and a grey classmate (no glasses) high-fiving: the picture for the pages
 * about learning with others. Both blink and breathe, each on its own beat.
 */
export function MascotDuo({ size = 104, title }: { size?: number; title?: string }) {
  return (
    <svg
      className="mascot mascot--duo"
      width={Math.round((size * 196) / 120)}
      height={size}
      viewBox="0 0 196 120"
      role={title ? 'img' : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
    >
      <ellipse cx="98" cy="111" rx="76" ry="3.6" fill="rgba(35,38,43,.1)" />
      {/* Each cat in its own viewport, so its blink/tail/breath pivots stay its own. */}
      <svg x="76" y="3" width="115" height="115" viewBox="0 0 120 120" overflow="visible" style={{ '--mascot-delay': '-1.7s' } as CSSProperties}>
        <CatDrawing mood="happy" coat="grey" glasses={false} />
      </svg>
      <svg x="0" y="0" width="120" height="120" viewBox="0 0 120 120" overflow="visible">
        <CatDrawing mood="hello" />
      </svg>
    </svg>
  );
}
