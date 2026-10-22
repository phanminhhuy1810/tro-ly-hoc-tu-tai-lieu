import type { CoinQuote } from '../../api/types';
import { BRAND_OPTIONS, BrandMark } from '../../components/Brand';
import { CoinConfirm } from '../../components/CoinConfirm';
import { Icon } from '../../components/Icon';
import { Mascot, type Mood, type Pose } from '../../components/Mascot';
import { ArtBadge } from '../../components/Art';
import { EmptyState, LoadingRows, ProblemNotice } from '../../components/StateViews';
import { describeError, describeJobFailure } from '../../lib/copy';
import { ApiError } from '../../api/client';
import { JobCard } from '../course/JobCard';
import type { Unit } from '../../api/types';

// Design review page: every state rendered with ILLUSTRATIVE data so they can be
// compared without forcing errors on the real backend. Nothing here calls the API.

const unit: Unit = { id: 'demo', title: 'Địa chỉ IP Classful: Cấu trúc và tính toán', source_refs: [], data: null };
const quote = (insufficient: boolean): CoinQuote => ({
  code: 'COIN_CONFIRMATION_REQUIRED',
  quote_id: 'demo',
  amount: insufficient ? 6 : 1,
  task: 'inline_help',
  insufficient_coin: insufficient,
  wallet: { balance: 1, held: 0, available: 1, enforcement_enabled: true },
});

function Frame({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="demo-frame">
      <p className="eyebrow">{title}</p>
      <div className="demo-frame__body">{children}</div>
    </section>
  );
}

export function StatesPage() {
  const moods: [Mood, string][] = [
    ['hello', 'Chào / mở chat'],
    ['hint', 'Gợi ý'],
    ['think', 'Đang làm'],
    ['happy', 'Hoàn thành'],
    ['oops', 'Có lỗi'],
    ['wink', 'Nháy mắt'],
    ['love', 'Thích quá'],
    ['surprised', 'Ngạc nhiên'],
    ['sad', 'Buồn'],
    ['smug', 'Láo láo'],
  ];
  return (
    <div className="page states">
      <header className="page-head">
        <div>
          <p className="eyebrow">Trang mẫu · dữ liệu minh họa, không gọi máy chủ</p>
          <h1 className="page-title">Các trạng thái</h1>
        </div>
        <a className="btn btn--secondary" href="#/">
          <Icon name="arrowLeft" size={18} /> Về Học tiếp
        </a>
      </header>

      <Frame title="Logo — 3 phương án (đang dùng: Kẹp)">
        <div className="brand-compare">
          {BRAND_OPTIONS.map((option, i) => (
            <figure key={option.id} className={i === 0 ? 'brand-sample is-current' : 'brand-sample'}>
              <div className="brand-sample__marks">
                <BrandMark option={option.id} size={96} />
                <BrandMark option={option.id} size={40} />
                <BrandMark option={option.id} size={18} />
              </div>
              <figcaption>
                <span className="title-m">
                  {option.name} {i === 0 && <span className="tag tag--sage">đang dùng</span>}
                </span>
                <span className="meta">{option.note}</span>
              </figcaption>
            </figure>
          ))}
        </div>
      </Frame>

      <Frame title="Nhân vật “Kẹp” — bấm vào mèo để nó nhảy và đổi mặt">
        <div className="mood-row">
          {moods.map(([mood, label]) => (
            <figure key={mood}>
              <Mascot mood={mood} size={92} pettable />
              <figcaption className="meta">{label}</figcaption>
            </figure>
          ))}
        </div>
      </Frame>

      <Frame title="Mèo dọc lộ trình — làm sẵn, khóa nào cũng có">
        <div className="mood-row">
          {(
            [
              ['book', 'Đọc sách'],
              ['mug', 'Ôm cốc cà phê'],
              ['laptop', 'Ngồi laptop'],
              ['flag', 'Cầm cờ'],
              ['sleep', 'Ngủ chờ bài sau'],
            ] as [Pose, string][]
          ).map(([pose, label]) => (
            <figure key={pose}>
              <Mascot pose={pose} size={92} pettable />
              <figcaption className="meta">{label}</figcaption>
            </figure>
          ))}
        </div>
      </Frame>

      <Frame title="Nút">
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <button type="button" className="btn btn--primary btn--lg">
            Học tiếp <Icon name="arrowRight" size={18} />
          </button>
          <button type="button" className="btn btn--secondary">Về lộ trình</button>
          <button type="button" className="chip">
            <Icon name="bulb" size={16} /> Gợi ý
          </button>
          <button type="button" className="chip" aria-pressed="true">
            <Icon name="check" size={16} /> Đã gắn câu 2
          </button>
          <button type="button" className="link">Đọc lại phần “Prefix /26”</button>
        </div>
      </Frame>

      <Frame title="Đang tải">
        <LoadingRows rows={2} />
      </Frame>

      <Frame title="Chưa có khóa nào">
        <EmptyState
          art={<ArtBadge name="sparkles" size={110} />}
          title="Chưa có khóa nào"
          body="Chọn slide, giáo trình hoặc ghi chú của bạn — mình đọc rồi đề xuất lộ trình để bạn duyệt trước khi tạo bài."
          action={<button className="btn btn--primary btn--lg">Chọn tài liệu</button>}
        />
      </Frame>

      <Frame title="Đang tạo bài (tiến độ lấy từ máy chủ)">
        <JobCard
          state={{
            phase: 'running',
            unit,
            jobId: 'demo',
            startedAt: Date.now() - 64_000,
            job: {
              id: 'demo',
              task: 'lesson',
              status: 'running',
              result: null,
              error: null,
              progress: {
                phase: 'receiving',
                planned_stages: 7,
                saved_stages: 2,
                requests: [
                  { index: 1, schema: 'ChapterBrief', phase: 'received' },
                  { index: 2, schema: 'LessonReading', phase: 'received' },
                  { index: 3, schema: 'McqDraft', phase: 'receiving' },
                ],
              },
            },
          }}
          onCancel={() => {}}
          onRetry={() => {}}
          onContinue={() => {}}
          onDismiss={() => {}}
        />
      </Frame>

      <Frame title="Lỗi có cách phục hồi">
        <div style={{ display: 'grid', gap: 12 }}>
          <ProblemNotice problem={describeJobFailure({ status: 'failed', error: { code: 'CONNECTION_FAILED', message: 'Không kết nối được 127.0.0.1:11434' } })} onRetry={() => {}} />
          <ProblemNotice problem={describeError(new ApiError(0, '', 'NETWORK'))} onRetry={() => {}} />
          <ProblemNotice problem={describeError(new ApiError(409, 'Khóa học đã đổi; tải lại trước khi tạo.'))} onRetry={() => {}} retryLabel="Tải bản mới" />
        </div>
      </Frame>

      <Frame title="Xác nhận Coin trước khi gọi AI">
        <div style={{ display: 'grid', gap: 12 }}>
          <CoinConfirm quote={quote(false)} what="Hỏi AI" onConfirm={() => {}} onCancel={() => {}} />
          <CoinConfirm quote={quote(true)} what="Tạo bài này" onConfirm={() => {}} onCancel={() => {}} />
        </div>
      </Frame>
    </div>
  );
}
