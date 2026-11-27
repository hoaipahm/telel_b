"use client";

import React, { useMemo, useState } from "react";
import {
  Activity,
  BookOpen,
  Bot,
  Brain,
  MessageSquare,
  Palette,
  Search,
  Server,
  Settings,
  Wallet,
} from "lucide-react";

export type NavTab =
  | "overview"
  | "conversations"
  | "brain"
  | "finance"
  | "digest"
  | "remote"
  | "settings"
  | "appearance";

interface SidebarProps {
  activeTab: NavTab;
  onSelect: (tab: NavTab) => void;
  botRunning: boolean;
  lang: "vi" | "en";
}

interface NavItem {
  id: NavTab;
  group: "control" | "app";
  vi: string;
  en: string;
  icon: React.ComponentType<{ className?: string }>;
}

const NAV_ITEMS: NavItem[] = [
  { id: "overview", group: "control", vi: "Tổng quan & Bot", en: "Overview & Bot", icon: Activity },
  { id: "conversations", group: "control", vi: "Hội thoại AI", en: "AI Conversations", icon: MessageSquare },
  { id: "brain", group: "control", vi: "Second Brain", en: "Second Brain", icon: Brain },
  { id: "finance", group: "control", vi: "Tài chính cá nhân", en: "Personal Finance", icon: Wallet },
  { id: "digest", group: "control", vi: "Đọc hộ & Tin", en: "Link & Feed Digest", icon: BookOpen },
  { id: "remote", group: "control", vi: "PC & Docker Remote", en: "PC & Docker Remote", icon: Server },
  { id: "settings", group: "app", vi: "Cài đặt chung", en: "General & Keys", icon: Settings },
  { id: "appearance", group: "app", vi: "Giao diện", en: "Appearance", icon: Palette },
];

export function Sidebar({ activeTab, onSelect, botRunning, lang }: SidebarProps) {
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return NAV_ITEMS;
    return NAV_ITEMS.filter(
      (item) => item.vi.toLowerCase().includes(q) || item.en.toLowerCase().includes(q),
    );
  }, [query]);

  const controlItems = filtered.filter((i) => i.group === "control");
  const appItems = filtered.filter((i) => i.group === "app");

  return (
    <aside
      className="flex h-full w-64 shrink-0 flex-col border-r p-3.5"
      style={{
        backgroundColor: "var(--surface)",
        borderColor: "var(--border)",
      }}
    >
      <div className="mb-3 flex items-center justify-between px-1.5">
        <div className="flex items-center gap-2.5">
          <span
            className="flex h-7 w-7 items-center justify-center rounded-lg border"
            style={{
              borderColor: "var(--border)",
              backgroundColor: "var(--surface-elevated)",
              color: "var(--accent)",
            }}
          >
            <Bot className="h-4 w-4" />
          </span>
          <div>
            <div className="text-sm font-semibold tracking-tight">TeleMind Hub</div>
            <div className="flex items-center gap-1.5 text-[11px]" style={{ color: "var(--muted)" }}>
              <span
                className="inline-block h-1.5 w-1.5 rounded-full"
                style={{ backgroundColor: botRunning ? "var(--accent)" : "#f59e0b" }}
              />
              {botRunning
                ? lang === "vi"
                  ? "Bot đang chạy"
                  : "Bot online"
                : lang === "vi"
                  ? "Chờ cấu hình token"
                  : "Awaiting token"}
            </div>
          </div>
        </div>
      </div>

      <div className="relative mb-4">
        <Search
          className="pointer-events-none absolute top-2.5 left-3 h-3.5 w-3.5"
          style={{ color: "var(--muted)" }}
        />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={lang === "vi" ? "Tìm kiếm" : "Search"}
          aria-label={lang === "vi" ? "Tìm kiếm menu" : "Search navigation"}
          className="w-full rounded-full border py-1.5 pr-3 pl-8 text-xs outline-none transition-colors"
          style={{
            backgroundColor: "var(--bg)",
            borderColor: "var(--border)",
            color: "var(--fg)",
          }}
        />
      </div>

      <nav className="flex-1 space-y-5 overflow-y-auto pr-0.5">
        {controlItems.length > 0 && (
          <div>
            <div className="mb-1.5 px-2.5 text-[11px] font-medium" style={{ color: "var(--muted)" }}>
              {lang === "vi" ? "Tài nguyên & Bot" : "Workspace & Bot"}
            </div>
            <div className="space-y-0.5">
              {controlItems.map((item) => {
                const Icon = item.icon;
                const active = activeTab === item.id;
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => onSelect(item.id)}
                    className="flex w-full items-center gap-2.5 px-2.5 py-2 text-left text-xs font-medium transition-colors"
                    style={{
                      borderRadius: "var(--radius-base)",
                      backgroundColor: active ? "var(--surface-elevated)" : "transparent",
                      color: active ? "var(--fg)" : "var(--muted)",
                    }}
                  >
                    <Icon className="h-4 w-4 shrink-0" />
                    <span className="truncate">{lang === "vi" ? item.vi : item.en}</span>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {appItems.length > 0 && (
          <div>
            <div className="mb-1.5 px-2.5 text-[11px] font-medium" style={{ color: "var(--muted)" }}>
              {lang === "vi" ? "Ứng dụng" : "Application"}
            </div>
            <div className="space-y-0.5">
              {appItems.map((item) => {
                const Icon = item.icon;
                const active = activeTab === item.id;
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => onSelect(item.id)}
                    className="flex w-full items-center gap-2.5 px-2.5 py-2 text-left text-xs font-medium transition-colors"
                    style={{
                      borderRadius: "var(--radius-base)",
                      backgroundColor: active ? "var(--surface-elevated)" : "transparent",
                      color: active ? "var(--fg)" : "var(--muted)",
                    }}
                  >
                    <Icon className="h-4 w-4 shrink-0" />
                    <span className="truncate">{lang === "vi" ? item.vi : item.en}</span>
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </nav>
    </aside>
  );
}
