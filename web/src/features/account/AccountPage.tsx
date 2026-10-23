import { useState, type FormEvent } from 'react';
import { api } from '../../api/client';
import { hrefFor } from '../../app/router';
import { useLoad } from '../../app/store';
import { BrandMark } from '../../components/Brand';
import { Icon } from '../../components/Icon';
import { Mascot, MascotDuo } from '../../components/Mascot';
import { LoadingRows, ProblemNotice } from '../../components/StateViews';
import { describeError } from '../../lib/copy';

// Sign in / create an account. Creating an account keeps everything this
// browser has learned so far (the anonymous learner becomes the account);
// signing in on another machine opens the same courses, cards and progress.

export interface Account {
  signed_in: boolean;
  email: string | null;
  name: string | null;
}

type Mode = 'login' | 'register';

const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/** Reload so every page, wallet and cache reads the new session. */
function goHome() {
  window.location.hash = hrefFor({ name: 'home' });
  window.location.reload();
}

function AuthForm() {
  const [mode, setMode] = useState<Mode>('login');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | unknown>(null);
  const register = mode === 'register';

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!EMAIL.test(email.trim())) return setProblem('Email chưa đúng dạng, ví dụ ten@gmail.com.');
    if (register && password.length < 8) return setProblem('Mật khẩu cần ít nhất 8 ký tự.');
    setBusy(true);
    setProblem(null);
    try {
      await api<Account>(register ? '/account/register' : '/account/login', { body: register ? { email, password, name } : { email, password } });
      goHome();
    } catch (error) {
      setProblem(error);
      setBusy(false);
    }
  };

  return (
    <div className="auth-card">
      <div className="auth-tabs" role="tablist" aria-label="Tài khoản">
        {(
          [
            ['login', 'Đăng nhập'],
            ['register', 'Tạo tài khoản'],
          ] as [Mode, string][]
        ).map(([value, label]) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={mode === value}
            onClick={() => {
              setMode(value);
              setProblem(null);
            }}
          >
            {label}
          </button>
        ))}
      </div>
      <h1 className="auth-card__title">{register ? 'Tạo tài khoản' : 'Chào bạn quay lại!'}</h1>
      <p className="auth-card__lead">
        {register ? 'Khóa học, thẻ và tiến độ bạn đang có trên máy này sẽ chuyển vào tài khoản, không mất gì.' : 'Đăng nhập để học tiếp đúng chỗ đang dở, trên máy nào cũng được.'}
      </p>
      <form className="auth-form" onSubmit={(event) => void submit(event)} noValidate>
        {register && (
          <label className="auth-field">
            <span>Tên hiển thị</span>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Ví dụ: Huy" autoComplete="nickname" maxLength={60} />
          </label>
        )}
        <label className="auth-field">
          <span>Email</span>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="ten@gmail.com" autoComplete="email" inputMode="email" required />
        </label>
        <label className="auth-field">
          <span>Mật khẩu</span>
          <span className="auth-field__password">
            <input
              type={show ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={register ? 'Ít nhất 8 ký tự' : 'Mật khẩu của bạn'}
              autoComplete={register ? 'new-password' : 'current-password'}
              required
            />
            <button type="button" className="auth-field__eye" aria-label={show ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'} aria-pressed={show} onClick={() => setShow((v) => !v)}>
              <Icon name="eye" size={18} />
            </button>
          </span>
        </label>
        {problem != null && (typeof problem === 'string' ? <p className="notice notice--coral">{problem}</p> : <ProblemNotice problem={describeError(problem)} compact />)}
        <button type="submit" className="btn btn--primary btn--lg btn--block" disabled={busy} aria-busy={busy}>
          {busy ? 'Đang xử lý…' : register ? 'Tạo tài khoản' : 'Đăng nhập'} {!busy && <Icon name="arrowRight" size={18} />}
        </button>
      </form>
      <p className="auth-card__switch">
        {register ? 'Đã có tài khoản?' : 'Chưa có tài khoản?'}{' '}
        <button
          type="button"
          className="link"
          onClick={() => {
            setMode(register ? 'login' : 'register');
            setProblem(null);
          }}
        >
          {register ? 'Đăng nhập' : 'Tạo tài khoản miễn phí'}
        </button>
      </p>
    </div>
  );
}

function SignedIn({ account }: { account: Account }) {
  const [busy, setBusy] = useState(false);
  const logout = async () => {
    setBusy(true);
    await api('/account/logout', { body: {} }).catch(() => undefined);
    goHome();
  };
  return (
    <div className="auth-card auth-card--me">
      <span className="auth-me__avatar" aria-hidden="true">
        <Mascot face size={84} />
      </span>
      <h1 className="auth-card__title">{account.name}</h1>
      <p className="auth-me__email">{account.email}</p>
      <p className="auth-card__lead">Khóa học, thẻ, ghi chú và tiến độ của bạn đang được lưu trong tài khoản này. Đăng nhập máy khác bằng email trên để học tiếp.</p>
      <div className="auth-me__actions">
        <a className="btn btn--primary btn--lg" href={hrefFor({ name: 'home' })}>
          Về trang học <Icon name="arrowRight" size={18} />
        </a>
        <button type="button" className="btn btn--ghost" disabled={busy} onClick={() => void logout()}>
          <Icon name="exit" size={18} /> Đăng xuất
        </button>
      </div>
    </div>
  );
}

export function AccountPage() {
  const state = useLoad(() => api<Account>('/account'), []);
  return (
    <div className="auth">
      <aside className="auth__art" aria-hidden="true">
        <a className="auth__brand" href={hrefFor({ name: 'home' })} tabIndex={-1}>
          <BrandMark size={44} />
          <strong>Folio</strong>
        </a>
        <div className="auth__pitch">
          <p className="auth__headline">Học từ chính tài liệu của bạn.</p>
          <ul className="auth__perks">
            <li>
              <Icon name="save" size={18} /> Lưu khóa học, thẻ và tiến độ
            </li>
            <li>
              <Icon name="refresh" size={18} /> Học tiếp trên máy khác
            </li>
            <li>
              <Icon name="heart" size={18} /> Kẹp nhớ cách bạn thích học
            </li>
          </ul>
        </div>
        <div className="auth__stage">
          <span className="auth__spark auth__spark--a" />
          <span className="auth__spark auth__spark--b" />
          <MascotDuo size={150} />
        </div>
      </aside>
      <main className="auth__panel">
        <a className="back auth__back" href={hrefFor({ name: 'home' })}>
          <Icon name="arrowLeft" size={18} /> Về trang học
        </a>
        {state.loading && !state.data ? <LoadingRows rows={2} /> : state.data?.signed_in ? <SignedIn account={state.data} /> : <AuthForm />}
        <p className="auth__fine">Mật khẩu được mã hóa trước khi lưu. Folio không gửi email quảng cáo.</p>
      </main>
    </div>
  );
}
