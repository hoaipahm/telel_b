"use client";

import React, { useCallback, useEffect, useState } from "react";
import { Bell, Check, Copy, Pencil, Plus, RefreshCw, Send, Trash2 } from "lucide-react";
import { api, BriefingConfig, DigestItem, FeedHeadline, FeedItem } from "@/lib/api";

export function DigestPanel({
  lang,
  briefing,
  onBriefingSaved,
}: {
  lang: "vi" | "en";
  briefing: BriefingConfig | null;
  onBriefingSaved: () => Promise<void>;
}) {
  const vi = lang === "vi";
  const [digests, setDigests] = useState<DigestItem[]>([]);
  const [feeds, setFeeds] = useState<FeedItem[]>([]);
  const [url, setUrl] = useState("");
  const [feedUrl, setFeedUrl] = useState("");
  const [feedTitle, setFeedTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [statusMsg, setStatusMsg] = useState("");
  const [copiedId, setCopiedId] = useState<number | null>(null);

  // Morning RSS briefing schedule
  const [briefEnabled, setBriefEnabled] = useState(briefing?.enabled ?? false);
  const [briefTime, setBriefTime] = useState(briefing?.time_hhmm ?? "07:30");

  useEffect(() => {
    if (briefing) {
      setBriefEnabled(briefing.enabled);
      setBriefTime(briefing.time_hhmm);
    }
  }, [briefing]);

  // Feed edit & live headlines state
  const [editingFeedId, setEditingFeedId] = useState<number | null>(null);
  const [editFeedTitle, setEditFeedTitle] = useState("");
  const [editFeedEnabled, setEditFeedEnabled] = useState(true);
  const [feedHeadlines, setFeedHeadlines] = useState<Record<number, FeedHeadline[]>>({});
  const [loadingFeedId, setLoadingFeedId] = useState<number | null>(null);

  const load = useCallback(async () => {
    const [dRes, fRes] = await Promise.all([api.getDigests(), api.getFeeds()]);
    setDigests(dRes.items);
    setFeeds(fRes.items);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const summarize = async (targetUrl: string) => {
    setErr("");
    setBusy(true);
    try {
      await api.createDigest(targetUrl);
      if (targetUrl === url) setUrl("");
      await load();
    } catch (error) {
      setErr(error instanceof Error ? error.message : "Failed to summarize URL");
    } finally {
      setBusy(false);
    }
  };

  const addFeed = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr("");
    try {
      await api.createFeed(feedUrl, feedTitle);
      setFeedUrl("");
      setFeedTitle("");
      await load();
    } catch (error) {
      setErr(error instanceof Error ? error.message : "Invalid RSS URL");
    }
  };

  const saveFeedEdit = async (id: number) => {
    if (!editFeedTitle.trim()) return;
    await api.updateFeed(id, { title: editFeedTitle, enabled: editFeedEnabled });
    setEditingFeedId(null);
    await load();
  };

  const fetchHeadlines = async (id: number) => {
    setErr("");
    setLoadingFeedId(id);
    try {
      const res = await api.getFeedItems(id);
      setFeedHeadlines((prev) => ({ ...prev, [id]: res.items }));
    } catch (error) {
      setErr(error instanceof Error ? error.message : "Failed to read RSS feed");
    } finally {
      setLoadingFeedId(null);
    }
  };

  const copyDigest = async (d: DigestItem) => {
    await navigator.clipboard.writeText(`${d.title}\n${d.url}\n\n${d.summary}`);
    setCopiedId(d.id);
    setTimeout(() => setCopiedId(null), 1500);
  };

  const saveBriefing = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr("");
    setStatusMsg("");
    try {
      await api.updateBriefing({
        enabled: briefEnabled,
        time_hhmm: briefTime || "07:30",
        last_sent_date: briefing?.last_sent_date ?? "",
      });
      await onBriefingSaved();
      setStatusMsg(vi ? "Đã lưu lịch điểm tin RSS hàng ngày." : "Saved daily RSS briefing.");
      setTimeout(() => setStatusMsg(""), 3000);
    } catch (error) {
      setErr(error instanceof Error ? error.message : "Failed to save briefing schedule");
    }
  };

  const triggerBriefingNow = async () => {
    setErr("");
    setStatusMsg("");
    setBusy(true);
    try {
      const res = await api.sendBriefingNow();
      setStatusMsg(
        vi
          ? `Đã gửi điểm tin RSS tới ${res.sent_chats} chat Telegram.`
          : `Sent briefing to ${res.sent_chats} chat(s).`,
      );
      setTimeout(() => setStatusMsg(""), 3500);
    } catch (error) {
      setErr(error instanceof Error ? error.message : "Failed to send briefing");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">
          {vi ? "Đọc hộ & Điểm tin (SSRF Safe)" : "Link & RSS Feed Digest"}
        </h1>
        <p className="text-xs" style={{ color: "var(--muted)" }}>
          {vi
            ? "Mọi URL đều qua bộ lọc chống SSRF (chặn IP nội bộ/localhost). Có thể sửa nguồn RSS, đọc tin mới và xóa bài tóm tắt."
            : "Every URL passes SSRF validation before fetching, summarizing, editing, or reading feeds."}
        </p>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void summarize(url);
        }}
        className="flex flex-wrap gap-2 border p-4"
        style={{
          backgroundColor: "var(--surface)",
          borderColor: "var(--border)",
          borderRadius: "var(--radius-base)",
        }}
      >
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://example.com/article"
          className="min-w-60 flex-1 rounded-lg border px-3 py-2 font-mono text-xs outline-none"
          style={{ backgroundColor: "var(--bg)", borderColor: "var(--border)" }}
        />
        <button
          type="submit"
          disabled={busy || !url.trim()}
          className="rounded-lg px-4 py-2 text-xs font-semibold disabled:opacity-45"
          style={{ backgroundColor: "var(--accent)", color: "#040805" }}
        >
          {busy ? (vi ? "Đang tóm tắt..." : "Summarizing...") : vi ? "Tóm tắt ngay" : "Summarize"}
        </button>
      </form>

      {err && <p className="text-xs text-red-400">{err}</p>}
      {statusMsg && (
        <p className="text-xs font-medium" style={{ color: "var(--accent)" }}>
          {statusMsg}
        </p>
      )}

      {/* Daily Briefing Schedule */}
      <form
        onSubmit={(e) => void saveBriefing(e)}
        className="flex flex-wrap items-center justify-between gap-3 border p-4"
        style={{
          backgroundColor: "var(--surface)",
          borderColor: "var(--border)",
          borderRadius: "var(--radius-base)",
        }}
      >
        <div className="flex items-center gap-2 text-xs">
          <Bell className="h-4 w-4" style={{ color: "var(--accent)" }} />
          <div>
            <div className="font-medium">
              {vi ? "Điểm tin sáng RSS tự động qua Telegram" : "Daily Telegram RSS Briefing"}
            </div>
            <div className="text-[11px]" style={{ color: "var(--muted)" }}>
              {vi
                ? "Tự gom tin mới từ các nguồn đang bật và gửi lúc giờ hẹn mỗi ngày."
                : "Aggregates latest enabled RSS headlines once per day at scheduled time."}
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2.5 text-xs">
          <label className="flex items-center gap-1.5">
            <input
              type="checkbox"
              checked={briefEnabled}
              onChange={(e) => setBriefEnabled(e.target.checked)}
            />
            <span>{vi ? "Bật tự động" : "Enable"}</span>
          </label>
          <input
            type="time"
            value={briefTime}
            onChange={(e) => setBriefTime(e.target.value)}
            className="rounded-lg border px-2 py-1 font-mono text-xs outline-none"
            style={{ backgroundColor: "var(--bg)", borderColor: "var(--border)" }}
          />
          <button
            type="submit"
            className="rounded-lg border px-3 py-1 font-medium"
            style={{ borderColor: "var(--border)", backgroundColor: "var(--surface-elevated)" }}
          >
            {vi ? "Lưu lịch" : "Save"}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void triggerBriefingNow()}
            className="inline-flex items-center gap-1 rounded-lg px-3 py-1 font-semibold disabled:opacity-45"
            style={{ backgroundColor: "var(--accent)", color: "#040805" }}
          >
            <Send className="h-3 w-3" />
            <span>{vi ? "Gửi thử ngay" : "Send Now"}</span>
          </button>
        </div>
      </form>

      <div className="grid gap-3 lg:grid-cols-2">
        {digests.map((d) => (
          <div
            key={d.id}
            className="border p-4"
            style={{
              backgroundColor: "var(--surface)",
              borderColor: "var(--border)",
              borderRadius: "var(--radius-base)",
            }}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium">{d.title}</div>
                <a
                  href={d.url}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-0.5 block truncate font-mono text-[11px] underline"
                  style={{ color: "var(--accent)" }}
                >
                  {d.url}
                </a>
              </div>
              <div className="flex shrink-0 items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => void copyDigest(d)}
                  title={vi ? "Copy tóm tắt" : "Copy digest"}
                  className="opacity-60 hover:opacity-100"
                >
                  {copiedId === d.id ? (
                    <Check className="h-3.5 w-3.5" style={{ color: "var(--accent)" }} />
                  ) : (
                    <Copy className="h-3.5 w-3.5" />
                  )}
                </button>
                <button
                  type="button"
                  onClick={() => void api.deleteDigest(d.id).then(load)}
                  title={vi ? "Xóa tóm tắt" : "Delete digest"}
                  className="opacity-60 hover:opacity-100"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
            <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed" style={{ color: "var(--muted)" }}>
              {d.summary}
            </p>
          </div>
        ))}
      </div>

      {/* RSS Subscriptions */}
      <div
        className="space-y-4 border p-4"
        style={{
          backgroundColor: "var(--surface)",
          borderColor: "var(--border)",
          borderRadius: "var(--radius-base)",
        }}
      >
        <h2 className="text-sm font-medium">{vi ? "Nguồn RSS theo dõi" : "RSS Feeds"}</h2>
        <form onSubmit={(e) => void addFeed(e)} className="grid gap-2 sm:grid-cols-5">
          <input
            type="text"
            value={feedTitle}
            onChange={(e) => setFeedTitle(e.target.value)}
            placeholder={vi ? "Tên nguồn (tuỳ chọn)" : "Feed title (optional)"}
            className="rounded-lg border px-3 py-1.5 text-xs outline-none"
            style={{ backgroundColor: "var(--bg)", borderColor: "var(--border)" }}
          />
          <input
            type="url"
            value={feedUrl}
            onChange={(e) => setFeedUrl(e.target.value)}
            placeholder="https://hnrss.org/frontpage"
            className="sm:col-span-3 rounded-lg border px-3 py-1.5 font-mono text-xs outline-none"
            style={{ backgroundColor: "var(--bg)", borderColor: "var(--border)" }}
          />
          <button
            type="submit"
            disabled={!feedUrl.trim()}
            className="inline-flex items-center justify-center gap-1 rounded-lg border px-3 py-1.5 text-xs font-medium disabled:opacity-45"
            style={{ borderColor: "var(--border)", backgroundColor: "var(--surface-elevated)" }}
          >
            <Plus className="h-3.5 w-3.5" />
            <span>{vi ? "Thêm Feed" : "Add Feed"}</span>
          </button>
        </form>

        <div className="space-y-3">
          {feeds.map((f) => {
            const isEditing = editingFeedId === f.id;
            const headlines = feedHeadlines[f.id];
            return (
              <div
                key={f.id}
                className="space-y-2 border p-3"
                style={{
                  backgroundColor: "var(--bg)",
                  borderColor: "var(--border)",
                  borderRadius: "var(--radius-base)",
                }}
              >
                {isEditing ? (
                  <div className="flex flex-wrap items-center gap-2">
                    <input
                      type="text"
                      value={editFeedTitle}
                      onChange={(e) => setEditFeedTitle(e.target.value)}
                      className="flex-1 rounded border px-2.5 py-1 text-xs outline-none"
                      style={{ backgroundColor: "var(--surface)", borderColor: "var(--border)" }}
                    />
                    <label className="flex items-center gap-1.5 text-xs">
                      <input
                        type="checkbox"
                        checked={editFeedEnabled}
                        onChange={(e) => setEditFeedEnabled(e.target.checked)}
                      />
                      <span>{vi ? "Đang bật" : "Enabled"}</span>
                    </label>
                    <button
                      type="button"
                      onClick={() => void saveFeedEdit(f.id)}
                      className="rounded px-2.5 py-1 text-xs font-semibold"
                      style={{ backgroundColor: "var(--accent)", color: "#040805" }}
                    >
                      {vi ? "Lưu" : "Save"}
                    </button>
                    <button
                      type="button"
                      onClick={() => setEditingFeedId(null)}
                      className="rounded border px-2.5 py-1 text-xs"
                      style={{ borderColor: "var(--border)" }}
                    >
                      {vi ? "Hủy" : "Cancel"}
                    </button>
                  </div>
                ) : (
                  <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                    <div className="min-w-0 flex-1">
                      <div className="font-medium">
                        {f.title || f.url}{" "}
                        {!f.enabled && (
                          <span className="text-[11px]" style={{ color: "var(--muted)" }}>
                            ({vi ? "Tạm tắt" : "Paused"})
                          </span>
                        )}
                      </div>
                      <div className="truncate font-mono text-[11px]" style={{ color: "var(--muted)" }}>
                        {f.url}
                      </div>
                    </div>

                    <div className="flex shrink-0 items-center gap-2">
                      <button
                        type="button"
                        onClick={() => void fetchHeadlines(f.id)}
                        className="inline-flex items-center gap-1 rounded border px-2.5 py-1 text-[11px] hover:opacity-80"
                        style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)" }}
                      >
                        <RefreshCw
                          className={`h-3 w-3 ${loadingFeedId === f.id ? "animate-spin" : ""}`}
                        />
                        <span>{vi ? "Đọc tin mới" : "Fetch News"}</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setEditingFeedId(f.id);
                          setEditFeedTitle(f.title);
                          setEditFeedEnabled(Boolean(f.enabled));
                        }}
                        title={vi ? "Sửa Feed" : "Edit feed"}
                        className="opacity-60 hover:opacity-100"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={() => void api.deleteFeed(f.id).then(load)}
                        title={vi ? "Xóa Feed" : "Delete feed"}
                        className="opacity-60 hover:opacity-100"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>
                )}

                {headlines && headlines.length > 0 && (
                  <ul className="space-y-1.5 border-t pt-2 text-xs" style={{ borderColor: "var(--border)" }}>
                    {headlines.map((item, idx) => (
                      <li key={`${item.url}-${idx}`} className="flex items-center justify-between gap-2">
                        <a
                          href={item.url}
                          target="_blank"
                          rel="noreferrer"
                          className="min-w-0 flex-1 truncate hover:underline"
                        >
                          • {item.title}
                        </a>
                        {item.url && (
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => void summarize(item.url)}
                            className="shrink-0 text-[11px] underline"
                            style={{ color: "var(--accent)" }}
                          >
                            {vi ? "Tóm tắt" : "Summarize"}
                          </button>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
