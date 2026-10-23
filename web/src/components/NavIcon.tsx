// Sidebar icons drawn for Clawledge: a pastel fill under a rounded outline in
// the text colour, so they read on the light rows and on the dark active row.
// Home has cat ears on its roof and Cộng đồng is two cat faces, after Byte.

export type NavName = 'home' | 'library' | 'users' | 'notebook' | 'chart' | 'settings';

function cog(cx: number, cy: number, outer: number, inner: number, teeth: number): string {
  const points: string[] = [];
  const step = (Math.PI * 2) / teeth;
  for (let i = 0; i < teeth; i += 1) {
    const a = i * step;
    for (const [r, t] of [
      [inner, -0.32],
      [outer, -0.16],
      [outer, 0.16],
      [inner, 0.32],
    ] as const) {
      points.push(`${(cx + r * Math.cos(a + t * step * 1.4)).toFixed(2)},${(cy + r * Math.sin(a + t * step * 1.4)).toFixed(2)}`);
    }
  }
  return points.join(' ');
}

export function NavIcon({ name, size = 24 }: { name: NavName; size?: number }) {
  const line = { stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };
  return (
    <svg className="nav-icon" width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      {name === 'home' && (
        <g {...line}>
          <path d="M5.5 11v8.2c0 .7.6 1.3 1.3 1.3h10.4c.7 0 1.3-.6 1.3-1.3V11" fill="#fcf0b8" />
          <path d="M3.5 12.2L12 4.8l8.5 7.4" fill="none" />
          <path d="M7.4 8.3l-.3-3.6 2.7 1.6M16.6 8.3l.3-3.6-2.7 1.6" fill="none" />
          <path d="M10.2 20.5v-3.8a1.8 1.8 0 0 1 3.6 0v3.8" fill="#fff" />
        </g>
      )}
      {name === 'library' && (
        <g {...line}>
          <rect x="3.8" y="4.5" width="4.4" height="15.5" rx="1.2" fill="#bcd3f7" />
          <rect x="9.6" y="6.8" width="4.2" height="13.2" rx="1.2" fill="#d9ecc6" />
          <path d="M15.2 8.3l3.4-.9 2.6 11.5-3.4.9z" fill="#f8d2c4" />
          <path d="M5.2 8.5h1.6M11 10.5h1.4" fill="none" />
        </g>
      )}
      {name === 'users' && (
        <g {...line}>
          <path d="M12.6 19.8v-5.4l.9-4.4 2.4 1.9h2.4l2.4-1.9.9 4.4v5.4z" fill="#dfe3ea" />
          <path d="M3 20v-6.2l1-4.8 2.7 2.1h2.8l2.7-2.1 1 4.8V20z" fill="#ffd8ad" />
          <path d="M6.5 15.6h.01M9.7 15.6h.01M16 15.2h.01M18.6 15.2h.01" fill="none" strokeWidth={2.4} />
        </g>
      )}
      {name === 'notebook' && (
        <g {...line}>
          <rect x="6" y="3.5" width="13.5" height="17" rx="2" fill="#f6c6d2" />
          <path d="M4 8h3.6M4 12h3.6M4 16h3.6M10.5 8.5h5.5M10.5 12h4" fill="none" />
        </g>
      )}
      {name === 'chart' && (
        <g {...line}>
          <rect x="3.8" y="12.5" width="4.2" height="7.5" rx="1.1" fill="#d9ecc6" />
          <rect x="9.9" y="8.5" width="4.2" height="11.5" rx="1.1" fill="#fcf0b8" />
          <rect x="16" y="4.5" width="4.2" height="15.5" rx="1.1" fill="#f8d2c4" />
        </g>
      )}
      {name === 'settings' && (
        <g {...line}>
          <polygon points={cog(12, 12, 9.2, 6.6, 8)} fill="#e3e6f0" />
          <circle cx="12" cy="12" r="2.6" fill="#fff" />
        </g>
      )}
    </svg>
  );
}
