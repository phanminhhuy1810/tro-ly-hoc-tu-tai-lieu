import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import { coverFor, parsePreset, Spot } from '../../components/Spot';

export interface CoverInfo {
  kind: 'auto' | 'preset' | 'upload';
  preset?: string | null;
  updated_at?: string | null;
}

// One request for every course on screen; refreshed after the creator changes a cover.
let cache: Promise<Record<string, CoverInfo>> | null = null;
const listeners = new Set<() => void>();

function loadCovers() {
  cache ??= api<Record<string, CoverInfo>>('/covers').catch(() => ({}));
  return cache;
}

export function invalidateCovers() {
  cache = null;
  listeners.forEach((listener) => listener());
}

export function useCovers(): Record<string, CoverInfo> {
  const [covers, setCovers] = useState<Record<string, CoverInfo>>({});
  useEffect(() => {
    let alive = true;
    const load = () => void loadCovers().then((value) => alive && setCovers(value));
    load();
    listeners.add(load);
    return () => {
      alive = false;
      listeners.delete(load);
    };
  }, []);
  return covers;
}

/** Uploaded image, chosen preset, or a preset picked from the course title. */
export function CourseCover({ courseId, title, size = 56 }: { courseId: string; title: string; size?: number }) {
  const info = useCovers()[courseId];
  if (info?.kind === 'upload') {
    return (
      <img
        className="cover-img"
        src={`/api/courses/${encodeURIComponent(courseId)}/cover/image?v=${encodeURIComponent(info.updated_at ?? '')}`}
        width={size}
        height={size}
        alt=""
      />
    );
  }
  const { glyph, tone } = (info?.kind === 'preset' && parsePreset(info.preset)) || coverFor(title);
  return <Spot glyph={glyph} tone={tone} size={size} />;
}
