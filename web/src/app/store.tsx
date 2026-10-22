import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { api } from '../api/client';
import type { CoinPolicy, Wallet } from '../api/types';

export type MotionPref = 'system' | 'off';
export type ChatSize = 'closed' | 'small' | 'large';

export interface ChatContext {
  courseId: string;
  courseTitle: string;
  unitId: string;
  unitTitle: string;
  /** Present while a check question is on screen; the learner chooses whether to attach it. */
  question?: { sessionId: string; itemId: string; label: string; returnTo: string };
}

interface Toast {
  id: number;
  text: string;
}

interface AppState {
  wallet: Wallet | null;
  refreshWallet: () => void;
  /** Coin price of an AI action as configured on the server (0 while Coin is not enforced). */
  priceOf: (task: string) => number;
  toast: (text: string) => void;
  toasts: Toast[];
  motion: MotionPref;
  setMotion: (value: MotionPref) => void;
  chatSize: ChatSize;
  setChatSize: (value: ChatSize) => void;
  chatContext: ChatContext | null;
  setChatContext: (value: ChatContext | null) => void;
}

const Context = createContext<AppState | null>(null);

function stored<T extends string>(key: string, allowed: readonly T[], fallback: T): T {
  try {
    const value = localStorage.getItem(key) as T | null;
    return value && allowed.includes(value) ? value : fallback;
  } catch {
    return fallback;
  }
}

function remember(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* Private mode: preference just lasts for this tab. */
  }
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [motion, setMotionState] = useState<MotionPref>(() => stored('folio.motion', ['system', 'off'] as const, 'system'));
  const [policy, setPolicy] = useState<CoinPolicy | null>(null);
  const [chatSize, setChatSizeState] = useState<ChatSize>(() => stored('folio.chat', ['closed', 'small', 'large'] as const, 'closed'));
  const [chatContext, setChatContext] = useState<ChatContext | null>(null);
  const counter = useRef(0);

  const refreshWallet = useCallback(() => {
    api<Wallet>('/wallet')
      .then(setWallet)
      .catch(() => setWallet(null));
  }, []);

  useEffect(() => {
    api<CoinPolicy>('/coin/policy')
      .then(setPolicy)
      .catch(() => setPolicy(null));
  }, []);

  const priceOf = useCallback(
    (task: string) => (policy && policy.enforcement_enabled === false ? 0 : policy?.prices?.[task] ?? 1),
    [policy],
  );

  const toast = useCallback((text: string) => {
    counter.current += 1;
    const id = counter.current;
    setToasts((list) => [...list.slice(-2), { id, text }]);
    window.setTimeout(() => setToasts((list) => list.filter((t) => t.id !== id)), 3600);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.motion = motion === 'off' ? 'off' : 'system';
  }, [motion]);

  const value = useMemo<AppState>(
    () => ({
      wallet,
      refreshWallet,
      priceOf,
      toast,
      toasts,
      motion,
      setMotion: (next) => {
        setMotionState(next);
        remember('folio.motion', next);
      },
      chatSize,
      setChatSize: (next) => {
        setChatSizeState(next);
        remember('folio.chat', next);
      },
      chatContext,
      setChatContext,
    }),
    [wallet, refreshWallet, priceOf, toast, toasts, motion, chatSize, chatContext],
  );

  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useApp(): AppState {
  const value = useContext(Context);
  if (!value) throw new Error('useApp must be used inside AppProvider');
  return value;
}

/** Load data with explicit loading/error states and a reload handle. */
export function useLoad<T>(load: () => Promise<T>, deps: unknown[]) {
  const [state, setState] = useState<{ data?: T; error?: unknown; loading: boolean }>({ loading: true });
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  useEffect(() => {
    let alive = true;
    setState((previous) => ({ data: previous.data, loading: true }));
    load()
      .then((data) => alive && setState({ data, loading: false }))
      .catch((error) => alive && setState({ error, loading: false }));
    return () => {
      alive = false;
    };
  }, [...deps, tick]);
  return { ...state, reload };
}
