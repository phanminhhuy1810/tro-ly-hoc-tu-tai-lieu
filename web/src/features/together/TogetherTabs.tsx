import { hrefFor } from '../../app/router';
import { Icon } from '../../components/Icon';

/** Khóa cộng đồng and Phòng đố vui share one place in the sidebar (“Cùng học”). */
export function TogetherTabs({ active }: { active: 'community' | 'rooms' }) {
  return (
    <nav className="together-tabs" aria-label="Cùng học">
      <a href={hrefFor({ name: 'community' })} aria-current={active === 'community' ? 'page' : undefined}>
        <Icon name="globe" size={17} /> Khóa cộng đồng
      </a>
      <a href={hrefFor({ name: 'rooms' })} aria-current={active === 'rooms' ? 'page' : undefined}>
        <Icon name="users" size={17} /> Phòng đố vui
      </a>
    </nav>
  );
}
