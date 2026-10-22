import { useEffect, useMemo, useRef } from 'react';
import { Icon, type IconName } from '../../components/Icon';
import { Mascot, type Pose } from '../../components/Mascot';
import { chapterGroups, type PathNode } from '../../lib/path';
import { Art } from '../../components/Art';
import { lessonIcons } from '../../lib/topicIcons';

// Duolingo-style path: chunky 3D lesson buttons on a gentle zigzag, a banner
// per chapter, a speech bubble on the one lesson to do next, Kẹp standing
// beside it, and a review chest at the end. Each lesson wears its own subject
// icon; a small corner badge says done, locked or not made yet. Titles live in
// the popover and in the table of contents, so the path itself stays calm.

const OFFSETS = [0, -58, -88, -58, 0, 58, 88, 58];
const TONES = ['sage', 'sky', 'coral'] as const;
const AWAKE: Pose[] = ['book', 'mug', 'laptop', 'flag'];

/**
 * Now and then a cat keeps the path company: beside every third lesson (the
 * 2nd, 5th, 8th…), on the empty side of the bend. Cats by a locked lesson
 * sleep; the others read, sip coffee, type or wave a flag, picked from the
 * course title so a course always shows the same cats.
 */
function sideCat(step: number, node: PathNode, courseTitle: string): Pose | null {
  if (step % 3 !== 1 || node.isCurrent) return null;
  if (node.state === 'locked') return 'sleep';
  let h = 0;
  for (const ch of courseTitle) h = (h * 31 + ch.codePointAt(0)!) >>> 0;
  return AWAKE[(h + node.index) % AWAKE.length];
}

function badgeFor(node: PathNode): IconName | null {
  if (node.state === 'done') return 'check';
  if (node.state === 'locked') return 'lock';
  if (node.state === 'not_generated') return 'sparkle';
  return null;
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
}: {
  node: PathNode;
  onOpen: () => void;
  onGenerate: () => void;
  onReview: () => void;
  onClose: () => void;
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
        <button type="button" className="btn btn--secondary btn--block" disabled>
          <Icon name="lock" size={16} /> Chưa mở
        </button>
      )}
    </div>
  );
}

export function ProgressPath({
  nodes,
  courseTitle,
  generatingUnitId,
  readFraction,
  reviewable,
  justUnlocked,
  selected,
  onSelect,
  onOpen,
  onGenerate,
  onReview,
}: {
  nodes: PathNode[];
  courseTitle: string;
  generatingUnitId?: string | null;
  /** Share of the current lesson already read on this device (0–1). */
  readFraction: (node: PathNode) => number;
  reviewable: boolean;
  justUnlocked?: string | null;
  selected: string | null;
  onSelect: (unitId: string | null) => void;
  onOpen: (node: PathNode) => void;
  onGenerate: (node: PathNode) => void;
  onReview: (node: PathNode | null) => void;
}) {
  const groups = useMemo(() => chapterGroups(nodes), [nodes]);
  const icons = useMemo(() => lessonIcons(nodes.map((node) => node.unit.title)), [nodes]);
  let step = 0;

  return (
    <div className="path">
      {groups.map((group, g) => {
        const tone = TONES[g % TONES.length];
        const done = group.nodes.filter((n) => n.state === 'done').length;
        return (
          <section key={g} className={`path-chapter path-chapter--${tone}`} aria-label={group.title || courseTitle}>
            <header className="path-banner">
              <div>
                <p className="path-banner__eyebrow">{groups.length > 1 ? `Chương ${g + 1}` : 'Lộ trình'} · {done}/{group.nodes.length} bài</p>
                <h3 className="path-banner__title">{group.title || courseTitle}</h3>
              </div>
              <span className="path-banner__badge" aria-hidden="true">
                <Icon name={done === group.nodes.length ? 'check' : 'bookOpen'} size={22} />
              </span>
            </header>
            <ol className="path-track">
              {group.nodes.map((node) => {
                const offset = OFFSETS[step % OFFSETS.length];
                const mascotSide = offset > 0 ? 'left' : 'right';
                const cat = sideCat(step, node, courseTitle);
                step += 1;
                const generating = generatingUnitId === node.unit.id;
                const read = node.isCurrent && node.state === 'ready' ? readFraction(node) : 0;
                const bubble = generating ? 'ĐANG TẠO…' : node.isCurrent ? (node.state === 'not_generated' ? 'TẠO BÀI' : read > 0 ? 'HỌC TIẾP' : 'BẮT ĐẦU') : null;
                const open = selected === node.unit.id;
                return (
                  <li key={node.unit.id} className={open ? 'path-step is-open' : 'path-step'} style={{ transform: `translateX(${offset}px)` }}>
                    {bubble && <span className={`path-bubble${generating ? ' is-busy' : ''}`}>{bubble}</span>}
                    <div className="path-node-wrap">
                      {(node.isCurrent || generating) && <Ring fraction={generating ? 0.25 : read} />}
                      <button
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
                        <Art name={icons[node.index]} size={node.isCurrent ? 46 : 42} className="path-node__art" />
                        {badgeFor(node) && (
                          <span className={`path-node__badge path-node__badge--${node.state}`} aria-hidden="true">
                            <Icon name={badgeFor(node)!} size={14} />
                          </span>
                        )}
                      </button>
                    </div>
                    {cat && (
                      <span className={`path-cat path-cat--${mascotSide}`} aria-hidden="true">
                        <Mascot pose={cat} size={84} pettable />
                      </span>
                    )}
                    {node.isCurrent && (
                      <span className={`path-mascot path-mascot--${mascotSide}`} aria-hidden="true">
                        <Mascot mood={node.state === 'not_generated' ? 'hint' : 'hello'} size={92} bob pettable />
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
    </div>
  );
}
