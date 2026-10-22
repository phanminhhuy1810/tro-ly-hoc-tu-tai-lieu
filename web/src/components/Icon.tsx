// One stroke icon set (24px grid, 1.8 stroke, round caps) so every icon in the
// app has the same weight. Decorative by default; pass `label` when an icon
// is the only content of a control.

const PATHS = {
  home: 'M3.5 10.5 12 4l8.5 6.5M6 9v10.5h12V9M10 19.5v-5h4v5',
  library: 'M5 4.5h4v15H5zM10.5 4.5h4v15h-4zM16 5.2l3.7-.9 3 14.6-3.8.8z',
  notebook: 'M6 3.5h11.5a1 1 0 0 1 1 1v15a1 1 0 0 1-1 1H6zM6 3.5v17M3.5 7.5h5M3.5 12h5M3.5 16.5h5M11 8h4.5',
  chart: 'M4 20V10M10 20V4M16 20v-7M21 20H3',
  settings:
    'M12 15.2a3.2 3.2 0 1 0 0-6.4 3.2 3.2 0 0 0 0 6.4zM19.4 13.5l1.6 1.2-1.8 3.1-1.9-.6a7 7 0 0 1-2 1.2L15 20.5h-3.6l-.4-2a7 7 0 0 1-2-1.2l-1.9.6-1.8-3.1 1.6-1.2a7 7 0 0 1 0-2.3L5.3 9.9l1.8-3.1 1.9.6a7 7 0 0 1 2-1.2l.4-2h3.6l.4 2a7 7 0 0 1 2 1.2l1.9-.6 1.8 3.1-1.6 1.2a7 7 0 0 1 0 2.3z',
  coin: 'M12 20.5a8.5 8.5 0 1 0 0-17 8.5 8.5 0 0 0 0 17zM14.6 9.2c-.6-.9-1.6-1.4-2.7-1.4-1.7 0-2.9 1-2.9 2.3 0 3.1 5.9 1.6 5.9 4.4 0 1.3-1.3 2.3-3 2.3-1.2 0-2.3-.5-2.9-1.5M12 6.3v1.4M12 16.9v1.2',
  plus: 'M12 5v14M5 12h14',
  arrowRight: 'M5 12h14M13 6l6 6-6 6',
  arrowLeft: 'M19 12H5M11 6l-6 6 6 6',
  check: 'M5 12.5l4.2 4.2L19 7',
  x: 'M6 6l12 12M18 6 6 18',
  lock: 'M6.5 10.5h11v9h-11zM8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5',
  sparkle: 'M12 3.5l1.9 5.1 5.1 1.9-5.1 1.9L12 17.5l-1.9-5.1-5.1-1.9 5.1-1.9zM18.5 16l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z',
  bulb: 'M9 18h6M10 21h4M12 3.5a6 6 0 0 0-3.6 10.8c.7.5 1.1 1.3 1.1 2.2h5c0-.9.4-1.7 1.1-2.2A6 6 0 0 0 12 3.5z',
  message: 'M20 11.5a7.5 7.5 0 0 1-11 6.6L4.5 19.5l1.3-4.2A7.5 7.5 0 1 1 20 11.5z',
  file: 'M14 3.5H7a1.5 1.5 0 0 0-1.5 1.5v14A1.5 1.5 0 0 0 7 20.5h10a1.5 1.5 0 0 0 1.5-1.5V8zM14 3.5V8h4.5M9 12.5h6M9 16h4',
  expand: 'M14.5 4.5h5v5M19.5 4.5l-6 6M9.5 19.5h-5v-5M4.5 19.5l6-6',
  collapse: 'M19.5 4.5l-5.5 5.5M14 5.5V10h4.5M4.5 19.5 10 14M10 18.5V14H5.5',
  send: 'M4.5 12 20 4.5 13.5 20l-2.3-6.2z',
  refresh: 'M19.5 12a7.5 7.5 0 1 1-2.2-5.3M19.5 4.5v4h-4',
  up: 'M6 14l6-6 6 6',
  down: 'M6 10l6 6 6-6',
  bookOpen: 'M12 6.5C10 5 7.5 4.5 4 4.5v13c3.5 0 6 .5 8 2 2-1.5 4.5-2 8-2v-13c-3.5 0-6 .5-8 2zM12 6.5v13',
  flag: 'M5.5 21V4M5.5 4.5h11l-2 4 2 4h-11',
  clock: 'M12 20.5a8.5 8.5 0 1 0 0-17 8.5 8.5 0 0 0 0 17zM12 7.5V12l3 2',
  eye: 'M2.5 12s3.5-6.5 9.5-6.5 9.5 6.5 9.5 6.5-3.5 6.5-9.5 6.5S2.5 12 2.5 12zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z',
  save: 'M5 4.5h11l3 3V19.5H5zM8 4.5v5h7v-5M8 19.5v-6h8v6',
  stop: 'M7 7h10v10H7z',
  layers: 'M12 4.5 3.5 9 12 13.5 20.5 9zM3.5 13.5 12 18l8.5-4.5',
  star: 'M12 3.6l2.5 5.3 5.8.8-4.2 4.1 1 5.8L12 16.9l-5.1 2.7 1-5.8-4.2-4.1 5.8-.8z',
  upload: 'M12 15.5V4.5M7.5 9 12 4.5 16.5 9M4.5 15v3.5a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2V15',
  image: 'M4.5 5.5h15v13h-15zM4.5 15.5l4.5-4.5 4 4 2.5-2.5 4 4M15 8.5h.01',
  edit: 'M4.5 19.5h4l10-10-4-4-10 10zM13 7l4 4',
  trash: 'M5 7h14M9.5 7V4.5h5V7M7 7l.8 12.5h8.4L17 7M10.5 10.5v6M13.5 10.5v6',
  brain: 'M9.5 5a3 3 0 0 0-3 3 3 3 0 0 0-2 5.2A3 3 0 0 0 7 18a2.5 2.5 0 0 0 5 .5V6.5A2 2 0 0 0 9.5 5zM14.5 5a3 3 0 0 1 3 3 3 3 0 0 1 2 5.2A3 3 0 0 1 17 18a2.5 2.5 0 0 1-5 .5',
  merge: 'M7 4.5v5a5 5 0 0 0 5 5h5M14 11.5l3 3-3 3M7 19.5v-5',
  scissors: 'M6.5 6a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5zM6.5 13a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5zM8.7 9.8 19.5 17M8.7 14.2 19.5 7',
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 20, label, className }: { name: IconName; size?: number; label?: string; className?: string }) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
