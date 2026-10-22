import { hrefFor } from '../../app/router';
import { Icon } from '../../components/Icon';

/** Khóa công khai and Phòng đố vui share one place in the sidebar (“Cộng đồng”). */
export function TogetherTabs({ active }: { active: 'community' | 'rooms' }) {
  return (
    <nav className="together-tabs" aria-label="Cộng đồng">
      <a href={hrefFor({ name: 'community' })} aria-current={active === 'community' ? 'page' : undefined}>
        <Icon name="globe" size={17} /> Khóa công khai
      </a>
      <a href={hrefFor({ name: 'rooms' })} aria-current={active === 'rooms' ? 'page' : undefined}>
        <Icon name="users" size={17} /> Phòng đố vui
      </a>
    </nav>
  );
}
