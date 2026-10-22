import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { api, ensureSession, newKey } from '../../api/client';
import type { Course, RoomBank, RoomCreated, RoomSnapshot, RoomSummary } from '../../api/types';
import { hrefFor, navigate } from '../../app/router';
import { useLoad } from '../../app/store';
import { Icon } from '../../components/Icon';
import { PageHeader } from '../../components/PageHeader';
import { EmojiTile } from '../../components/EmojiTile';
import { Spot } from '../../components/Spot';
import { LoadingRows, ProblemNotice } from '../../components/StateViews';
import { describeError } from '../../lib/copy';
import { isTerminal, normalizeCode, PHASE_LABEL } from '../../lib/rooms';
import { TogetherTabs } from '../together/TogetherTabs';
import { loadNickname, roomProblem, saveNickname, saveRoomCode } from './roomStore';

const SECONDS = [15, 20, 30, 45, 60, 90];

function when(iso: string) {
  return new Intl.DateTimeFormat('vi-VN', { day: 'numeric', month: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(iso));
}

function JoinCard({ initial }: { initial?: string }) {
  const [code, setCode] = useState(() => normalizeCode(initial ?? ''));
  const [name, setName] = useState(loadNickname);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const join = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setProblem(null);
    try {
      await ensureSession();
      const room = await api<RoomSnapshot>('/rooms/join', { body: { code, nickname: name.trim() } });
      saveNickname(name);
      navigate({ name: 'room', roomId: room.id });
    } catch (error) {
      setProblem(roomProblem(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="panel-card room-join" onSubmit={(event) => void join(event)}>
      <h2 className="title-m">Vào phòng</h2>
      <p className="meta">Nhập mã chủ phòng gửi cho bạn.</p>
      <label>
        <span className="eyebrow">Mã phòng</span>
        <input
          className="field room-code-input"
          value={code}
          placeholder="VD: K7PM2QXA"
          autoComplete="off"
          spellCheck={false}
          autoFocus={Boolean(initial)}
          onChange={(event) => setCode(normalizeCode(event.target.value))}
        />
      </label>
      <label>
        <span className="eyebrow">Tên trong phòng</span>
        <input className="field" value={name} maxLength={40} placeholder="Ví dụ: Huy" onChange={(event) => setName(event.target.value)} />
      </label>
      {problem && (
        <p className="missing" role="alert">
          {problem}
        </p>
      )}
      <button type="submit" className="btn btn--primary" disabled={busy || code.length < 6 || !name.trim()} aria-busy={busy}>
        Vào phòng <Icon name="arrowRight" size={18} />
      </button>
    </form>
  );
}

/** A room needs fixed-answer questions from lessons that are already made and open. */
const readyUnits = (course: Course) => course.content.units.filter((unit) => unit.data && unit.unlocked);

function CreateCard({ courses, initialCourse }: { courses: Course[]; initialCourse?: string }) {
  const options = courses.filter((course) => readyUnits(course).length > 0);
  const [courseId, setCourseId] = useState(() => (initialCourse && options.some((c) => c.id === initialCourse) ? initialCourse : (options[0]?.id ?? '')));
  const course = options.find((c) => c.id === courseId);
  const ready = useMemo(() => (course ? readyUnits(course) : []), [course]);
  const [unitIds, setUnitIds] = useState<string[]>(() => ready.map((unit) => unit.id));
  const [count, setCount] = useState(5);
  const [seconds, setSeconds] = useState(30);
  const [name, setName] = useState(loadNickname);
  const [bank, setBank] = useState<RoomBank | null>(null);
  const [bankProblem, setBankProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  // Another course starts with all of its ready lessons picked.
  useEffect(() => setUnitIds(ready.map((unit) => unit.id)), [courseId]);

  const scope = unitIds.join(',');
  useEffect(() => {
    setBank(null);
    setBankProblem(null);
    if (!course || !scope) return;
    let alive = true;
    api<RoomBank>(`/courses/${encodeURIComponent(course.id)}/room-bank?expected_revision=${course.revision}&unit_ids=${encodeURIComponent(scope)}`)
      .then((value) => alive && setBank(value))
      .catch((error) => alive && setBankProblem(roomProblem(error)));
    return () => {
      alive = false;
    };
  }, [course?.id, course?.revision, scope]);

  if (options.length === 0) {
    return (
      <section className="panel-card room-create">
        <h2 className="title-m">Tạo phòng</h2>
        <p className="meta">Phòng dùng bộ câu của các bài đã tạo. Tạo và mở ít nhất một bài trong khóa của bạn trước nhé.</p>
        <a className="btn btn--secondary" href={hrefFor({ name: 'library' })}>
          Mở Thư viện
        </a>
      </section>
    );
  }

  const max = bank?.max_selectable ?? 0;
  const picked = Math.max(1, Math.min(count, max));
  const toggle = (id: string) => setUnitIds((all) => (all.includes(id) ? all.filter((x) => x !== id) : ready.filter((u) => u.id === id || all.includes(u.id)).map((u) => u.id)));

  const create = async () => {
    if (!course || !bank || max === 0) return;
    setBusy(true);
    setProblem(null);
    try {
      const room = await api<RoomCreated>('/rooms', {
        body: { course_id: course.id, expected_revision: course.revision, unit_ids: unitIds, question_count: picked, seconds_per_question: seconds, nickname: name.trim() },
        idempotencyKey: newKey('room-create'),
      });
      if (room.join_code) saveRoomCode(room.room_id, room.join_code);
      saveNickname(name);
      navigate({ name: 'room', roomId: room.room_id });
    } catch (error) {
      setProblem(roomProblem(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel-card room-create" aria-labelledby="room-create-title">
      <div className="room-create__head">
        <EmojiTile icon="trophy" tone="peach" size={60} />
        <div>
          <h2 id="room-create-title" className="title-m">
            Tạo phòng đố vui
          </h2>
          <p className="meta">Mọi người làm cùng một bộ câu, cùng lúc; máy chủ chấm và giữ đồng hồ.</p>
        </div>
      </div>

      <label>
        <span className="eyebrow">Khóa</span>
        <select className="field" value={courseId} onChange={(event) => setCourseId(event.target.value)}>
          {options.map((option) => (
            <option key={option.id} value={option.id}>
              {option.content.title}
              {option.access_role === 'learner' ? ' (khóa bạn tham gia)' : ''}
            </option>
          ))}
        </select>
      </label>

      <fieldset className="practice-units">
        <legend className="eyebrow">Bài lấy câu</legend>
        {ready.map((unit) => (
          <label key={unit.id} className="check-row practice-unit">
            <input type="checkbox" checked={unitIds.includes(unit.id)} onChange={() => toggle(unit.id)} />
            <span>{unit.title}</span>
          </label>
        ))}
      </fieldset>

      {bankProblem && <p className="notice notice--butter">{bankProblem}</p>}
      {bank && (
        <p className="meta">
          {bank.available} câu dùng được
          {bank.omitted.length > 0 && ` · ${bank.omitted.length} câu bỏ qua (tự luận hoặc đang cần xem lại)`}
        </p>
      )}

      <div className="room-create__row">
        <label className="count-row">
          <span>Số câu</span>
          <input type="range" min={1} max={Math.max(1, max)} value={picked} disabled={max <= 1} aria-label="Số câu" onChange={(event) => setCount(Number(event.target.value))} />
          <strong>
            {max ? picked : 0}/{max}
          </strong>
        </label>
        <div>
          <span className="eyebrow">Mỗi câu</span>
          <div className="segmented segmented--fit" role="radiogroup" aria-label="Thời gian mỗi câu">
            {SECONDS.map((value) => (
              <button key={value} type="button" role="radio" aria-checked={seconds === value} onClick={() => setSeconds(value)}>
                {value}s
              </button>
            ))}
          </div>
        </div>
      </div>

      <label>
        <span className="eyebrow">Tên của bạn trong phòng</span>
        <input className="field" value={name} maxLength={40} placeholder="Ví dụ: Huy" onChange={(event) => setName(event.target.value)} />
      </label>

      {problem && (
        <p className="missing" role="alert">
          {problem}
        </p>
      )}
      <button type="button" className="btn btn--primary btn--lg" disabled={busy || !bank || max === 0 || !name.trim()} aria-busy={busy} onClick={() => void create()}>
        <Icon name="play" size={18} /> Tạo phòng
      </button>
      <p className="meta room-rules">
        Tối đa {bank?.policy.max_players ?? 8} người · đúng +1 điểm, không tính tốc độ · không đổi tiến trình học hay Coin của ai · Kẹp chỉ giải thích sau khi phòng kết thúc.
      </p>
    </section>
  );
}

function RecentRooms({ rooms }: { rooms: RoomSummary[] }) {
  if (rooms.length === 0) return null;
  return (
    <section className="panel-card">
      <h2 className="title-m">Phòng gần đây</h2>
      <ul className="room-recent">
        {rooms.slice(0, 6).map((room) => (
          <li key={room.id}>
            <a href={hrefFor({ name: 'room', roomId: room.id })}>
              <span className="room-recent__text">
                <strong>{room.title}</strong>
                <span className="meta">{when(room.created_at)}</span>
              </span>
              <span className={isTerminal(room.phase) ? 'tag' : 'tag tag--sage'}>{PHASE_LABEL[room.phase]}</span>
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Phòng đố vui: join with a code, or host a round from your own lessons. */
export function RoomsPage({ code, courseId }: { code?: string; courseId?: string }) {
  const state = useLoad(async () => {
    await ensureSession();
    const [rooms, courses] = await Promise.all([api<RoomSummary[]>('/rooms'), api<Course[]>('/courses')]);
    return { rooms, courses };
  }, []);

  return (
    <div className="page together">
      <PageHeader
        title="Cùng học"
        tone="mint"
        note="Học với bạn bè: vào khóa người khác chia sẻ, hoặc mở phòng đố vui thi xem ai nhớ bài hơn."
        art={<Spot glyph="globe" tone="sage" size={88} badge />}
      >
        <TogetherTabs active="rooms" />
      </PageHeader>

      {/* Coming from a course's “Phòng đố vui” card means hosting: on narrow screens the create card goes first. */}
      <div className={courseId ? 'together-grid together-grid--rooms together-grid--create-first' : 'together-grid together-grid--rooms'}>
        <div className="together-aside">
          <JoinCard initial={code} />
          {state.data && <RecentRooms rooms={state.data.rooms} />}
        </div>
        <div className="rooms-create-col">
          {state.loading && !state.data && <LoadingRows rows={2} label="Đang tải khóa của bạn…" />}
          {state.error != null && <ProblemNotice problem={describeError(state.error)} onRetry={state.reload} />}
          {state.data && <CreateCard courses={state.data.courses} initialCourse={courseId} />}
        </div>
      </div>
    </div>
  );
}
