import type { ReactNode } from 'react';
import { Mascot, type Mood } from './Mascot';

/** A message from Kẹp: the mascot beside a white bubble. */
export function BotBubble({ who, mood = 'hello', children }: { who?: ReactNode; mood?: Mood; children: ReactNode }) {
  return (
    <div className="chat-row">
      <span className="chat-avatar" aria-hidden="true">
        <Mascot mood={mood} size={30} />
      </span>
      <div className="bubble bubble--bot">
        {who && <span className="bubble__who">{who}</span>}
        {children}
      </div>
    </div>
  );
}

/** A message from the learner, on the right. */
export function MyBubble({ children }: { children: ReactNode }) {
  return (
    <div className="chat-row chat-row--me">
      <div className="bubble bubble--me">{children}</div>
    </div>
  );
}

/** Kẹp is writing: bouncing dots, with what it is doing for screen readers and as a small caption. */
export function TypingBubble({ text = 'Kẹp đang soạn câu trả lời' }: { text?: string }) {
  return (
    <div className="chat-row" role="status">
      <span className="chat-avatar chat-avatar--busy" aria-hidden="true">
        <Mascot mood="think" size={30} />
      </span>
      <div className="bubble bubble--bot bubble--typing">
        <span className="typing__dots" aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
        <span className="bubble--typing__text">{text}</span>
      </div>
    </div>
  );
}
