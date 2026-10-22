import { useMemo, useState } from 'react';
import { api, ApiError, ensureSession } from '../../api/client';
import type { Note } from '../../api/types';
import { useApp, useLoad } from '../../app/store';
import { Icon } from '../../components/Icon';
import { RichText } from '../../components/RichText';
import { Spot } from '../../components/Spot';
import { EmptyState, LoadingRows, ProblemNotice } from '../../components/StateViews';
import { describeError } from '../../lib/copy';
import { fold, makeTextFix, stripRefLabels } from '../../lib/text';

const LABEL: Record<string, string> = { ai: 'Kẹp giải thích', user: 'Của bạn', teacher: 'Giáo viên' };

function when(iso: string) {
  return new Intl.DateTimeFormat('vi-VN', { day: 'numeric', month: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(iso));
}

/**
 * Sổ tay: notes the learner writes and answers saved from Kẹp ("Lưu vào sổ
 * tay"). Edits keep versions on the server; deleting can be undone.
 */
export function NotebookPage() {
  const { toast } = useApp();
  const state = useLoad(async () => {
    await ensureSession();
    return api<Note[]>('/notebook');
  }, []);
  const [draft, setDraft] = useState('');
  const [editing, setEditing] = useState<{ id: string; body: string } | null>(null);
  const [query, setQuery] = useState('');
  const [label, setLabel] = useState<'all' | 'ai' | 'user'>('all');
  const [deleted, setDeleted] = useState<Note | null>(null);
  const [busy, setBusy] = useState(false);

  const add = async () => {
    setBusy(true);
    try {
      await api('/notebook', { body: { body: draft.trim(), label: 'user', source_refs: [] } });
      setDraft('');
      toast('Đã thêm vào sổ tay');
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
      await api(`/notebook/${note.id}`, { method: 'PUT', body: { body: editing.body.trim(), label: note.label === 'teacher' ? 'teacher' : 'user', source_refs: note.source_refs, expected_version: note.version } });
      setEditing(null);
      toast('Đã lưu ghi chú');
      state.reload();
    } catch (error) {
      toast(error instanceof ApiError && error.status === 409 ? 'Ghi chú vừa đổi ở nơi khác — đã tải lại' : describeError(error).title);
      if (error instanceof ApiError && error.status === 409) state.reload();
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
  const notes = (state.data ?? []).filter((n) => (label === 'all' || (label === 'ai' ? n.label === 'ai' : n.label !== 'ai')) && (!q || fold(n.body).includes(q)));

  return (
    <div className="page notebook">
      <header className="page-head">
        <div>
          <p className="eyebrow">Ghi chú của bạn và lời giải đã lưu</p>
          <h1 className="page-title">Sổ tay</h1>
        </div>
      </header>

      <section className="note-new">
        <textarea className="field" rows={3} maxLength={10000} value={draft} placeholder="Ghi nhanh một ý, công thức hay mẹo nhớ…" onChange={(e) => setDraft(e.target.value)} aria-label="Ghi chú mới" />
        <button type="button" className="btn btn--primary" disabled={!draft.trim() || busy} aria-busy={busy} onClick={() => void add()}>
          <Icon name="plus" size={18} /> Thêm ghi chú
        </button>
      </section>

      <div className="library__bar">
        <div className="segmented segmented--fit" role="radiogroup" aria-label="Loại ghi chú">
          <button type="button" role="radio" aria-checked={label === 'all'} onClick={() => setLabel('all')}>
            Tất cả
          </button>
          <button type="button" role="radio" aria-checked={label === 'user'} onClick={() => setLabel('user')}>
            Của bạn
          </button>
          <button type="button" role="radio" aria-checked={label === 'ai'} onClick={() => setLabel('ai')}>
            Kẹp giải thích
          </button>
        </div>
        <label className="search">
          <Icon name="search" size={18} />
          <input className="field" value={query} placeholder="Tìm trong sổ tay…" aria-label="Tìm trong sổ tay" onChange={(e) => setQuery(e.target.value)} />
        </label>
      </div>

      {deleted && (
        <div className="notice notice--butter undo-bar" role="status">
          <Icon name="trash" />
          <p className="notice__body">Đã xóa một ghi chú.</p>
          <button type="button" className="btn btn--secondary btn--sm" onClick={() => void undo()}>
            Hoàn tác
          </button>
        </div>
      )}

      {state.loading && !state.data && <LoadingRows rows={3} label="Đang mở sổ tay…" />}
      {state.error != null && <ProblemNotice problem={describeError(state.error)} onRetry={state.reload} />}
      {state.data && notes.length === 0 && (
        <EmptyState
          art={<Spot glyph="pencil" tone="butter" size={110} />}
          title={state.data.length ? 'Không có ghi chú phù hợp' : 'Sổ tay đang trống'}
          body="Khi Kẹp giải thích hay, bấm “Lưu vào sổ tay” ngay dưới câu trả lời. Bạn cũng có thể tự ghi ở ô phía trên."
        />
      )}
      <div className="notes">
        {notes.map((note) => (
          <article key={note.id} className={`note note--${note.label}`}>
            <header className="note__head">
              <span className={note.label === 'ai' ? 'tag tag--sage' : note.label === 'teacher' ? 'tag tag--butter' : 'tag'}>{LABEL[note.label] ?? note.label}</span>
              <span className="meta">{when(note.updated_at)}</span>
              <span className="note__tools">
                <button type="button" className="icon-btn" aria-label="Sửa ghi chú" onClick={() => setEditing({ id: note.id, body: note.body })}>
                  <Icon name="edit" size={17} />
                </button>
                <button type="button" className="icon-btn" aria-label="Xóa ghi chú" onClick={() => void remove(note)}>
                  <Icon name="trash" size={17} />
                </button>
              </span>
            </header>
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
