import { useId } from 'react';

const OUTER = 'M60 134C34 134 16 116 16 92C16 74 25 61 30 46C36 56 40 62 47 65C45 44 52 22 70 6C76 26 92 40 100 60C104 70 105 82 104 92C104 116 86 134 60 134Z';
const MIDDLE = 'M60 128C42 128 30 115 30 98C30 86 36 77 41 68C45 75 49 79 54 80C52 64 58 48 70 36C76 52 86 62 89 76C91 84 91 90 90 98C90 115 78 128 60 128Z';
const CORE = 'M60 124C48 124 41 115 41 105C41 93 52 85 61 71C68 84 79 93 79 105C79 115 72 124 60 124Z';

/**
 * The streak flame: three warm layers, a soft glow and a few embers drifting
 * up while it is lit. `still` drops the glow and motion for small uses (the
 * week row); unlit it waits in grey for today's study.
 */
export function Flame({ size = 96, lit = true, still = false }: { size?: number; lit?: boolean; still?: boolean }) {
  const id = useId();
  const g = (name: string) => `${id}-${name}`;
  const className = ['flame', lit && 'is-lit', still && 'is-still'].filter(Boolean).join(' ');
  return (
    <svg className={className} width={size} height={(size * 144) / 120} viewBox="0 0 120 144" aria-hidden="true">
      <defs>
        <radialGradient id={g('glow')} cx="0.5" cy="0.62" r="0.5">
          <stop offset="0" stopColor="#ffb347" stopOpacity="0.55" />
          <stop offset="1" stopColor="#ffb347" stopOpacity="0" />
        </radialGradient>
        <linearGradient id={g('outer')} x1="0" y1="1" x2="0.15" y2="0">
          <stop offset="0" stopColor="#f0401d" />
          <stop offset="0.55" stopColor="#ff6a1f" />
          <stop offset="1" stopColor="#ff9b30" />
        </linearGradient>
        <linearGradient id={g('middle')} x1="0" y1="1" x2="0" y2="0">
          <stop offset="0" stopColor="#ff8a1c" />
          <stop offset="1" stopColor="#ffc93c" />
        </linearGradient>
        <linearGradient id={g('core')} x1="0" y1="1" x2="0" y2="0">
          <stop offset="0" stopColor="#ffe36a" />
          <stop offset="1" stopColor="#fff9dc" />
        </linearGradient>
      </defs>
      {!still && <ellipse className="flame__glow" cx="60" cy="88" rx="60" ry="58" fill={`url(#${g('glow')})`} />}
      {!still && <ellipse className="flame__shadow" cx="60" cy="139" rx="30" ry="4" />}
      <g className="flame__body">
        <path d={OUTER} fill={`url(#${g('outer')})`} />
        <path className="flame__middle" d={MIDDLE} fill={`url(#${g('middle')})`} />
        <path className="flame__core" d={CORE} fill={`url(#${g('core')})`} />
        <path className="flame__shine" d="M27 100C25 86 29 75 34 66" />
      </g>
      {!still && (
        <g className="flame__embers">
          <circle cx="40" cy="40" r="3" />
          <circle cx="84" cy="30" r="2.4" />
          <circle cx="62" cy="18" r="2" />
        </g>
      )}
    </svg>
  );
}
