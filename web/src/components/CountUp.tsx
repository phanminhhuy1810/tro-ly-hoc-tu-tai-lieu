import { useEffect, useRef, useState } from 'react';
import { motionAllowed } from '../app/router';

/** A number that counts up when it appears or changes; instant when motion is off. */
export function CountUp({ value, duration = 800 }: { value: number; duration?: number }) {
  const [shown, setShown] = useState(() => (motionAllowed() ? 0 : value));
  const from = useRef(0);
  useEffect(() => {
    if (!motionAllowed()) {
      from.current = value;
      setShown(value);
      return;
    }
    const begin = from.current;
    const start = performance.now();
    let frame = 0;
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - (1 - t) ** 3;
      setShown(Math.round(begin + (value - begin) * eased));
      if (t < 1) frame = requestAnimationFrame(step);
      else from.current = value;
    };
    frame = requestAnimationFrame(step);
    // Hidden tabs pause animation frames; the real number must still show.
    const settle = window.setTimeout(() => {
      from.current = value;
      setShown(value);
    }, duration + 80);
    return () => {
      cancelAnimationFrame(frame);
      window.clearTimeout(settle);
    };
  }, [value, duration]);
  return <>{shown}</>;
}
