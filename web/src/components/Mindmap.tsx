import type { Section } from '../api/types';

// Mindmap drawn from the lesson's saved key ideas (title + short text each):
// the lesson in the middle, ideas alternating left/right, curved links. No
// image model is needed; the AI only supplies the ideas as text.

const W = 960;
const NODE_W = 300;
const NODE_H = 118;
const GAP = 22;
const CENTER_W = 260;
const TONES = ['#e3edd4', '#fcf0b8', '#dfe8f5', '#f8dccf', '#e3edd4', '#fcf0b8'];

export function Mindmap({ title, ideas, fix = (t: string) => t }: { title: string; ideas: Section[]; fix?: (text: string) => string }) {
  const shown = ideas.slice(0, 6);
  const rows = Math.max(1, Math.ceil(shown.length / 2));
  const height = rows * NODE_H + (rows - 1) * GAP + 40;
  const cy = height / 2;
  const centerX = (W - CENTER_W) / 2;
  const nodes = shown.map((idea, i) => {
    const left = i % 2 === 0;
    const row = Math.floor(i / 2);
    const inRow = left ? Math.ceil(shown.length / 2) : Math.floor(shown.length / 2);
    const columnHeight = inRow * NODE_H + (inRow - 1) * GAP;
    const y = (height - columnHeight) / 2 + row * (NODE_H + GAP);
    const x = left ? 16 : W - NODE_W - 16;
    return { idea, i, left, x, y };
  });
  return (
    <svg className="mindmap" viewBox={`0 0 ${W} ${height}`} role="img" aria-label={`Sơ đồ ý chính: ${title}`}>
      {nodes.map(({ i, left, x, y }) => {
        const fromX = left ? centerX : centerX + CENTER_W;
        const toX = left ? x + NODE_W : x;
        const toY = y + NODE_H / 2;
        const bend = (fromX - toX) / 2;
        return <path key={`l${i}`} className="mindmap__link" d={`M${fromX} ${cy} C${fromX - bend} ${cy}, ${toX + bend} ${toY}, ${toX} ${toY}`} />;
      })}
      <g className="mindmap__center">
        <rect x={centerX} y={cy - 54} width={CENTER_W} height={108} rx={26} />
        <foreignObject x={centerX + 14} y={cy - 46} width={CENTER_W - 28} height={92}>
          <div className="mindmap__center-text">{fix(title)}</div>
        </foreignObject>
      </g>
      {nodes.map(({ idea, i, x, y }) => (
        <g key={`n${i}`} className="mindmap__node" style={{ animationDelay: `${120 + i * 70}ms` }}>
          <rect x={x} y={y} width={NODE_W} height={NODE_H} rx={20} fill={TONES[i]} />
          <foreignObject x={x + 14} y={y + 10} width={NODE_W - 28} height={NODE_H - 20}>
            <div className="mindmap__idea">
              <strong>
                {i + 1}. {fix(idea.title)}
              </strong>
              <span>{fix(idea.text)}</span>
            </div>
          </foreignObject>
        </g>
      ))}
    </svg>
  );
}
