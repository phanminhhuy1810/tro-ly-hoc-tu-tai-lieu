import { lazy, Suspense, useEffect } from 'react';
import { isFocus, useRoute } from './app/router';
import { useApp } from './app/store';
import { Icon } from './components/Icon';
import { Mascot } from './components/Mascot';
import { EmptyState, LoadingRows } from './components/StateViews';
import { FlashcardPage } from './features/cards/FlashcardPage';
import { ChatDock } from './features/chat/ChatDock';
import { CoursePage } from './features/course/CoursePage';
import { HomePage } from './features/home/HomePage';
import { LessonPlayer } from './features/lesson/LessonPlayer';
import { PracticePage } from './features/practice/PracticePage';
import { PracticeRunner } from './features/practice/PracticeRunner';
import { AccountCorner } from './features/shell/AccountCorner';
import { Sidebar } from './features/shell/Sidebar';

// The learning loop (Học tiếp, khóa, bài, thẻ, ôn luyện) ships in the first bundle; the other
// screens load on demand and are fetched in the background once the app is idle.
const pages = {
  create: () => import('./features/create/CreatePage').then((m) => ({ default: m.CreatePage })),
  library: () => import('./features/library/LibraryPage').then((m) => ({ default: m.LibraryPage })),
  notebook: () => import('./features/notebook/NotebookPage').then((m) => ({ default: m.NotebookPage })),
  progress: () => import('./features/progress/ProgressPage').then((m) => ({ default: m.ProgressPage })),
  settings: () => import('./features/settings/SettingsPage').then((m) => ({ default: m.SettingsPage })),
  community: () => import('./features/community/CommunityPage').then((m) => ({ default: m.CommunityPage })),
  communityCourse: () => import('./features/community/CommunityCoursePage').then((m) => ({ default: m.CommunityCoursePage })),
  share: () => import('./features/community/SharePage').then((m) => ({ default: m.SharePage })),
  rooms: () => import('./features/rooms/RoomsPage').then((m) => ({ default: m.RoomsPage })),
  room: () => import('./features/rooms/RoomPage').then((m) => ({ default: m.RoomPage })),
  states: () => import('./features/preview/StatesPage').then((m) => ({ default: m.StatesPage })),
  account: () => import('./features/account/AccountPage').then((m) => ({ default: m.AccountPage })),
};
const CreatePage = lazy(pages.create);
const LibraryPage = lazy(pages.library);
const NotebookPage = lazy(pages.notebook);
const ProgressPage = lazy(pages.progress);
const SettingsPage = lazy(pages.settings);
const CommunityPage = lazy(pages.community);
const CommunityCoursePage = lazy(pages.communityCourse);
const SharePage = lazy(pages.share);
const RoomsPage = lazy(pages.rooms);
const RoomPage = lazy(pages.room);
const StatesPage = lazy(pages.states);
const AccountPage = lazy(pages.account);

function preloadPages() {
  for (const load of Object.values(pages)) void load().catch(() => undefined);
}

const NO_CONTEXT = new Set(['home', 'states', 'account', 'create', 'library', 'notebook', 'progress', 'settings', 'community', 'share', 'rooms']);

export function App() {
  const route = useRoute();
  const { toasts, setChatContext, refreshWallet } = useApp();
  const focus = isFocus(route);

  useEffect(refreshWallet, [refreshWallet]);
  useEffect(() => {
    const idle = window.requestIdleCallback ?? ((run: () => void) => window.setTimeout(run, 1500));
    idle(preloadPages);
  }, []);
  useEffect(() => {
    if (NO_CONTEXT.has(route.name)) setChatContext(null);
  }, [route.name, setChatContext]);

  return (
    <div className={focus ? 'app app--focus' : 'app'}>
      {!focus && <Sidebar route={route} />}
      <div className={focus ? undefined : 'main'}>
        {!focus && <AccountCorner />}
        <Suspense fallback={<LoadingRows rows={3} label="Đang mở…" />}>
          {route.name === 'home' && <HomePage />}
          {route.name === 'course' && <CoursePage key={route.courseId} courseId={route.courseId} />}
          {route.name === 'lesson' && <LessonPlayer key={`${route.courseId}/${route.unitId}/${route.mode}`} courseId={route.courseId} unitId={route.unitId} weak={route.mode === 'weak'} />}
          {route.name === 'cards' && <FlashcardPage key={route.courseId} courseId={route.courseId} />}
          {route.name === 'practice' &&
            (route.sessionId ? (
              <PracticeRunner key={route.sessionId} courseId={route.courseId} sessionId={route.sessionId} />
            ) : (
              <PracticePage key={route.courseId} courseId={route.courseId} />
            ))}
          {route.name === 'create' && <CreatePage />}
          {route.name === 'library' && <LibraryPage />}
          {route.name === 'notebook' && <NotebookPage />}
          {route.name === 'progress' && <ProgressPage />}
          {route.name === 'settings' && <SettingsPage key={route.section ?? ''} section={route.section} />}
          {route.name === 'community' &&
            (route.courseId ? <CommunityCoursePage key={route.courseId} courseId={route.courseId} /> : <CommunityPage key={route.code ?? ''} code={route.code} />)}
          {route.name === 'share' && <SharePage key={route.courseId} courseId={route.courseId} />}
          {route.name === 'rooms' && <RoomsPage key={`${route.code ?? ''}/${route.courseId ?? ''}`} code={route.code} courseId={route.courseId} />}
          {route.name === 'room' && <RoomPage key={route.roomId} roomId={route.roomId} />}
          {route.name === 'states' && <StatesPage />}
          {route.name === 'account' && <AccountPage key={route.mode ?? ''} initialMode={route.mode ?? 'login'} />}
          {route.name === 'missing' && (
            <EmptyState
              art={<Mascot mood="surprised" size={110} pettable />}
              title="Không có trang này"
              body="Đường dẫn có thể đã cũ."
              action={
                <a className="btn btn--primary" href="#/">
                  <Icon name="home" size={18} /> Về Học tiếp
                </a>
              }
            />
          )}
        </Suspense>
      </div>
      {/* Lessons and practice rounds have their own chat beside the content; a deck keeps the general chat; a quiz room has none until it ends. */}
      {(!focus || route.name === 'cards') && <ChatDock />}
      <div className="toasts" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className="toast">
            <Icon name="check" size={18} /> {t.text}
          </div>
        ))}
      </div>
    </div>
  );
}
