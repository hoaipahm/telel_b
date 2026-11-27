"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Check, Copy, RefreshCw, Send, Settings, Trash2 } from "lucide-react";
import { api, ConversationItem } from "@/lib/api";

interface ConversationsPanelProps {
  lang: "vi" | "en";
  onOpenSettings: () => void;
  onMessageSent: () => Promise<void>;
}

export function ConversationsPanel({
  lang,
  onOpenSettings,
  onMessageSent,
}: ConversationsPanelProps) {
  const vi = lang === "vi";
  const [items, setItems] = useState<ConversationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [chatFilter, setChatFilter] = useState<string>("all");
  const [confirmClear, setConfirmClear] = useState(false);
  const [copiedId, setCopiedId] = useState<number | null>(null);
  const [errorMsg, setErrorMsg] = useState("");
  const listBottomRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    try {
      const res = await api.getConversations();
      setItems(res.items);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const chatIds = useMemo(() => {
    const ids = Array.from(new Set(items.map((m) => m.chat_id)));
    return ids.sort((a, b) => a - b);
  }, [items]);

  const visibleMessages = useMemo(() => {
    const filtered =
      chatFilter === "all" ? items : items.filter((m) => String(m.chat_id) === chatFilter);
    return [...filtered].reverse();
  }, [items, chatFilter]);

  const targetChatId =
    chatFilter !== "all" ? Number.parseInt(chatFilter, 10) || 0 : 0;

  const handleSend = async (e?: React.FormEvent) => {
    e?.preventDefault();
    const clean = draft.trim();
    if (!clean || sending) return;
    setSending(true);
    setErrorMsg("");
    try {
      await api.sendChat(clean, targetChatId);
      setDraft("");
      await Promise.all([load(), onMessageSent()]);
      setTimeout(() => listBottomRef.current?.scrollIntoView({ behavior: "smooth" }), 80);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to get AI reply");
    } finally {
      setSending(false);
    }
  };

  const handleDeleteOne = async (id: number) => {
    await api.deleteConversationMessage(id);
    await load();
  };

  const handleClearAll = async () => {
    const scopeId = chatFilter === "all" ? undefined : Number.parseInt(chatFilter, 10);
    await api.clearConversations(scopeId);
    setConfirmClear(false);
    await load();
  };

  const handleCopy = async (id: number, text: string) => {
    await navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 1500);
  };

  return (
    <div className="mx-auto flex h-full max-w-6xl flex-col gap-4">
      {/* Header & Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">
            {vi ? "Hội thoại AI (Desktop & Telegram)" : "AI Conversations"}
          </h1>
          <p className="text-xs" style={{ color: "var(--muted)" }}>
            {vi
              ? "Chat trực tiếp ngay trong app để test model, xem lại hoặc xóa lịch sử hội thoại."
              : "Chat directly inside the app, test your AI setup, or manage stored history."}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <select
            value={chatFilter}
            onChange={(e) => setChatFilter(e.target.value)}
            aria-label={vi ? "Lọc luồng chat" : "Filter chat thread"}
            className="rounded-lg border px-2.5 py-1.5 text-xs outline-none"
            style={{ backgroundColor: "var(--surface)", borderColor: "var(--border)" }}
          >
            <option value="all">{vi ? "Tất cả luồng chat" : "All threads"}</option>
            {chatIds.map((cid) => (
              <option key={cid} value={String(cid)}>
                {cid === 0 ? (vi ? "Desktop (Chat #0)" : "Desktop (#0)") : `Telegram #${cid}`}
              </option>
            ))}
          </select>

          <button
            type="button"
            onClick={() => void load()}
            className="inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium hover:opacity-80"
            style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)" }}
          >
            <RefreshCw className="h-3.5 w-3.5" />
            <span>{vi ? "Làm mới" : "Refresh"}</span>
          </button>

          {items.length > 0 &&
            (confirmClear ? (
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => void handleClearAll()}
                  className="rounded-lg px-2.5 py-1.5 text-xs font-semibold text-white"
                  style={{ backgroundColor: "#dc2626" }}
                >
                  {vi ? "Xác nhận xóa hết" : "Confirm clear"}
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmClear(false)}
                  className="rounded-lg border px-2.5 py-1.5 text-xs"
                  style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)" }}
                >
                  {vi ? "Hủy" : "Cancel"}
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setConfirmClear(true)}
                className="inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium hover:opacity-80"
                style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)" }}
              >
                <Trash2 className="h-3.5 w-3.5" />
                <span>{vi ? "Xóa lịch sử" : "Clear History"}</span>
              </button>
            ))}
        </div>
      </div>

      {/* Error Recovery Banner */}
      {errorMsg && (
        <div
          className="flex flex-wrap items-center justify-between gap-3 rounded-lg border px-4 py-3 text-xs"
          style={{
            borderColor: "#ef4444",
            backgroundColor: "var(--surface)",
            color: "#fca5a5",
          }}
        >
          <span className="max-w-3xl break-words">{errorMsg}</span>
          <button
            type="button"
            onClick={onOpenSettings}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border px-3 py-1 font-medium"
            style={{ borderColor: "var(--border)", color: "var(--fg)" }}
          >
            <Settings className="h-3.5 w-3.5" />
            <span>{vi ? "Mở Cài đặt chung" : "Open Settings"}</span>
          </button>
        </div>
      )}

      {/* Message Stream */}
      <div
        className="flex-1 space-y-3 overflow-y-auto border p-4"
        style={{
          backgroundColor: "var(--surface)",
          borderColor: "var(--border)",
          borderRadius: "var(--radius-base)",
        }}
      >
        {loading ? (
          <div className="space-y-3">
            <div className="h-16 animate-pulse rounded-lg" style={{ backgroundColor: "var(--bg)" }} />
            <div className="h-16 animate-pulse rounded-lg" style={{ backgroundColor: "var(--bg)" }} />
          </div>
        ) : visibleMessages.length === 0 ? (
          <div className="flex h-full min-h-40 flex-col items-center justify-center gap-2 text-center">
            <p className="text-sm font-medium">
              {vi ? "Chưa có tin nhắn nào trong luồng này" : "No messages in this thread yet"}
            </p>
            <p className="max-w-md text-xs" style={{ color: "var(--muted)" }}>
              {vi
                ? "Gõ tin nhắn bên dưới để chat trực tiếp với AI ngay tại đây, hoặc nhắn cho bot trên Telegram."
                : "Type below to chat directly with your configured AI, or message your bot on Telegram."}
            </p>
          </div>
        ) : (
          visibleMessages.map((msg) => {
            const isAssistant = msg.role === "assistant";
            return (
              <div
                key={msg.id}
                className="group border p-3.5"
                style={{
                  backgroundColor: isAssistant ? "var(--surface-elevated)" : "var(--bg)",
                  borderColor: "var(--border)",
                  borderRadius: "var(--radius-base)",
                }}
              >
                <div className="mb-1.5 flex items-center justify-between gap-2 text-[11px]">
                  <div className="flex items-center gap-2">
                    <span
                      className="font-mono font-semibold uppercase"
                      style={{ color: isAssistant ? "var(--accent)" : "var(--fg)" }}
                    >
                      {isAssistant ? "AI" : "YOU"}
                    </span>
                    <span className="font-mono" style={{ color: "var(--muted)" }}>
                      {msg.chat_id === 0 ? "Desktop" : `TG:${msg.chat_id}`}
                      {msg.provider ? ` · ${msg.provider}/${msg.model}` : ""}
                      {msg.tokens_used > 0 ? ` · ${msg.tokens_used} tok` : ""}
                    </span>
                  </div>

                  <div className="flex items-center gap-2">
                    <span className="tabular-nums" style={{ color: "var(--muted)" }}>
                      {new Date(msg.created_at).toLocaleString()}
                    </span>
                    <button
                      type="button"
                      onClick={() => void handleCopy(msg.id, msg.content)}
                      title={vi ? "Copy nội dung" : "Copy content"}
                      className="opacity-60 transition-opacity hover:opacity-100"
                    >
                      {copiedId === msg.id ? (
                        <Check className="h-3.5 w-3.5" style={{ color: "var(--accent)" }} />
                      ) : (
                        <Copy className="h-3.5 w-3.5" />
                      )}
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleDeleteOne(msg.id)}
                      title={vi ? "Xóa tin nhắn" : "Delete message"}
                      className="opacity-60 transition-opacity hover:opacity-100"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
                <div className="max-w-3xl whitespace-pre-wrap text-xs leading-relaxed">
                  <MessageContent text={msg.content} />
                </div>
              </div>
            );
          })
        )}
        <div ref={listBottomRef} />
      </div>

      {/* Composer */}
      <form
        onSubmit={(e) => void handleSend(e)}
        className="flex shrink-0 items-end gap-2.5 border p-3"
        style={{
          backgroundColor: "var(--surface)",
          borderColor: "var(--border)",
          borderRadius: "var(--radius-base)",
        }}
      >
        <textarea
          rows={2}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void handleSend();
            }
          }}
          placeholder={
            vi
              ? "Nhắn trực tiếp cho AI (Enter để gửi, Shift+Enter xuống dòng)..."
              : "Message AI directly (Enter to send, Shift+Enter for newline)..."
          }
          className="min-h-11 flex-1 resize-none rounded-lg border px-3 py-2 text-xs outline-none"
          style={{ backgroundColor: "var(--bg)", borderColor: "var(--border)" }}
        />
        <button
          type="submit"
          disabled={sending || !draft.trim()}
          className="inline-flex h-10 shrink-0 items-center gap-1.5 rounded-lg px-4 text-xs font-semibold disabled:opacity-45"
          style={{ backgroundColor: "var(--accent)", color: "#040805" }}
        >
          <Send className="h-3.5 w-3.5" />
          <span>{sending ? (vi ? "Đang gọi..." : "Thinking...") : vi ? "Gửi" : "Send"}</span>
        </button>
      </form>
    </div>
  );
}

const FENCED_BLOCK_RE = /(```[\s\S]*?```)/g;
const INLINE_TOKEN_RE =
  /(\[[^\]\n]+\]\(https?:\/\/[^\s)]+\)|https?:\/\/[^\s<>()"']+|\*\*[^*\n]+\*\*|`[^`\n]+`)/g;

function renderInlineSegment(segment: string, keyPrefix: string) {
  const parts = segment.split(INLINE_TOKEN_RE);
  return parts.map((part, idx) => {
    if (!part) return null;
    const key = `${keyPrefix}-${idx}`;
    const mdMatch = /^\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)$/.exec(part);
    if (mdMatch) {
      return (
        <a
          key={key}
          href={mdMatch[2]}
          target="_blank"
          rel="noreferrer"
          className="underline break-all hover:opacity-85"
          style={{ color: "var(--accent)" }}
        >
          {mdMatch[1]}
        </a>
      );
    }
    if (/^https?:\/\//i.test(part)) {
      const cleanUrl = part.replace(/[.,;!?]+$/, "");
      const trailing = part.slice(cleanUrl.length);
      return (
        <React.Fragment key={key}>
          <a
            href={cleanUrl}
            target="_blank"
            rel="noreferrer"
            className="underline break-all hover:opacity-85"
            style={{ color: "var(--accent)" }}
          >
            {cleanUrl}
          </a>
          {trailing}
        </React.Fragment>
      );
    }
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return (
        <strong key={key} className="font-semibold">
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      return (
        <code
          key={key}
          className="rounded px-1 py-0.5 font-mono text-[11px]"
          style={{ backgroundColor: "var(--bg)", border: "1px solid var(--border)" }}
        >
          {part.slice(1, -1)}
        </code>
      );
    }
    return <React.Fragment key={key}>{part}</React.Fragment>;
  });
}

function MessageContent({ text }: { text: string }) {
  const blocks = text.split(FENCED_BLOCK_RE);
  return (
    <>
      {blocks.map((block, bIdx) => {
        if (!block) return null;
        if (block.startsWith("```") && block.endsWith("```") && block.length >= 6) {
          const inner = block.slice(3, -3).replace(/^[a-zA-Z0-9_-]+\n/, "").trim();
          return (
            <pre
              key={`b-${bIdx}`}
              className="my-2 overflow-x-auto rounded-lg border p-2.5 font-mono text-[11px] leading-relaxed"
              style={{ backgroundColor: "var(--bg)", borderColor: "var(--border)" }}
            >
              <code>{inner}</code>
            </pre>
          );
        }
        return <React.Fragment key={`t-${bIdx}`}>{renderInlineSegment(block, `s-${bIdx}`)}</React.Fragment>;
      })}
    </>
  );
}
