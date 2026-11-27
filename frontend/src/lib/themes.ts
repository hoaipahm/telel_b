export type ColorMode = "system" | "light" | "dark";
export type FontChoice = "sans" | "mono" | "system";
export type RadiusChoice = "sm" | "md" | "lg";
export type LanguageChoice = "vi" | "en";

export interface ThemeConfig {
  mode: ColorMode;
  preset: string;
  accent: string;
  background: string;
  foreground: string;
  fontFamily: FontChoice;
  radius: RadiusChoice;
  language: LanguageChoice;
}

export interface ThemePreset {
  id: string;
  label: string;
  accent: string;
  background: string;
  foreground: string;
}

export const THEME_PRESETS: ThemePreset[] = [
  { id: "matrix", label: "Matrix", accent: "#22c55e", background: "#040805", foreground: "#ffffff" },
  { id: "monokai", label: "Monokai", accent: "#a6e22e", background: "#1e1f1c", foreground: "#f8f8f2" },
  { id: "night-owl", label: "Night Owl", accent: "#82aaff", background: "#011627", foreground: "#d6deeb" },
  { id: "nord", label: "Nord", accent: "#88c0d0", background: "#2e3440", foreground: "#eceff4" },
  { id: "notion", label: "Notion", accent: "#2383e2", background: "#191919", foreground: "#e6e6e5" },
  { id: "material", label: "Material", accent: "#84ffff", background: "#0f111a", foreground: "#eeffff" },
  { id: "lobster", label: "Lobster", accent: "#f43f5e", background: "#160b0b", foreground: "#fff1f2" },
  { id: "og", label: "OG", accent: "#a1a1aa", background: "#09090b", foreground: "#fafafa" },
  { id: "one", label: "One", accent: "#61afef", background: "#1e222a", foreground: "#abb2bf" },
];

export const DEFAULT_THEME: ThemeConfig = {
  mode: "dark",
  preset: "matrix",
  accent: "#22c55e",
  background: "#040805",
  foreground: "#ffffff",
  fontFamily: "sans",
  radius: "md",
  language: "vi",
};

export function normalizeHex(raw: string, fallback: string): string {
  const clean = raw.trim();
  if (/^#[0-9a-fA-F]{6}$/.test(clean)) {
    return clean.toLowerCase();
  }
  return fallback;
}

function hexToRgb(hex: string): [number, number, number] {
  const clean = normalizeHex(hex, "#000000").slice(1);
  return [
    Number.parseInt(clean.slice(0, 2), 16),
    Number.parseInt(clean.slice(2, 4), 16),
    Number.parseInt(clean.slice(4, 6), 16),
  ];
}

function mixHex(hexA: string, hexB: string, ratioB: number): string {
  const [r1, g1, b1] = hexToRgb(hexA);
  const [r2, g2, b2] = hexToRgb(hexB);
  const clamp = (v: number) => Math.max(0, Math.min(255, Math.round(v)));
  const r = clamp(r1 * (1 - ratioB) + r2 * ratioB);
  const g = clamp(g1 * (1 - ratioB) + g2 * ratioB);
  const b = clamp(b1 * (1 - ratioB) + b2 * ratioB);
  return `#${[r, g, b].map((c) => c.toString(16).padStart(2, "0")).join("")}`;
}

function relativeLuminance(hex: string): number {
  const [r, g, b] = hexToRgb(hex).map((c) => {
    const srgb = c / 255;
    return srgb <= 0.03928 ? srgb / 12.92 : ((srgb + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * (r ?? 0) + 0.7152 * (g ?? 0) + 0.0722 * (b ?? 0);
}

export function contrastRatio(hex1: string, hex2: string): number {
  const l1 = relativeLuminance(hex1);
  const l2 = relativeLuminance(hex2);
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  return Number(((lighter + 0.05) / (darker + 0.05)).toFixed(2));
}

export interface DerivedCssTokens {
  "--bg": string;
  "--fg": string;
  "--accent": string;
  "--surface": string;
  "--surface-elevated": string;
  "--border": string;
  "--muted": string;
  "--radius-base": string;
  "--font-active": string;
}

export function deriveThemeTokens(theme: ThemeConfig, systemPrefersDark: boolean): DerivedCssTokens {
  const effectiveDark =
    theme.mode === "dark" || (theme.mode === "system" && systemPrefersDark);

  const bg = effectiveDark ? normalizeHex(theme.background, "#040805") : "#f7f8fa";
  const fg = effectiveDark ? normalizeHex(theme.foreground, "#ffffff") : "#0f172a";
  const accent = normalizeHex(theme.accent, "#22c55e");

  const surface = effectiveDark ? mixHex(bg, "#ffffff", 0.035) : "#ffffff";
  const surfaceElevated = effectiveDark ? mixHex(bg, "#ffffff", 0.075) : "#eef2f6";
  const [fr, fgG, fb] = hexToRgb(fg);
  const border = `rgba(${fr}, ${fgG}, ${fb}, ${effectiveDark ? 0.09 : 0.12})`;
  const muted = mixHex(fg, bg, 0.42);

  const radiusMap: Record<RadiusChoice, string> = {
    sm: "6px",
    md: "10px",
    lg: "14px",
  };
  const fontMap: Record<FontChoice, string> = {
    sans: 'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    mono: '"Cascadia Code", "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
    system: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif",
  };

  return {
    "--bg": bg,
    "--fg": fg,
    "--accent": accent,
    "--surface": surface,
    "--surface-elevated": surfaceElevated,
    "--border": border,
    "--muted": muted,
    "--radius-base": radiusMap[theme.radius],
    "--font-active": fontMap[theme.fontFamily],
  };
}
