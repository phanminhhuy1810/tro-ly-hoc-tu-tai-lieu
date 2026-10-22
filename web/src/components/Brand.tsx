// Logo options, drawn in the same hand as the mascot and spot illustrations
// (thick ink outline, flat sage/butter). "kep" is the one in use; the others
// stay here so they can be compared on the states page before choosing.

const INK = '#23262b';

export type BrandOption = 'kep' | 'bubble' | 'path';

export const BRAND_OPTIONS: { id: BrandOption; name: string; note: string }[] = [
  { id: 'kep', name: 'Kẹp', note: 'Mặt mèo Kẹp đeo kính trên nền vàng — logo cũng là linh vật, nhận ra ngay ở cỡ favicon.' },
  { id: 'bubble', name: 'Bóng nói + sách', note: 'Gia sư AI trò chuyện về tài liệu của bạn; nói rõ công dụng nhưng ít cá tính hơn.' },
  { id: 'path', name: 'Lộ trình', note: 'Con đường có các chặng và ngôi sao đích — nhấn vào cảm giác đi tiếp từng bài.' },
];

function Kep() {
  // The cat's face: ears, nerd glasses, the half-lidded look, on butter.
  return (
    <>
      <rect x="3" y="3" width="58" height="58" rx="18" fill="#f7dd72" stroke={INK} strokeWidth="3" />
      <path d="M13 49V25L18.5 9L27 18.5Q32 17 37 18.5L45.5 9L51 25V49Q51 55 45 55H19Q13 55 13 49Z" fill="#ffcf94" stroke={INK} strokeWidth="2.8" strokeLinejoin="round" />
      <path d="M16.5 21l2.6-7 4 5.2zM40.9 19.2l4-5.2 2.6 7z" fill="#f59bb0" />
      <path d="M28.5 21.5v3.5M32 21v4M35.5 21.5v3.5" stroke="#e98d3c" strokeWidth="2" strokeLinecap="round" />
      <rect x="15.5" y="28.5" width="14" height="11" rx="3.5" fill="rgba(255,255,255,.55)" />
      <rect x="34.5" y="28.5" width="14" height="11" rx="3.5" fill="rgba(255,255,255,.55)" />
      <path d="M19 33h7.5M37.5 33h7.5" stroke={INK} strokeWidth="2.2" strokeLinecap="round" />
      <circle cx="23" cy="35" r="1.9" fill={INK} />
      <circle cx="41" cy="35" r="1.9" fill={INK} />
      <rect x="15.5" y="28.5" width="14" height="11" rx="3.5" fill="none" stroke={INK} strokeWidth="2.4" />
      <rect x="34.5" y="28.5" width="14" height="11" rx="3.5" fill="none" stroke={INK} strokeWidth="2.4" />
      <path d="M29.5 33q2.5-2 5 0" stroke={INK} strokeWidth="2.2" fill="none" strokeLinecap="round" />
      <path d="M30 42h4l-2 2.4z" fill="#f59bb0" stroke={INK} strokeWidth="1.4" strokeLinejoin="round" />
      <path d="M28.5 46.5q1.8 1.5 3.5-.4q2.5 1.8 5-1.2" stroke={INK} strokeWidth="2" fill="none" strokeLinecap="round" />
      <path d="M13 43.5l-6-1M13 47l-5.5 1.2M51 43.5l6-1M51 47l5.5 1.2" stroke={INK} strokeWidth="1.8" strokeLinecap="round" />
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
