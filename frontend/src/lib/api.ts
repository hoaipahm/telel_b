import { ThemeConfig } from "@/lib/themes";

export interface SecretHint {
  configured: boolean;
  source: "vault" | "env" | "none";
  hint: string;
  updated_at: string | null;
}

export interface ModuleFlags {
  chat: boolean;
  brain: boolean;
  finance: boolean;
  digest: boolean;
  remote: boolean;
}

export interface AIConfig {
  primary_provider: "gemini" | "openai";
  fallback_enabled: boolean;
  gemini_model: string;
  openai_model: string;
  openai_base_url: string;
  active_persona: string;
  daily_request_cap: number;
  daily_token_cap: number;
}

export interface BriefingConfig {
  enabled: boolean;
  time_hhmm: string;
  last_sent_date: string;
}

export interface OverviewData {
  bot: {
    running: boolean;
    last_error: string;
    allowed_user_ids: number[];
    polling_disabled: boolean;
  };
  secrets: Record<"telegram" | "gemini" | "openai", SecretHint>;
  modules: ModuleFlags;
  ai: AIConfig;
  theme: ThemeConfig;
  personas: Record<string, string>;
  briefing?: BriefingConfig;
  usage: {
    requests: number;
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
  };
}

export interface ConversationItem {
  id: number;
  chat_id: number;
  role: string;
  content: string;
  provider: string | null;
  model: string | null;
  tokens_used: number;
  created_at: string;
}

export interface NoteItem {
  id: number;
  title: string;
  content: string;
  tags: string;
  source_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReminderItem {
  id: number;
  chat_id: number;
  message: string;
  remind_at: string;
  status: string;
  created_at: string;
}

export interface TransactionItem {
  id: number;
  kind: "expense" | "income";
  amount_minor: number;
  currency: string;
  category: string;
  note: string;
  occurred_at: string;
  created_at: string;
}

export interface FinanceSummary {
  month: string;
  totals: Array<{ kind: string; currency: string; total_minor: number }>;
  by_category: Array<{
    kind: string;
    category: string;
    currency: string;
    total_minor: number;
    tx_count: number;
  }>;
}

export interface DigestItem {
  id: number;
  url: string;
  title: string;
  summary: string;
  created_at: string;
}

export interface FeedItem {
  id: number;
  url: string;
  title: string;
  enabled: number;
  created_at: string;
}

export interface RemoteStatus {
  enabled: boolean;
  host: {
    platform: string;
    python: string;
    cpu_percent: number;
    ram_used_gb: number;
    ram_total_gb: number;
    ram_percent: number;
    disk_free_gb: number;
    disk_total_gb: number;
  } | null;
  containers: Array<{
    id: string;
    names: string;
    image: string;
    status: string;
    state: string;
  }>;
  docker_error?: string;
}

export interface AuditLogItem {
  id: number;
  actor: string;
  action: string;
  status: string;
  detail: string;
  created_at: string;
}

export interface AITestResult {
  ok: boolean;
  provider: "gemini" | "openai";
  latency_ms: number;
  models: string[];
  error: string;
}

export interface ChatReply {
  text: string;
  provider: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
}

export interface FeedHeadline {
  title: string;
  url: string;
}

export class ApiClientError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

interface WebView2Bridge {
  postMessage: (msg: unknown) => void;
  addEventListener: (type: "message", listener: (ev: MessageEvent) => void) => void;
}

interface DesktopReply {
  type?: string;
  id?: string;
  ok?: boolean;
  status?: number;
  text?: string;
  error?: { code?: string; message?: string };
}

declare global {
  interface Window {
    chrome?: {
      webview?: WebView2Bridge;
    };
  }
}

const pendingCalls = new Map<
  string,
  { resolve: (res: DesktopReply) => void; reject: (err: Error) => void }
>();
let listenerAttached = false;
let callCounter = 0;

function ensureWebViewListener(bridge: WebView2Bridge): void {
  if (listenerAttached) return;
  listenerAttached = true;
  bridge.addEventListener("message", (event: MessageEvent) => {
    const raw = typeof event.data === "string" ? (JSON.parse(event.data) as DesktopReply) : (event.data as DesktopReply);
    if (!raw || raw.type !== "api_response" || !raw.id) return;
    const entry = pendingCalls.get(raw.id);
    if (!entry) return;
    pendingCalls.delete(raw.id);
    entry.resolve(raw);
  });
}

export function isDesktopRuntime(): boolean {
  return typeof window !== "undefined" && Boolean(window.chrome?.webview);
}

export function notifyDesktopThemeMode(mode: "system" | "light" | "dark"): void {
  if (typeof window === "undefined") return;
  window.chrome?.webview?.postMessage({ type: "theme_mode", mode });
}

async function requestViaDesktopBridge(
  method: string,
  path: string,
  body?: string,
): Promise<DesktopReply> {
  const bridge = window.chrome?.webview;
  if (!bridge) {
    throw new ApiClientError(
      "DESKTOP_HOST_REQUIRED",
      "Giao diện này chạy bên trong ứng dụng desktop TeleMind.exe.",
      503,
    );
  }
  ensureWebViewListener(bridge);
  callCounter += 1;
  const id = `req_${Date.now()}_${callCounter}`;
  return new Promise<DesktopReply>((resolve, reject) => {
    const timer = window.setTimeout(() => {
      pendingCalls.delete(id);
      reject(new ApiClientError("IPC_TIMEOUT", "Desktop engine timed out.", 504));
    }, 65000);

    pendingCalls.set(id, {
      resolve: (res) => {
        window.clearTimeout(timer);
        resolve(res);
      },
      reject: (err) => {
        window.clearTimeout(timer);
        reject(err);
      },
    });
    bridge.postMessage({ type: "api_request", id, method, path, body: body ?? null });
  });
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const clean = path.replace(/^\/+/, "");
  const method = (init?.method ?? "GET").toUpperCase();
  const body = typeof init?.body === "string" ? init.body : undefined;

  const reply = await requestViaDesktopBridge(method, clean, body);
  if (!reply.ok) {
    const status = reply.status ?? 500;
    const code = reply.error?.code ?? `HTTP_${status}`;
    const message = reply.error?.message ?? (reply.text || "Request failed");
    throw new ApiClientError(code, message, status);
  }
  return JSON.parse(reply.text || "{}") as T;
}

export const api = {
  getOverview: () => requestJson<OverviewData>("api/v1/overview"),
  updateModules: (modules: ModuleFlags) =>
    requestJson<ModuleFlags>("api/v1/settings/modules", {
      method: "PUT",
      body: JSON.stringify(modules),
    }),
  updateAI: (ai: AIConfig) =>
    requestJson<AIConfig>("api/v1/settings/ai", {
      method: "PUT",
      body: JSON.stringify(ai),
    }),
  updateTheme: (theme: ThemeConfig) =>
    requestJson<ThemeConfig>("api/v1/settings/theme", {
      method: "PUT",
      body: JSON.stringify(theme),
    }),
  updatePersonas: (personas: Record<string, string>) =>
    requestJson<Record<string, string>>("api/v1/settings/personas", {
      method: "PUT",
      body: JSON.stringify({ personas }),
    }),
  updateBriefing: (briefing: BriefingConfig) =>
    requestJson<BriefingConfig>("api/v1/settings/briefing", {
      method: "PUT",
      body: JSON.stringify(briefing),
    }),
  sendBriefingNow: () =>
    requestJson<{ sent_chats: number; preview: string }>("api/v1/digest/briefing/send", {
      method: "POST",
    }),
  updateAllowlist: (user_ids: number[]) =>
    requestJson<{ user_ids: number[] }>("api/v1/settings/telegram-allowlist", {
      method: "PUT",
      body: JSON.stringify({ user_ids }),
    }),
  setSecret: (provider: "telegram" | "gemini" | "openai", value: string) =>
    requestJson<{ provider: string; configured: boolean; hint: string }>(
      `api/v1/secrets/${provider}`,
      { method: "PUT", body: JSON.stringify({ value }) },
    ),
  deleteSecret: (provider: "telegram" | "gemini" | "openai") =>
    requestJson<{ provider: string; configured: boolean; hint: string }>(
      `api/v1/secrets/${provider}`,
      { method: "DELETE" },
    ),
  testAI: (provider: "gemini" | "openai") =>
    requestJson<AITestResult>("api/v1/ai/test", {
      method: "POST",
      body: JSON.stringify({ provider }),
    }),
  reloadBot: () =>
    requestJson<{ running: boolean; last_error: string }>("api/v1/bot/reload", {
      method: "POST",
    }),
  getConversations: () => requestJson<{ items: ConversationItem[] }>("api/v1/conversations"),
  sendChat: (message: string, chat_id = 0) =>
    requestJson<ChatReply>("api/v1/chat", {
      method: "POST",
      body: JSON.stringify({ chat_id, message }),
    }),
  deleteConversationMessage: (id: number) =>
    requestJson<{ deleted: boolean }>(`api/v1/conversations/${id}`, { method: "DELETE" }),
  clearConversations: (chatId?: number) =>
    requestJson<{ deleted_count: number }>(
      chatId !== undefined ? `api/v1/conversations?chat_id=${chatId}` : "api/v1/conversations",
      { method: "DELETE" },
    ),
  getNotes: (q = "") =>
    requestJson<{ items: NoteItem[] }>(`api/v1/notes?q=${encodeURIComponent(q)}`),
  createNote: (data: { title: string; content: string; tags: string }) =>
    requestJson<NoteItem>("api/v1/notes", { method: "POST", body: JSON.stringify(data) }),
  updateNote: (id: number, data: { title: string; content: string; tags: string }) =>
    requestJson<NoteItem>(`api/v1/notes/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  deleteNote: (id: number) =>
    requestJson<{ deleted: boolean }>(`api/v1/notes/${id}`, { method: "DELETE" }),
  getReminders: () => requestJson<{ items: ReminderItem[] }>("api/v1/reminders"),
  createReminder: (data: { chat_id: number; raw: string }) =>
    requestJson<ReminderItem>("api/v1/reminders", { method: "POST", body: JSON.stringify(data) }),
  cancelReminder: (id: number) =>
    requestJson<{ cancelled: boolean }>(`api/v1/reminders/${id}`, { method: "DELETE" }),
  deleteReminder: (id: number) =>
    requestJson<{ deleted: boolean }>(`api/v1/reminders/${id}?hard=true`, { method: "DELETE" }),
  getTransactions: (month = "") =>
    requestJson<{ items: TransactionItem[] }>(
      month ? `api/v1/finance/transactions?month=${encodeURIComponent(month)}` : "api/v1/finance/transactions",
    ),
  createTransaction: (data: {
    kind: "expense" | "income";
    amount: string;
    category: string;
    note: string;
  }) =>
    requestJson<TransactionItem>("api/v1/finance/transactions", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateTransaction: (
    id: number,
    data: { kind: "expense" | "income"; amount: string; category: string; note: string },
  ) =>
    requestJson<TransactionItem>(`api/v1/finance/transactions/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  deleteTransaction: (id: number) =>
    requestJson<{ deleted: boolean }>(`api/v1/finance/transactions/${id}`, { method: "DELETE" }),
  getFinanceSummary: (month = "") =>
    requestJson<FinanceSummary>(
      month ? `api/v1/finance/summary?month=${encodeURIComponent(month)}` : "api/v1/finance/summary",
    ),
  exportFinanceCsv: async (month = ""): Promise<string> => {
    const path = month
      ? `api/v1/finance/export.csv?month=${encodeURIComponent(month)}`
      : "api/v1/finance/export.csv";
    const reply = await requestViaDesktopBridge("GET", path);
    if (!reply.ok) {
      throw new ApiClientError("EXPORT_FAILED", reply.text || "Export failed", reply.status ?? 500);
    }
    return reply.text ?? "";
  },
  getDigests: () => requestJson<{ items: DigestItem[] }>("api/v1/digest"),
  createDigest: (url: string) =>
    requestJson<DigestItem>("api/v1/digest", { method: "POST", body: JSON.stringify({ url }) }),
  deleteDigest: (id: number) =>
    requestJson<{ deleted: boolean }>(`api/v1/digest/${id}`, { method: "DELETE" }),
  getFeeds: () => requestJson<{ items: FeedItem[] }>("api/v1/digest/feeds"),
  createFeed: (url: string, title = "") =>
    requestJson<FeedItem>("api/v1/digest/feeds", {
      method: "POST",
      body: JSON.stringify({ url, title }),
    }),
  updateFeed: (id: number, data: { title: string; enabled: boolean }) =>
    requestJson<FeedItem>(`api/v1/digest/feeds/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  getFeedItems: (id: number) =>
    requestJson<{ items: FeedHeadline[] }>(`api/v1/digest/feeds/${id}/items`),
  deleteFeed: (id: number) =>
    requestJson<{ deleted: boolean }>(`api/v1/digest/feeds/${id}`, { method: "DELETE" }),
  getRemoteStatus: () => requestJson<RemoteStatus>("api/v1/remote/status"),
  getRemoteDockerLogs: (containerName: string) =>
    requestJson<{ container: string; logs: string }>(
      `api/v1/remote/docker/${encodeURIComponent(containerName)}/logs`,
      { method: "POST" },
    ),
  getAuditLogs: () => requestJson<{ items: AuditLogItem[] }>("api/v1/audit-logs"),
  clearAuditLogs: () =>
    requestJson<{ deleted_count: number }>("api/v1/audit-logs", { method: "DELETE" }),
};
