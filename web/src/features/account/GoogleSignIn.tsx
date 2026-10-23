import { useEffect, useRef, useState } from 'react';
import { api, ensureSession } from '../../api/client';
import { describeError } from '../../lib/copy';

type GoogleIdentity = {
  initialize: (options: { client_id: string; nonce: string; auto_select: boolean; callback: (reply: { credential: string }) => void }) => void;
  renderButton: (element: HTMLElement, options: { type: string; theme: string; size: string; text: string; shape: string; locale: string; width: number }) => void;
};
type GoogleWindow = Window & { google?: { accounts: { id: GoogleIdentity } } };
let sdk: Promise<GoogleIdentity> | null = null;

function loadGoogle(): Promise<GoogleIdentity> {
  const existing = (window as GoogleWindow).google?.accounts.id;
  if (existing) return Promise.resolve(existing);
  sdk ??= new Promise<GoogleIdentity>((resolve, reject) => {
    const script = document.createElement('script');
    script.src = 'https://accounts.google.com/gsi/client';
    script.async = true;
    const timeout = window.setTimeout(() => fail(), 15000);
    const fail = () => {
      window.clearTimeout(timeout);
      script.remove();
      sdk = null;
      reject(new Error('Chưa tải được Google. Bạn vẫn có thể đăng nhập bằng email.'));
    };
    script.onload = () => {
      window.clearTimeout(timeout);
      const identity = (window as GoogleWindow).google?.accounts.id;
      if (identity) resolve(identity);
      else fail();
    };
    script.onerror = fail;
    document.head.appendChild(script);
  });
  return sdk;
}

function GoogleMark() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true">
      <path fill="#4285F4" d="M21.6 12.23c0-.71-.06-1.39-.18-2.05H12v3.88h5.38a4.6 4.6 0 0 1-2 3.02v2.51h3.24c1.9-1.75 2.98-4.33 2.98-7.36Z" />
      <path fill="#34A853" d="M12 22c2.7 0 4.96-.9 6.62-2.41l-3.24-2.51c-.9.6-2.05.97-3.38.97-2.6 0-4.8-1.76-5.59-4.12H3.07v2.59A10 10 0 0 0 12 22Z" />
      <path fill="#FBBC05" d="M6.41 13.93a6 6 0 0 1 0-3.86V7.48H3.07a10 10 0 0 0 0 9.04l3.34-2.59Z" />
      <path fill="#EA4335" d="M12 5.95c1.47 0 2.79.5 3.82 1.49l2.87-2.87A9.6 9.6 0 0 0 12 2a10 10 0 0 0-8.93 5.48l3.34 2.59C7.2 7.7 9.4 5.95 12 5.95Z" />
    </svg>
  );
}

export function GoogleSignIn({ connected = false, connect = false, onSuccess }: { connected?: boolean; connect?: boolean; onSuccess: () => void }) {
  const holder = useRef<HTMLDivElement>(null);
  const [phase, setPhase] = useState<'loading' | 'disabled' | 'ready' | 'busy' | 'error'>('loading');
  const [problem, setProblem] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (connected) return;
    let active = true;
    setPhase('loading');
    setProblem(null);
    const prepare = async () => {
      const config = await api<{ enabled: boolean; client_id: string | null }>('/account/google/config');
      if (!active) return;
      if (!config.enabled || !config.client_id) return setPhase('disabled');
      await ensureSession();
      const [identity, challenge] = await Promise.all([loadGoogle(), api<{ nonce: string }>('/account/google/challenge', { method: 'POST' })]);
      if (!active || !holder.current) return;
      identity.initialize({
        client_id: config.client_id,
        nonce: challenge.nonce,
        auto_select: false,
        callback: ({ credential }) => {
          if (!active) return;
          setPhase('busy');
          setProblem(null);
          void api('/account/google', { body: { credential } }).then(() => {
            if (active) onSuccess();
          }).catch((error: unknown) => {
            if (!active) return;
            setPhase('ready');
            setProblem(describeError(error).body);
          });
        },
      });
      holder.current.replaceChildren();
      identity.renderButton(holder.current, { type: 'standard', theme: 'outline', size: 'large', text: 'continue_with', shape: 'pill', locale: 'vi', width: Math.min(holder.current.clientWidth || 360, 400) });
      setPhase('ready');
    };
    void prepare().catch((error: unknown) => {
      if (!active) return;
      setPhase('error');
      setProblem(error instanceof Error ? error.message : 'Chưa kết nối được Google.');
    });
    return () => { active = false; };
  }, [attempt, connected, onSuccess]);

  if (connected) return <p className="auth-google__connected"><GoogleMark /> Google đã kết nối</p>;
  return (
    <div className="auth-google">
      {connect && <p className="meta">Kết nối Google có cùng email để lần sau đăng nhập nhanh hơn.</p>}
      <div ref={holder} className="auth-google__button" hidden={phase !== 'ready'} />
      {phase !== 'ready' && (
        <button type="button" className="auth-google__fallback" disabled={phase !== 'error'} onClick={() => setAttempt((value) => value + 1)}>
          <GoogleMark /> {phase === 'busy' ? 'Đang đăng nhập…' : phase === 'loading' ? 'Đang kết nối Google…' : phase === 'error' ? 'Thử lại Google' : 'Tiếp tục với Google'}
        </button>
      )}
      {phase === 'disabled' && <p className="meta">Google chưa được kết nối. Bạn vẫn có thể dùng email và mật khẩu.</p>}
      {problem && <p className="missing" role="alert">{problem}</p>}
      {problem && phase === 'ready' && <button type="button" className="link" onClick={() => setAttempt((value) => value + 1)}>Mở lại đăng nhập Google</button>}
    </div>
  );
}
