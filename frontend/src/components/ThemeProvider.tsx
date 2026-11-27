"use client";

import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, notifyDesktopThemeMode } from "@/lib/api";
import {
  DEFAULT_THEME,
  deriveThemeTokens,
  THEME_PRESETS,
  ThemeConfig,
} from "@/lib/themes";

const STORAGE_KEY = "telemind_theme_v1";

interface ThemeContextValue {
  theme: ThemeConfig;
  setTheme: (next: ThemeConfig, syncRemote?: boolean) => void;
  applyPreset: (presetId: string) => void;
  resetTheme: () => void;
  syncFromServer: (serverTheme: Partial<ThemeConfig> | undefined) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function applyCssVars(theme: ThemeConfig, systemDark: boolean): void {
  if (typeof document === "undefined") return;
  const tokens = deriveThemeTokens(theme, systemDark);
  const root = document.documentElement;
  (Object.keys(tokens) as Array<keyof typeof tokens>).forEach((key) => {
    root.style.setProperty(key, tokens[key]);
  });
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<ThemeConfig>(DEFAULT_THEME);
  const [systemDark, setSystemDark] = useState(true);

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    setSystemDark(media.matches);
    const onChange = (e: MediaQueryListEvent) => setSystemDark(e.matches);
    media.addEventListener("change", onChange);

    try {
      const saved = window.localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved) as Partial<ThemeConfig>;
        setThemeState({ ...DEFAULT_THEME, ...parsed });
      }
    } catch {
      // ignore corrupted local theme
    }
    return () => media.removeEventListener("change", onChange);
  }, []);

  useEffect(() => {
    applyCssVars(theme, systemDark);
    notifyDesktopThemeMode(theme.mode);
  }, [theme, systemDark]);

  const setTheme = useCallback((next: ThemeConfig, syncRemote = true) => {
    setThemeState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      // ignore storage quota errors
    }
    if (syncRemote) {
      void api.updateTheme(next).catch(() => {
        // local preview continues even if backend is offline
      });
    }
  }, []);

  const applyPreset = useCallback(
    (presetId: string) => {
      const found = THEME_PRESETS.find((p) => p.id === presetId);
      if (!found) return;
      setTheme({
        ...theme,
        preset: found.id,
        accent: found.accent,
        background: found.background,
        foreground: found.foreground,
      });
    },
    [setTheme, theme],
  );

  const resetTheme = useCallback(() => {
    setTheme(DEFAULT_THEME);
  }, [setTheme]);

  const syncFromServer = useCallback((serverTheme: Partial<ThemeConfig> | undefined) => {
    if (!serverTheme) return;
    try {
      const hasLocal = Boolean(window.localStorage.getItem(STORAGE_KEY));
      if (!hasLocal) {
        const merged = { ...DEFAULT_THEME, ...serverTheme };
        setThemeState(merged);
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(merged));
      }
    } catch {
      // ignore local storage issues
    }
  }, []);

  return (
    <ThemeContext.Provider value={{ theme, setTheme, applyPreset, resetTheme, syncFromServer }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useThemeStudio(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error("useThemeStudio must be used inside ThemeProvider");
  }
  return ctx;
}
