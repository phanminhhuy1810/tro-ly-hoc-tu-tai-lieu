import type { CSSProperties } from 'react';
import { nameOf, type TileTone, type TopicIcon } from '../lib/topicIcons';
import { artSrc } from './Art';

/** A subject icon (3D picture) on a soft pastel tile: course covers, lesson icons and the cover picker. */
export function EmojiTile({ icon, tone, size = 56, label = false }: { icon: TopicIcon; tone: TileTone; size?: number; label?: boolean }) {
  return (
    <span
      className={`emoji-tile emoji-tile--${tone}`}
      style={{ '--tile': `${size}px` } as CSSProperties}
      role={label ? 'img' : undefined}
      aria-label={label ? nameOf(icon) : undefined}
      aria-hidden={label ? undefined : true}
    >
      <img className="emoji-tile__art" src={artSrc(icon)} alt="" draggable={false} decoding="async" />
    </span>
  );
}
