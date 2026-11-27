"use client";

import React, { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, ChevronRight, Copy, Download, RotateCcw, Upload } from "lucide-react";
import { useThemeStudio } from "@/components/ThemeProvider";
import {
  ColorMode,
  contrastRatio,
  FontChoice,
  normalizeHex,
  RadiusChoice,
  THEME_PRESETS,
  ThemeConfig,
} from "@/lib/themes";

export function AppearancePanel() {
  const { theme, setTheme, applyPreset, resetTheme } = useThemeStudio();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [copiedMsg, setCopiedMsg] = useState("");
  const dropdownRef = useRef<HTMLDivElement>(null);
  const importInputRef = useRef<HTMLInputElement>(null);

  const vi = theme.language === "vi";
  const activePreset = THEME_PRESETS.find((p) => p.id === theme.preset);
  const ratio = contrastRatio(theme.background, theme.foreground);

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  const updateColor = (field: "accent" | "background" | "foreground", val: string) => {
    const fallback = theme[field];
    const clean = normalizeHex(val, fallback);
    setTheme({ ...theme, preset: "custom", [field]: clean });
  };

  const handleExport = () => {
    const blob = new Blob([JSON.stringify(theme, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `telemind-theme-${theme.preset}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleCopyJson = async () => {
    await navigator.clipboard.writeText(JSON.stringify(theme, null, 2));
    setCopiedMsg(vi ? "Đã copy JSON" : "Copied JSON");
    setTimeout(() => setCopiedMsg(""), 1800);
  };

  const handleImport = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const parsed = JSON.parse(String(reader.result)) as Partial<ThemeConfig>;
        setTheme({
          ...theme,
          ...parsed,
          accent: normalizeHex(parsed.accent ?? theme.accent, theme.accent),
          background: normalizeHex(parsed.background ?? theme.background, theme.background),
          foreground: normalizeHex(parsed.foreground ?? theme.foreground, theme.foreground),
        });
      } catch {
        // ignore invalid json import
      }
    };
    reader.readAsText(file);
    e.target.value = "";
  };

  const modeCards: Array<{ id: ColorMode; labelVi: string; labelEn: string }> = [
    { id: "system", labelVi: "Hệ thống", labelEn: "System" },
    { id: "light", labelVi: "Sáng", labelEn: "Light" },
    { id: "dark", labelVi: "Tối", labelEn: "Dark" },
  ];

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <header className="space-y-1">
        <h1 className="text-xl font-semibold tracking-tight">
          {vi ? "Giao diện" : "Appearance"}
        </h1>
        <p className="text-xs" style={{ color: "var(--muted)" }}>
          {vi
            ? "Chọn màu sắc và phông chữ hiển thị trong ứng dụng"
            : "Customize colors, theme presets, and typography across the app"}
        </p>
      </header>

      <section className="space-y-4">
        <h2 className="font-mono text-sm font-medium">
          {vi ? "Kiểu giao diện" : "Interface Theme"}
        </h2>

        <div
          className="divide-y border"
          style={{
            backgroundColor: "var(--surface)",
            borderColor: "var(--border)",
            borderRadius: "var(--radius-base)",
          }}
        >
          {/* Chế độ màu */}
          <div className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="text-sm font-medium">{vi ? "Chế độ màu" : "Color Mode"}</div>
              <div className="text-xs" style={{ color: "var(--muted)" }}>
                {vi
                  ? "Sử dụng màu sáng hoặc tối, hoặc theo cài đặt hệ thống"
                  : "Use light, dark, or match your system appearance"}
              </div>
            </div>

            <div className="flex items-center gap-2.5">
              {modeCards.map((card) => {
                const selected = theme.mode === card.id;
                return (
                  <button
                    key={card.id}
                    type="button"
                    onClick={() => setTheme({ ...theme, mode: card.id })}
                    className="group flex flex-col items-center gap-1.5"
                    aria-label={vi ? card.labelVi : card.labelEn}
                  >
                    <div
                      className="relative h-12 w-18 overflow-hidden rounded-lg border-2 p-1.5 transition-all"
                      style={{
                        borderColor: selected ? "var(--accent)" : "var(--border)",
                        background:
                          card.id === "light"
                            ? "#f8fafc"
                            : card.id === "dark"
                              ? "#090d0b"
                              : "linear-gradient(90deg, #f8fafc 50%, #090d0b 50%)",
                      }}
                    >
                      <div className="flex h-full flex-col justify-between">
                        <div className="h-1.5 w-7 rounded-full bg-current opacity-20" />
                        <div className="space-y-1">
                          <div
                            className="h-1.5 w-10 rounded-full"
                            style={{ backgroundColor: "var(--accent)", opacity: 0.85 }}
                          />
                          <div className="h-1 w-8 rounded-full bg-slate-400/40" />
                        </div>
                      </div>
                    </div>
                    <span
                      className="text-[11px]"
                      style={{ color: selected ? "var(--fg)" : "var(--muted)" }}
                    >
                      {vi ? card.labelVi : card.labelEn}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Preset Selector */}
          <div className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between">
            <div className="max-w-md">
              <div className="text-sm font-medium">{vi ? "Giao diện" : "Theme Preset"}</div>
              <div className="text-xs" style={{ color: "var(--muted)" }}>
                {vi
                  ? "Bắt đầu với một mẫu có sẵn, rồi điều chỉnh màu sắc và phông chữ của mẫu đó"
                  : "Start with a curated preset, then fine-tune accent, background, and foreground"}
              </div>
            </div>

            <div className="flex items-center gap-2">
              <input
                ref={importInputRef}
                type="file"
                accept="application/json"
                onChange={handleImport}
                className="hidden"
              />
              <button
                type="button"
                onClick={handleExport}
                title={vi ? "Tải JSON theme" : "Export theme JSON"}
                className="flex h-8 w-8 items-center justify-center rounded-lg border transition-colors hover:opacity-80"
                style={{ borderColor: "var(--border)", backgroundColor: "var(--bg)" }}
              >
                <Download className="h-3.5 w-3.5" style={{ color: "var(--muted)" }} />
              </button>
              <button
                type="button"
                onClick={() => importInputRef.current?.click()}
                title={vi ? "Nhập JSON theme" : "Import theme JSON"}
                className="flex h-8 w-8 items-center justify-center rounded-lg border transition-colors hover:opacity-80"
                style={{ borderColor: "var(--border)", backgroundColor: "var(--bg)" }}
              >
                <Upload className="h-3.5 w-3.5" style={{ color: "var(--muted)" }} />
              </button>
              <button
                type="button"
                onClick={() => void handleCopyJson()}
                title={vi ? "Copy JSON" : "Copy JSON"}
                className="flex h-8 w-8 items-center justify-center rounded-lg border transition-colors hover:opacity-80"
                style={{ borderColor: "var(--border)", backgroundColor: "var(--bg)" }}
              >
                <Copy className="h-3.5 w-3.5" style={{ color: "var(--muted)" }} />
              </button>

              <div className="relative" ref={dropdownRef}>
                <button
                  type="button"
                  onClick={() => setDropdownOpen((o) => !o)}
                  className="flex min-w-44 items-center justify-between gap-3 rounded-lg border px-3 py-1.5 text-xs font-medium"
                  style={{
                    borderColor: "var(--border)",
                    backgroundColor: "var(--bg)",
                    color: "var(--fg)",
                  }}
                >
                  <span className="flex items-center gap-2">
                    <span
                      className="inline-block h-2.5 w-2.5 rounded-full border border-white/20"
                      style={{ backgroundColor: theme.accent }}
                    />
                    {activePreset ? activePreset.label : vi ? "Tùy chỉnh" : "Custom"}
                  </span>
                  <ChevronDown className="h-3.5 w-3.5" style={{ color: "var(--muted)" }} />
                </button>

                {dropdownOpen && (
                  <div
                    className="absolute right-0 z-50 mt-2 w-56 rounded-xl border p-1.5 shadow-2xl"
                    style={{
                      backgroundColor: "var(--surface-elevated)",
                      borderColor: "var(--border)",
                    }}
                  >
                    <div className="max-h-72 space-y-0.5 overflow-y-auto">
                      {THEME_PRESETS.map((preset) => {
                        const isSelected = theme.preset === preset.id;
                        return (
                          <button
                            key={preset.id}
                            type="button"
                            onClick={() => {
                              applyPreset(preset.id);
                              setDropdownOpen(false);
                            }}
                            className="flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-left text-xs transition-colors hover:opacity-90"
                            style={{
                              backgroundColor: isSelected ? "rgba(255,255,255,0.06)" : "transparent",
                              color: "var(--fg)",
                            }}
                          >
                            <span className="flex items-center gap-2.5">
                              <span
                                className="flex h-5 w-5 items-center justify-center rounded-full border text-[10px] font-semibold"
                                style={{
                                  backgroundColor: preset.background,
                                  color: preset.accent,
                                  borderColor: "rgba(255,255,255,0.16)",
                                }}
                              >
                                Aa
                              </span>
                              <span>{preset.label}</span>
                            </span>
                            {isSelected && (
                              <Check className="h-3.5 w-3.5" style={{ color: "var(--accent)" }} />
                            )}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
              {copiedMsg && (
                <span className="text-[11px]" style={{ color: "var(--accent)" }}>
                  {copiedMsg}
                </span>
              )}
            </div>
          </div>

          {/* Màu nhấn */}
          <ColorPickerRow
            label={vi ? "Màu nhấn" : "Accent Color"}
            description={
              vi
                ? "Đặt màu cho các điểm nhấn và thành phần tương tác"
                : "Set the accent color for buttons, focus rings, and highlights"
            }
            value={theme.accent}
            onChange={(v) => updateColor("accent", v)}
          />

          {/* Nền */}
          <ColorPickerRow
            label={vi ? "Nền" : "Background"}
            description={
              vi ? "Đặt màu nền cho nội dung ứng dụng" : "Set the primary canvas background color"
            }
            value={theme.background}
            onChange={(v) => updateColor("background", v)}
          />

          {/* Tiền cảnh */}
          <ColorPickerRow
            label={vi ? "Tiền cảnh" : "Foreground"}
            description={
              vi
                ? `Chọn màu chữ chính (Độ tương phản: ${ratio}:1 ${ratio >= 4.5 ? "· Đạt WCAG AA" : "· Thấp"})`
                : `Primary text color (Contrast: ${ratio}:1 ${ratio >= 4.5 ? "· WCAG AA OK" : "· Low"})`
            }
            value={theme.foreground}
            onChange={(v) => updateColor("foreground", v)}
          />
        </div>

        {/* Cài đặt nâng cao & Đặt lại */}
        <div className="space-y-3">
          <div className="flex items-center justify-between pt-1">
            <button
              type="button"
              onClick={() => setAdvancedOpen((v) => !v)}
              className="flex items-center gap-1 text-xs font-medium transition-opacity hover:opacity-80"
              style={{ color: "var(--muted)" }}
            >
              <span>{vi ? "Cài đặt nâng cao" : "Advanced settings"}</span>
              {advancedOpen ? (
                <ChevronDown className="h-3.5 w-3.5" />
              ) : (
                <ChevronRight className="h-3.5 w-3.5" />
              )}
            </button>

            <button
              type="button"
              onClick={resetTheme}
              className="flex items-center gap-1.5 text-xs font-medium transition-opacity hover:opacity-80"
              style={{ color: "var(--muted)" }}
            >
              <RotateCcw className="h-3.5 w-3.5" />
              <span>{vi ? "Đặt lại về mặc định" : "Reset to default"}</span>
            </button>
          </div>

          {advancedOpen && (
            <div
              className="grid gap-4 border p-4 sm:grid-cols-3"
              style={{
                backgroundColor: "var(--surface)",
                borderColor: "var(--border)",
                borderRadius: "var(--radius-base)",
              }}
            >
              <label className="space-y-1.5 text-xs">
                <span style={{ color: "var(--muted)" }}>
                  {vi ? "Phông chữ" : "Font Family"}
                </span>
                <select
                  value={theme.fontFamily}
                  onChange={(e) =>
                    setTheme({ ...theme, fontFamily: e.target.value as FontChoice })
                  }
                  className="w-full rounded-lg border px-2.5 py-1.5 text-xs outline-none"
                  style={{
                    backgroundColor: "var(--bg)",
                    borderColor: "var(--border)",
                    color: "var(--fg)",
                  }}
                >
                  <option value="sans">Sans (Inter / Clean)</option>
                  <option value="mono">Monospace (Developer)</option>
                  <option value="system">System UI</option>
                </select>
              </label>

              <label className="space-y-1.5 text-xs">
                <span style={{ color: "var(--muted)" }}>
                  {vi ? "Bo góc" : "Corner Radius"}
                </span>
                <select
                  value={theme.radius}
                  onChange={(e) =>
                    setTheme({ ...theme, radius: e.target.value as RadiusChoice })
                  }
                  className="w-full rounded-lg border px-2.5 py-1.5 text-xs outline-none"
                  style={{
                    backgroundColor: "var(--bg)",
                    borderColor: "var(--border)",
                    color: "var(--fg)",
                  }}
                >
                  <option value="sm">{vi ? "Gọn (6px)" : "Compact (6px)"}</option>
                  <option value="md">{vi ? "Vừa (10px)" : "Standard (10px)"}</option>
                  <option value="lg">{vi ? "Mềm (14px)" : "Rounded (14px)"}</option>
                </select>
              </label>

              <label className="space-y-1.5 text-xs">
                <span style={{ color: "var(--muted)" }}>
                  {vi ? "Ngôn ngữ UI" : "UI Language"}
                </span>
                <select
                  value={theme.language}
                  onChange={(e) =>
                    setTheme({ ...theme, language: e.target.value as "vi" | "en" })
                  }
                  className="w-full rounded-lg border px-2.5 py-1.5 text-xs outline-none"
                  style={{
                    backgroundColor: "var(--bg)",
                    borderColor: "var(--border)",
                    color: "var(--fg)",
                  }}
                >
                  <option value="vi">Tiếng Việt</option>
                  <option value="en">English</option>
                </select>
              </label>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

function ColorPickerRow({
  label,
  description,
  value,
  onChange,
}: {
  label: string;
  description: string;
  value: string;
  onChange: (next: string) => void;
}) {
  const [draft, setDraft] = useState(value.toUpperCase());

  useEffect(() => {
    setDraft(value.toUpperCase());
  }, [value]);

  return (
    <div className="flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <div className="text-sm font-medium">{label}</div>
        <div className="text-xs" style={{ color: "var(--muted)" }}>
          {description}
        </div>
      </div>

      <div
        className="flex items-center gap-2 rounded-full border px-2.5 py-1"
        style={{ backgroundColor: "var(--bg)", borderColor: "var(--border)" }}
      >
        <input
          type="color"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          aria-label={label}
          className="h-5 w-5 cursor-pointer rounded-full border-0 bg-transparent p-0"
        />
        <input
          type="text"
          value={draft}
          onChange={(e) => {
            setDraft(e.target.value);
            if (/^#[0-9a-fA-F]{6}$/.test(e.target.value.trim())) {
              onChange(e.target.value.trim());
            }
          }}
          className="w-20 bg-transparent font-mono text-xs uppercase outline-none"
          style={{ color: "var(--fg)" }}
        />
      </div>
    </div>
  );
}
