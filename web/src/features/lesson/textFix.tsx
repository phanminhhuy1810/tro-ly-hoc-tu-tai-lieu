import { createContext, useContext } from 'react';

// Display-only repair for slide text in older lessons (see lib/text.ts).
const TextFix = createContext<(text: string) => string>((text) => text);

export const TextFixProvider = TextFix.Provider;

export function useTextFix() {
  return useContext(TextFix);
}
