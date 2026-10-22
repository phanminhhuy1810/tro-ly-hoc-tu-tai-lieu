import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../../api/client';
import type { RoomSnapshot } from '../../api/types';
import { clockOffset, isTerminal } from '../../lib/rooms';

/**
 * Live room state. The server owns phase, deadline and score: its event
 * stream pushes snapshots, and a presence call every few seconds keeps the
 * host's seat (the room stops after a minute without the host) and covers the
 * gap while the stream reconnects. An older snapshot never replaces a newer one.
 */
export function useRoom(roomId: string) {
  const [snapshot, setSnapshot] = useState<RoomSnapshot | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [streaming, setStreaming] = useState(true);
  const latest = useRef<RoomSnapshot | null>(null);
  const offset = useRef(0);
  const path = `/rooms/${encodeURIComponent(roomId)}`;

  const accept = useCallback((value: RoomSnapshot) => {
    if (latest.current && value.event_index < latest.current.event_index) return;
    latest.current = value;
    offset.current = clockOffset(value.server_time, Date.now());
    setSnapshot(value);
    setError(null);
  }, []);

  const refresh = useCallback(async () => {
    try {
      accept(await api<RoomSnapshot>(`${path}/presence`, { method: 'POST' }));
    } catch (cause) {
      setError(cause);
    }
  }, [path, accept]);

  const ended = snapshot ? isTerminal(snapshot.phase) : false;

  useEffect(() => {
    if (ended) return;
    void refresh();
    if (typeof EventSource === 'undefined') {
      setStreaming(false);
      return;
    }
    const source = new EventSource(`/api${path}/events`);
    source.addEventListener('snapshot', (event) => accept(JSON.parse((event as MessageEvent<string>).data) as RoomSnapshot));
    const stop = () => {
      source.close();
      setStreaming(false);
      void refresh();
    };
    source.addEventListener('access_changed', stop);
    source.addEventListener('session_expired', stop);
    // The server ends each stream after ~25 s and the browser reconnects by itself; only a refused stream stays closed.
    source.onerror = () => {
      if (source.readyState === EventSource.CLOSED) setStreaming(false);
    };
    return () => source.close();
  }, [path, ended, accept, refresh]);

  useEffect(() => {
    if (ended) return;
    const timer = window.setInterval(() => void refresh(), streaming ? 4000 : 1500);
    return () => window.clearInterval(timer);
  }, [ended, streaming, refresh]);

  return { snapshot, error, offset, refresh };
}

/** A clock that ticks while a countdown is on screen. */
export function useNow(active: boolean, step = 250): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), step);
    return () => window.clearInterval(timer);
  }, [active, step]);
  return now;
}
