import { useEffect } from 'react';
import { useRoute } from './app/router';
import { useApp } from './app/store';
import { Icon } from './components/Icon';
import { Mascot } from './components/Mascot';
import { EmptyState } from './components/StateViews';
import { ChatDock } from './features/chat/ChatDock';
import { CoursePage } from './features/course/CoursePage';
import { CreatePage } from './features/create/CreatePage';
import { HomePage } from './features/home/HomePage';
import { LessonPlayer } from './features/lesson/LessonPlayer';
import { StatesPage } from './features/preview/StatesPage';
import { Sidebar } from './features/shell/Sidebar';

export function App() {
  const route = useRoute();
  const { toasts, setChatContext, refreshWallet } = useApp();
  const focus = route.name === 'lesson';

  useEffect(refreshWallet, [refreshWallet]);
  useEffect(() => {
    if (route.name === 'home' || route.name === 'states' || route.name === 'create') setChatContext(null);
  }, [route.name, setChatContext]);

  return (
    <div className={focus ? 'app app--focus' : 'app'}>
      {!focus && <Sidebar route={route} />}
      <div className={focus ? undefined : 'main'}>
        {route.name === 'home' && <HomePage />}
        {route.name === 'course' && <CoursePage key={route.courseId} courseId={route.courseId} />}
        {route.name === 'lesson' && <LessonPlayer key={`${route.courseId}/${route.unitId}/${route.mode}`} courseId={route.courseId} unitId={route.unitId} weak={route.mode === 'weak'} />}
        {route.name === 'create' && <CreatePage />}
        {route.name === 'states' && <StatesPage />}
        {route.name === 'missing' && (
          <EmptyState
            art={<Mascot mood="oops" size={110} />}
            title="Không có trang này"
            body="Đường dẫn có thể đã cũ."
            action={
              <a className="btn btn--primary" href="#/">
                <Icon name="home" size={18} /> Về Học tiếp
              </a>
            }
          />
        )}
      </div>
      {/* Lessons have their own tutor chat (learning) and question chat (practice). */}
      {!focus && <ChatDock />}
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
