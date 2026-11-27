import { describe, expect, it } from "vitest";
import {
  contrastRatio,
  DEFAULT_THEME,
  deriveThemeTokens,
  normalizeHex,
  THEME_PRESETS,
} from "@/lib/themes";

describe("Theme Studio Engine", () => {
  it("normalizes valid hex and falls back on malformed values", () => {
    expect(normalizeHex(" #22C55E ", "#000000")).toBe("#22c55e");
    expect(normalizeHex("not-a-hex", "#111111")).toBe("#111111");
  });

  it("derives dark Matrix tokens accurately", () => {
    const tokens = deriveThemeTokens(DEFAULT_THEME, true);
    expect(tokens["--bg"]).toBe("#040805");
    expect(tokens["--fg"]).toBe("#ffffff");
    expect(tokens["--accent"]).toBe("#22c55e");
  });

  it("switches canvas cleanly in light mode while keeping accent", () => {
    const tokens = deriveThemeTokens({ ...DEFAULT_THEME, mode: "light" }, true);
    expect(tokens["--bg"]).toBe("#f7f8fa");
    expect(tokens["--fg"]).toBe("#0f172a");
    expect(tokens["--accent"]).toBe("#22c55e");
  });

  it("provides accessible contrast across all built-in presets", () => {
    for (const preset of THEME_PRESETS) {
      expect(contrastRatio(preset.background, preset.foreground)).toBeGreaterThanOrEqual(7);
    }
  });
});
