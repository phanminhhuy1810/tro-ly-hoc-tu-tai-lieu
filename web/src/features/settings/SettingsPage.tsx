import { useState } from 'react';
import { api, ApiError, ensureSession } from '../../api/client';
import type { AiCatalog, AiModel, CoinPolicy } from '../../api/types';
import { useApp, useLoad, type MotionPref } from '../../app/store';
import { Icon } from '../../components/Icon';
import { LoadingRows, ProblemNotice } from '../../components/StateViews';
import { describeError } from '../../lib/copy';

const PRICE_LABEL: Record<string, string> = {
  inline_help: 'Hỏi Kẹp trong bài / trong câu',
  chat: 'Hỏi chung',
  blueprint: 'Kẹp đọc toàn bộ tài liệu để đề xuất lộ trình',
  outline: 'Phác thảo lộ trình (bản cũ)',
  correction: 'Nhờ AI sửa nội dung',
  source_vision: 'Nhờ AI đọc lại một trang ảnh',
  subject_analysis: 'Gợi ý môn học',
  short_feedback: 'Nhận xét câu tự luận',
};

function status(model: AiModel): { text: string; tone: 'sage' | 'butter' | 'coral' } {
  if (!model.enabled) return { text: 'Người vận hành chưa bật', tone: 'coral' };
  if (!model.configured) return { text: 'Thiếu cấu hình', tone: 'coral' };
  if (!model.ready) return { text: 'Chưa sẵn sàng (chưa chạy?)', tone: 'butter' };
  return { text: 'Sẵn sàng', tone: 'sage' };
}

/**
 * Cài đặt: which AI writes lessons and answers, what leaves the machine, and
 * what each AI action costs in Coin. Keys stay on the server; this screen
 * never shows or asks for one.
 */
export function SettingsPage() {
  const { toast, motion, setMotion } = useApp();
  const state = useLoad(async () => {
    await ensureSession();
    const [catalog, policy] = await Promise.all([api<AiCatalog>('/ai/models'), api<CoinPolicy>('/coin/policy')]);
    return { catalog, policy };
  }, []);
  const [pending, setPending] = useState<string | null>(null);
  const [allowExternal, setAllowExternal] = useState<string | null>(null);

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
    ['system', 'Theo hệ thống'],
    ['off', 'Tắt chuyển động'],
  ];

  return (
    <div className="page settings-page">
      <header className="page-head">
        <div>
          <p className="eyebrow">AI, chuyển động và Coin</p>
          <h1 className="page-title">Cài đặt</h1>
        </div>
      </header>

      {state.loading && !state.data && <LoadingRows rows={3} label="Đang mở cài đặt…" />}
      {state.error != null && <ProblemNotice problem={describeError(state.error)} onRetry={state.reload} />}

      {state.data && (
        <>
          <section className="panel-card">
            <h2 className="title-m">AI dùng để soạn bài và trả lời</h2>
            <p className="meta">
              Model “trên máy này” chạy bằng Ollama, tài liệu không rời máy. Model ngoài máy sẽ nhận các trích đoạn của bài khi tạo/hỏi. Lựa chọn áp dụng cho
              lượt mới; bài đã tạo giữ nguyên.
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
                        {model.id === state.data!.catalog.default_model_id ? ' · mặc định của máy chủ' : ''}
                      </span>
                      <span className={`tag tag--${s.tone}`}>{s.text}</span>
                    </div>
                    {selected ? (
                      <span className="tag tag--sage">
                        <Icon name="check" size={14} /> Đang dùng
                      </span>
                    ) : (
                      <button type="button" className="btn btn--secondary btn--sm" disabled={!model.selectable || pending !== null} aria-busy={pending === model.id} onClick={() => void choose(model)}>
                        {allowExternal === model.id ? 'Đồng ý gửi trích đoạn & dùng' : 'Dùng model này'}
                      </button>
                    )}
                    {allowExternal === model.id && (
                      <p className="notice notice--butter model__warn">
                        Model này chạy ngoài máy: các trích đoạn tài liệu của bài sẽ được gửi tới nhà cung cấp khi bạn tạo bài hoặc hỏi. Bấm lại để đồng ý.
                      </p>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>

          <div className="progress-grid">
            <section className="panel-card">
              <h2 className="title-m">Chuyển động</h2>
              <p className="meta">Hiệu ứng mở bài và chuyển trang. “Tắt” giúp dễ chịu hơn nếu bạn hay chóng mặt.</p>
              <div className="segmented" role="radiogroup" aria-label="Chuyển động">
                {motionOptions.map(([value, label]) => (
                  <button key={value} type="button" role="radio" aria-checked={motion === value} onClick={() => setMotion(value)}>
                    {label}
                  </button>
                ))}
              </div>
            </section>

            <section className="panel-card">
              <h2 className="title-m">Giá Coin của từng việc AI</h2>
              <p className="meta">
                {state.data.policy.enforcement_enabled ? 'Mức đề xuất, còn chờ chốt. Lời giải và bài đã lưu luôn dùng miễn phí.' : 'Máy chủ đang tắt tính Coin.'}
              </p>
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
            </section>
          </div>

        </>
      )}
    </div>
  );
}
