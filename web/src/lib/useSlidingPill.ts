import { useLayoutEffect, type RefObject } from 'react';

type Box = { x: number; y: number; w: number; h: number };
const last = new Map<string, Box>();

/**
 * Slides a highlight (the container's ::before, see `.has-pill`) to the selected
 * item instead of jumping. It remembers where the highlight was per `key`, so a
 * control rebuilt on the next page (the Cộng đồng tabs) slides from there too.
 */
export function useSlidingPill(ref: RefObject<HTMLElement | null>, key: string, selected: unknown) {
  useLayoutEffect(() => {
    const box = ref.current;
    if (!box) return;
    const item = box.querySelector<HTMLElement>('[aria-current="page"], [aria-selected="true"], [aria-checked="true"]');
    if (!item) {
      box.style.setProperty('--pill-o', '0');
      return;
    }
    const place = ({ x, y, w, h }: Box) => {
      box.style.setProperty('--pill-x', `${x}px`);
      box.style.setProperty('--pill-y', `${y}px`);
      box.style.setProperty('--pill-w', `${w}px`);
      box.style.setProperty('--pill-h', `${h}px`);
      box.style.setProperty('--pill-o', '1');
    };
    const next = { x: item.offsetLeft, y: item.offsetTop, w: item.offsetWidth, h: item.offsetHeight };
    const prev = last.get(key);
    if (prev && !box.dataset.pillReady) {
      // A freshly built control starts where the previous one left off, then slides.
      box.classList.add('no-pill-motion');
      place(prev);
      void box.offsetWidth;
      box.classList.remove('no-pill-motion');
    }
    box.dataset.pillReady = '1';
    place(next);
    last.set(key, next);
  }, [ref, key, selected]);
}
