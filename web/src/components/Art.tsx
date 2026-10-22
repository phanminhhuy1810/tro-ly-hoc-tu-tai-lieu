import type { CSSProperties } from 'react';
import type { TopicIcon } from '../lib/topicIcons';

// Pictures from Microsoft's Fluent Emoji 3D set (MIT, web/public/art), drawn
// once and reused everywhere: subject icons plus a few for the app itself.
export type ArtName = TopicIcon | 'fire' | 'memo' | 'sparkles' | 'glowing' | 'medal' | 'calendar' | 'coin' | 'party' | 'house' | 'hourglass';

export const artSrc = (name: ArtName) => `/art/${name === 'brain' ? 'psychology' : name}.webp`;

/** One 3D picture; decorative unless given a label. */
export function Art({ name, size = 48, label, className }: { name: ArtName; size?: number; label?: string; className?: string }) {
  return (
    <img
      className={className ? `art ${className}` : 'art'}
      src={artSrc(name)}
      width={size}
      height={size}
      alt={label ?? ''}
      aria-hidden={label ? undefined : true}
      draggable={false}
      loading="lazy"
      decoding="async"
    />
  );
}

/** A 3D picture on a white sticker disc (ink rim, hard shadow): page banners and empty states. */
export function ArtBadge({ name, size = 88 }: { name: ArtName; size?: number }) {
  return (
    <span className="art-badge" style={{ '--badge': `${size}px` } as CSSProperties} aria-hidden="true">
      <Art name={name} size={Math.round(size * 0.64)} />
    </span>
  );
}
