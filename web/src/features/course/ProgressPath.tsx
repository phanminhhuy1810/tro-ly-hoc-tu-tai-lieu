import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Icon } from '../../components/Icon';
import { Mascot, type Pose } from '../../components/Mascot';
import { chapterGroups, type PathNode } from '../../lib/path';

// Duolingo-style path. Each chapter has its own bright colour and a sticky
// banner with a "Mục tiêu" guide (like Duolingo's Guidebook). Lessons are round
// 3D pebbles with a plain white sign (star to learn, tick when done, lock
// ahead); a speech bubble and Byte mark the lesson to do next. Each chapter also
// has a flashcard stop halfway and a trophy for chapter review at the end. Cats
// sit beside every third stop, locked stretches included (they nap or wait in a
// box there), so even a fresh course has company. A floating button brings you
// back to the current lesson. Titles live in the popover, the guide and the table
// of contents.

const OFFSETS = [0, -58, -88, -58, 0, 58, 88, 58];
const THEMES = ['green', 'blue', 'orange', 'purple'] as const;
const AWAKE: Pose[] = ['book', 'mug', 'laptop', 'flag', 'pencil', 'target'];
const WAITING: Pose[] = ['sleep', 'box', 'sleep', 'book'];

type Glyph = 'star' | 'check' | 'lock' | 'sparkle' | 'cards' | 'trophy';

/** Plain white signs drawn for the pebbles (currentColor, so locked ones turn grey). */
function NodeGlyph({ kind, size = 34 }: { kind: Glyph; size?: number }) {
  return (
    <svg className="path-glyph" width={size} height={size} viewBox="0 0 40 40" aria-hidden="true">
      {kind === 'star' && <path d="M20 4.5l4.6 9.6 10.5 1.4-7.7 7.3 1.9 10.4L20 28.2l-9.3 5 1.9-10.4-7.7-7.3 10.5-1.4z" fill="currentColor" stroke="currentColor" strokeWidth="2.5" strokeLinejoin="round" />}
      {kind === 'check' && <path d="M8.5 21l7.5 7.5L32 12.5" fill="none" stroke="currentColor" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" />}
      {kind === 'lock' && (
        <g fill="currentColor">
          <path d="M13 17v-4a7 7 0 0 1 14 0v4" fill="none" stroke="currentColor" strokeWidth="4.5" strokeLinecap="round" />
          <rect x="8.5" y="16" width="23" height="18" rx="5" />
        </g>
      )}
      {kind === 'sparkle' && <path d="M20 4l4.2 11.8L36 20l-11.8 4.2L20 36l-4.2-11.8L4 20l11.8-4.2z" fill="currentColor" strokeLinejoin="round" />}
      {kind === 'cards' && (
        <g fill="currentColor">
          <rect x="6" y="11" width="20" height="24" rx="4" transform="rotate(-10 16 23)" opacity=".7" />
          <rect x="14" y="7" width="20" height="25" rx="4" transform="rotate(8 24 19.5)" />
        </g>
      )}
      {kind === 'trophy' && (
        <g fill="currentColor">
          <path d="M11 6h18v8a9 9 0 0 1-18 0z" />
          <path d="M11 9H6.5q0 7 6 7.5M29 9h4.5q0 7-6 7.5" fill="none" stroke="currentColor" strokeWidth="3.2" strokeLinecap="round" />
          <path d="M17.5 22.5h5v5h-5zM12 34q0-5 8-5t8 5z" />
        </g>
      )}
    </svg>
  );
}

function glyphFor(node: PathNode, generating: boolean): Glyph {
  if (generating || node.state === 'not_generated') return 'sparkle';
  if (node.state === 'done') return 'check';
  if (node.state === 'locked') return 'lock';
  return 'star';
}

function meta(node: PathNode): string {
  if (node.state === 'done') return 'Đã xong · mở để ôn lại';
  if (node.state === 'locked') return 'Mở sau khi luyện xong bài trước — không cần điểm tối thiểu';
  if (node.state === 'not_generated') return 'Chưa tạo nội dung — AI đọc nguồn của bài rồi soạn giải thích và câu hỏi';
  return `${node.unit.data?.sections.length ?? 0} phần · ${node.unit.data?.questions.length ?? 0} câu luyện tập`;
}

function Ring({ fraction }: { fraction: number }) {
  const r = 52;
  const length = 2 * Math.PI * r;
  return (
    <svg className="path-node__ring" viewBox="0 0 120 120" aria-hidden="true">
      <circle cx="60" cy="60" r={r} className="path-node__ring-track" />
      <circle cx="60" cy="60" r={r} className="path-node__ring-fill" strokeDasharray={`${length * fraction} ${length}`} />
    </svg>
  );
}

function Popover({
  node,
  onOpen,
  onGenerate,
  onReview,
  onClose,
  onCurrent,
  onOpenAll,
}: {
  node: PathNode;
  onOpen: () => void;
  onGenerate: () => void;
  onReview: () => void;
  onClose: () => void;
  onCurrent: () => void;
  onOpenAll?: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && onClose();
    const onDown = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node) && !(event.target as Element).closest?.('.path-node')) onClose();
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('mousedown', onDown);
    ref.current?.querySelector<HTMLElement>('button, a')?.focus();
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('mousedown', onDown);
    };
  }, [onClose]);
  return (
    <div className={`path-pop path-pop--${node.state}`} ref={ref} role="dialog" aria-label={`Bài ${node.index + 1}: ${node.unit.title}`}>
      <p className="eyebrow">Bài {node.index + 1}</p>
      <p className="path-pop__title">{node.unit.title}</p>
      {node.unit.objective && node.state !== 'locked' && <p className="path-pop__objective">{node.unit.objective}</p>}
      <p className="meta">{meta(node)}</p>
      {node.state === 'ready' && (
        <button type="button" className="btn btn--primary btn--block" onClick={onOpen}>
          {node.isCurrent ? 'Học bài này' : 'Mở bài'} <Icon name="arrowRight" size={18} />
        </button>
      )}
      {node.state === 'done' && (
        <div className="path-pop__row">
          <button type="button" className="btn btn--secondary btn--block" onClick={onOpen}>
            Ôn lại bài
          </button>
          <button type="button" className="btn btn--ghost" onClick={onReview}>
            Câu sai
          </button>
        </div>
      )}
      {node.state === 'not_generated' && (
        <button type="button" className="btn btn--primary btn--block" onClick={onGenerate}>
          <Icon name="sparkle" size={18} /> Tạo bài này
        </button>
      )}
      {node.state === 'locked' && (
        <div className="path-pop__row path-pop__row--stack">
          <button type="button" className="btn btn--secondary btn--block" onClick={onCurrent}>
            Tới bài đang học
          </button>
          {onOpenAll && (
            <button type="button" className="btn btn--ghost btn--block" onClick={onOpenAll}>
              <Icon name="unlock" size={16} /> Mở mọi bài để học tự do
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/** The chapter's "guidebook": every lesson with its goal; picking one opens it on the path. */
function Guide({ nodes, onPick, onClose }: { nodes: PathNode[]; onPick: (node: PathNode) => void; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && onClose();
    const onDown = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node) && !(event.target as Element).closest?.('.path-banner__guide')) onClose();
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('mousedown', onDown);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('mousedown', onDown);
    };
  }, [onClose]);
  return (
    <div className="path-guide enter" ref={ref} role="dialog" aria-label="Mục tiêu của chương">
      <ol>
        {nodes.map((node) => (
          <li key={node.unit.id}>
            <button type="button" className={`path-guide__item is-${node.state}`} onClick={() => onPick(node)}>
              <span className="path-guide__mark" aria-hidden="true">
                <NodeGlyph kind={glyphFor(node, false)} size={16} />
              </span>
              <span>
                <strong>
                  Bài {node.index + 1}. {node.unit.title}
                </strong>
                {node.unit.objective && <span className="meta">{node.unit.objective}</span>}
              </span>
            </button>
          </li>
        ))}
      </ol>
    </div>
  );
}

type Step = { kind: 'lesson'; node: PathNode } | { kind: 'cards' } | { kind: 'trophy' };

/** A chapter's stops: its lessons, a flashcard stop after the middle one (3+ lessons), and the trophy at the end. */
function chapterSteps(nodes: PathNode[]): Step[] {
  const steps: Step[] = [];
  const middle = nodes.length >= 3 ? Math.ceil(nodes.length / 2) - 1 : -1;
  nodes.forEach((node, i) => {
    steps.push({ kind: 'lesson', node });
    if (i === middle) steps.push({ kind: 'cards' });
  });
  steps.push({ kind: 'trophy' });
  return steps;
}

/**
 * A cat beside every third stop of the whole path, but not at or next to the
 * current lesson, where Byte already stands. Ahead of the learner (locked
 * lessons, stops not open yet) they nap or wait; elsewhere they read, sip,
 * type… Poses follow the course title, so reopening a course looks the same.
 */
function catAt(stop: number, current: number, ahead: boolean, seed: number): Pose | null {
  if (stop % 3 !== 2 || Math.abs(stop - current) <= 1) return null;
  const pool = ahead ? WAITING : AWAKE;
  return pool[(seed + stop) % pool.length];
}

export function ProgressPath({
  nodes,
  courseTitle,
  generatingUnitId,
  readFraction,
  reviewable,
  cardCount,
  justUnlocked,
  selected,
  onSelect,
  onOpen,
  onGenerate,
  onReview,
  onCards,
  onPractice,
  onOpenAll,
}: {
  nodes: PathNode[];
  courseTitle: string;
  generatingUnitId?: string | null;
  /** Share of the current lesson already read on this device (0–1). */
  readFraction: (node: PathNode) => number;
  reviewable: boolean;
  cardCount: number;
  justUnlocked?: string | null;
  selected: string | null;
  onSelect: (unitId: string | null) => void;
  onOpen: (node: PathNode) => void;
  onGenerate: (node: PathNode) => void;
  onReview: (node: PathNode | null) => void;
  onCards: () => void;
  onPractice: () => void;
  /** Creator of a course that opens lessons one by one: switch to opening them all. */
  onOpenAll?: () => void;
}) {
  const groups = useMemo(() => chapterGroups(nodes), [nodes]);
  const chapters = useMemo(() => groups.map((group) => chapterSteps(group.nodes)), [groups]);
  const currentStop = chapters.flat().findIndex((item) => item.kind === 'lesson' && item.node.isCurrent);
  let seed = 0;
  for (const ch of courseTitle) seed = (seed * 31 + ch.codePointAt(0)!) >>> 0;
  const [guide, setGuide] = useState<number | null>(null);
  const [away, setAway] = useState<'up' | 'down' | null>(null);
  const current = useRef<HTMLButtonElement | null>(null);

  // Show the "back to your lesson" button while the current lesson is off screen.
  const watch = useCallback((el: HTMLButtonElement | null) => {
    current.current = el;
  }, []);
  useEffect(() => {
    const el = current.current;
    if (!el || typeof IntersectionObserver === 'undefined') return;
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) setAway(null);
      else setAway(entry.boundingClientRect.top < 0 ? 'up' : 'down');
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [nodes]);

  let step = 0;
  return (
    <div className="path">
      {groups.map((group, g) => {
        const theme = THEMES[g % THEMES.length];
        const done = group.nodes.filter((n) => n.state === 'done').length;
        const steps = chapters[g];
        return (
          <section key={g} className={`path-chapter path-chapter--${theme}`} aria-label={group.title || courseTitle}>
            <header className="path-banner">
              <div>
                <p className="path-banner__eyebrow">
                  {groups.length > 1 ? `Chương ${g + 1}` : 'Lộ trình'} · {done}/{group.nodes.length} bài
                </p>
                <h3 className="path-banner__title">{group.title || courseTitle}</h3>
              </div>
              <button type="button" className="path-banner__guide" aria-expanded={guide === g} onClick={() => setGuide(guide === g ? null : g)}>
                <Icon name="bookOpen" size={18} /> Mục tiêu
              </button>
              {guide === g && (
                <Guide
                  nodes={group.nodes}
                  onClose={() => setGuide(null)}
                  onPick={(node) => {
                    setGuide(null);
                    onSelect(node.unit.id);
                    document.getElementById(`path-${node.unit.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
                  }}
                />
              )}
            </header>
            <ol className="path-track">
              {steps.map((item) => {
                const offset = OFFSETS[step % OFFSETS.length];
                const side = offset > 0 ? 'left' : 'right';
                const stop = step;
                step += 1;
                if (item.kind !== 'lesson') {
                  const open = item.kind === 'cards' ? cardCount > 0 : done > 0;
                  const label = item.kind === 'cards' ? 'Ôn thẻ của chương' : 'Ôn tập chương';
                  const pose = catAt(stop, currentStop, !open, seed);
                  return (
                    <li key={`${item.kind}-${g}`} className="path-step path-step--special" style={{ transform: `translateX(${offset}px)` }}>
                      <button
                        type="button"
                        className={`path-special path-special--${item.kind}${open ? '' : ' is-locked'}`}
                        disabled={!open}
                        onClick={item.kind === 'cards' ? onCards : onPractice}
                        aria-label={open ? label : `${label} — mở sau khi học xong một bài`}
                        title={label}
                      >
                        <NodeGlyph kind={open ? item.kind : 'lock'} />
                      </button>
                      <span className="path-special__label">{item.kind === 'cards' ? 'Ôn thẻ' : 'Ôn chương'}</span>
                      {pose && (
                        <span className={`path-cat path-cat--${side}`} aria-hidden="true">
                          <Mascot pose={pose} size={112} pettable />
                        </span>
                      )}
                    </li>
                  );
                }
                const node = item.node;
                const pose = catAt(stop, currentStop, node.state === 'locked', seed);
                const generating = generatingUnitId === node.unit.id;
                const read = node.isCurrent && node.state === 'ready' ? readFraction(node) : 0;
                const bubble = generating ? 'ĐANG TẠO…' : node.isCurrent ? (node.state === 'not_generated' ? 'TẠO BÀI' : read > 0 ? 'HỌC TIẾP' : 'BẮT ĐẦU') : null;
                const open = selected === node.unit.id;
                return (
                  <li key={node.unit.id} id={`path-${node.unit.id}`} className={open ? 'path-step is-open' : 'path-step'} style={{ transform: `translateX(${offset}px)` }}>
                    {bubble && <span className={`path-bubble${generating ? ' is-busy' : ''}`}>{bubble}</span>}
                    <div className="path-node-wrap">
                      {(node.isCurrent || generating) && <Ring fraction={generating ? 0.25 : read} />}
                      <button
                        ref={node.isCurrent ? watch : undefined}
                        type="button"
                        className={[
                          'path-node',
                          `path-node--${node.state}`,
                          node.isCurrent ? 'is-current' : '',
                          generating ? 'is-generating' : '',
                          justUnlocked === node.unit.id ? 'is-fresh' : '',
                        ]
                          .filter(Boolean)
                          .join(' ')}
                        aria-expanded={open}
                        aria-label={`Bài ${node.index + 1}: ${node.unit.title}. ${meta(node)}`}
                        title={node.unit.title}
                        onClick={() => onSelect(open ? null : node.unit.id)}
                      >
                        <NodeGlyph kind={glyphFor(node, generating)} size={node.isCurrent ? 38 : 34} />
                      </button>
                    </div>
                    {pose && (
                      <span className={`path-cat path-cat--${side}`} aria-hidden="true">
                        <Mascot pose={pose} size={112} pettable />
                      </span>
                    )}
                    {node.isCurrent && (
                      <span className={`path-mascot path-mascot--${side}`} aria-hidden="true">
                        <Mascot mood={node.state === 'not_generated' ? 'hint' : 'hello'} size={104} bob pettable />
                      </span>
                    )}
                    {open && (
                      <Popover
                        node={node}
                        onOpen={() => onOpen(node)}
                        onGenerate={() => {
                          onSelect(null);
                          onGenerate(node);
                        }}
                        onReview={() => onReview(node)}
                        onClose={() => onSelect(null)}
                        onCurrent={() => {
                          const target = nodes.find((n) => n.isCurrent);
                          onSelect(target ? target.unit.id : null);
                          current.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        }}
                        onOpenAll={
                          onOpenAll &&
                          (() => {
                            onSelect(null);
                            onOpenAll();
                          })
                        }
                      />
                    )}
                  </li>
                );
              })}
            </ol>
          </section>
        );
      })}
      <div className="path-end">
        <button
          type="button"
          className={`path-chest${reviewable ? '' : ' is-locked'}`}
          disabled={!reviewable}
          onClick={() => onReview(null)}
          aria-label={reviewable ? 'Ôn tất cả câu sai' : 'Ôn câu sai — có sau khi luyện xong bài đầu tiên'}
        >
          <svg viewBox="0 0 64 56" width="64" height="56" aria-hidden="true">
            <path d="M6 22h52v26a5 5 0 0 1-5 5H11a5 5 0 0 1-5-5z" className="path-chest__box" />
            <path d="M6 22c0-9 6-16 14-16h24c8 0 14 7 14 16z" className="path-chest__lid" />
            <rect x="27" y="18" width="10" height="13" rx="3" className="path-chest__lock" />
            <path d="M6 30h52" className="path-chest__band" />
          </svg>
        </button>
        <span className="meta">{reviewable ? 'Ôn câu sai' : 'Ôn tập mở sau bài đầu tiên'}</span>
      </div>
      {away && (
        <button type="button" className="path-jump" aria-label="Về bài đang học" title="Về bài đang học" onClick={() => current.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })}>
          <Icon name={away === 'up' ? 'up' : 'down'} size={22} />
        </button>
      )}
    </div>
  );
}

