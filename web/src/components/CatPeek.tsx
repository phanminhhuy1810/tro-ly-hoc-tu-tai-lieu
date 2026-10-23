import type { CSSProperties, ReactNode } from 'react';
import { Mascot, type Coat, type Mood } from './Mascot';

// Byte's classmates hiding behind the Cộng đồng banner: drawn under it, so only
// heads and ears peek over its top edge or round its sides, each ducking on its
// own beat. Tap one and it pulls a face.
// `at` places a cat behind an edge; `turn` points its head out (0 = over the top,
// -90 = round the left edge, 90 = round the right); `duck` is where it hides.
const PEEKERS: { at: CSSProperties; turn?: number; duck: string; coat: Coat; mood: Mood; glasses?: boolean }[] = [
  { at: { left: '7%', top: -50 }, duck: '0px, 7px', coat: 'grey', mood: 'hello' },
  { at: { left: '29%', top: -50 }, duck: '0px, 7px', coat: 'ginger', mood: 'smug', glasses: true },
  { at: { left: '52%', top: -50 }, duck: '0px, 7px', coat: 'cocoa', mood: 'surprised' },
  { at: { left: -46, top: '38%' }, turn: -90, duck: '7px, 0px', coat: 'cocoa', mood: 'wink' },
  { at: { right: -46, top: '10%' }, turn: 90, duck: '-7px, 0px', coat: 'grey', mood: 'happy' },
  { at: { right: -46, bottom: '8%' }, turn: 90, duck: '-7px, 0px', coat: 'ginger', mood: 'love' },
];

export function CatPeek({ children }: { children: ReactNode }) {
  return (
    <div className="peek">
      <div className="peek__cats" aria-hidden="true">
        {PEEKERS.map((cat, i) => (
          <span key={i} className={cat.turn ? 'peek__cat peek__cat--side' : 'peek__cat'} style={{ ...cat.at, '--peek-delay': `${-i * 0.7}s`, '--duck': cat.duck } as CSSProperties}>
            <span className="peek__turn" style={{ transform: cat.turn ? `rotate(${cat.turn}deg)` : undefined }}>
              <Mascot mood={cat.mood} coat={cat.coat} glasses={cat.glasses ?? false} size={88} pettable />
            </span>
          </span>
        ))}
      </div>
      {children}
    </div>
  );
}
