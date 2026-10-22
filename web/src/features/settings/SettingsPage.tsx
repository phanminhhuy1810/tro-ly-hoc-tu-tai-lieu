import { useEffect, useRef, useState } from 'react';
import { api, ApiError, ensureSession } from '../../api/client';
import type { AiCatalog, AiModel, CoinPolicy, Wallet } from '../../api/types';
import { useApp, useLoad, type MotionPref } from '../../app/store';
import { CountUp } from '../../components/CountUp';
import { Icon } from '../../components/Icon';
import { Mascot } from '../../components/Mascot';
import { PageHeader } from '../../components/PageHeader';
import { ArtBadge } from '../../components/Art';
import { LoadingRows, ProblemNotice } from '../../components/StateViews';
import { describeError } from '../../lib/copy';

const PRICE_LABEL: Record<string, string> = {
  inline_help: 'Hỏi Kẹp trong bài / trong câu',
  chat: 'Hỏi chung',
  blueprint: 'Kẹp đọc cả tài liệu để gợi ý lộ trình',
  outline: 'Phác thảo lộ trình (bản cũ)',
  correction: 'Nhờ Kẹp sửa nội dung',
  source_vision: 'Nhờ Kẹp đọc lại một trang ảnh',
  subject_analysis: 'Đoán môn học',
  short_feedback: 'Nhận xét câu tự luận',
};

const CATEGORY: Record<string, string> = {
  onboarding: 'Coin chào mừng',
  ai_spend: 'Hỏi / tạo bằng AI',
  learning: 'Học và ôn',
  mission: 'Nhiệm vụ ngày',
  achievement: 'Thành tựu',
  community: 'Được người khác thích khóa',
};

interface TutorStyle {
  persona: string;
  emphasis: string;
  version: number;
  max_length: number;
}

const PERSONAS = ['Gia sư kiên nhẫn, giải thích từng bước', 'Bạn cùng lớp vui tính, nói chuyện thoải mái', 'Thầy cô nghiêm khắc, đi thẳng vào ý chính', 'Mèo mọt sách hơi láo nhưng cực giỏi'];
const EMPHASES = ['Ví dụ đời thường', 'Công thức và cách tính', 'Lỗi hay gặp', 'Thuật ngữ tiếng Anh', 'Tóm tắt thật ngắn'];

/** “Bạn sẽ là…, nhớ nhấn mạnh…”: one style for Kẹp across every course; each course still keeps its own notes. */
function TutorStyleCard() {
  const { toast } = useApp();
  const [saved, setSaved] = useState<TutorStyle | null>(null);
  const [persona, setPersona] = useState('');
  const [emphasis, setEmphasis] = useState('');
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<unknown>(null);

  const load = () =>
    api<TutorStyle>('/tutor-style')
      .then((value) => {
        setSaved(value);
        setPersona(value.persona);
        setEmphasis(value.emphasis);
      })
      .catch(setProblem);
  useEffect(() => {
    void load();
  }, []);

  const toggleEmphasis = (item: string) => {
    const parts = emphasis
      .split(',')
      .map((p) => p.trim())
      .filter(Boolean);
    const next = parts.includes(item) ? parts.filter((p) => p !== item) : [...parts, item];
    setEmphasis(next.join(', '));
  };

  const save = async () => {
    if (!saved) return;
    setBusy(true);
    try {
      const value = await api<TutorStyle>('/tutor-style', { method: 'PUT', body: { persona, emphasis, expected_version: saved.version } });
      setSaved(value);
      toast('Kẹp sẽ trả lời theo kiểu này ở mọi khóa');
    } catch (error) {
      toast(error instanceof ApiError && error.status === 409 ? 'Vừa có thay đổi ở cửa sổ khác — đã tải lại' : describeError(error).title);
      if (error instanceof ApiError && error.status === 409) void load();
    } finally {
      setBusy(false);
    }
  };

  const max = saved?.max_length ?? 300;
  const changed = saved !== null && (persona.trim() !== saved.persona || emphasis.trim() !== saved.emphasis);
  return (
    <section className="panel-card tutor-style">
      <div className="tutor-style__head">
        <Mascot mood="hint" size={64} />
        <div>
          <h2 className="title-m">Kẹp dạy bạn theo kiểu nào?</h2>
          <p className="meta">Dặn một lần, Kẹp nhớ ở mọi khóa khi bạn chat hay hỏi trong câu. Mỗi khóa vẫn có ghi chú riêng trong thẻ “Kẹp nhớ gì về bạn”.</p>
        </div>
      </div>
      {problem != null && <ProblemNotice problem={describeError(problem)} compact />}
      <label className="tutor-style__field">
        <span className="eyebrow">Bạn sẽ là…</span>
        <textarea className="field" rows={2} maxLength={max} value={persona} placeholder="Ví dụ: gia sư kiên nhẫn, nói ngắn gọn, hay hỏi lại để mình tự nghĩ" onChange={(e) => setPersona(e.target.value)} disabled={!saved} />
      </label>
      <div className="chips">
        {PERSONAS.map((item) => (
          <button key={item} type="button" className="chip" aria-pressed={persona === item} onClick={() => setPersona(item)} disabled={!saved}>
            {item}
          </button>
        ))}
      </div>
      <label className="tutor-style__field">
        <span className="eyebrow">Luôn nhấn mạnh…</span>
        <textarea className="field" rows={2} maxLength={max} value={emphasis} placeholder="Ví dụ: công thức, lỗi hay gặp, giữ thuật ngữ tiếng Anh" onChange={(e) => setEmphasis(e.target.value)} disabled={!saved} />
      </label>
      <div className="chips">
        {EMPHASES.map((item) => (
          <button key={item} type="button" className="chip" aria-pressed={emphasis.split(',').map((p) => p.trim()).includes(item)} onClick={() => toggleEmphasis(item)} disabled={!saved}>
            {item}
          </button>
        ))}
      </div>
      <div className="tutor-style__foot">
        <span className="meta">Kẹp vẫn chỉ trả lời theo tài liệu của bạn; phần này đổi giọng và điểm nhấn, không đổi kiến thức.</span>
        <button type="button" className="btn btn--primary" disabled={!changed || busy} aria-busy={busy} onClick={() => void save()}>
          Lưu cách dạy
        </button>
      </div>
    </section>
  );
}

interface Ledger {
  ledger: { amount: number; reason: string; category: string | null; created_at: string }[];
}

function status(model: AiModel): { text: string; tone: 'sage' | 'butter' | 'coral' } {
  if (!model.enabled) return { text: 'Người vận hành chưa bật', tone: 'coral' };
  if (!model.configured) return { text: 'Thiếu cấu hình', tone: 'coral' };
  if (!model.ready) return { text: 'Chưa chạy (mở Ollama?)', tone: 'butter' };
  return { text: 'Sẵn sàng', tone: 'sage' };
}

/** Coin history stays folded away until someone wants to look. */
function CoinHistory({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  const [ledger, setLedger] = useState<Ledger['ledger'] | null>(null);
  const [problem, setProblem] = useState<unknown>(null);
  useEffect(() => {
    if (!open || ledger) return;
    api<Ledger>('/wallet/history')
      .then((value) => setLedger(value.ledger))
      .catch(setProblem);
  }, [open, ledger]);
  return (
    <div className="coin-history">
      <button type="button" className="btn btn--secondary btn--sm" aria-expanded={open} onClick={onToggle}>
        <Icon name={open ? 'up' : 'down'} size={16} /> {open ? 'Ẩn lịch sử Coin' : 'Xem lịch sử Coin'}
      </button>
      {open && (
        <div className="coin-history__body enter">
          {problem != null && <ProblemNotice problem={describeError(problem)} compact />}
          {!ledger && problem == null && <div className="skeleton" style={{ height: 80 }} />}
          {ledger && ledger.length === 0 && <p className="meta">Chưa có lần nhận hay dùng Coin nào.</p>}
          {ledger && ledger.length > 0 && (
            <ul className="ledger">
              {ledger.slice(0, 40).map((row, i) => (
                <li key={i}>
                  <span className={row.amount >= 0 ? 'ledger__amount is-plus' : 'ledger__amount'}>{row.amount >= 0 ? `+${row.amount}` : row.amount}</span>
                  <span>{CATEGORY[row.category ?? ''] ?? row.reason}</span>
                  <span className="meta">{new Intl.DateTimeFormat('vi-VN', { day: 'numeric', month: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(row.created_at))}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Cài đặt: which AI Kẹp uses, what leaves the machine, motion, and Coin
 * (balance, prices, and the history on demand). Keys stay on the server;
 * this screen never shows or asks for one.
 */
export function SettingsPage({ section }: { section?: 'coin' }) {
  const { toast, motion, setMotion } = useApp();
  const state = useLoad(async () => {
    await ensureSession();
    const [catalog, policy, wallet] = await Promise.all([api<AiCatalog>('/ai/models'), api<CoinPolicy>('/coin/policy'), api<Wallet>('/wallet')]);
    return { catalog, policy, wallet };
  }, []);
  const [pending, setPending] = useState<string | null>(null);
  const [allowExternal, setAllowExternal] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(section === 'coin');
  const coinCard = useRef<HTMLElement>(null);

  useEffect(() => {
    if (section === 'coin' && state.data) coinCard.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [section, Boolean(state.data)]);

  const choose = async (model: AiModel) => {
    if (!state.data) return;
    if (model.external && allowExternal !== model.id) {
      setAllowExternal(model.id);
      return;
    }
    setPending(model.id);
    try {
      await api('/ai/selection', { method: 'PUT', body: { model_id: model.id, expected_revision: state.data.catalog.selection_revision, allow_external: model.external } });
      toast(`Kẹp sẽ dùng ${model.label}`);
      setAllowExternal(null);
      state.reload();
    } catch (error) {
      toast(error instanceof ApiError ? error.message : describeError(error).title);
    } finally {
      setPending(null);
    }
  };

  const motionOptions: [MotionPref, string][] = [
    ['system', 'Theo máy'],
    ['off', 'Tắt chuyển động'],
  ];

  return (
    <div className="page settings-page">
      <PageHeader title="Cài đặt" tone="lilac" note="Chọn AI cho Kẹp, chỉnh chuyển động và xem Coin của bạn." art={<ArtBadge name="gear" size={92} />} />

      {state.loading && !state.data && <LoadingRows rows={3} label="Đang mở cài đặt…" />}
      {state.error != null && <ProblemNotice problem={describeError(state.error)} onRetry={state.reload} />}

      {state.data && (
        <>
          <section className="panel-card">
            <h2 className="title-m">Kẹp dùng AI nào?</h2>
            <p className="meta">
              AI “trên máy này” chạy bằng Ollama nên tài liệu không rời máy. AI ngoài máy sẽ nhận các trích đoạn của bài khi tạo bài hoặc khi bạn hỏi. Đổi ở đây chỉ áp dụng cho lượt sau; bài đã tạo giữ nguyên.
            </p>
            <ul className="models">
              {state.data.catalog.models.map((model) => {
                const s = status(model);
                const selected = model.id === state.data!.catalog.selected_model_id;
                return (
                  <li key={model.id} className={selected ? 'model is-selected' : 'model'}>
                    <div className="model__text">
                      <strong>{model.label}</strong>
                      <span className="meta">
                        <Icon name={model.external ? 'send' : 'home'} size={14} /> {model.external ? 'Gửi trích đoạn ra nhà cung cấp ngoài' : 'Chạy trên máy này, không tốn phí'}
                        {model.id === state.data!.catalog.default_model_id ? ' · mặc định' : ''}
                      </span>
                      <span className={`tag tag--${s.tone}`}>{s.text}</span>
                    </div>
                    {selected ? (
                      <span className="tag tag--sage">
                        <Icon name="check" size={14} /> Đang dùng
                      </span>
                    ) : (
                      <button type="button" className="btn btn--secondary btn--sm" disabled={!model.selectable || pending !== null} aria-busy={pending === model.id} onClick={() => void choose(model)}>
                        {allowExternal === model.id ? 'Đồng ý gửi trích đoạn & dùng' : 'Dùng AI này'}
                      </button>
                    )}
                    {allowExternal === model.id && (
                      <p className="notice notice--butter model__warn">AI này chạy ngoài máy: các trích đoạn tài liệu của bài sẽ được gửi tới nhà cung cấp khi bạn tạo bài hoặc hỏi. Bấm lại để đồng ý.</p>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>

          <TutorStyleCard />

          <div className="settings-pair">
            <section className="panel-card">
              <h2 className="title-m">Chuyển động</h2>
              <p className="meta">Hiệu ứng mở bài, chuyển trang và rê chuột. Chọn “Tắt” nếu bạn dễ chóng mặt.</p>
              <div className="segmented" role="radiogroup" aria-label="Chuyển động">
                {motionOptions.map(([value, label]) => (
                  <button key={value} type="button" role="radio" aria-checked={motion === value} onClick={() => setMotion(value)}>
                    {label}
                  </button>
                ))}
              </div>
            </section>

            <section className="panel-card coin-card" ref={coinCard} id="coin">
              <div className="coin-card__balance">
                <span className="coin-card__icon">
                  <Icon name="coin" size={26} />
                </span>
                <div>
                  <p className="coin-card__value">
                    <CountUp value={state.data.wallet.available} /> Coin
                  </p>
                  <p className="meta">Dùng cho lượt hỏi Kẹp và tạo bằng AI; bài và lời giải đã có luôn xem được.</p>
                </div>
              </div>
              <details className="coin-card__prices">
                <summary>Mỗi việc tốn bao nhiêu Coin?</summary>
                <p className="meta">{state.data.policy.enforcement_enabled ? 'Mức đề xuất, còn chờ chốt.' : 'Máy chủ đang tắt tính Coin.'}</p>
                <ul className="prices">
                  {Object.entries(state.data.policy.prices).map(([task, price]) => (
                    <li key={task}>
                      <span>{PRICE_LABEL[task] ?? task}</span>
                      <strong>{price} Coin</strong>
                    </li>
                  ))}
                  <li>
                    <span>Tạo một bài học</span>
                    <strong>1 + số câu</strong>
                  </li>
                </ul>
              </details>
              <CoinHistory open={historyOpen} onToggle={() => setHistoryOpen((open) => !open)} />
            </section>
          </div>
        </>
      )}
    </div>
  );
}
