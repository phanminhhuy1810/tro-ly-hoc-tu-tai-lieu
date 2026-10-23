import type { CSSProperties, ReactNode } from 'react';
import { Mascot, type Coat, type Mood } from './Mascot';

// Byte's classmates hiding behind the Cộng đồng banner: drawn under it, so only
// heads and ears peek over its top edge, each ducking on its own beat. Tap one
// and it pulls a face.
const PEEKERS: { left: string; coat: Coat; mood: Mood; glasses?: boolean }[] = [
  { left: '5%', coat: 'grey', mood: 'hello' },
  { left: '18%', coat: 'cocoa', mood: 'happy' },
  { left: '31%', coat: 'ginger', mood: 'smug', glasses: true },
  { left: '47%', coat: 'grey', mood: 'surprised' },
  { left: '60%', coat: 'cocoa', mood: 'wink' },
  { left: '73%', coat: 'ginger', mood: 'love' },
];

export function CatPeek({ children }: { children: ReactNode }) {
  return (
    <div className="peek">
      <div className="peek__cats" aria-hidden="true">
        {PEEKERS.map((cat, i) => (
          <span key={i} className="peek__cat" style={{ left: cat.left, '--peek-delay': `${-i * 0.7}s` } as CSSProperties}>
            <Mascot mood={cat.mood} coat={cat.coat} glasses={cat.glasses ?? false} size={88} pettable />
          </span>
        ))}
      </div>
      {children}
    </div>
  );
}
