import type { CoinQuote } from '../api/types';
import { Icon } from './Icon';

/**
 * Inline confirmation for an AI action that costs Coin. Nothing is queued or
 * held before the learner presses the primary button.
 */
export function CoinConfirm({
  quote,
  what,
  busy,
  onConfirm,
  onCancel,
}: {
  quote: CoinQuote;
  what: string;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const available = quote.wallet?.available ?? 0;
  if (quote.insufficient_coin) {
    return (
      <div className="notice notice--butter coin-confirm" role="alert">
        <Icon name="coin" />
        <div style={{ display: 'grid', gap: 8 }}>
          <p className="notice__title">
            {what} cần {quote.amount} Coin, bạn đang có {available}.
          </p>
          <p className="notice__body">Bài, câu hỏi và lời giải đã lưu vẫn dùng bình thường. Coin có thêm khi bạn hoàn thành lượt luyện.</p>
          <div>
            <button type="button" className="btn btn--secondary btn--sm" onClick={onCancel}>
              Đã hiểu
            </button>
          </div>
        </div>
      </div>
    );
  }
  return (
    <div className="notice notice--butter coin-confirm" role="group" aria-label="Xác nhận dùng Coin">
      <Icon name="coin" />
      <div style={{ display: 'grid', gap: 8 }}>
        <p className="notice__title">
          {what} dùng {quote.amount} Coin · bạn còn {available}
        </p>
        <p className="notice__body">Chỉ trừ khi kết quả được lưu. Lỗi giữa chừng sẽ hoàn lại.</p>
        <div style={{ display: 'flex', gap: 8 }}>
          <button type="button" className="btn btn--primary btn--sm" onClick={onConfirm} aria-busy={busy}>
            Dùng {quote.amount} Coin
          </button>
          <button type="button" className="btn btn--ghost btn--sm" onClick={onCancel}>
            Thôi
          </button>
        </div>
      </div>
    </div>
  );
}
