"use client";

import React, { useCallback, useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { AppearancePanel } from "@/components/AppearancePanel";
import { ConversationsPanel } from "@/components/ConversationsPanel";
import { DigestPanel } from "@/components/DigestPanel";
import { FinancePanel } from "@/components/FinancePanel";
import { OverviewPanel } from "@/components/OverviewPanel";
import { RemotePanel } from "@/components/RemotePanel";
import { SecondBrainPanel } from "@/components/SecondBrainPanel";
import { NavTab, Sidebar } from "@/components/Sidebar";
import { useThemeStudio } from "@/components/ThemeProvider";
import { api, OverviewData } from "@/lib/api";

export default function HomePage() {
  const { theme, syncFromServer } = useThemeStudio();
  const [activeTab, setActiveTab] = useState<NavTab>("overview");
  const [overview, setOverview] = useState<OverviewData | null>(null);
  const [loadError, setLoadError] = useState("");
  const [refreshing, setRefreshing] = useState(false);

  const vi = theme.language === "vi";

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      const data = await api.getOverview();
      setOverview(data);
      syncFromServer(data.theme);
      setLoadError("");
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Backend unreachable");
    } finally {
      setRefreshing(false);
    }
  }, [syncFromServer]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const activeModel =
    overview?.ai.primary_provider === "gemini"
      ? overview.ai.gemini_model
      : overview?.ai.openai_model;

  return (
    <div className="flex h-screen w-full overflow-hidden">
      <Sidebar
        activeTab={activeTab}
        onSelect={setActiveTab}
        botRunning={overview?.bot.running ?? false}
        lang={theme.language}
      />

      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* Global Status Toolbar */}
        <header
          className="flex shrink-0 items-center justify-between gap-4 border-b px-6 py-2.5"
          style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)" }}
        >
          <div className="flex flex-wrap items-center gap-2 text-xs">
            {overview ? (
              <>
                <span
                  className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 font-mono text-[11px]"
                  style={{ borderColor: "var(--border)", backgroundColor: "var(--bg)" }}
                >
                  <span
                    className="h-1.5 w-1.5 rounded-full"
                    style={{ backgroundColor: "var(--accent)" }}
                  />
                  {overview.ai.primary_provider.toUpperCase()} · {activeModel}
                </span>
                <span
                  className="rounded-full border px-2.5 py-0.5 font-mono text-[11px] tabular-nums"
                  style={{
                    borderColor: "var(--border)",
                    backgroundColor: "var(--bg)",
                    color: "var(--muted)",
                  }}
                >
                  {overview.usage.requests}/{overview.ai.daily_request_cap} req
                </span>
                {overview.bot.allowed_user_ids.length === 0 && (
                  <button
                    type="button"
                    onClick={() => setActiveTab("settings")}
                    className="rounded-full border px-2.5 py-0.5 text-[11px] font-medium"
                    style={{
                      borderColor: "#f59e0b",
                      color: "#f59e0b",
                    }}
                  >
                    {vi ? "Chưa nhập Telegram User ID" : "Missing Telegram User ID"}
                  </button>
                )}
              </>
            ) : (
              <span className="text-[11px]" style={{ color: "var(--muted)" }}>
                {vi ? "Đang kết nối engine nội bộ..." : "Connecting local engine..."}
              </span>
            )}
          </div>

          <button
            type="button"
            onClick={() => void refresh()}
            className="inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium transition-opacity hover:opacity-80"
            style={{ borderColor: "var(--border)", backgroundColor: "var(--bg)" }}
          >
            <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`} />
            <span>{vi ? "Đồng bộ" : "Sync"}</span>
          </button>
        </header>

        <main className="flex-1 overflow-y-auto px-6 py-6 sm:px-8">
          {loadError && activeTab !== "appearance" && (
            <div
              className="mx-auto mb-5 max-w-6xl rounded-lg border px-4 py-3 text-xs"
              style={{
                borderColor: "var(--border)",
                backgroundColor: "var(--surface)",
                color: "var(--muted)",
              }}
            >
              Đang kết nối engine nội bộ ({loadError}). Thử bấm{" "}
              <button type="button" onClick={() => void refresh()} className="underline">
                tải lại
              </button>
              . Phần Giao diện / Theme Studio vẫn hoạt động ngay lập tức.
            </div>
          )}

          {activeTab === "appearance" && <AppearancePanel />}
          {activeTab === "overview" && overview && (
            <OverviewPanel
              overview={overview}
              onRefresh={refresh}
              onNavigate={setActiveTab}
              lang={theme.language}
              mode="overview"
            />
          )}
          {activeTab === "settings" && overview && (
            <OverviewPanel
              overview={overview}
              onRefresh={refresh}
              onNavigate={setActiveTab}
              lang={theme.language}
              mode="settings"
            />
          )}
          {activeTab === "conversations" && (
            <ConversationsPanel
              lang={theme.language}
              onOpenSettings={() => setActiveTab("settings")}
              onMessageSent={refresh}
            />
          )}
          {activeTab === "brain" && (
            <SecondBrainPanel
              lang={theme.language}
              defaultChatId={overview?.bot.allowed_user_ids[0] ?? 0}
            />
          )}
          {activeTab === "finance" && <FinancePanel lang={theme.language} />}
          {activeTab === "digest" && (
            <DigestPanel
              lang={theme.language}
              briefing={overview?.briefing ?? null}
              onBriefingSaved={refresh}
            />
          )}
          {activeTab === "remote" && (
            <RemotePanel
              lang={theme.language}
              modules={overview?.modules ?? null}
              onToggleRemote={async (nextEnabled) => {
                if (!overview) return;
                await api.updateModules({ ...overview.modules, remote: nextEnabled });
                await refresh();
              }}
            />
          )}
        </main>
      </div>
    </div>
  );
}
