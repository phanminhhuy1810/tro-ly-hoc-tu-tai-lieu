import { useEffect, useRef, useState } from 'react';
import { hrefFor, type Route } from '../../app/router';
import { useApp, type MotionPref } from '../../app/store';
import { BrandMark } from '../../components/Brand';
import { Icon, type IconName } from '../../components/Icon';

// Screens not rebuilt yet open the previous interface, clearly labelled, so
// no feature disappears while the new frontend grows screen by screen.
const LEGACY = '/legacy/';

interface NavItem {
  label: string;
  icon: IconName;
  href: string;
  active?: boolean;
  legacy?: boolean;
}

function SettingsPopover({ onClose }: { onClose: () => void }) {
  const { motion, setMotion } = useApp();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && onClose();
    const onClick = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) onClose();
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('mousedown', onClick);
    ref.current?.querySelector<HTMLElement>('button')?.focus();
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('mousedown', onClick);
    };
  }, [onClose]);
  const motionOptions: [MotionPref, string][] = [
    ['system', 'Theo hệ thống'],
    ['off', 'Tắt'],
  ];
  return (
    <div className="settings-pop" ref={ref} role="dialog" aria-label="Tùy chỉnh nhanh">
      <p className="eyebrow">Chuyển động</p>
      <div className="segmented" role="radiogroup" aria-label="Chuyển động">
        {motionOptions.map(([value, label]) => (
          <button key={value} type="button" role="radio" aria-checked={motion === value} onClick={() => setMotion(value)}>
            {label}
          </button>
        ))}
      </div>
      <a className="link" href={LEGACY + '#settings'}>
        Nguồn AI và cài đặt khác <span className="tag">bản cũ</span>
      </a>
    </div>
  );
}

export function Sidebar({ route }: { route: Route }) {
  const { wallet } = useApp();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const learning = route.name === 'home' || route.name === 'course';
  const items: NavItem[] = [
    { label: 'Học tiếp', icon: 'home', href: '#/', active: learning },
    { label: 'Thư viện', icon: 'library', href: LEGACY + '#library', legacy: true },
    { label: 'Sổ tay', icon: 'notebook', href: LEGACY + '#notebook', legacy: true },
    { label: 'Tiến độ', icon: 'chart', href: LEGACY + '#dashboard', legacy: true },
  ];
  return (
    <aside className="sidebar" aria-label="Điều hướng chính">
      <a className="brand" href="#/">
        <BrandMark size={40} />
        <span>
          <strong>Folio</strong>
          <small>học từ tài liệu của bạn</small>
        </span>
      </a>
      <nav className="nav">
        {items.map((item) => (
          <a key={item.label} className="nav__item" href={item.href} aria-current={item.active ? 'page' : undefined}>
            <Icon name={item.icon} />
            <span>{item.label}</span>
            {item.legacy && <span className="nav__legacy">bản cũ</span>}
          </a>
        ))}
      </nav>
      <div className="sidebar__bottom">
        <a className="btn btn--secondary btn--block" href={hrefFor({ name: 'create' })} aria-current={route.name === 'create' ? 'page' : undefined}>
          <Icon name="plus" size={18} /> Tạo khóa mới
        </a>
        <div className="sidebar__row">
          <span className="coin-chip" title="Coin dùng cho lượt hỏi AI. Bài và lời giải đã lưu luôn dùng được.">
            <Icon name="coin" size={18} />
            {wallet ? `${wallet.available} Coin` : '— Coin'}
          </span>
          <div style={{ position: 'relative' }}>
            <button type="button" className="icon-btn" aria-expanded={settingsOpen} aria-label="Tùy chỉnh nhanh" onClick={() => setSettingsOpen((v) => !v)}>
              <Icon name="settings" />
            </button>
            {settingsOpen && <SettingsPopover onClose={() => setSettingsOpen(false)} />}
          </div>
        </div>
        <a className="sidebar__foot" href="#/mau-trang-thai">
          Xem mẫu trạng thái và logo
        </a>
      </div>
    </aside>
  );
}
