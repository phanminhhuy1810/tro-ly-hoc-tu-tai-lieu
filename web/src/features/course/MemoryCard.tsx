import { useEffect, useState } from 'react';
import { api, ApiError } from '../../api/client';
import { useApp } from '../../app/store';
import { Icon } from '../../components/Icon';
import { Mascot } from '../../components/Mascot';
import { describeError } from '../../lib/copy';

interface Memory {
  notes: string;
  version: number;
  max_notes: number;
  struggles: { prompt: string; unit_id?: string }[];
  course: { subject?: string; goal?: string; instructions?: string; language?: string; terms_to_keep?: string[] };
  overview: { summary: string; key_ideas: string[] } | null;
}

const EXAMPLES = ['Giải thích bằng ví dụ đời thường', 'Mình hay nhầm prefix và subnet mask', 'Ưu tiên bài tính toán, ít lý thuyết'];

/**
 * What Byte keeps in mind in every chat and lesson of this course: the
 * learner's own notes, the course rules, recent mistakes and the overview it
 * wrote after reading the whole document.
 */
export function MemoryCard({ courseId }: { courseId: string }) {
  const { toast } = useApp();
  const [memory, setMemory] = useState<Memory | null>(null);
  const [draft, setDraft] = useState('');
  const [saving, setSaving] = useState(false);
  const [open, setOpen] = useState(false);

  const load = async () => {
    const value = await api<Memory>(`/courses/${courseId}/memory`);
    setMemory(value);
    setDraft(value.notes);
  };

  useEffect(() => {
    load().catch(() => setMemory(null));
  }, [courseId]);

  const save = async () => {
    if (!memory) return;
    setSaving(true);
    try {
      const saved = await api<{ notes: string; version: number }>(`/courses/${courseId}/memory`, { method: 'PUT', body: { notes: draft, expected_version: memory.version } });
      setMemory({ ...memory, ...saved });
      toast('Byte sẽ nhớ điều này trong mọi bài của khóa');
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        await load();
        toast('Ghi nhớ vừa đổi ở cửa sổ khác — đã tải bản mới');
      } else toast(describeError(error).title);
    } finally {
      setSaving(false);
    }
  };

  if (!memory) return null;
  const changed = draft.trim() !== memory.notes.trim();
  return (
    <section className="memory-card" aria-labelledby="memory-title">
      <header className="memory-card__head">
        <Mascot mood="think" size={48} />
        <div>
          <h2 id="memory-title" className="title-m">
            Byte nhớ gì về bạn
          </h2>
          <p className="meta">Dùng trong mọi câu hỏi của khóa này</p>
        </div>
      </header>

      <label className="memory-card__notes">
        <span className="eyebrow">Bạn muốn Byte nhớ</span>
        <textarea
          className="field"
          rows={3}
          maxLength={memory.max_notes}
          value={draft}
          placeholder="Ví dụ: giải thích bằng ví dụ đời thường; mình hay nhầm /26 và /27…"
          onChange={(event) => setDraft(event.target.value)}
        />
      </label>
      {!draft && (
        <div className="memory-card__examples">
          {EXAMPLES.map((example) => (
            <button key={example} type="button" className="chip" onClick={() => setDraft(example)}>
              {example}
            </button>
          ))}
        </div>
      )}
      {changed && (
        <button type="button" className="btn btn--primary btn--sm" onClick={() => void save()} aria-busy={saving} disabled={saving}>
          <Icon name="save" size={16} /> Lưu ghi nhớ
        </button>
      )}

      <button type="button" className="link link--quiet" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <Icon name={open ? 'up' : 'down'} size={15} /> {open ? 'Ẩn phần Byte tự ghi nhớ' : 'Xem phần Byte tự ghi nhớ'}
      </button>
      {open && (
        <div className="memory-card__auto enter">
          {memory.overview && (
            <div>
              <p className="eyebrow">Tóm tắt sau khi đọc toàn bộ tài liệu</p>
              <p>{memory.overview.summary}</p>
            </div>
          )}
          {(memory.course.goal || memory.course.instructions) && (
            <div>
              <p className="eyebrow">Mục tiêu và quy tắc của khóa</p>
              {memory.course.goal && <p>{memory.course.goal}</p>}
              {memory.course.instructions && <p className="meta">{memory.course.instructions}</p>}
            </div>
          )}
          <div>
            <p className="eyebrow">Câu bạn làm sai gần đây</p>
            {memory.struggles.length ? (
              <ul>
                {memory.struggles.map((s) => (
                  <li key={s.prompt}>{s.prompt}</li>
                ))}
              </ul>
            ) : (
              <p className="meta">Chưa có — Byte sẽ tự nhớ khi bạn luyện tập.</p>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
