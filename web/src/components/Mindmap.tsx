import type { CSSProperties } from 'react';
import type { Section } from '../api/types';

// Mindmap drawn from the lesson's saved key ideas (title + short text each):
// the lesson in the middle, the ideas in two columns joined to it by a dotted
// spine (one column on phones). Plain HTML so text keeps its reading size and
// each card grows to fit; the AI only supplies the ideas as text.

const TONES = ['#e3edd4', '#fcf0b8', '#dfe8f5', '#f8dccf', '#ebe2fb', '#d9f1df'];

export function Mindmap({ title, ideas, fix = (t: string) => t }: { title: string; ideas: Section[]; fix?: (text: string) => string }) {
  const shown = ideas.slice(0, 6);
  return (
    <figure className="mindmap" aria-label={`Sơ đồ ý chính: ${title}`}>
      <div className="mindmap__center">{fix(title)}</div>
      <ol className="mindmap__ideas">
        {shown.map((idea, i) => (
          <li key={i} className="mindmap__idea" style={{ '--tone': TONES[i % TONES.length], '--i': i } as CSSProperties}>
            <strong>
              {i + 1}. {fix(idea.title)}
            </strong>
            <span>{fix(idea.text)}</span>
          </li>
        ))}
      </ol>
    </figure>
  );
}
