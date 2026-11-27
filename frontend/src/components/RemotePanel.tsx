"use client";

import React, { useCallback, useEffect, useState } from "react";
import { RefreshCw, Terminal, Trash2, X } from "lucide-react";
import { api, AuditLogItem, ModuleFlags, RemoteStatus } from "@/lib/api";

export function RemotePanel({
  lang,
  modules,
  onToggleRemote,
}: {
  lang: "vi" | "en";
  modules: ModuleFlags | null;
  onToggleRemote: (nextEnabled: boolean) => Promise<void>;
}) {
  const vi = lang === "vi";
  const [remote, setRemote] = useState<RemoteStatus | null>(null);
  const [logs, setLogs] = useState<AuditLogItem[]>([]);
  const [selectedLogs, setSelectedLogs] = useState<{ container: string; text: string } | null>(null);
  const [confirmClearAudit, setConfirmClearAudit] = useState(false);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [rRes, lRes] = await Promise.all([api.getRemoteStatus(), api.getAuditLogs()]);
    setRemote(rRes);
    setLogs(lRes.items);
  }, []);

  useEffect(() => {
    void load();
  }, [load, modules?.remote]);

  const handleToggle = async () => {
    if (!modules) return;
    setBusy(true);
    try {
      await onToggleRemote(!modules.remote);
      await load();
    } finally {
      setBusy(false);
    }
  };

  const inspectLogs = async (containerName: string) => {
    setErr("");
    try {
      const res = await api.getRemoteDockerLogs(containerName);
      setSelectedLogs({ container: res.container, text: res.logs || "(Trống)" });
      await load();
    } catch (error) {
      setErr(error instanceof Error ? error.message : "Failed to fetch Docker logs");
    }
  };

  const clearAudit = async () => {
    await api.clearAuditLogs();
    setConfirmClearAudit(false);
    await load();
  };

  const isEnabled = remote?.enabled ?? modules?.remote ?? false;

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">
            {vi ? "PC & Docker Remote + Nhật ký Bảo mật" : "PC & Docker Remote + Audit Log"}
          </h1>
          <p className="text-xs" style={{ color: "var(--muted)" }}>
            {vi
              ? "Mặc định tắt. Chỉ hỗ trợ đọc thông số máy, xem log Docker whitelist và quản lý nhật ký."
              : "Disabled by default. Allows safe telemetry, allowlisted Docker logs, and audit cleanup."}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={busy || !modules}
            onClick={() => void handleToggle()}
            className="rounded-lg border px-3 py-1.5 text-xs font-medium disabled:opacity-45"
            style={{
              borderColor: isEnabled ? "var(--accent)" : "var(--border)",
              backgroundColor: isEnabled ? "var(--surface-elevated)" : "var(--surface)",
              color: isEnabled ? "var(--accent)" : "var(--fg)",
            }}
          >
            {isEnabled
              ? vi
                ? "Remote: ĐANG BẬT (Tắt)"
                : "Remote: ON (Disable)"
              : vi
                ? "Remote: ĐANG TẮT (Bật)"
                : "Remote: OFF (Enable)"}
          </button>

          <button
            type="button"
            onClick={() => void load()}
            className="inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium hover:opacity-80"
            style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)" }}
          >
            <RefreshCw className="h-3.5 w-3.5" />
            <span>{vi ? "Làm mới" : "Refresh"}</span>
          </button>
        </div>
      </div>

      {err && <p className="text-xs text-red-400">{err}</p>}

      {remote && !remote.enabled ? (
        <div
          className="border p-5 text-xs"
          style={{
            backgroundColor: "var(--surface)",
            borderColor: "var(--border)",
            borderRadius: "var(--radius-base)",
            color: "var(--muted)",
          }}
        >
          {vi
            ? "Module PC & Docker Remote hiện đang TẮT để bảo vệ máy. Nhấn nút 'Remote: ĐANG TẮT (Bật)' ở góc trên phải nếu bạn muốn bật nhanh."
            : "PC & Docker Remote is currently OFF. Use the button above to enable it."}
        </div>
      ) : (
        remote?.host && (
          <div className="grid gap-3 sm:grid-cols-3">
            <Metric title="CPU" value={`${remote.host.cpu_percent}%`} sub={remote.host.platform} />
            <Metric
              title="RAM"
              value={`${remote.host.ram_used_gb}/${remote.host.ram_total_gb} GB`}
              sub={`${remote.host.ram_percent}%`}
            />
            <Metric
              title="Disk Free"
              value={`${remote.host.disk_free_gb} GB`}
              sub={`/${remote.host.disk_total_gb} GB`}
            />
          </div>
        )
      )}

      {remote?.enabled && (
        <div
          className="space-y-3 border p-4"
          style={{
            backgroundColor: "var(--surface)",
            borderColor: "var(--border)",
            borderRadius: "var(--radius-base)",
          }}
        >
          <h2 className="text-sm font-medium">Docker Containers</h2>
          {remote.docker_error ? (
            <p className="text-xs" style={{ color: "var(--muted)" }}>
              {remote.docker_error}
            </p>
          ) : remote.containers.length === 0 ? (
            <p className="text-xs" style={{ color: "var(--muted)" }}>
              {vi ? "Không có container nào." : "No containers found."}
            </p>
          ) : (
            <div className="space-y-2 text-xs">
              {remote.containers.map((c) => (
                <div
                  key={c.id}
                  className="flex flex-wrap items-center justify-between gap-2 border-b pb-2 last:border-b-0 last:pb-0 font-mono"
                  style={{ borderColor: "var(--border)" }}
                >
                  <div>
                    <span className="font-semibold">{c.names}</span>
                    <span className="ml-2 text-[11px]" style={{ color: "var(--muted)" }}>
                      {c.status}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => void inspectLogs(c.names)}
                    className="inline-flex items-center gap-1 rounded border px-2 py-1 font-sans text-[11px] hover:opacity-80"
                    style={{ borderColor: "var(--border)", backgroundColor: "var(--bg)" }}
                  >
                    <Terminal className="h-3 w-3" />
                    <span>{vi ? "Xem 40 dòng log" : "View Logs"}</span>
                  </button>
                </div>
              ))}
            </div>
          )}

          {selectedLogs && (
            <div
              className="space-y-2 border p-3"
              style={{
                backgroundColor: "var(--bg)",
                borderColor: "var(--border)",
                borderRadius: "var(--radius-base)",
              }}
            >
              <div className="flex items-center justify-between text-xs">
                <span className="font-mono font-semibold" style={{ color: "var(--accent)" }}>
                  logs: {selectedLogs.container}
                </span>
                <button
                  type="button"
                  onClick={() => setSelectedLogs(null)}
                  className="opacity-70 hover:opacity-100"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
              <pre className="max-h-60 overflow-auto whitespace-pre-wrap font-mono text-[11px] leading-relaxed">
                {selectedLogs.text}
              </pre>
            </div>
          )}
        </div>
      )}

      <div
        className="space-y-3 border p-4"
        style={{
          backgroundColor: "var(--surface)",
          borderColor: "var(--border)",
          borderRadius: "var(--radius-base)",
        }}
      >
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-sm font-medium">{vi ? "Nhật ký Audit gần đây" : "Recent Audit Log"}</h2>
          {logs.length > 0 &&
            (confirmClearAudit ? (
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => void clearAudit()}
                  className="rounded px-2.5 py-1 text-xs font-semibold text-white"
                  style={{ backgroundColor: "#dc2626" }}
                >
                  {vi ? "Xác nhận xóa" : "Confirm"}
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmClearAudit(false)}
                  className="rounded border px-2.5 py-1 text-xs"
                  style={{ borderColor: "var(--border)" }}
                >
                  {vi ? "Hủy" : "Cancel"}
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setConfirmClearAudit(true)}
                className="inline-flex items-center gap-1 rounded border px-2.5 py-1 text-xs opacity-75 hover:opacity-100"
                style={{ borderColor: "var(--border)", backgroundColor: "var(--bg)" }}
              >
                <Trash2 className="h-3.5 w-3.5" />
                <span>{vi ? "Dọn nhật ký" : "Clear Log"}</span>
              </button>
            ))}
        </div>

        {logs.length === 0 ? (
          <p className="text-xs" style={{ color: "var(--muted)" }}>
            {vi ? "Nhật ký trống." : "Audit log is empty."}
          </p>
        ) : (
          <div className="space-y-1.5 font-mono text-[11px]">
            {logs.map((l) => (
              <div
                key={l.id}
                className="flex flex-wrap items-center justify-between gap-2 border-b pb-1.5 last:border-b-0"
                style={{ borderColor: "var(--border)" }}
              >
                <span>
                  [{l.actor}] {l.action} →{" "}
                  <strong style={{ color: l.status === "denied" ? "#f87171" : "var(--accent)" }}>
                    {l.status}
                  </strong>{" "}
                  {l.detail}
                </span>
                <span className="tabular-nums" style={{ color: "var(--muted)" }}>
                  {new Date(l.created_at).toLocaleTimeString()}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function Metric({ title, value, sub }: { title: string; value: string; sub: string }) {
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
        {title}
      </div>
      <div className="mt-1 font-mono text-lg font-semibold tabular-nums">{value}</div>
      <div className="text-[11px]" style={{ color: "var(--muted)" }}>
        {sub}
      </div>
    </div>
  );
}
