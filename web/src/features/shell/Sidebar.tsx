import { hrefFor, type Route } from '../../app/router';
import { useApp } from '../../app/store';
import { BrandMark } from '../../components/Brand';
import { Icon, type IconName } from '../../components/Icon';

interface NavItem {
  label: string;
  icon: IconName;
  href: string;
  active: boolean;
}

export function Sidebar({ route }: { route: Route }) {
  const { wallet } = useApp();
  const items: NavItem[] = [
    { label: 'Học tiếp', icon: 'home', href: '#/', active: route.name === 'home' || route.name === 'course' || route.name === 'practice' },
    { label: 'Thư viện', icon: 'library', href: hrefFor({ name: 'library' }), active: route.name === 'library' },
    {
      label: 'Cùng học',
      icon: 'users',
      href: hrefFor({ name: 'community' }),
      active: route.name === 'community' || route.name === 'share' || route.name === 'rooms' || route.name === 'room',
    },
    { label: 'Sổ tay', icon: 'notebook', href: hrefFor({ name: 'notebook' }), active: route.name === 'notebook' },
    { label: 'Tiến độ', icon: 'chart', href: hrefFor({ name: 'progress' }), active: route.name === 'progress' },
    { label: 'Cài đặt', icon: 'settings', href: hrefFor({ name: 'settings' }), active: route.name === 'settings' },
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
          </a>
        ))}
      </nav>
      <div className="sidebar__bottom">
        <a className="btn btn--secondary btn--block" href={hrefFor({ name: 'create' })} aria-current={route.name === 'create' ? 'page' : undefined}>
          <Icon name="plus" size={18} /> Tạo khóa mới
        </a>
        <a className="coin-chip coin-chip--link" href={hrefFor({ name: 'progress' })} title="Coin dùng cho lượt hỏi/tạo bằng AI. Bài và lời giải đã lưu luôn dùng được.">
          <Icon name="coin" size={18} />
          {wallet ? `${wallet.available} Coin` : '— Coin'}
        </a>
        <a className="sidebar__foot" href="#/mau-trang-thai">
          Xem mẫu trạng thái và logo
        </a>
      </div>
    </aside>
  );
}
