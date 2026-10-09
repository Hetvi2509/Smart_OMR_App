import React, { createContext, useContext, useMemo, useState } from 'react';
import { useColorScheme } from 'react-native';

import { Colors, palette } from './index';

type Mode = 'system' | 'light' | 'dark';

type Ctx = {
  colors: Colors;
  dark: boolean;
  mode: Mode;
  setMode: (m: Mode) => void;
};

const ThemeContext = createContext<Ctx | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const system = useColorScheme();
  // Light is the app's default regardless of the device's own OS setting --
  // a phone with system dark mode on would otherwise open the app dark on
  // first launch, before the user has expressed any preference here. The
  // Settings screen still offers System/Light/Dark explicitly.
  const [mode, setMode] = useState<Mode>('light');
  const dark = mode === 'system' ? system === 'dark' : mode === 'dark';

  const value = useMemo<Ctx>(
    () => ({ colors: dark ? palette.dark : palette.light, dark, mode, setMode }),
    [dark, mode],
  );
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): Ctx {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used inside <ThemeProvider>');
  return ctx;
}
