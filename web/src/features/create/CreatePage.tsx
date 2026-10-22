import { useCallback, useEffect, useRef, useState } from 'react';
import { api, ApiError, ensureSession } from '../../api/client';
import { askAi, settleAi, type AiOutcome } from '../../api/consent';
import type { AiStart } from '../../api/jobs';
import type { CoinQuote, Job, SourceDoc } from '../../api/types';
import { useApp } from '../../app/store';
import { CoinConfirm } from '../../components/CoinConfirm';
import { Icon } from '../../components/Icon';
import { PageHeader } from '../../components/PageHeader';
import { Mascot } from '../../components/Mascot';
import { ArtBadge } from '../../components/Art';
import { LoadingRows, ProblemNotice } from '../../components/StateViews';
import { describeError, describeJobFailure, locatorLabel, type Problem } from '../../lib/copy';
import { makeTextFix } from '../../lib/text';
import type { BlueprintValue } from './roadmap';
import { RoadmapStep } from './RoadmapStep';

type Step = 'source' | 'review' | 'read' | 'roadmap';

interface Draft {
  sourceId: string | null;
  goal: string;
  notes: string;
}

const DRAFT_KEY = 'folio.create.v1';
const STEPS: [Step, string][] = [
  ['source', 'Tài liệu'],
  ['review', 'Kiểm tra bản đọc'],
  ['read', 'AI đọc toàn bộ'],
  ['roadmap', 'Lộ trình & gợi ý'],
];
const ACCEPT = '.pdf,.docx,.pptx,.txt,.md,.png,.jpg,.jpeg,.webp,.tif,.tiff,.bmp,.heic';

function loadDraft(): Draft {
  try {
    return { sourceId: null, goal: '', notes: '', ...(JSON.parse(localStorage.getItem(DRAFT_KEY) ?? '{}') as Partial<Draft>) };
  } catch {
    return { sourceId: null, goal: '', notes: '' };
  }
}

function keepDraft(draft: Draft) {
  try {
    localStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
  } catch {
    /* The flow still works; only resuming after a reload is lost. */
  }
}

async function uploadFile(file: File): Promise<SourceDoc> {
  const form = new FormData();
  form.append('file', file);
  await ensureSession();
  const response = await fetch('/api/sources/upload', { method: 'POST', body: form, credentials: 'same-origin' });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = (payload as { detail?: unknown } | null)?.detail;
    const message = typeof detail === 'string' ? detail : (detail as { message?: string } | null)?.message ?? 'Chưa đọc được file này.';
    throw new ApiError(response.status, message);
  }
  return payload as SourceDoc;
}

/* Step 1 ------------------------------------------------------------------ */
function SourceStep({ onSource }: { onSource: (source: SourceDoc) => void }) {
  const [rows, setRows] = useState<{ name: string; state: 'reading' | 'done' | 'failed'; message?: string }[]>([]);
  const [dragging, setDragging] = useState(false);
  const [paste, setPaste] = useState({ open: false, name: '', text: '' });
  const [recent, setRecent] = useState<Omit<SourceDoc, 'fragments'>[] | null>(null);
  const [problem, setProblem] = useState<Problem | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const busy = rows.some((r) => r.state === 'reading');

  useEffect(() => {
    ensureSession()
      .then(() => api<Omit<SourceDoc, 'fragments'>[]>('/sources?limit=8'))
      .then(setRecent)
      .catch(() => setRecent([]));
  }, []);

  const files = async (list: FileList | File[]) => {
    const chosen = [...list].slice(0, 20);
    if (!chosen.length) return;
    setProblem(null);
    setRows(chosen.map((f) => ({ name: f.name, state: 'reading' })));
    const sources: SourceDoc[] = [];
    for (const [i, file] of chosen.entries()) {
      try {
        sources.push(await uploadFile(file));
        setRows((all) => all.map((r, j) => (j === i ? { ...r, state: 'done' } : r)));
      } catch (error) {
        setRows((all) => all.map((r, j) => (j === i ? { ...r, state: 'failed', message: (error as Error).message } : r)));
      }
    }
    if (sources.length === 1) onSource(sources[0]);
    else if (sources.length > 1) {
      try {
        const name = `Bộ ${sources.length} tài liệu`;
        onSource(await api<SourceDoc>('/sources/collection', { body: { name, sources: sources.map((s) => ({ source_id: s.id, expected_revision: s.revision })) } }));
      } catch (error) {
        setProblem(describeError(error));
      }
    }
  };

  const pasteText = async () => {
    try {
      setProblem(null);
      onSource(await api<SourceDoc>('/sources/text', { body: { name: paste.name.trim() || 'Ghi chú', text: paste.text } }));
    } catch (error) {
      setProblem(describeError(error));
    }
  };

  const reuse = async (id: string) => {
    try {
      onSource(await api<SourceDoc>(`/sources/${id}`));
    } catch (error) {
      setProblem(describeError(error));
    }
  };

  return (
    <div className="create-source">
      <section
        className={`drop${dragging ? ' is-over' : ''}`}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          void files(event.dataTransfer.files);
        }}
      >
        <ArtBadge name="papers" size={104} />
        <p className="title-m">Kéo thả slide, giáo trình hoặc ghi chú vào đây</p>
        <p className="meta">PDF, Word, PowerPoint, văn bản hoặc ảnh chụp · tối đa 50 MB mỗi file · nhiều file sẽ gộp thành một bộ</p>
        <input ref={input} type="file" multiple accept={ACCEPT} hidden onChange={(event) => event.target.files && void files(event.target.files)} />
        <button type="button" className="btn btn--primary btn--lg" disabled={busy} onClick={() => input.current?.click()}>
          <Icon name="upload" size={18} /> Chọn file
        </button>
        {rows.length > 0 && (
          <ul className="upload-rows">
            {rows.map((row) => (
              <li key={row.name} className={`upload-row upload-row--${row.state}`}>
                <Icon name={row.state === 'done' ? 'check' : row.state === 'failed' ? 'x' : 'file'} size={16} />
                <span>{row.name}</span>
                <span className="meta">{row.state === 'reading' ? 'Đang đọc nội dung…' : row.state === 'done' ? 'Đã đọc' : row.message}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
      {problem && <ProblemNotice problem={problem} compact />}

      <div className="create-source__more">
        <section className="panel">
          <button type="button" className="link" aria-expanded={paste.open} onClick={() => setPaste((p) => ({ ...p, open: !p.open }))}>
            <Icon name="edit" size={16} /> Dán văn bản thay vì tải file
          </button>
          {paste.open && (
            <div className="paste enter">
              <input className="field" placeholder="Tên tài liệu" value={paste.name} onChange={(e) => setPaste((p) => ({ ...p, name: e.target.value }))} />
              <textarea className="field" rows={6} placeholder="Dán nội dung bài học…" value={paste.text} onChange={(e) => setPaste((p) => ({ ...p, text: e.target.value }))} />
              <button type="button" className="btn btn--secondary" disabled={!paste.text.trim()} onClick={() => void pasteText()}>
                Dùng văn bản này
              </button>
            </div>
          )}
        </section>
        <section className="panel">
          <p className="eyebrow">Tài liệu đã tải trước đây</p>
          {recent === null && <div className="skeleton" style={{ height: 40 }} />}
          {recent?.length === 0 && <p className="meta">Chưa có tài liệu nào.</p>}
          <ul className="recent-sources">
            {recent?.map((source) => (
              <li key={source.id}>
                <button type="button" className="recent-source" onClick={() => void reuse(source.id)}>
                  <Icon name="file" size={16} />
                  <span>{source.metadata.name}</span>
                  <span className={`tag${source.reviewed ? ' tag--sage' : ''}`}>{source.reviewed ? 'đã kiểm tra' : 'cần kiểm tra'}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}

/* Step 2 ------------------------------------------------------------------ */
function ReviewStep({ source, onReviewed }: { source: SourceDoc; onReviewed: (source: SourceDoc) => void }) {
  const [texts, setTexts] = useState(() => source.fragments.map((f) => f.text));
  const [editing, setEditing] = useState<number | null>(null);
  const [shown, setShown] = useState(12);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);
  const fix = makeTextFix([]);
  const changed = texts.filter((t, i) => t !== source.fragments[i].text).length;

  const confirm = async () => {
    setBusy(true);
    setProblem(null);
    try {
      onReviewed(await api<SourceDoc>(`/sources/${source.id}/review`, { body: { expected_revision: source.revision, texts } }));
    } catch (error) {
      setProblem(describeError(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="create-review">
      <header className="create-review__head">
        <Mascot mood="hint" size={64} />
        <div>
          <p className="title-m">
            Mình đã đọc “{source.metadata.name}” thành {source.fragments.length} đoạn
          </p>
          <p className="meta">Lướt qua xem chữ có bị sai hoặc thiếu không. Sửa trực tiếp nếu cần — AI sẽ học đúng bản bạn xác nhận.</p>
        </div>
      </header>
      {source.metadata.warnings.length > 0 && (
        <details className="notice notice--butter">
          <summary className="notice__title">Lưu ý khi đối chiếu ({source.metadata.warnings.length})</summary>
          <ul>
            {source.metadata.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </details>
      )}
      <ol className="fragments">
        {source.fragments.slice(0, shown).map((fragment, i) => (
          <li key={fragment.id} className={texts[i] !== fragment.text ? 'fragment is-edited' : 'fragment'}>
            <div className="fragment__head">
              <span className="tag">{locatorLabel(fragment.locator)}</span>
              <button type="button" className="link link--quiet" onClick={() => setEditing(editing === i ? null : i)}>
                <Icon name="edit" size={14} /> {editing === i ? 'Xong' : 'Sửa'}
              </button>
            </div>
            {editing === i ? (
              <textarea className="field" rows={5} value={texts[i]} onChange={(event) => setTexts((all) => all.map((t, j) => (j === i ? event.target.value : t)))} />
            ) : (
              <p className="fragment__text">{fix(texts[i])}</p>
            )}
          </li>
        ))}
      </ol>
      {shown < source.fragments.length && (
        <button type="button" className="link" onClick={() => setShown((n) => n + 24)}>
          Xem thêm {Math.min(24, source.fragments.length - shown)} đoạn (còn {source.fragments.length - shown})
        </button>
      )}
      {problem && <ProblemNotice problem={problem} compact />}
      <footer className="create-foot">
        <span className="meta">{changed ? `Bạn đã sửa ${changed} đoạn.` : 'Chưa sửa đoạn nào.'}</span>
        <button type="button" className="btn btn--primary btn--lg" onClick={() => void confirm()} disabled={busy} aria-busy={busy}>
          Bản đọc ổn — tiếp tục <Icon name="arrowRight" size={18} />
        </button>
      </footer>
    </div>
  );
}

/* Step 3 ------------------------------------------------------------------ */
interface Reading {
  status: string;
  continuation_required?: boolean;
  read_parts?: number;
  total_parts?: number;
}

interface ReadingState {
  read: number;
  total: number | null;
  synthesizing: boolean;
}

function ReadStep({
  source,
  draft,
  onDraft,
  onReady,
}: {
  source: SourceDoc;
  draft: Draft;
  onDraft: (patch: Partial<Draft>) => void;
  onReady: (blueprint: BlueprintValue & { id: string }) => void;
}) {
  const { priceOf, refreshWallet } = useApp();
  const price = priceOf('blueprint');
  const [running, setRunning] = useState<ReadingState | null>(null);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [quote, setQuote] = useState<{ quote: CoinQuote; confirm: () => Promise<AiStart<Reading>> } | null>(null);
  const characters = source.fragments.reduce((n, f) => n + f.text.length, 0);

  const finish = useCallback(async () => {
    const value = await api<{ status: string } & BlueprintValue & { id: string }>(`/sources/${source.id}/blueprint`);
    if (value.status === 'ready') onReady(value);
  }, [source.id, onReady]);

  const watch = {
    onUpdate: (job: Job) => {
      const chapter = job.progress?.chapter_context;
      if (chapter) setRunning({ read: chapter.read_parts ?? 0, total: chapter.total_parts ?? null, synthesizing: chapter.status === 'synthesizing' });
    },
  };

  const handle = async (outcome: AiOutcome<Reading>): Promise<void> => {
    refreshWallet();
    if (outcome.kind === 'quote') {
      setRunning(null);
      setQuote({ quote: outcome.quote, confirm: outcome.confirm });
      return;
    }
    if (outcome.kind === 'failed') {
      setRunning(null);
      setProblem(describeJobFailure(outcome.job));
      return;
    }
    if (outcome.value?.continuation_required) {
      // A long document continues in the next job; parts already read are not read again.
      setRunning({ read: outcome.value.read_parts ?? 0, total: outcome.value.total_parts ?? null, synthesizing: false });
      return run(outcome.job?.id ?? `resume-${Date.now()}`);
    }
    await finish();
  };

  const run = async (resume?: string): Promise<void> => {
    setProblem(null);
    setQuote(null);
    setRunning((r) => r ?? { read: 0, total: null, synthesizing: false });
    try {
      const body = { expected_revision: source.revision, goal: draft.goal, notes: draft.notes, ...(resume ? { resume_job_id: resume } : {}) };
      await handle(await askAi<Reading>(`/sources/${source.id}/blueprint`, body, price, watch));
    } catch (error) {
      setRunning(null);
      setProblem(describeError(error));
    }
  };

  const confirmQuote = async () => {
    const current = quote;
    if (!current) return;
    setQuote(null);
    setRunning({ read: 0, total: null, synthesizing: false });
    try {
      await handle(await settleAi(await current.confirm(), watch));
    } catch (error) {
      setRunning(null);
      setProblem(describeError(error));
    }
  };

  // A roadmap finished earlier (another tab, a reload) opens directly.
  useEffect(() => {
    api<{ status: string }>(`/sources/${source.id}/blueprint`)
      .then((value) => {
        if (value.status === 'ready') void finish();
      })
      .catch(() => undefined);
  }, [source.id, finish]);

  if (running) {
    const total = running.total;
    return (
      <div className="create-read is-running" aria-live="polite">
        <Mascot mood="think" size={110} bob />
        <p className="display-title">{running.synthesizing ? 'Đang sắp xếp thành chương và bài…' : 'Kẹp đang đọc toàn bộ tài liệu…'}</p>
        <ol className="stages">
          <li className={`stage ${total && running.read >= total ? 'stage--done' : 'stage--active'}`}>
            <span className="stage__dot">{total && running.read >= total ? <Icon name="check" size={14} /> : null}</span>
            Đọc hết {source.fragments.length} đoạn{total ? ` · ${running.read}/${total} phần` : ''}
          </li>
          <li className={`stage ${running.synthesizing ? 'stage--active' : ''}`}>
            <span className="stage__dot" />
            Chia chương, bài và gợi ý cách học
          </li>
        </ol>
        <p className="meta">Phần đã đọc được lưu lại — rời trang rồi quay lại vẫn tiếp tục được. Tài liệu dài sẽ đọc làm nhiều lượt.</p>
      </div>
    );
  }

  return (
    <div className="create-read">
      <div className="create-read__intro">
        <Mascot mood="hello" size={96} />
        <div>
          <p className="title-l">Để Kẹp đọc hết tài liệu trước khi chia bài</p>
          <p>
            Mình sẽ đọc toàn bộ {source.fragments.length} đoạn (~{Math.round(characters / 1000)} nghìn ký tự), rồi đề xuất chương và bài, phần nên tập trung,
            cách ôn, quy tắc khi soạn bài và ngôn ngữ phù hợp. Bạn sửa được tất cả trước khi tạo khóa.
          </p>
        </div>
      </div>
      <div className="create-read__form">
        <label>
          <span className="eyebrow">Bạn học để làm gì? (không bắt buộc)</span>
          <input className="field" value={draft.goal} maxLength={1000} placeholder="Ví dụ: ôn thi giữa kỳ, nắm chắc cách chia subnet" onChange={(e) => onDraft({ goal: e.target.value })} />
        </label>
        <label>
          <span className="eyebrow">Dặn thêm AI (không bắt buộc)</span>
          <textarea
            className="field"
            rows={3}
            maxLength={2000}
            value={draft.notes}
            placeholder="Ví dụ: giữ thuật ngữ tiếng Anh, thêm nhiều ví dụ tính toán, bỏ phần lịch sử"
            onChange={(e) => onDraft({ notes: e.target.value })}
          />
        </label>
      </div>
      {quote && <CoinConfirm quote={quote.quote} what="Đọc toàn bộ tài liệu" onCancel={() => setQuote(null)} onConfirm={() => void confirmQuote()} />}
      {problem && <ProblemNotice problem={problem} onRetry={() => void run()} compact />}
      <footer className="create-foot">
        <a className="link link--quiet" href="/legacy/#live">
          Không dùng AI? Chia bài theo trang ở bản cũ
        </a>
        <button type="button" className="btn btn--primary btn--lg" onClick={() => void run()}>
          <Icon name="sparkle" size={18} /> Để Kẹp đọc toàn bộ {price > 0 && <span className="price">{price} Coin</span>}
        </button>
      </footer>
    </div>
  );
}

/* Page ------------------------------------------------------------------- */
export function CreatePage() {
  const [draft, setDraft] = useState<Draft>(loadDraft);
  const [source, setSource] = useState<SourceDoc | null>(null);
  const [blueprint, setBlueprint] = useState<(BlueprintValue & { id: string }) | null>(null);
  const [step, setStep] = useState<Step>('source');
  const [loading, setLoading] = useState(Boolean(draft.sourceId));
  const [problem, setProblem] = useState<Problem | null>(null);

  const patch = useCallback((value: Partial<Draft>) => {
    setDraft((current) => {
      const next = { ...current, ...value };
      keepDraft(next);
      return next;
    });
  }, []);

  const useSource = useCallback(
    async (value: SourceDoc) => {
      setSource(value);
      setBlueprint(null);
      patch({ sourceId: value.id });
      if (!value.reviewed) return setStep('review');
      const saved = await api<{ status: string } & BlueprintValue & { id: string }>(`/sources/${value.id}/blueprint`).catch(() => null);
      if (saved?.status === 'ready') {
        setBlueprint(saved);
        setStep('roadmap');
      } else setStep('read');
    },
    [patch],
  );

  // Resume an unfinished draft (reload, coming back later).
  useEffect(() => {
    if (!draft.sourceId) return;
    ensureSession()
      .then(() => api<SourceDoc>(`/sources/${draft.sourceId}`))
      .then((value) => useSource(value))
      .catch(() => patch({ sourceId: null }))
      .finally(() => setLoading(false));
  }, []);

  const restart = () => {
    patch({ sourceId: null, goal: '', notes: '' });
    setSource(null);
    setBlueprint(null);
    setStep('source');
    setProblem(null);
  };

  const at = STEPS.findIndex(([s]) => s === step);
  return (
    <div className="page create">
      <PageHeader
        title="Tạo khóa mới"
        tone="butter"
        note="Đưa slide, giáo trình hay ghi chú vào đây — Kẹp đọc hết rồi gợi ý lộ trình để bạn sửa trước khi học."
        art={<Mascot pose="wand" mood="wink" size={100} pettable />}
        actions={
          source && (
            <button type="button" className="btn btn--secondary" onClick={restart}>
              <Icon name="refresh" size={16} /> Chọn tài liệu khác
            </button>
          )
        }
      />
      <ol className="create-steps" aria-label="Các bước tạo khóa">
        {STEPS.map(([value, label], i) => (
          <li key={value} className={i < at ? 'is-done' : i === at ? 'is-current' : ''} aria-current={i === at ? 'step' : undefined}>
            <span className="create-steps__num">{i < at ? <Icon name="check" size={14} /> : i + 1}</span>
            {label}
          </li>
        ))}
      </ol>
      {problem && <ProblemNotice problem={problem} onRetry={restart} retryLabel="Bắt đầu lại" />}
      {loading ? (
        <LoadingRows rows={2} label="Đang mở bản nháp…" />
      ) : (
        <div key={step} className="create-body enter">
          {step === 'source' && <SourceStep onSource={(value) => void useSource(value).catch((error) => setProblem(describeError(error)))} />}
          {step === 'review' && source && <ReviewStep source={source} onReviewed={(value) => void useSource(value)} />}
          {step === 'read' && source && (
            <ReadStep
              source={source}
              draft={draft}
              onDraft={patch}
              onReady={(value) => {
                setBlueprint(value);
                setStep('roadmap');
              }}
            />
          )}
          {step === 'roadmap' && source && blueprint && (
            <RoadmapStep
              source={source}
              blueprint={blueprint}
              notes={draft.notes}
              onReread={() => setStep('read')}
              onCreated={() => patch({ sourceId: null, goal: '', notes: '' })}
            />
          )}
        </div>
      )}
    </div>
  );
}
