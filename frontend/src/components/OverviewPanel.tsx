"use client";

import React, { useEffect, useState } from "react";
import {
  Check,
  KeyRound,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { AITestResult, api, ModuleFlags, OverviewData } from "@/lib/api";
import { NavTab } from "@/components/Sidebar";

interface OverviewPanelProps {
  overview: OverviewData;
  onRefresh: () => Promise<void>;
  onNavigate: (tab: NavTab) => void;
  lang: "vi" | "en";
  mode: "overview" | "settings";
}

export function OverviewPanel({
  overview,
  onRefresh,
  onNavigate,
  lang,
  mode,
}: OverviewPanelProps) {
  const vi = lang === "vi";
  const [modules, setModules] = useState<ModuleFlags>(overview.modules);
  const [aiCfg, setAiCfg] = useState(overview.ai);
  const [allowlistText, setAllowlistText] = useState(overview.bot.allowed_user_ids.join(", "));
  const [personas, setPersonas] = useState<Record<string, string>>(overview.personas);
  const [tgToken, setTgToken] = useState("");
  const [geminiKey, setGeminiKey] = useState("");
  const [openaiKey, setOpenaiKey] = useState("");
  const [statusMsg, setStatusMsg] = useState("");
  const [errorMsg, setErrorMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [testResults, setTestResults] = useState<Partial<Record<"gemini" | "openai", AITestResult>>>({});
  const [testingProvider, setTestingProvider] = useState<"gemini" | "openai" | null>(null);

  // Persona editor states
  const [newPersonaName, setNewPersonaName] = useState("");
  const [newPersonaPrompt, setNewPersonaPrompt] = useState("");
  const [editingPersona, setEditingPersona] = useState<string | null>(null);
  const [editingPrompt, setEditingPrompt] = useState("");

  useEffect(() => {
    setModules(overview.modules);
    setAiCfg(overview.ai);
    setAllowlistText(overview.bot.allowed_user_ids.join(", "));
    setPersonas(overview.personas);
  }, [overview]);

  const flash = (msg: string, isErr = false) => {
    if (isErr) {
      setErrorMsg(msg);
      setStatusMsg("");
      setTimeout(() => setErrorMsg(""), 4500);
    } else {
      setStatusMsg(msg);
      setErrorMsg("");
      setTimeout(() => setStatusMsg(""), 3200);
    }
  };

  const toggleModule = async (key: keyof ModuleFlags) => {
    const next = { ...modules, [key]: !modules[key] };
    setModules(next);
    await api.updateModules(next);
    await onRefresh();
    flash(vi ? "Đã cập nhật trạng thái module." : "Updated module toggle.");
  };

  const saveSecret = async (provider: "telegram" | "gemini" | "openai", val: string) => {
    setBusy(true);
    try {
      await api.setSecret(provider, val);
      if (provider === "telegram") setTgToken("");
      if (provider === "gemini") setGeminiKey("");
      if (provider === "openai") setOpenaiKey("");
      await onRefresh();
      flash(vi ? `Đã mã hóa & lưu key ${provider}.` : `Encrypted & saved ${provider} key.`);
    } catch (err) {
      flash(err instanceof Error ? err.message : "Failed to save key", true);
    } finally {
      setBusy(false);
    }
  };

  const removeSecret = async (provider: "telegram" | "gemini" | "openai") => {
    setBusy(true);
    try {
      await api.deleteSecret(provider);
      await onRefresh();
      flash(vi ? `Đã xóa key ${provider}.` : `Deleted ${provider} key.`);
    } catch (err) {
      flash(err instanceof Error ? err.message : "Failed to delete key", true);
    } finally {
      setBusy(false);
    }
  };

  const runTestProvider = async (provider: "gemini" | "openai") => {
    setTestingProvider(provider);
    try {
      const res = await api.testAI(provider);
      setTestResults((prev) => ({ ...prev, [provider]: res }));
      if (res.ok) {
        flash(
          vi
            ? `Kết nối ${provider.toUpperCase()} OK (${res.latency_ms}ms, tìm thấy ${res.models.length} model).`
            : `${provider.toUpperCase()} connected (${res.latency_ms}ms).`,
        );
      } else {
        flash(res.error || "Test failed", true);
      }
    } finally {
      setTestingProvider(null);
    }
  };

  const saveAIConfig = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.updateAI(aiCfg);
      const ids = allowlistText
        .split(",")
        .map((s) => Number.parseInt(s.trim(), 10))
        .filter((n) => Number.isFinite(n) && n > 0);
      await api.updateAllowlist(ids);
      await onRefresh();
      flash(vi ? "Đã lưu cấu hình AI & Allowlist." : "Saved AI config & allowlist.");
    } catch (err) {
      flash(err instanceof Error ? err.message : "Failed to save settings", true);
    } finally {
      setBusy(false);
    }
  };

  const persistPersonas = async (nextPersonas: Record<string, string>, nextActive?: string) => {
    setBusy(true);
    try {
      const updated = await api.updatePersonas(nextPersonas);
      setPersonas(updated);
      if (nextActive && updated[nextActive]) {
        const nextAi = { ...aiCfg, active_persona: nextActive };
        await api.updateAI(nextAi);
        setAiCfg(nextAi);
      }
      await onRefresh();
      flash(vi ? "Đã cập nhật Persona." : "Updated personas.");
    } finally {
      setBusy(false);
    }
  };

  const addPersona = async (e: React.FormEvent) => {
    e.preventDefault();
    const key = newPersonaName.trim().toLowerCase().replace(/\s+/g, "_");
    const prompt = newPersonaPrompt.trim();
    if (!key || !prompt) return;
    await persistPersonas({ ...personas, [key]: prompt });
    setNewPersonaName("");
    setNewPersonaPrompt("");
  };

  const savePersonaEdit = async (key: string) => {
    if (!editingPrompt.trim()) return;
    await persistPersonas({ ...personas, [key]: editingPrompt.trim() });
    setEditingPersona(null);
  };

  const deletePersona = async (key: string) => {
    if (Object.keys(personas).length <= 1) {
      flash(vi ? "Phải giữ lại ít nhất 1 persona." : "At least one persona is required.", true);
      return;
    }
    const copy = { ...personas };
    delete copy[key];
    const fallbackActive =
      aiCfg.active_persona === key ? Object.keys(copy)[0] : aiCfg.active_persona;
    await persistPersonas(copy, fallbackActive);
  };

  const moduleMeta: Array<{
    key: keyof ModuleFlags;
    titleVi: string;
    titleEn: string;
    descVi: string;
    descEn: string;
    tab?: NavTab;
  }> = [
    {
      key: "chat",
      titleVi: "AI Chat đa model",
      titleEn: "Multi-Model AI Chat",
      descVi: "Chat Gemini / OpenAI, đổi persona, đọc ảnh & PDF.",
      descEn: "Gemini / OpenAI chat, personas, image & PDF analysis.",
      tab: "conversations",
    },
    {
      key: "brain",
      titleVi: "Second Brain & Nhắc việc",
      titleEn: "Second Brain & Reminders",
      descVi: "Lưu ghi chú tìm kiếm FTS5 và hẹn giờ nhắc qua Telegram.",
      descEn: "FTS5 notes search and scheduled Telegram reminders.",
      tab: "brain",
    },
    {
      key: "finance",
      titleVi: "Tài chính cá nhân",
      titleEn: "Personal Finance",
      descVi: "Ghi thu/chi (/chi 55k), đọc ảnh hóa đơn, xuất CSV.",
      descEn: "Log income/expenses, receipt OCR, monthly stats & CSV.",
      tab: "finance",
    },
    {
      key: "digest",
      titleVi: "Đọc hộ & Điểm tin (SSRF Safe)",
      titleEn: "Link & RSS Digest",
      descVi: "Tóm tắt bài viết web và theo dõi nguồn RSS công khai.",
      descEn: "Summarize web pages and subscribe to RSS feeds safely.",
      tab: "digest",
    },
    {
      key: "remote",
      titleVi: "PC & Docker Remote (Bảo mật 2 lớp)",
      titleEn: "PC & Docker Remote (2FA)",
      descVi: "Tắt mặc định. Chỉ chạy lệnh whitelist sau khi bấm xác nhận 60s.",
      descEn: "Disabled by default. Allowlisted commands require 60s confirm.",
      tab: "remote",
    },
  ];

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">
            {mode === "overview"
              ? vi
                ? "Tổng quan & Điều khiển Module"
                : "Overview & Modular Controls"
              : vi
                ? "Cài đặt chung, API Keys & AI Persona"
                : "Settings, API Keys & AI Personas"}
          </h1>
          <p className="text-xs" style={{ color: "var(--muted)" }}>
            {vi
              ? "Toàn bộ API keys được mã hóa Fernet trên máy và hỗ trợ kiểm tra/xóa trực tiếp."
              : "All API keys are Fernet-encrypted locally and can be tested or removed anytime."}
          </p>
        </div>

        <button
          type="button"
          onClick={() =>
            void api.reloadBot().then(async (res) => {
              await onRefresh();
              flash(
                res.running
                  ? vi
                    ? "Bot Telegram đã khởi động lại."
                    : "Telegram bot reloaded."
                  : res.last_error || "Bot offline",
                !res.running,
              );
            })
          }
          className="flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium hover:opacity-80"
          style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)" }}
        >
          <RefreshCw className="h-3.5 w-3.5" />
          <span>{vi ? "Tải lại Telegram Bot" : "Reload Bot"}</span>
        </button>
      </div>

      {statusMsg && (
        <div
          className="rounded-lg border px-3.5 py-2 text-xs font-medium"
          style={{
            borderColor: "var(--accent)",
            backgroundColor: "var(--surface-elevated)",
            color: "var(--accent)",
          }}
        >
          {statusMsg}
        </div>
      )}
      {errorMsg && (
        <div
          className="rounded-lg border px-3.5 py-2 text-xs font-medium"
          style={{
            borderColor: "#ef4444",
            backgroundColor: "var(--surface)",
            color: "#fca5a5",
          }}
        >
          {errorMsg}
        </div>
      )}

      {mode === "overview" && (
        <div className="grid gap-6 lg:grid-cols-3">
          <div className="space-y-6 lg:col-span-2">
            {/* Status Row */}
            <div className="grid gap-3 sm:grid-cols-3">
              <StatBox
                label={vi ? "Trạng thái Telegram" : "Telegram Status"}
                value={overview.bot.running ? "Online" : "Offline"}
                sub={overview.bot.last_error || (vi ? "Polling cục bộ an toàn" : "Local polling active")}
              />
              <StatBox
                label={vi ? "Lượt gọi AI hôm nay" : "Daily AI Requests"}
                value={`${overview.usage.requests} / ${overview.ai.daily_request_cap}`}
                sub={`${overview.usage.total_tokens.toLocaleString()} tokens`}
              />
              <StatBox
                label={vi ? "AI Provider mặc định" : "Primary AI Provider"}
                value={overview.ai.primary_provider.toUpperCase()}
                sub={
                  overview.ai.primary_provider === "gemini"
                    ? overview.ai.gemini_model
                    : overview.ai.openai_model
                }
              />
            </div>

            {/* Module Toggles */}
            <div
              className="divide-y border"
              style={{
                backgroundColor: "var(--surface)",
                borderColor: "var(--border)",
                borderRadius: "var(--radius-base)",
              }}
            >
              {moduleMeta.map((m) => {
                const enabled = modules[m.key];
                return (
                  <div key={m.key} className="flex items-center justify-between gap-4 p-4">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium">{vi ? m.titleVi : m.titleEn}</span>
                        {m.tab && (
                          <button
                            type="button"
                            onClick={() => onNavigate(m.tab!)}
                            className="text-[11px] underline opacity-75 hover:opacity-100"
                            style={{ color: "var(--accent)" }}
                          >
                            {vi ? "Mở" : "Open"}
                          </button>
                        )}
                      </div>
                      <div className="text-xs" style={{ color: "var(--muted)" }}>
                        {vi ? m.descVi : m.descEn}
                      </div>
                    </div>
                    <button
                      type="button"
                      role="switch"
                      aria-checked={enabled}
                      onClick={() => void toggleModule(m.key)}
                      className="relative h-6 w-11 shrink-0 rounded-full border transition-colors"
                      style={{
                        backgroundColor: enabled ? "var(--accent)" : "var(--bg)",
                        borderColor: "var(--border)",
                      }}
                    >
                      <span
                        className="block h-4 w-4 rounded-full bg-white transition-transform"
                        style={{
                          transform: enabled ? "translateX(22px)" : "translateX(3px)",
                        }}
                      />
                    </button>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Command Cheat-Sheet Sidebar */}
          <div
            className="space-y-3 border p-5"
            style={{
              backgroundColor: "var(--surface)",
              borderColor: "var(--border)",
              borderRadius: "var(--radius-base)",
            }}
          >
            <h2 className="text-sm font-semibold">
              {vi ? "Lệnh nhanh trên Telegram" : "Telegram Quick Commands"}
            </h2>
            <ul className="space-y-2 text-xs" style={{ color: "var(--muted)" }}>
              <li><code className="font-mono text-[11px]" style={{ color: "var(--accent)" }}>/model gemini|openai</code> — Đổi AI</li>
              <li><code className="font-mono text-[11px]" style={{ color: "var(--accent)" }}>/mode &lt;persona&gt;</code> — Đổi vai trò AI</li>
              <li><code className="font-mono text-[11px]" style={{ color: "var(--accent)" }}>/clear</code> — Xóa ngữ cảnh chat</li>
              <li><code className="font-mono text-[11px]" style={{ color: "var(--accent)" }}>/note Tiêu đề | Nội dung #tag</code></li>
              <li><code className="font-mono text-[11px]" style={{ color: "var(--accent)" }}>/find từ khóa</code> — Tìm ghi chú FTS5</li>
              <li><code className="font-mono text-[11px]" style={{ color: "var(--accent)" }}>/remind 30m Nội dung</code> — Nhắc việc</li>
              <li><code className="font-mono text-[11px]" style={{ color: "var(--accent)" }}>/chi 55k ăn trưa</code>, <code className="font-mono text-[11px]" style={{ color: "var(--accent)" }}>/thu 15tr lương</code></li>
              <li><code className="font-mono text-[11px]" style={{ color: "var(--accent)" }}>/thongke</code> hoặc ảnh + <code className="font-mono text-[11px]" style={{ color: "var(--accent)" }}>/bill</code></li>
              <li><code className="font-mono text-[11px]" style={{ color: "var(--accent)" }}>/tomtat https://...</code> &amp; <code className="font-mono text-[11px]" style={{ color: "var(--accent)" }}>/feed</code></li>
              <li><code className="font-mono text-[11px]" style={{ color: "var(--accent)" }}>/pc</code>, <code className="font-mono text-[11px]" style={{ color: "var(--accent)" }}>/docker</code> (Remote)</li>
            </ul>
            <button
              type="button"
              onClick={() => onNavigate("conversations")}
              className="w-full rounded-lg px-3 py-2 text-xs font-semibold"
              style={{ backgroundColor: "var(--accent)", color: "#040805" }}
            >
              {vi ? "Chat thử với AI ngay" : "Test AI Chat Now"}
            </button>
          </div>
        </div>
      )}

      {mode === "settings" && (
        <div className="space-y-6">
          {/* Encrypted Secrets Vault */}
          <div
            className="space-y-4 border p-5"
            style={{
              backgroundColor: "var(--surface)",
              borderColor: "var(--border)",
              borderRadius: "var(--radius-base)",
            }}
          >
            <div className="flex items-center gap-2 text-sm font-medium">
              <KeyRound className="h-4 w-4" style={{ color: "var(--accent)" }} />
              <span>{vi ? "Kho khóa mã hóa (Fernet Vault)" : "Encrypted Key Vault"}</span>
            </div>

            <SecretRow
              title="Telegram Bot Token (@BotFather)"
              hint={overview.secrets.telegram.hint}
              configured={overview.secrets.telegram.configured}
              value={tgToken}
              onChange={setTgToken}
              onSave={() => void saveSecret("telegram", tgToken)}
              onDelete={() => void removeSecret("telegram")}
              busy={busy}
            />

            <SecretRow
              title="Google Gemini API Key (AI Studio)"
              hint={overview.secrets.gemini.hint}
              configured={overview.secrets.gemini.configured}
              value={geminiKey}
              onChange={setGeminiKey}
              onSave={() => void saveSecret("gemini", geminiKey)}
              onDelete={() => void removeSecret("gemini")}
              onTest={() => void runTestProvider("gemini")}
              testing={testingProvider === "gemini"}
              testResult={testResults.gemini}
              onPickModel={(m) => {
                const next = { ...aiCfg, gemini_model: m };
                setAiCfg(next);
                void api.updateAI(next).then(onRefresh).then(() => {
                  flash(vi ? `Đã đổi Gemini model sang ${m}` : `Selected ${m}`);
                });
              }}
              activeModel={aiCfg.gemini_model}
              busy={busy}
            />

            <SecretRow
              title="OpenAI API Key (hoặc Local Endpoint)"
              hint={overview.secrets.openai.hint}
              configured={overview.secrets.openai.configured}
              value={openaiKey}
              onChange={setOpenaiKey}
              onSave={() => void saveSecret("openai", openaiKey)}
              onDelete={() => void removeSecret("openai")}
              onTest={() => void runTestProvider("openai")}
              testing={testingProvider === "openai"}
              testResult={testResults.openai}
              onPickModel={(m) => {
                const next = { ...aiCfg, openai_model: m };
                setAiCfg(next);
                void api.updateAI(next).then(onRefresh).then(() => {
                  flash(vi ? `Đã đổi OpenAI model sang ${m}` : `Selected ${m}`);
                });
              }}
              activeModel={aiCfg.openai_model}
              busy={busy}
            />
          </div>

          {/* AI Router & Fail-Closed Allowlist */}
          <form
            onSubmit={(e) => void saveAIConfig(e)}
            className="space-y-4 border p-5"
            style={{
              backgroundColor: "var(--surface)",
              borderColor: "var(--border)",
              borderRadius: "var(--radius-base)",
            }}
          >
            <div className="flex items-center gap-2 text-sm font-medium">
              <ShieldCheck className="h-4 w-4" style={{ color: "var(--accent)" }} />
              <span>AI Router, Budget &amp; Allowlist</span>
            </div>

            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <label className="space-y-1 text-xs">
                <span style={{ color: "var(--muted)" }}>Primary Provider</span>
                <select
                  value={aiCfg.primary_provider}
                  onChange={(e) =>
                    setAiCfg({ ...aiCfg, primary_provider: e.target.value as "gemini" | "openai" })
                  }
                  className="w-full rounded-lg border px-3 py-2 text-xs outline-none"
                  style={{ backgroundColor: "var(--bg)", borderColor: "var(--border)" }}
                >
                  <option value="gemini">Google Gemini (Free / Paid)</option>
                  <option value="openai">OpenAI / Local Compatible</option>
                </select>
              </label>

              <label className="space-y-1 text-xs">
                <span style={{ color: "var(--muted)" }}>Gemini Model ID</span>
                <input
                  type="text"
                  value={aiCfg.gemini_model}
                  onChange={(e) => setAiCfg({ ...aiCfg, gemini_model: e.target.value })}
                  className="w-full rounded-lg border px-3 py-2 font-mono text-xs outline-none"
                  style={{ backgroundColor: "var(--bg)", borderColor: "var(--border)" }}
                />
              </label>

              <label className="space-y-1 text-xs">
                <span style={{ color: "var(--muted)" }}>OpenAI Model ID</span>
                <input
                  type="text"
                  value={aiCfg.openai_model}
                  onChange={(e) => setAiCfg({ ...aiCfg, openai_model: e.target.value })}
                  className="w-full rounded-lg border px-3 py-2 font-mono text-xs outline-none"
                  style={{ backgroundColor: "var(--bg)", borderColor: "var(--border)" }}
                />
              </label>

              <label className="space-y-1 text-xs">
                <span style={{ color: "var(--muted)" }}>OpenAI Base URL</span>
                <input
                  type="text"
                  value={aiCfg.openai_base_url}
                  onChange={(e) => setAiCfg({ ...aiCfg, openai_base_url: e.target.value })}
                  className="w-full rounded-lg border px-3 py-2 font-mono text-xs outline-none"
                  style={{ backgroundColor: "var(--bg)", borderColor: "var(--border)" }}
                />
              </label>

              <label className="space-y-1 text-xs">
                <span style={{ color: "var(--muted)" }}>
                  {vi ? "Giới hạn request/ngày" : "Daily Request Cap"}
                </span>
                <input
                  type="number"
                  value={aiCfg.daily_request_cap}
                  onChange={(e) =>
                    setAiCfg({ ...aiCfg, daily_request_cap: Number(e.target.value) || 200 })
                  }
                  className="w-full rounded-lg border px-3 py-2 text-xs tabular-nums outline-none"
                  style={{ backgroundColor: "var(--bg)", borderColor: "var(--border)" }}
                />
              </label>

              <label className="space-y-1 text-xs">
                <span style={{ color: "var(--muted)" }}>
                  {vi
                    ? "Allowed Telegram User IDs (nhiều ID cách bằng dấu phẩy)"
                    : "Allowed Telegram User IDs (comma-separated)"}
                </span>
                <input
                  type="text"
                  value={allowlistText}
                  onChange={(e) => setAllowlistText(e.target.value)}
                  placeholder="123456789"
                  className="w-full rounded-lg border px-3 py-2 font-mono text-xs outline-none"
                  style={{ backgroundColor: "var(--bg)", borderColor: "var(--border)" }}
                />
              </label>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
              <label className="flex items-center gap-2 text-xs">
                <input
                  type="checkbox"
                  checked={aiCfg.fallback_enabled}
                  onChange={(e) => setAiCfg({ ...aiCfg, fallback_enabled: e.target.checked })}
                />
                <span>
                  {vi
                    ? "Tự động fallback sang provider còn lại khi lỗi"
                    : "Automatic fallback to secondary provider"}
                </span>
              </label>

              <button
                type="submit"
                disabled={busy}
                className="rounded-lg px-4 py-2 text-xs font-semibold"
                style={{ backgroundColor: "var(--accent)", color: "#040805" }}
              >
                {vi ? "Lưu cấu hình" : "Save Configuration"}
              </button>
            </div>
          </form>

          {/* AI Personas Manager */}
          <div
            className="space-y-4 border p-5"
            style={{
              backgroundColor: "var(--surface)",
              borderColor: "var(--border)",
              borderRadius: "var(--radius-base)",
            }}
          >
            <div className="flex items-center gap-2 text-sm font-medium">
              <Sparkles className="h-4 w-4" style={{ color: "var(--accent)" }} />
              <span>{vi ? "Quản lý AI Personas (Vai trò trợ lý)" : "AI Personas"}</span>
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              {Object.entries(personas).map(([key, prompt]) => {
                const isActive = aiCfg.active_persona === key;
                const isEditing = editingPersona === key;
                return (
                  <div
                    key={key}
                    className="space-y-2 border p-3.5"
                    style={{
                      backgroundColor: "var(--bg)",
                      borderColor: isActive ? "var(--accent)" : "var(--border)",
                      borderRadius: "var(--radius-base)",
                    }}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          const next = { ...aiCfg, active_persona: key };
                          setAiCfg(next);
                          void api.updateAI(next).then(onRefresh).then(() => {
                            flash(vi ? `Đang dùng persona: ${key}` : `Active persona: ${key}`);
                          });
                        }}
                        className="flex items-center gap-1.5 text-xs font-semibold"
                      >
                        <span className="font-mono">{key}</span>
                        {isActive && (
                          <span
                            className="rounded-full px-2 py-0.5 text-[10px] font-semibold"
                            style={{ backgroundColor: "var(--accent)", color: "#040805" }}
                          >
                            Active
                          </span>
                        )}
                      </button>

                      <div className="flex items-center gap-1.5">
                        {isEditing ? (
                          <>
                            <button
                              type="button"
                              onClick={() => void savePersonaEdit(key)}
                              title={vi ? "Lưu" : "Save"}
                              className="opacity-80 hover:opacity-100"
                              style={{ color: "var(--accent)" }}
                            >
                              <Check className="h-3.5 w-3.5" />
                            </button>
                            <button
                              type="button"
                              onClick={() => setEditingPersona(null)}
                              title={vi ? "Hủy" : "Cancel"}
                              className="opacity-70 hover:opacity-100"
                            >
                              <X className="h-3.5 w-3.5" />
                            </button>
                          </>
                        ) : (
                          <>
                            <button
                              type="button"
                              onClick={() => {
                                setEditingPersona(key);
                                setEditingPrompt(prompt);
                              }}
                              title={vi ? "Sửa" : "Edit"}
                              className="opacity-60 hover:opacity-100"
                            >
                              <Pencil className="h-3.5 w-3.5" />
                            </button>
                            <button
                              type="button"
                              onClick={() => void deletePersona(key)}
                              title={vi ? "Xóa" : "Delete"}
                              className="opacity-60 hover:opacity-100"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </>
                        )}
                      </div>
                    </div>

                    {isEditing ? (
                      <textarea
                        rows={3}
                        value={editingPrompt}
                        onChange={(e) => setEditingPrompt(e.target.value)}
                        className="w-full rounded-lg border px-2.5 py-1.5 text-xs outline-none"
                        style={{ backgroundColor: "var(--surface)", borderColor: "var(--border)" }}
                      />
                    ) : (
                      <p className="text-xs leading-relaxed" style={{ color: "var(--muted)" }}>
                        {prompt}
                      </p>
                    )}
                  </div>
                );
              })}
            </div>

            <form onSubmit={(e) => void addPersona(e)} className="grid gap-2 sm:grid-cols-4">
              <input
                type="text"
                value={newPersonaName}
                onChange={(e) => setNewPersonaName(e.target.value)}
                placeholder={vi ? "Tên persona (vd: mentor)" : "Persona key"}
                className="rounded-lg border px-3 py-2 font-mono text-xs outline-none"
                style={{ backgroundColor: "var(--bg)", borderColor: "var(--border)" }}
              />
              <input
                type="text"
                value={newPersonaPrompt}
                onChange={(e) => setNewPersonaPrompt(e.target.value)}
                placeholder={vi ? "System prompt hướng dẫn AI..." : "System prompt instructions..."}
                className="sm:col-span-2 rounded-lg border px-3 py-2 text-xs outline-none"
                style={{ backgroundColor: "var(--bg)", borderColor: "var(--border)" }}
              />
              <button
                type="submit"
                disabled={busy || !newPersonaName.trim() || !newPersonaPrompt.trim()}
                className="inline-flex items-center justify-center gap-1 rounded-lg border px-3 py-2 text-xs font-medium disabled:opacity-40"
                style={{ borderColor: "var(--border)", backgroundColor: "var(--surface-elevated)" }}
              >
                <Plus className="h-3.5 w-3.5" />
                <span>{vi ? "Thêm Persona" : "Add Persona"}</span>
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

function StatBox({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div
      className="border p-4"
      style={{
        backgroundColor: "var(--surface)",
        borderColor: "var(--border)",
        borderRadius: "var(--radius-base)",
      }}
    >
      <div className="text-[11px]" style={{ color: "var(--muted)" }}>
        {label}
      </div>
      <div className="mt-1 text-lg font-semibold tracking-tight tabular-nums">{value}</div>
      <div className="mt-0.5 truncate text-[11px]" style={{ color: "var(--muted)" }}>
        {sub}
      </div>
    </div>
  );
}

function SecretRow({
  title,
  hint,
  configured,
  value,
  onChange,
  onSave,
  onDelete,
  onTest,
  testing,
  testResult,
  onPickModel,
  activeModel,
  busy,
}: {
  title: string;
  hint: string;
  configured: boolean;
  value: string;
  onChange: (v: string) => void;
  onSave: () => void;
  onDelete: () => void;
  onTest?: () => void;
  testing?: boolean;
  testResult?: AITestResult;
  onPickModel?: (model: string) => void;
  activeModel?: string;
  busy: boolean;
}) {
  return (
    <div className="space-y-2 border-b pb-3.5 last:border-b-0 last:pb-0" style={{ borderColor: "var(--border)" }}>
      <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <div className="text-xs font-medium">{title}</div>
          <div className="font-mono text-[11px]" style={{ color: configured ? "var(--accent)" : "var(--muted)" }}>
            {configured ? `Đã lưu: ${hint}` : "Chưa cấu hình"}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <input
            type="password"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder="Nhập key mới..."
            className="w-56 rounded-lg border px-3 py-1.5 font-mono text-xs outline-none"
            style={{ backgroundColor: "var(--bg)", borderColor: "var(--border)" }}
          />
          <button
            type="button"
            disabled={busy || !value.trim()}
            onClick={onSave}
            className="rounded-lg border px-3 py-1.5 text-xs font-medium disabled:opacity-40"
            style={{ borderColor: "var(--border)", backgroundColor: "var(--surface-elevated)" }}
          >
            Lưu
          </button>
          {onTest && configured && (
            <button
              type="button"
              disabled={busy || testing}
              onClick={onTest}
              className="inline-flex items-center gap-1 rounded-lg border px-2.5 py-1.5 text-xs font-medium disabled:opacity-40"
              style={{ borderColor: "var(--border)", backgroundColor: "var(--bg)" }}
            >
              <Play className="h-3 w-3" />
              <span>{testing ? "Đang test..." : "Kiểm tra & Lấy Model"}</span>
            </button>
          )}
          {configured && (
            <button
              type="button"
              disabled={busy}
              onClick={onDelete}
              title="Xóa key đã lưu"
              className="inline-flex items-center gap-1 rounded-lg border px-2.5 py-1.5 text-xs opacity-80 hover:opacity-100 disabled:opacity-40"
              style={{ borderColor: "var(--border)", color: "#fca5a5" }}
            >
              <Trash2 className="h-3.5 w-3.5" />
              <span>Xóa</span>
            </button>
          )}
        </div>
      </div>

      {testResult && (
        <div className="space-y-1.5 pl-0.5 text-[11px]">
          {testResult.ok ? (
            <>
              <div style={{ color: "var(--accent)" }}>
                Kết nối OK ({testResult.latency_ms}ms) — bấm chọn nhanh Model ID:
              </div>
              <div className="flex flex-wrap gap-1.5">
                {testResult.models.map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => onPickModel?.(m)}
                    className="rounded-full border px-2 py-0.5 font-mono text-[10px] transition-opacity hover:opacity-90"
                    style={{
                      borderColor: activeModel === m ? "var(--accent)" : "var(--border)",
                      backgroundColor: activeModel === m ? "var(--accent)" : "var(--bg)",
                      color: activeModel === m ? "#040805" : "var(--fg)",
                    }}
                  >
                    {m}
                  </button>
                ))}
              </div>
            </>
          ) : (
            <div style={{ color: "#fca5a5" }}>{testResult.error}</div>
          )}
        </div>
      )}
    </div>
  );
}
