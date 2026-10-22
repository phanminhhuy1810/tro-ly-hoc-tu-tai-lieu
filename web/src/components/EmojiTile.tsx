import type { CSSProperties } from 'react';
import { emojiOf, nameOf, type TileTone, type TopicIcon } from '../lib/topicIcons';

/** A subject icon on a soft pastel tile: course covers, lesson icons and the cover picker. */
export function EmojiTile({ icon, tone, size = 56, label = false }: { icon: TopicIcon; tone: TileTone; size?: number; label?: boolean }) {
  return (
    <span
      className={`emoji-tile emoji-tile--${tone}`}
      style={{ '--tile': `${size}px` } as CSSProperties}
      role={label ? 'img' : undefined}
      aria-label={label ? nameOf(icon) : undefined}
      aria-hidden={label ? undefined : true}
    >
      <span className="emoji-tile__glyph">{emojiOf(icon)}</span>
    </span>
  );
}
