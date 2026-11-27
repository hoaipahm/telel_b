"use client";

import React, { useCallback, useEffect, useState } from "react";
import { BellPlus, Check, Copy, Pencil, Plus, Search, Trash2, X } from "lucide-react";
import { api, NoteItem, ReminderItem } from "@/lib/api";

export function SecondBrainPanel({
  lang,
  defaultChatId,
}: {
  lang: "vi" | "en";
  defaultChatId: number;
}) {
  const vi = lang === "vi";
  const [notes, setNotes] = useState<NoteItem[]>([]);
  const [reminders, setReminders] = useState<ReminderItem[]>([]);
  const [query, setQuery] = useState("");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [tags, setTags] = useState("");

  // Inline note editing
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editContent, setEditContent] = useState("");
  const [editTags, setEditTags] = useState("");
  const [copiedId, setCopiedId] = useState<number | null>(null);

  // Add reminder form
  const [remRaw, setRemRaw] = useState("");
  const [remChatId, setRemChatId] = useState(defaultChatId ? String(defaultChatId) : "");
  const [remError, setRemError] = useState("");

  useEffect(() => {
    if (defaultChatId && !remChatId) {
      setRemChatId(String(defaultChatId));
    }
  }, [defaultChatId, remChatId]);

  const load = useCallback(async (q = "") => {
    const [nRes, rRes] = await Promise.all([api.getNotes(q), api.getReminders()]);
    setNotes(nRes.items);
    setReminders(rRes.items);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !content.trim()) return;
    await api.createNote({ title, content, tags });
    setTitle("");
    setContent("");
    setTags("");
    await load(query);
  };

  const startEdit = (n: NoteItem) => {
    setEditingId(n.id);
    setEditTitle(n.title);
    setEditContent(n.content);
    setEditTags(n.tags);
  };

  const saveEdit = async (id: number) => {
    if (!editTitle.trim() || !editContent.trim()) return;
    await api.updateNote(id, { title: editTitle, content: editContent, tags: editTags });
    setEditingId(null);
    await load(query);
  };

  const handleAddReminder = async (e: React.FormEvent) => {
    e.preventDefault();
    setRemError("");
    const parsedId = Number.parseInt(remChatId.trim(), 10);
    if (!Number.isFinite(parsedId) || parsedId <= 0) {
      setRemError(
        vi
          ? "Cần nhập Telegram User/Chat ID hợp lệ (hoặc lưu Allowlist trong Cài đặt chung)."
          : "Valid Telegram Chat ID required.",
      );
      return;
    }
    try {
      await api.createReminder({ chat_id: parsedId, raw: remRaw });
      setRemRaw("");
      await load(query);
    } catch (err) {
      setRemError(err instanceof Error ? err.message : "Không tạo được lịch nhắc.");
    }
  };

  const copyNote = async (n: NoteItem) => {
    await navigator.clipboard.writeText(`${n.title}\n\n${n.content}`);
    setCopiedId(n.id);
    setTimeout(() => setCopiedId(null), 1500);
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Second Brain &amp; Reminders</h1>
        <p className="text-xs" style={{ color: "var(--muted)" }}>
          {vi
            ? "Thêm, sửa, xóa, tìm kiếm FTS5 ghi chú và hẹn giờ nhắc việc gửi thẳng về Telegram."
            : "Create, edit, search, and schedule reminders synced with Telegram."}
        </p>
      </div>

      {/* Create Note */}
      <form
        onSubmit={(e) => void handleAdd(e)}
        className="space-y-3 border p-4"
        style={{
          backgroundColor: "var(--surface)",
          borderColor: "var(--border)",
          borderRadius: "var(--radius-base)",
        }}
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={vi ? "Tiêu đề ghi chú..." : "Note title..."}
            className="rounded-lg border px-3 py-2 text-xs outline-none"
            style={{ backgroundColor: "var(--bg)", borderColor: "var(--border)" }}
          />
          <input
            type="text"
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            placeholder="Tags (docker, sql, idea)"
            className="rounded-lg border px-3 py-2 text-xs outline-none"
            style={{ backgroundColor: "var(--bg)", borderColor: "var(--border)" }}
          />
        </div>
        <textarea
          rows={3}
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder={vi ? "Nội dung ghi chú..." : "Note content..."}
          className="w-full rounded-lg border px-3 py-2 text-xs outline-none"
          style={{ backgroundColor: "var(--bg)", borderColor: "var(--border)" }}
        />
        <button
          type="submit"
          disabled={!title.trim() || !content.trim()}
          className="inline-flex items-center gap-1.5 rounded-lg px-3.5 py-1.5 text-xs font-semibold disabled:opacity-45"
          style={{ backgroundColor: "var(--accent)", color: "#040805" }}
        >
          <Plus className="h-3.5 w-3.5" />
          <span>{vi ? "Lưu ghi chú" : "Save Note"}</span>
        </button>
      </form>

      {/* Search */}
      <div className="relative">
        <Search
          className="pointer-events-none absolute top-2.5 left-3 h-3.5 w-3.5"
          style={{ color: "var(--muted)" }}
        />
        <input
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            void load(e.target.value);
          }}
          placeholder={vi ? "Tìm kiếm trong Second Brain..." : "Search notes..."}
          className="w-full rounded-lg border py-2 pr-8 pl-8 text-xs outline-none"
          style={{ backgroundColor: "var(--surface)", borderColor: "var(--border)" }}
        />
        {query && (
          <button
            type="button"
            onClick={() => {
              setQuery("");
              void load("");
            }}
            aria-label="Clear search"
            className="absolute top-2.5 right-3 opacity-60 hover:opacity-100"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {/* Notes Grid */}
      {notes.length === 0 ? (
        <div
          className="border p-6 text-center text-xs"
          style={{
            backgroundColor: "var(--surface)",
            borderColor: "var(--border)",
            borderRadius: "var(--radius-base)",
            color: "var(--muted)",
          }}
        >
          {vi
            ? "Chưa có ghi chú phù hợp. Tạo ghi chú phía trên hoặc gõ `/note Tiêu đề | Nội dung #tag` trên Telegram."
            : "No matching notes."}
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {notes.map((n) => {
            const isEditing = editingId === n.id;
            return (
              <div
                key={n.id}
                className="flex flex-col justify-between gap-3 border p-4"
                style={{
                  backgroundColor: "var(--surface)",
                  borderColor: isEditing ? "var(--accent)" : "var(--border)",
                  borderRadius: "var(--radius-base)",
                }}
              >
                {isEditing ? (
                  <div className="space-y-2">
                    <input
                      type="text"
                      value={editTitle}
                      onChange={(e) => setEditTitle(e.target.value)}
                      className="w-full rounded-lg border px-2.5 py-1.5 text-xs font-medium outline-none"
                      style={{ backgroundColor: "var(--bg)", borderColor: "var(--border)" }}
                    />
                    <input
                      type="text"
                      value={editTags}
                      onChange={(e) => setEditTags(e.target.value)}
                      placeholder="Tags"
                      className="w-full rounded-lg border px-2.5 py-1.5 text-xs outline-none"
                      style={{ backgroundColor: "var(--bg)", borderColor: "var(--border)" }}
                    />
                    <textarea
                      rows={4}
                      value={editContent}
                      onChange={(e) => setEditContent(e.target.value)}
                      className="w-full rounded-lg border px-2.5 py-1.5 text-xs outline-none"
                      style={{ backgroundColor: "var(--bg)", borderColor: "var(--border)" }}
                    />
                    <div className="flex items-center justify-end gap-1.5">
                      <button
                        type="button"
                        onClick={() => void saveEdit(n.id)}
                        className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-xs font-semibold"
                        style={{ backgroundColor: "var(--accent)", color: "#040805" }}
                      >
                        <Check className="h-3.5 w-3.5" />
                        <span>{vi ? "Lưu" : "Save"}</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => setEditingId(null)}
                        className="inline-flex items-center gap-1 rounded-lg border px-2.5 py-1 text-xs"
                        style={{ borderColor: "var(--border)", backgroundColor: "var(--bg)" }}
                      >
                        <X className="h-3.5 w-3.5" />
                        <span>{vi ? "Hủy" : "Cancel"}</span>
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <div>
                      <div className="flex items-start justify-between gap-2">
                        <h3 className="text-sm font-medium">{n.title}</h3>
                        <div className="flex shrink-0 items-center gap-1.5">
                          <button
                            type="button"
                            onClick={() => void copyNote(n)}
                            title={vi ? "Copy" : "Copy"}
                            className="opacity-60 hover:opacity-100"
                          >
                            {copiedId === n.id ? (
                              <Check className="h-3.5 w-3.5" style={{ color: "var(--accent)" }} />
                            ) : (
                              <Copy className="h-3.5 w-3.5" />
                            )}
                          </button>
                          <button
                            type="button"
                            onClick={() => startEdit(n)}
                            title={vi ? "Sửa ghi chú" : "Edit note"}
                            className="opacity-60 hover:opacity-100"
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </button>
                          <button
                            type="button"
                            onClick={() => void api.deleteNote(n.id).then(() => load(query))}
                            title={vi ? "Xóa ghi chú" : "Delete note"}
                            className="opacity-60 hover:opacity-100"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </div>
                      <p className="mt-1.5 whitespace-pre-wrap text-xs" style={{ color: "var(--muted)" }}>
                        {n.content}
                      </p>
                    </div>
                    {n.tags && (
                      <div className="font-mono text-[11px]" style={{ color: "var(--accent)" }}>
                        #{n.tags}
                      </div>
                    )}
                  </>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Reminders */}
      <div
        className="space-y-4 border p-4"
        style={{
          backgroundColor: "var(--surface)",
          borderColor: "var(--border)",
          borderRadius: "var(--radius-base)",
        }}
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-medium">{vi ? "Lịch nhắc Telegram" : "Reminders"}</h2>
          <span className="text-[11px]" style={{ color: "var(--muted)" }}>
            {vi
              ? "Ví dụ: 30m Uống nước · 09:30 Họp team · 2026-11-28 08:00 Gửi mail"
              : "Examples: 30m Drink water · 09:30 Standup · 2026-11-28 08:00 Send report"}
          </span>
        </div>

        <form onSubmit={(e) => void handleAddReminder(e)} className="grid gap-2 sm:grid-cols-5">
          <input
            type="text"
            value={remChatId}
            onChange={(e) => setRemChatId(e.target.value)}
            placeholder="Telegram ID"
            className="rounded-lg border px-3 py-2 font-mono text-xs outline-none"
            style={{ backgroundColor: "var(--bg)", borderColor: "var(--border)" }}
          />
          <input
            type="text"
            value={remRaw}
            onChange={(e) => setRemRaw(e.target.value)}
            placeholder={vi ? "30m Nhắc làm báo cáo..." : "30m Finish report..."}
            className="sm:col-span-3 rounded-lg border px-3 py-2 text-xs outline-none"
            style={{ backgroundColor: "var(--bg)", borderColor: "var(--border)" }}
          />
          <button
            type="submit"
            disabled={!remRaw.trim()}
            className="inline-flex items-center justify-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-medium disabled:opacity-40"
            style={{ borderColor: "var(--border)", backgroundColor: "var(--surface-elevated)" }}
          >
            <BellPlus className="h-3.5 w-3.5" />
            <span>{vi ? "Hẹn nhắc" : "Schedule"}</span>
          </button>
        </form>
        {remError && <p className="text-xs text-red-400">{remError}</p>}

        {reminders.length === 0 ? (
          <p className="text-xs" style={{ color: "var(--muted)" }}>
            {vi ? "Chưa có nhắc nhở nào." : "No reminders scheduled."}
          </p>
        ) : (
          <div className="space-y-2">
            {reminders.map((r) => (
              <div
                key={r.id}
                className="flex items-center justify-between gap-3 border-b pb-2 text-xs last:border-b-0 last:pb-0"
                style={{ borderColor: "var(--border)" }}
              >
                <div className="min-w-0">
                  <span className="font-medium">{r.message}</span>
                  <span className="ml-2 font-mono text-[11px] tabular-nums" style={{ color: "var(--muted)" }}>
                    {new Date(r.remind_at).toLocaleString()} · {r.status}
                  </span>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {r.status === "pending" && (
                    <button
                      type="button"
                      onClick={() => void api.cancelReminder(r.id).then(() => load(query))}
                      className="text-[11px] underline"
                      style={{ color: "var(--muted)" }}
                    >
                      {vi ? "Hủy" : "Cancel"}
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => void api.deleteReminder(r.id).then(() => load(query))}
                    title={vi ? "Xóa hẳn" : "Delete"}
                    className="opacity-60 hover:opacity-100"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
