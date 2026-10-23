import type { CSSProperties, ReactNode } from 'react';
import { Mascot, type Coat, type Mood } from './Mascot';

// Byte's classmates hiding behind the Cộng đồng banner: drawn under it, so only
// heads peek over its top edge or round its sides. Calm and even: one size,
// upright, evenly spaced, the row mirrored round the middle cat, no idle bobbing;
// their sparkles and hearts only show when a cat is tapped. Point at a cat and it
// ducks behind the banner (`duck` is which way) until the pointer leaves.
type Peeker = { at: CSSProperties; turn: number; duck: string; coat: Coat; mood: Mood; glasses: boolean };
const SIZE = 88;
const SHOWN = Math.round(SIZE * 0.56);
const COATS: Coat[] = ['grey', 'cocoa', 'ginger', 'grey', 'ginger', 'cocoa', 'grey'];

function peekers(): Peeker[] {
  const cats: Peeker[] = COATS.map((coat, i) => ({
    at: { left: `calc(${8 + i * 14}% - ${SIZE / 2}px)`, top: -SHOWN },
    turn: 0,
    duck: '0px 26px',
    coat,
    mood: i % 2 ? 'smug' : 'happy',
    glasses: coat === 'ginger',
  }));
  // One round each side, level with each other halfway down.
  const middle = `calc(50% - ${SIZE / 2}px)`;
  cats.push({ at: { left: -SHOWN, top: middle }, turn: -90, duck: '26px 0px', coat: 'ginger', mood: 'love', glasses: false });
  cats.push({ at: { right: -SHOWN, top: middle }, turn: 90, duck: '-26px 0px', coat: 'ginger', mood: 'love', glasses: false });
  return cats;
}

const PEEKERS = peekers();

export function CatPeek({ children }: { children: ReactNode }) {
  return (
    <div className="peek">
      <div className="peek__cats" aria-hidden="true">
        {PEEKERS.map((cat, i) => (
          <span key={i} className={cat.turn ? 'peek__cat peek__cat--side' : 'peek__cat'} style={{ ...cat.at, '--duck': cat.duck } as CSSProperties}>
            <span className="peek__turn" style={cat.turn ? { transform: `rotate(${cat.turn}deg)` } : undefined}>
              <Mascot mood={cat.mood} coat={cat.coat} glasses={cat.glasses} size={SIZE} pettable />
            </span>
          </span>
        ))}
      </div>
      {children}
    </div>
  );
}
