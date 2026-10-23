import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { api, ApiError, ensureSession } from '../../api/client';
import type { Note, NoteColor } from '../../api/types';
import { useApp, useLoad } from '../../app/store';
import { Icon } from '../../components/Icon';
import { Mascot } from '../../components/Mascot';
import { PageHeader } from '../../components/PageHeader';
import { RichText } from '../../components/RichText';
import { EmptyState, LoadingRows, ProblemNotice } from '../../components/StateViews';
import { describeError } from '../../lib/copy';
import { fold, makeTextFix, stripRefLabels } from '../../lib/text';
import { NOTE_COLORS, noteColor } from './noteColors';

const LABEL: Record<string, string> = { ai: 'Byte giải thích', user: 'Bạn viết', teacher: 'Giáo viên' };

function when(iso: string) {
  return new Intl.DateTimeFormat('vi-VN', { day: 'numeric', month: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(iso));
}

function ColorDots({ value, label, onPick }: { value: NoteColor | null; label: string; onPick: (color: NoteColor) => void }) {
  return (
    <div className="color-dots" role="radiogroup" aria-label={label}>
      {NOTE_COLORS.map((color) => (
        <button
          key={color.value}
          type="button"
          role="radio"
          aria-checked={value === color.value}
          aria-label={color.name}
          title={color.name}
          className={`color-dot color-dot--${color.value}`}
          onClick={() => onPick(color.value)}
        >
          {value === color.value && <Icon name="check" size={14} />}
        </button>
      ))}
    </div>
  );
}

/**
 * Sổ tay: sticky notes the learner writes and answers saved from Byte
 * (“Lưu vào sổ tay”). Each note keeps the colour the learner gives it; edits
 * keep versions on the server and deleting can be undone.
 */
export function NotebookPage() {
  const { toast } = useApp();
  const state = useLoad(async () => {
    await ensureSession();
    return api<Note[]>('/notebook');
  }, []);
  const [draft, setDraft] = useState('');
  const [draftColor, setDraftColor] = useState<NoteColor>('butter');
  const [composing, setComposing] = useState(false);
  const composer = useRef<HTMLElement>(null);
  const writing = composing || draft.length > 0;
  const [editing, setEditing] = useState<{ id: string; body: string } | null>(null);
  const [palette, setPalette] = useState<string | null>(null);
  const [colors, setColors] = useState<Record<string, NoteColor>>({});
  const [query, setQuery] = useState('');
  const [label, setLabel] = useState<'all' | 'ai' | 'user'>('all');
  const [colorFilter, setColorFilter] = useState<NoteColor | null>(null);
  const [deleted, setDeleted] = useState<Note | null>(null);
  const [busy, setBusy] = useState(false);

  // Like a note app: one line until you write, folds back when you click away with nothing written.
  useEffect(() => {
    if (!writing) return;
    const away = (event: PointerEvent) => {
      if (!draft.trim() && !composer.current?.contains(event.target as Node)) setComposing(false);
    };
    document.addEventListener('pointerdown', away);
    return () => document.removeEventListener('pointerdown', away);
  }, [writing, draft]);

  const add = async () => {
    setBusy(true);
    try {
      await api('/notebook', { body: { body: draft.trim(), label: 'user', source_refs: [], color: draftColor } });
      setDraft('');
      setComposing(false);
      toast('Đã dán thêm một ghi chú');
      state.reload();
    } catch (error) {
      toast(describeError(error).title);
    } finally {
      setBusy(false);
    }
  };

  const save = async (note: Note) => {
    if (!editing) return;
    try {
      await api(`/notebook/${note.id}`, { method: 'PUT', body: { body: editing.body.trim(), label: note.label === 'teacher' ? 'teacher' : 'user', source_refs: note.source_refs, expected_version: note.version, color: noteColor(note) } });
      setEditing(null);
      toast('Đã lưu ghi chú');
      state.reload();
    } catch (error) {
      toast(error instanceof ApiError && error.status === 409 ? 'Ghi chú vừa đổi ở nơi khác — đã tải lại' : describeError(error).title);
      if (error instanceof ApiError && error.status === 409) state.reload();
    }
  };

  // The colour changes on screen at once; the server keeps it, and a failure puts the old one back.
  const recolor = async (note: Note, color: NoteColor) => {
    setPalette(null);
    setColors((all) => ({ ...all, [note.id]: color }));
    try {
      await api(`/notebook/${note.id}/color`, { method: 'PUT', body: { color } });
    } catch (error) {
      setColors((all) => {
        const next = { ...all };
        delete next[note.id];
        return next;
      });
      toast(describeError(error).title);
    }
  };

  const remove = async (note: Note) => {
    try {
      await api(`/notebook/${note.id}`, { method: 'DELETE' });
      setDeleted(note);
      state.reload();
    } catch (error) {
      toast(describeError(error).title);
    }
  };

  const undo = async () => {
    if (!deleted) return;
    try {
      await api(`/notebook/${deleted.id}/restore`, { method: 'POST' });
      setDeleted(null);
      state.reload();
    } catch (error) {
      toast(describeError(error).title);
    }
  };

  const q = fold(query.trim());
  // Answers saved before the PDF reader fix can hold glued slide text; repair it for display from the notebook's own words.
  const fix = useMemo(() => makeTextFix((state.data ?? []).map((n) => n.body)), [state.data]);
  const all = (state.data ?? []).map((note) => (colors[note.id] ? { ...note, color: colors[note.id] } : note));
  const notes = all.filter(
    (n) =>
      (label === 'all' || (label === 'ai' ? n.label === 'ai' : n.label !== 'ai')) &&
      (!colorFilter || noteColor(n) === colorFilter) &&
      (!q || fold(n.body).includes(q)),
  );

  return (
    <div className="page notebook">
      <PageHeader
        title="Sổ tay"
        tone="butter"
        note="Ghi nhanh mẹo nhớ, công thức — và những lời giải hay của Byte. Tô màu để tự xếp theo ý bạn."
        art={<Mascot pose="pencil" size={100} pettable />}
      />

      <section ref={composer} className={`note-new note--${draftColor}${writing ? ' is-open' : ''}`} aria-label="Viết ghi chú mới">
        <span className="note__tape" aria-hidden="true" />
        <textarea
          className="note-new__field"
          rows={writing ? 3 : 1}
          maxLength={10000}
          value={draft}
          placeholder="Ghi nhanh một ý, công thức hay mẹo nhớ…"
          aria-label="Ghi chú mới"
          onFocus={() => setComposing(true)}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Escape' && !draft.trim()) {
              setComposing(false);
              e.currentTarget.blur();
            }
          }}
        />
        {writing && (
          <div className="note-new__bar">
            <ColorDots value={draftColor} label="Màu cho ghi chú mới" onPick={setDraftColor} />
            <div className="note-new__actions">
              {draft.trim() ? (
                <button type="button" className="btn btn--primary btn--sm note-new__save" disabled={busy} aria-busy={busy} onClick={() => void add()}>
                  <Icon name="plus" size={16} /> Dán vào sổ
                </button>
              ) : (
                <button type="button" className="btn btn--ghost btn--sm" onClick={() => setComposing(false)}>
                  Đóng
                </button>
              )}
            </div>
          </div>
        )}
      </section>

      <div className="library__bar notebook__bar">
        <div className="segmented segmented--fit" role="radiogroup" aria-label="Loại ghi chú">
          <button type="button" role="radio" aria-checked={label === 'all'} onClick={() => setLabel('all')}>
            Tất cả
          </button>
          <button type="button" role="radio" aria-checked={label === 'user'} onClick={() => setLabel('user')}>
            Bạn viết
          </button>
          <button type="button" role="radio" aria-checked={label === 'ai'} onClick={() => setLabel('ai')}>
            Byte giải thích
          </button>
        </div>
        <div className="notebook__colors">
          <span className="meta">Lọc màu</span>
          <ColorDots value={colorFilter} label="Lọc theo màu" onPick={(color) => setColorFilter((current) => (current === color ? null : color))} />
        </div>
        <label className="search">
          <Icon name="search" size={18} />
          <input className="field" value={query} placeholder="Tìm trong sổ tay…" aria-label="Tìm trong sổ tay" onChange={(e) => setQuery(e.target.value)} />
        </label>
      </div>

      {deleted && (
        <div className="notice notice--butter undo-bar" role="status">
          <Icon name="trash" />
          <p className="notice__body">Đã gỡ một ghi chú khỏi sổ.</p>
          <button type="button" className="btn btn--secondary btn--sm" onClick={() => void undo()}>
            Hoàn tác
          </button>
        </div>
      )}

      {state.loading && !state.data && <LoadingRows rows={3} label="Đang mở sổ tay…" />}
      {state.error != null && <ProblemNotice problem={describeError(state.error)} onRetry={state.reload} />}
      {state.data && notes.length === 0 && (
        <EmptyState
          art={<Mascot pose="pencil" size={120} pettable />}
          title={state.data.length ? 'Không có ghi chú khớp bộ lọc' : 'Sổ tay đang trống'}
          body="Khi Byte giải thích hay, bấm “Lưu vào sổ tay” ngay dưới câu trả lời. Bạn cũng có thể tự ghi ở ô phía trên."
        />
      )}
      <div className="notes">
        {notes.map((note, index) => (
          <article key={note.id} className={`note note--${noteColor(note)}`} style={{ '--i': Math.min(index, 12) } as CSSProperties}>
            <span className="note__tape" aria-hidden="true" />
            <header className="note__head">
              <span className="note__label">{LABEL[note.label] ?? note.label}</span>
              <span className="meta">{when(note.updated_at)}</span>
              <span className="note__tools">
                <button type="button" className="icon-btn" aria-label="Đổi màu ghi chú" aria-expanded={palette === note.id} onClick={() => setPalette((open) => (open === note.id ? null : note.id))}>
                  <span className={`color-dot color-dot--${noteColor(note)} color-dot--sm`} aria-hidden="true" />
                </button>
                <button type="button" className="icon-btn" aria-label="Sửa ghi chú" onClick={() => setEditing({ id: note.id, body: note.body })}>
                  <Icon name="edit" size={17} />
                </button>
                <button type="button" className="icon-btn" aria-label="Xóa ghi chú" onClick={() => void remove(note)}>
                  <Icon name="trash" size={17} />
                </button>
              </span>
            </header>
            {palette === note.id && (
              <div className="note__palette enter">
                <ColorDots value={noteColor(note)} label="Màu ghi chú" onPick={(color) => void recolor(note, color)} />
              </div>
            )}
            {editing?.id === note.id ? (
              <div className="note__edit">
                <textarea className="field" rows={6} maxLength={10000} value={editing.body} onChange={(e) => setEditing({ id: note.id, body: e.target.value })} />
                <div className="dialog__actions">
                  <button type="button" className="btn btn--ghost btn--sm" onClick={() => setEditing(null)}>
                    Thôi
                  </button>
                  <button type="button" className="btn btn--primary btn--sm" disabled={!editing.body.trim()} onClick={() => void save(note)}>
                    Lưu
                  </button>
                </div>
              </div>
            ) : (
              <RichText className="note__body" text={fix(note.label === 'ai' ? stripRefLabels(note.body) : note.body)} />
            )}
          </article>
        ))}
      </div>
    </div>
  );
}
