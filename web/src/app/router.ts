import { useEffect, useRef, useState } from 'react';
import { flushSync } from 'react-dom';

// Hash routes keep deep links working while the Python backend serves plain
// static files (no server-side rewrites needed).
export type Route =
  | { name: 'home' }
  | { name: 'course'; courseId: string }
  | { name: 'lesson'; courseId: string; unitId: string; mode: 'learn' | 'weak' }
  | { name: 'cards'; courseId: string }
  | { name: 'practice'; courseId: string; sessionId?: string }
  | { name: 'create' }
  | { name: 'library' }
  | { name: 'notebook' }
  | { name: 'progress' }
  | { name: 'settings'; section?: 'coin' }
  | { name: 'community'; courseId?: string; code?: string }
  | { name: 'share'; courseId: string }
  | { name: 'rooms'; code?: string; courseId?: string }
  | { name: 'room'; roomId: string }
  | { name: 'states' }
  | { name: 'missing' };

export function parseRoute(hash: string): Route {
  const parts = hash.replace(/^#\/?/, '').split('/').filter(Boolean).map(decodeURIComponent);
  if (parts.length === 0) return { name: 'home' };
  if (parts[0] === 'khoa' && parts[1]) return { name: 'course', courseId: parts[1] };
  if (parts[0] === 'hoc' && parts[1] && parts[2]) return { name: 'lesson', courseId: parts[1], unitId: parts[2], mode: 'learn' };
  if (parts[0] === 'on-cau-sai' && parts[1] && parts[2]) return { name: 'lesson', courseId: parts[1], unitId: parts[2], mode: 'weak' };
  if (parts[0] === 'the' && parts[1]) return { name: 'cards', courseId: parts[1] };
  if (parts[0] === 'on-luyen' && parts[1]) return { name: 'practice', courseId: parts[1], sessionId: parts[2] };
  if (parts[0] === 'tao-khoa') return { name: 'create' };
  if (parts[0] === 'thu-vien') return { name: 'library' };
  if (parts[0] === 'so-tay') return { name: 'notebook' };
  if (parts[0] === 'tien-do') return { name: 'progress' };
  if (parts[0] === 'cai-dat') return { name: 'settings', section: parts[1] === 'coin' ? 'coin' : undefined };
  if (parts[0] === 'cong-dong' && parts[1] === 'ma') return { name: 'community', code: parts[2] };
  if (parts[0] === 'cong-dong') return { name: 'community', courseId: parts[1] };
  if (parts[0] === 'chia-se' && parts[1]) return { name: 'share', courseId: parts[1] };
  if (parts[0] === 'phong' && parts[1] === 'vao') return { name: 'rooms', code: parts[2] };
  if (parts[0] === 'phong' && parts[1] === 'tao') return { name: 'rooms', courseId: parts[2] };
  if (parts[0] === 'phong' && parts[1]) return { name: 'room', roomId: parts[1] };
  if (parts[0] === 'phong') return { name: 'rooms' };
  if (parts[0] === 'mau-trang-thai') return { name: 'states' };
  return { name: 'missing' };
}

export function hrefFor(route: Route): string {
  switch (route.name) {
    case 'home':
      return '#/';
    case 'course':
      return `#/khoa/${encodeURIComponent(route.courseId)}`;
    case 'lesson':
      return `#/${route.mode === 'weak' ? 'on-cau-sai' : 'hoc'}/${encodeURIComponent(route.courseId)}/${encodeURIComponent(route.unitId)}`;
    case 'cards':
      return `#/the/${encodeURIComponent(route.courseId)}`;
    case 'practice':
      return `#/on-luyen/${encodeURIComponent(route.courseId)}${route.sessionId ? `/${encodeURIComponent(route.sessionId)}` : ''}`;
    case 'create':
      return '#/tao-khoa';
    case 'library':
      return '#/thu-vien';
    case 'notebook':
      return '#/so-tay';
    case 'progress':
      return '#/tien-do';
    case 'settings':
      return route.section ? `#/cai-dat/${route.section}` : '#/cai-dat';
    case 'community':
      if (route.code) return `#/cong-dong/ma/${encodeURIComponent(route.code)}`;
      return `#/cong-dong${route.courseId ? `/${encodeURIComponent(route.courseId)}` : ''}`;
    case 'share':
      return `#/chia-se/${encodeURIComponent(route.courseId)}`;
    case 'rooms':
      if (route.code) return `#/phong/vao/${encodeURIComponent(route.code)}`;
      return route.courseId ? `#/phong/tao/${encodeURIComponent(route.courseId)}` : '#/phong';
    case 'room':
      return `#/phong/${encodeURIComponent(route.roomId)}`;
    case 'states':
      return '#/mau-trang-thai';
    default:
      return '#/';
  }
}

/** Screens that take the whole window (no sidebar): a lesson, a card deck, a running practice round, a quiz room. */
export function isFocus(route: Route): boolean {
  return route.name === 'lesson' || route.name === 'cards' || route.name === 'room' || (route.name === 'practice' && Boolean(route.sessionId));
}

/** Room invites from the old screens look like /?room_code=ABCD2345#rooms; open them on the new join screen. */
export function upgradeLegacyLink() {
  const code = new URLSearchParams(window.location.search).get('room_code');
  if (code) window.history.replaceState(null, '', `${window.location.pathname}${hrefFor({ name: 'rooms', code })}`);
}

export function navigate(route: Route) {
  window.location.hash = hrefFor(route);
}

type ViewTransition = { ready?: Promise<unknown>; finished?: Promise<unknown> };
type TransitionDocument = Document & { startViewTransition?: (update: () => void) => ViewTransition | undefined };

export function motionAllowed() {
  return document.documentElement.dataset.motion !== 'off' && !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parseRoute(window.location.hash));
  const current = useRef(route);
  useEffect(() => {
    const doc = document as TransitionDocument;
    if (!doc.startViewTransition) document.documentElement.classList.add('no-vt');
    const onChange = () => {
      const next = parseRoute(window.location.hash);
      const apply = () => {
        current.current = next;
        setRoute(next);
        window.scrollTo({ top: 0 });
      };
      if (!doc.startViewTransition || !motionAllowed()) return apply();
      // Opening a lesson, a deck or a practice round drops the new page in from the top; other moves cross-fade.
      document.documentElement.dataset.nav = isFocus(next) && hrefFor(current.current) !== hrefFor(next) ? 'lesson' : 'page';
      const transition = doc.startViewTransition(() => flushSync(apply));
      // A skipped transition (hidden tab, quick double navigation) still applies the route.
      transition?.ready?.catch(() => undefined);
      transition?.finished?.catch(() => undefined);
    };
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);
  return route;
}
