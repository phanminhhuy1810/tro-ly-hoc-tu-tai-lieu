import type { CSSProperties, ReactNode } from 'react';
import { Mascot, type Coat, type Mood } from './Mascot';

// Byte's classmates hiding behind the Cộng đồng banner: drawn under it, so only
// heads and ears peek over its top edge or round its sides, each ducking on its
// own beat. Tap one and it pulls a face.
// `at` places a cat behind an edge; `turn` points its head out (0 = over the top,
// -90 = round the left edge, 90 = round the right); `duck` is where it hides.
// "Chaotic but orderly": cats are spaced evenly round the banner, while size,
// tilt, coat and face follow short repeating cycles of different lengths, so
// the row never looks copied yet never looks messy.
type Peeker = { at: CSSProperties; turn: number; duck: string; size: number; coat: Coat; mood: Mood; glasses: boolean };
const COATS: Coat[] = ['grey', 'ginger', 'cocoa'];
const MOODS: Mood[] = ['hello', 'smug', 'surprised', 'love', 'wink', 'happy', 'think', 'oops'];
const SIZES = [84, 100, 76, 92, 108];
const TILTS = [-7, 4, -3, 8, -5, 2];

function peekers(): Peeker[] {
  const cats: Peeker[] = [];
  const top = 9;
  for (let i = 0; i < top; i += 1) {
    const size = SIZES[i % SIZES.length];
    const coat = COATS[i % COATS.length];
    cats.push({ at: { left: `${2 + i * (88 / (top - 1))}%`, top: -Math.round(size * 0.58) }, turn: TILTS[i % TILTS.length], duck: '0px, 7px', size, coat, mood: MOODS[i % MOODS.length], glasses: coat === 'ginger' && i % 2 === 1 });
  }
  // Two round each side, mirrored, at a third and two thirds of the height.
  [
    ['left', 28, -90],
    ['left', 66, -84],
    ['right', 22, 90],
    ['right', 60, 96],
  ].forEach(([edge, at, turn], i) => {
    const size = SIZES[(i + 2) % SIZES.length];
    const coat = COATS[(i + 1) % COATS.length];
    cats.push({ at: { [edge as string]: -Math.round(size * 0.52), top: `calc(${at}% - ${size / 2}px)` }, turn: turn as number, duck: edge === 'left' ? '7px, 0px' : '-7px, 0px', size, coat, mood: MOODS[(i + 3) % MOODS.length], glasses: false });
  });
  return cats;
}

const PEEKERS = peekers();

export function CatPeek({ children }: { children: ReactNode }) {
  return (
    <div className="peek">
      <div className="peek__cats" aria-hidden="true">
        {PEEKERS.map((cat, i) => (
          <span key={i} className={Math.abs(cat.turn) > 45 ? 'peek__cat peek__cat--side' : 'peek__cat'} style={{ ...cat.at, '--peek-delay': `${-((i * 0.9) % 4)}s`, '--duck': cat.duck } as CSSProperties}>
            <span className="peek__turn" style={{ transform: `rotate(${cat.turn}deg)` }}>
              <Mascot mood={cat.mood} coat={cat.coat} glasses={cat.glasses} size={cat.size} pettable />
            </span>
          </span>
        ))}
      </div>
      {children}
    </div>
  );
}
