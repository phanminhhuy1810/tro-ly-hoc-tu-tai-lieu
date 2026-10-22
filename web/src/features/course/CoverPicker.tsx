import { useEffect, useRef, useState } from 'react';
import { api, ApiError } from '../../api/client';
import { useApp } from '../../app/store';
import { EmojiTile } from '../../components/EmojiTile';
import { Icon } from '../../components/Icon';
import { describeError } from '../../lib/copy';
import { nameOf, PICKER_ICONS, TILE_TONES, TONE_LABEL, type TileTone } from '../../lib/topicIcons';
import { coverOf, invalidateCovers, useCovers } from './covers';

const MAX_SIDE = 640;

/** Shrink and re-encode in the browser so the stored cover stays small (and EXIF is dropped). */
async function shrink(file: File): Promise<Blob> {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext('2d')!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  const encode = (type: string) => new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, type, 0.86));
  const blob = (await encode('image/webp')) ?? (await encode('image/jpeg'));
  if (!blob) throw new Error('Trình duyệt chưa đọc được ảnh này.');
  return blob;
}

async function uploadCover(courseId: string, blob: Blob) {
  const form = new FormData();
  form.append('file', blob, blob.type === 'image/webp' ? 'cover.webp' : 'cover.jpg');
  const response = await fetch(`/api/courses/${encodeURIComponent(courseId)}/cover/upload`, { method: 'POST', body: form, credentials: 'same-origin' });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new ApiError(response.status, (detail as { detail?: string } | null)?.detail ?? 'Chưa tải được ảnh bìa.');
  }
}

/** Pick the course's icon and colour (Notion-style), upload an image, or go back to the automatic one. */
export function CoverPicker({ courseId, title, open, onClose }: { courseId: string; title: string; open: boolean; onClose: () => void }) {
  const { toast } = useApp();
  const dialog = useRef<HTMLDialogElement>(null);
  const file = useRef<HTMLInputElement>(null);
  const current = coverOf(useCovers()[courseId], title);
  const [tone, setTone] = useState<TileTone>(current.tone);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const el = dialog.current;
    if (!el) return;
    if (open && !el.open) {
      setTone(current.tone);
      el.showModal();
    }
    if (!open && el.open) el.close();
  }, [open]);

  const done = (message: string) => {
    invalidateCovers();
    toast(message);
    onClose();
  };

  const pick = async (preset: string) => {
    setBusy(true);
    try {
      await api(`/courses/${courseId}/cover`, { method: 'PUT', body: { preset } });
      done('Đã đổi ảnh bìa');
    } catch (error) {
      toast(describeError(error).title);
    } finally {
      setBusy(false);
    }
  };

  const upload = async (chosen: File | undefined) => {
    if (!chosen) return;
    setBusy(true);
    try {
      await uploadCover(courseId, await shrink(chosen));
      done('Đã dùng ảnh của bạn làm ảnh bìa');
    } catch (error) {
      toast(error instanceof ApiError ? error.message : describeError(error).title);
    } finally {
      setBusy(false);
      if (file.current) file.current.value = '';
    }
  };

  const reset = async () => {
    setBusy(true);
    try {
      await api(`/courses/${courseId}/cover`, { method: 'DELETE' });
      done('Ảnh bìa sẽ tự chọn theo tên khóa');
    } catch (error) {
      toast(describeError(error).title);
    } finally {
      setBusy(false);
    }
  };

  return (
    <dialog
      ref={dialog}
      className="dialog dialog--wide"
      aria-labelledby="cover-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <div className="dialog__inner">
        <div className="dialog__head">
          <h2 id="cover-title" className="title-l">
            Ảnh bìa của khóa
          </h2>
          <button type="button" className="icon-btn" aria-label="Đóng" onClick={onClose}>
            <Icon name="x" />
          </button>
        </div>
        <div className="cover-tones" role="radiogroup" aria-label="Màu nền">
          {TILE_TONES.map((name) => (
            <button
              key={name}
              type="button"
              role="radio"
              aria-checked={tone === name}
              aria-label={TONE_LABEL[name]}
              title={TONE_LABEL[name]}
              className={`cover-tone emoji-tile--${name}`}
              onClick={() => setTone(name)}
            />
          ))}
        </div>
        <div className="cover-grid">
          {PICKER_ICONS.map((icon) => (
            <button
              key={icon}
              type="button"
              className={icon === current.icon && tone === current.tone ? 'cover-choice is-current' : 'cover-choice'}
              disabled={busy}
              onClick={() => void pick(`${icon}-${tone}`)}
              aria-label={nameOf(icon)}
              title={nameOf(icon)}
            >
              <EmojiTile icon={icon} tone={tone} size={54} />
            </button>
          ))}
        </div>
        <div className="cover-actions">
          <input ref={file} type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={(event) => void upload(event.target.files?.[0])} />
          <button type="button" className="btn btn--secondary" disabled={busy} onClick={() => file.current?.click()}>
            <Icon name="upload" size={18} /> Tải ảnh của bạn
          </button>
          <button type="button" className="btn btn--ghost" disabled={busy} onClick={() => void reset()}>
            Tự chọn theo tên khóa
          </button>
        </div>
        <p className="meta">Chọn màu rồi bấm một biểu tượng. Ảnh tải lên được thu nhỏ còn tối đa 640 px trước khi lưu.</p>
      </div>
    </dialog>
  );
}
