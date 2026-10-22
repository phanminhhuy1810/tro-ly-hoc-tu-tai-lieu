// Logo options, drawn in the same hand as the mascot and spot illustrations
// (thick ink outline, flat sage/butter). "kep" is the one in use; the others
// stay here so they can be compared on the states page before choosing.

import { useId } from 'react';
import { CatDrawing } from './Mascot';

const INK = '#23262b';

export type BrandOption = 'kep' | 'bubble' | 'path';

export const BRAND_OPTIONS: { id: BrandOption; name: string; note: string }[] = [
  { id: 'kep', name: 'Kẹp', note: 'Đầu mèo Kẹp (vẽ theo phác thảo của Huy) trên nền vàng — logo cũng là linh vật.' },
  { id: 'bubble', name: 'Bóng nói + sách', note: 'Gia sư AI trò chuyện về tài liệu của bạn; nói rõ công dụng nhưng ít cá tính hơn.' },
  { id: 'path', name: 'Lộ trình', note: 'Con đường có các chặng và ngôi sao đích — nhấn vào cảm giác đi tiếp từng bài.' },
];

function Kep() {
  // The head of Huy's cat drawing on butter, so the logo is the mascot.
  const clip = useId();
  return (
    <>
      <clipPath id={clip}>
        <rect x="3" y="3" width="58" height="58" rx="18" />
      </clipPath>
      <rect x="3" y="3" width="58" height="58" rx="18" fill="#f7dd72" />
      <g clipPath={`url(#${clip})`}>
        <svg x="4" y="8" width="56" height="56" viewBox="18 6 84 84">
          <CatDrawing />
        </svg>
      </g>
      <rect x="3" y="3" width="58" height="58" rx="18" fill="none" stroke={INK} strokeWidth="3" />
    </>
  );
}

function Bubble() {
  return (
    <>
      <path d="M12 7h40a8 8 0 0 1 8 8v25a8 8 0 0 1-8 8H31l-11 9.5V48h-8a8 8 0 0 1-8-8V15a8 8 0 0 1 8-8z" fill="#92b06c" stroke={INK} strokeWidth="3" strokeLinejoin="round" />
      <path d="M15.5 18.5c5.5-2.4 11-2.2 16.5 1 5.5-3.2 11-3.4 16.5-1v19.5c-5.5-2.4-11-2.2-16.5 1-5.5-3.2-11-3.4-16.5-1z" fill="#fff" stroke={INK} strokeWidth="2.6" strokeLinejoin="round" />
      <path d="M32 19.5V39" stroke={INK} strokeWidth="2.6" />
      <path d="M52 2.5l1.7 4.6 4.6 1.7-4.6 1.7L52 15.1l-1.7-4.6-4.6-1.7 4.6-1.7z" fill="#f7dd72" stroke={INK} strokeWidth="2" strokeLinejoin="round" />
    </>
  );
}

function Path() {
  return (
    <>
      <rect x="3" y="3" width="58" height="58" rx="18" fill="#e3edd4" stroke={INK} strokeWidth="3" />
      <path d="M18 47c11 0 3-11 14-11s4-12 14-12" fill="none" stroke={INK} strokeWidth="3" strokeLinecap="round" strokeDasharray="0.1 6.5" />
      <circle cx="18" cy="47" r="5.5" fill="#92b06c" stroke={INK} strokeWidth="2.6" />
      <circle cx="32" cy="36" r="5.5" fill="#fff" stroke={INK} strokeWidth="2.6" />
      <path d="M46 11.5l3.1 6.3 6.9 1-5 4.9 1.2 6.9-6.2-3.3-6.2 3.3 1.2-6.9-5-4.9 6.9-1z" fill="#f7dd72" stroke={INK} strokeWidth="2.4" strokeLinejoin="round" />
    </>
  );
}

export function BrandMark({ option = 'kep', size = 36, label }: { option?: BrandOption; size?: number; label?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" role={label ? 'img' : undefined} aria-label={label} aria-hidden={label ? undefined : true}>
      {option === 'kep' ? <Kep /> : option === 'bubble' ? <Bubble /> : <Path />}
    </svg>
  );
}
