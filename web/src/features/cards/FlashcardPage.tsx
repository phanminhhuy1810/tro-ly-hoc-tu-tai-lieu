import { useCallback, useEffect, useMemo, useState } from 'react';
import { api, ApiError, ensureSession } from '../../api/client';
import type { Course, StudyCard } from '../../api/types';
import { hrefFor, motionAllowed } from '../../app/router';
import { useApp, useLoad } from '../../app/store';
import { useStudyPulse } from '../../app/usePulse';
import { EmojiTile } from '../../components/EmojiTile';
import { Icon } from '../../components/Icon';
import { Mascot } from '../../components/Mascot';
import { RichText } from '../../components/RichText';
import { EmptyState, LoadingRows, ProblemNotice } from '../../components/StateViews';
import { describeError } from '../../lib/copy';
import { emojiOf, lessonIcons } from '../../lib/topicIcons';
import { coverOf, useCovers } from '../course/covers';
import { deckOrder, memoryOf, type CardMemory, type DeckFilter } from './deck';

interface Loaded {
  course: Course;
  cards: StudyCard[];
}

function CardEditor({ courseId, card, onSaved, onCancel }: { courseId: string; card: StudyCard | null; onSaved: () => void; onCancel: () => void }) {
  const { toast } = useApp();
  const [front, setFront] = useState(card?.front ?? '');
  const [back, setBack] = useState(card?.back ?? '');
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try {
      if (card) await api(`/cards/${encodeURIComponent(card.id)}`, { method: 'PUT', body: { front, back, course_id: courseId, source_refs: card.source_refs ?? [], expected_version: card.version } });
      else await api('/cards', { body: { front, back, course_id: courseId, source_refs: [] } });
      toast(card ? 'Đã sửa thẻ' : 'Đã thêm thẻ vào bộ');
      onSaved();
    } catch (error) {
      toast(error instanceof ApiError && error.status === 409 ? 'Thẻ vừa đổi ở nơi khác — tải lại rồi sửa nhé' : describeError(error).title);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="card-editor enter">
      <label>
        <span className="eyebrow">Mặt trước — câu hỏi hoặc thuật ngữ</span>
        <textarea className="field" rows={2} maxLength={1000} value={front} onChange={(e) => setFront(e.target.value)} />
      </label>
      <label>
        <span className="eyebrow">Mặt sau — đáp án hoặc giải thích</span>
        <textarea className="field" rows={4} maxLength={3000} value={back} onChange={(e) => setBack(e.target.value)} />
      </label>
      <div className="dialog__actions">
        <button type="button" className="btn btn--ghost" onClick={onCancel}>
          Thôi
        </button>
        <button type="button" className="btn btn--primary" disabled={busy || !front.trim() || !back.trim()} aria-busy={busy} onClick={() => void save()}>
          {card ? 'Lưu thẻ' : 'Thêm thẻ'}
        </button>
      </div>
    </div>
  );
}

/**
 * Flashcard mode: one card at a time, flip, then "Nhớ rồi" / "Chưa nhớ".
 * Reviews count towards the daily card mission; personal cards can be added
 * and edited, cards generated with a lesson stay read-only.
 */
export function FlashcardPage({ courseId }: { courseId: string }) {
  const { toast, refreshWallet, setChatContext, wallet } = useApp();
  const state = useLoad<Loaded>(async () => {
    await ensureSession();
    const [course, cards] = await Promise.all([api<Course>(`/courses/${courseId}`), api<StudyCard[]>(`/cards?course_id=${encodeURIComponent(courseId)}`)]);
    return { course, cards };
  }, [courseId]);
  const [filter, setFilter] = useState<DeckFilter>('due');
  const [position, setPosition] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [view, setView] = useState<'deck' | 'list'>('deck');
  const [editing, setEditing] = useState<StudyCard | 'new' | null>(null);
  // This round's marks; the deck order stays fixed until the learner reloads or changes the filter.
  const [local, setLocal] = useState<Record<string, CardMemory>>({});
  const [busy, setBusy] = useState(false);
  // The marked card slides off (right: remembered, left: not yet) while the server records it.
  const [leaving, setLeaving] = useState<'left' | 'right' | null>(null);

  const cards = useMemo(() => state.data?.cards ?? [], [state.data]);
  const course = state.data?.course;
  const covers = useCovers();
  const icons = useMemo(() => lessonIcons(course?.content.units.map((u) => u.title) ?? []), [course]);
  const order = useMemo(() => deckOrder(cards, filter), [cards, filter]);
  const current = order[position];

  useEffect(() => {
    setPosition(0);
    setFlipped(false);
    setLocal({});
  }, [filter, cards]);

  const unit = current?.unit_id ?? course?.content.units.find((u) => u.data)?.id;
  // Time is credited only while course, unit and mode stay put, so the whole deck beats on one unit.
  const deckUnit = course?.content.units.find((u) => u.data)?.id;
  useStudyPulse(course && deckUnit ? { courseId: course.id, unitId: deckUnit, revision: course.revision, mode: 'cards' } : null);

  useEffect(() => {
    if (!course || !unit) return;
    const unitTitle = course.content.units.find((u) => u.id === unit)?.title ?? '';
    setChatContext({
      courseId: course.id,
      courseTitle: course.content.title,
      unitId: unit,
      unitTitle,
      card: current ? { id: current.id, label: `Thẻ: ${current.front.slice(0, 60)}` } : undefined,
    });
  }, [course, unit, current?.id, setChatContext]);

  const mark = useCallback(
    async (remembered: boolean) => {
      if (!current || !course || busy) return;
      setBusy(true);
      setLeaving(remembered ? 'right' : 'left');
      const slide = new Promise((resolve) => window.setTimeout(resolve, motionAllowed() ? 300 : 0));
      try {
        const result = await api<{ version: number; rewards?: { amount: number; replayed?: boolean }[] }>(`/cards/${encodeURIComponent(current.id)}/memory`, {
          method: 'PUT',
          body: { course_id: course.id, expected_revision: course.revision, expected_version: memoryOf(current, local).version, remembered },
        });
        setLocal((all) => ({ ...all, [current.id]: { remembered, version: result.version } }));
        const coin = (result.rewards ?? []).filter((r) => !r.replayed).reduce((sum, r) => sum + (r.amount ?? 0), 0);
        if (coin > 0) {
          toast(`+${coin} Coin — ôn đủ thẻ hôm nay`);
          refreshWallet();
        }
        await slide;
        setFlipped(false);
        setPosition((p) => p + 1);
      } catch (error) {
        if (error instanceof ApiError && error.status === 409) {
          toast('Thẻ vừa được đánh dấu ở cửa sổ khác — đã tải lại bộ thẻ');
          state.reload();
        } else toast(describeError(error).title);
      } finally {
        setLeaving(null);
        setBusy(false);
      }
    },
    [current, course, busy, local, toast, refreshWallet, state],
  );

  useEffect(() => {
    if (view !== 'deck' || editing) return;
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (target.closest('input, textarea, select, .chat, .chat-large')) return;
      if (event.key === ' ' || event.key === 'Enter') {
        event.preventDefault();
        setFlipped((f) => !f);
      } else if (event.key === 'ArrowRight' && flipped) void mark(true);
      else if (event.key === 'ArrowLeft' && flipped) void mark(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [view, editing, flipped, mark]);

  const remove = async (card: StudyCard) => {
    try {
      await api(`/cards/${encodeURIComponent(card.id)}`, { method: 'DELETE' });
      toast('Đã xóa thẻ');
      state.reload();
    } catch (error) {
      toast(describeError(error).title);
    }
  };

  if (state.loading && !state.data) {
    return (
      <div className="lesson-shell">
        <div className="page" style={{ maxWidth: 720, paddingTop: 80 }}>
          <LoadingRows rows={2} label="Đang mở bộ thẻ…" />
        </div>
      </div>
    );
  }
  if (state.error != null || !course) {
    return (
      <div className="lesson-shell">
        <div className="page" style={{ paddingTop: 40 }}>
          <a className="back" href={hrefFor({ name: 'course', courseId })}>
            <Icon name="arrowLeft" size={18} /> Lộ trình
          </a>
          <ProblemNotice problem={describeError(state.error)} onRetry={state.reload} />
        </div>
      </div>
    );
  }

  const remembered = cards.filter((c) => memoryOf(c, local).remembered === true).length;
  const due = cards.filter((c) => memoryOf(c, local).remembered !== true).length;
  const marks = Object.values(local);
  const reviewedNow = marks.length;
  const finished = position >= order.length && order.length > 0;

  return (
    <div className="lesson-shell cards-shell">
      <header className="lesson-top">
        <a className="back back--bar" href={hrefFor({ name: 'course', courseId })}>
          <Icon name="arrowLeft" size={18} />
          <span>Lộ trình</span>
        </a>
        <div className="lesson-top__title">
          <EmojiTile {...coverOf(covers[course.id], course.content.title)} size={44} />
          <span className="eyebrow">Flashcard · {course.content.title}</span>
          <strong>
            {remembered}/{cards.length} thẻ đã nhớ
          </strong>
        </div>
        <div className="segmented cards-view" role="radiogroup" aria-label="Cách xem">
          <button type="button" role="radio" aria-checked={view === 'deck'} onClick={() => setView('deck')}>
            Ôn thẻ
          </button>
          <button type="button" role="radio" aria-checked={view === 'list'} onClick={() => setView('list')}>
            Danh sách
          </button>
        </div>
        <span className="coin-chip" title="Coin dùng cho lượt hỏi AI">
          <Icon name="coin" size={17} />
          {wallet ? wallet.available : '—'}
        </span>
        <div className="lesson-top__bar" aria-hidden="true">
          <span style={{ width: `${cards.length ? Math.round((remembered / cards.length) * 100) : 0}%` }} />
        </div>
      </header>

      {cards.length === 0 ? (
        <EmptyState
          art={<Mascot mood="hint" size={110} />}
          title="Khóa này chưa có thẻ"
          body="Thẻ được tạo cùng mỗi bài học. Bạn cũng có thể tự thêm thẻ của mình."
          action={
            <button type="button" className="btn btn--primary btn--lg" onClick={() => setEditing('new')}>
              <Icon name="plus" size={18} /> Thêm thẻ
            </button>
          }
        />
      ) : view === 'deck' ? (
        <main className="deck" id="main">
          <div className="deck__filters">
            <div className="segmented segmented--fit" role="radiogroup" aria-label="Thẻ cần ôn">
              <button type="button" role="radio" aria-checked={filter === 'due'} onClick={() => setFilter('due')}>
                Chưa nhớ ({due})
              </button>
              <button type="button" role="radio" aria-checked={filter === 'all'} onClick={() => setFilter('all')}>
                Tất cả ({cards.length})
              </button>
            </div>
            {order.length > 0 && !finished && (
              <span className="meta">
                Thẻ {position + 1}/{order.length}
                <span className="kbd-hint"> · Space để lật, ← chưa nhớ, → nhớ rồi</span>
              </span>
            )}
          </div>

          {order.length === 0 ? (
            <EmptyState
              art={<Mascot mood="happy" size={110} />}
              title="Bạn đã nhớ hết các thẻ"
              body="Chọn “Tất cả” để ôn lại từ đầu, hoặc thêm thẻ mới."
              action={
                <button type="button" className="btn btn--secondary btn--lg" onClick={() => setFilter('all')}>
                  Ôn lại tất cả
                </button>
              }
            />
          ) : finished ? (
            <section className="deck__done enter">
              <Mascot mood="happy" size={110} />
              <p className="display-title">Xong một vòng {order.length} thẻ!</p>
              <p className="body-l">
                Lượt này bạn đánh dấu nhớ {marks.filter((m) => m.remembered).length}, chưa nhớ {marks.filter((m) => !m.remembered).length}. Ôn đủ 5 thẻ khác
                nhau trong ngày là hoàn thành nhiệm vụ thẻ.
              </p>
              <div className="result__actions">
                <button
                  type="button"
                  className="btn btn--primary btn--lg"
                  onClick={() => {
                    setFilter('due');
                    state.reload();
                  }}
                >
                  Ôn tiếp thẻ chưa nhớ <Icon name="arrowRight" size={18} />
                </button>
                <a className="btn btn--secondary btn--lg" href={hrefFor({ name: 'practice', courseId })}>
                  Sang Ôn luyện
                </a>
              </div>
            </section>
          ) : (
            current && (
              <>
                <div className="deck__stage">
                  {order.length - position > 2 && <span className="deck__under deck__under--far" aria-hidden="true" />}
                  {order.length - position > 1 && <span className="deck__under" aria-hidden="true" />}
                  <button
                    type="button"
                    className={`flashcard${flipped ? ' is-flipped' : ''}${leaving ? ` is-leaving-${leaving}` : ''}`}
                    aria-label={flipped ? 'Mặt sau của thẻ, bấm để lật lại' : 'Mặt trước của thẻ, bấm để xem đáp án'}
                    onClick={() => setFlipped((f) => !f)}
                    key={current.id}
                  >
                    <span className="flashcard__inner">
                      <span className="flashcard__face flashcard__face--front">
                        <span className="flashcard__top">
                          <span className="flashcard__tag">
                            {(() => {
                              const index = course.content.units.findIndex((u) => u.id === current.unit_id);
                              return index >= 0 ? `${emojiOf(icons[index])} ` : '';
                            })()}
                            {current.kind === 'personal' ? 'Thẻ của bạn' : 'Thẻ của bài'}
                          </span>
                          <span className="flashcard__count">
                            {position + 1}/{order.length}
                          </span>
                        </span>
                        <span className="flashcard__text">{current.front}</span>
                        <span className="flashcard__flip">
                          <Icon name="refresh" size={15} /> Bấm để lật
                        </span>
                      </span>
                      <span className="flashcard__face flashcard__face--back">
                        <span className="flashcard__top">
                          <span className="flashcard__tag flashcard__tag--answer">
                            <Icon name="check" size={14} /> Đáp án
                          </span>
                          <span className="flashcard__count">
                            {position + 1}/{order.length}
                          </span>
                        </span>
                        <RichText className="flashcard__answer" text={current.back} />
                      </span>
                    </span>
                  </button>
                </div>
                <div className="deck__actions">
                  {flipped ? (
                    <>
                      <button type="button" className="btn btn--danger btn--lg deck__answer" disabled={busy} onClick={() => void mark(false)}>
                        <Icon name="refresh" size={18} /> Chưa nhớ
                      </button>
                      <button type="button" className="btn btn--primary btn--lg deck__answer" disabled={busy} onClick={() => void mark(true)}>
                        <Icon name="check" size={18} /> Nhớ rồi
                      </button>
                    </>
                  ) : (
                    <button type="button" className="btn btn--secondary btn--lg deck__answer" onClick={() => setFlipped(true)}>
                      <Icon name="refresh" size={18} /> Lật xem đáp án
                    </button>
                  )}
                </div>
                <p className="meta deck__hint">{flipped ? 'Tự đánh giá — không có điểm, chỉ để chọn thẻ cần ôn lại.' : 'Thử nhớ đáp án trước khi lật.'}</p>
              </>
            )
          )}
          {reviewedNow > 0 && !finished && <p className="meta deck__count">Đã ôn {reviewedNow} thẻ trong lượt này</p>}
        </main>
      ) : (
        <main className="card-list" id="main">
          <div className="card-list__head">
            <p className="title-m">{cards.length} thẻ</p>
            <button type="button" className="btn btn--secondary btn--sm" onClick={() => setEditing('new')}>
              <Icon name="plus" size={16} /> Thêm thẻ
            </button>
          </div>
          {editing === 'new' && (
            <CardEditor
              courseId={courseId}
              card={null}
              onSaved={() => {
                setEditing(null);
                state.reload();
              }}
              onCancel={() => setEditing(null)}
            />
          )}
          <ul>
            {cards.map((card) => (
              <li key={card.id} className="card-row">
                {editing !== 'new' && editing?.id === card.id ? (
                  <CardEditor
                    courseId={courseId}
                    card={card}
                    onSaved={() => {
                      setEditing(null);
                      state.reload();
                    }}
                    onCancel={() => setEditing(null)}
                  />
                ) : (
                  <>
                    <span className={`card-row__state${memoryOf(card, local).remembered ? ' is-remembered' : memoryOf(card, local).remembered === false ? ' is-due' : ''}`}>
                      <Icon name={memoryOf(card, local).remembered ? 'check' : 'bookOpen'} size={14} />
                    </span>
                    <div className="card-row__text">
                      <p className="card-row__front">{card.front}</p>
                      <p className="meta card-row__back">{card.back}</p>
                    </div>
                    {card.kind === 'personal' ? (
                      <span className="card-row__tools">
                        <button type="button" className="icon-btn" aria-label="Sửa thẻ" onClick={() => setEditing(card)}>
                          <Icon name="edit" size={18} />
                        </button>
                        <button type="button" className="icon-btn" aria-label="Xóa thẻ" onClick={() => void remove(card)}>
                          <Icon name="trash" size={18} />
                        </button>
                      </span>
                    ) : (
                      <span className="tag">của bài</span>
                    )}
                  </>
                )}
              </li>
            ))}
          </ul>
        </main>
      )}
      {editing === 'new' && view === 'deck' && (
        <div className="deck__editor">
          <CardEditor
            courseId={courseId}
            card={null}
            onSaved={() => {
              setEditing(null);
              state.reload();
            }}
            onCancel={() => setEditing(null)}
          />
        </div>
      )}
    </div>
  );
}
