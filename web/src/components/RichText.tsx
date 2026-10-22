import { Fragment, type ReactNode } from 'react';

// AI answers arrive as plain text with light Markdown habits (paragraphs,
// "- " bullets, "1." steps, **bold**, `code`). Render just those, as text
// nodes only: nothing is injected as HTML.

function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|`[^`\n]+`)/g).map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) return <code key={i}>{part.slice(1, -1)}</code>;
    return <Fragment key={i}>{part}</Fragment>;
  });
}

export function RichText({ text, fix = (t: string) => t, className }: { text: string; fix?: (text: string) => string; className?: string }) {
  const blocks: ReactNode[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  const flush = () => {
    if (!list) return;
    const items = list.items.map((item, i) => <li key={i}>{inline(fix(item))}</li>);
    blocks.push(list.ordered ? <ol key={blocks.length}>{items}</ol> : <ul key={blocks.length}>{items}</ul>);
    list = null;
  };
  for (const raw of text.split('\n')) {
    const line = raw.trim();
    const bullet = /^(?:[-*•]\s+)(.*)$/.exec(line);
    const step = /^\d+[.)]\s+(.*)$/.exec(line);
    if (bullet || step) {
      const ordered = Boolean(step);
      if (!list || list.ordered !== ordered) {
        flush();
        list = { ordered, items: [] };
      }
      list.items.push((bullet ?? step)![1]);
      continue;
    }
    flush();
    if (line) blocks.push(<p key={blocks.length}>{inline(fix(line.replace(/^#+\s*/, '')))}</p>);
  }
  flush();
  return <div className={className ? `rich ${className}` : 'rich'}>{blocks}</div>;
}
