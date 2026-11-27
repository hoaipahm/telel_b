"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Check, Download, Pencil, Plus, Trash2, X } from "lucide-react";
import { api, FinanceSummary, TransactionItem } from "@/lib/api";

function formatMoney(amountMinor: number, currency: string): string {
  if (currency === "USD") {
    return `$${(amountMinor / 100).toLocaleString(undefined, { minimumFractionDigits: 2 })}`;
  }
  return `${amountMinor.toLocaleString()} ${currency}`;
}

function toEditableAmount(amountMinor: number, currency: string): string {
  if (currency === "USD") {
    return `${(amountMinor / 100).toFixed(2)} USD`;
  }
  return String(amountMinor);
}

export function FinancePanel({ lang }: { lang: "vi" | "en" }) {
  const vi = lang === "vi";
  const [month, setMonth] = useState("");
  const [items, setItems] = useState<TransactionItem[]>([]);
  const [summary, setSummary] = useState<FinanceSummary | null>(null);
  const [kind, setKind] = useState<"expense" | "income">("expense");
  const [amount, setAmount] = useState("");
  const [category, setCategory] = useState("Ăn uống");
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");

  // Inline editing state
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editKind, setEditKind] = useState<"expense" | "income">("expense");
  const [editAmount, setEditAmount] = useState("");
  const [editCategory, setEditCategory] = useState("");
  const [editNote, setEditNote] = useState("");

  const load = useCallback(async (targetMonth = month) => {
    const [txRes, sumRes] = await Promise.all([
      api.getTransactions(targetMonth),
      api.getFinanceSummary(targetMonth),
    ]);
    setItems(txRes.items);
    setSummary(sumRes);
  }, [month]);

  useEffect(() => {
    void load(month);
  }, [load, month]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr("");
    try {
      await api.createTransaction({ kind, amount, category, note });
      setAmount("");
      setNote("");
      await load(month);
    } catch (error) {
      setErr(error instanceof Error ? error.message : "Failed to save transaction");
    }
  };

  const startEdit = (tx: TransactionItem) => {
    setEditingId(tx.id);
    setEditKind(tx.kind);
    setEditAmount(toEditableAmount(tx.amount_minor, tx.currency));
    setEditCategory(tx.category);
    setEditNote(tx.note);
    setErr("");
  };

  const saveEdit = async (id: number) => {
    setErr("");
    try {
      await api.updateTransaction(id, {
        kind: editKind,
        amount: editAmount,
        category: editCategory,
        note: editNote,
      });
      setEditingId(null);
      await load(month);
    } catch (error) {
      setErr(error instanceof Error ? error.message : "Failed to update transaction");
    }
  };

  const balanceByCurrency = useMemo(() => {
    if (!summary) return [];
    const map = new Map<string, { income: number; expense: number }>();
    for (const t of summary.totals) {
      const cur = map.get(t.currency) ?? { income: 0, expense: 0 };
      if (t.kind === "income") cur.income += t.total_minor;
      else cur.expense += t.total_minor;
      map.set(t.currency, cur);
    }
    return Array.from(map.entries()).map(([currency, vals]) => ({
      currency,
      net: vals.income - vals.expense,
    }));
  }, [summary]);

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">
            {vi ? "Tài chính cá nhân" : "Personal Finance"}
          </h1>
          <p className="text-xs" style={{ color: "var(--muted)" }}>
            {vi
              ? "Thêm, sửa, xóa giao dịch & lọc theo tháng. Hỗ trợ `/chi 55k`, `/thu 15tr` và ảnh hóa đơn."
              : "Exact integer accounting. Add, edit, delete, filter by month, or log via Telegram."}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <input
            type="month"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
            aria-label={vi ? "Lọc theo tháng" : "Filter by month"}
            className="rounded-lg border px-2.5 py-1.5 text-xs outline-none"
            style={{ backgroundColor: "var(--surface)", borderColor: "var(--border)" }}
          />
          {month && (
            <button
              type="button"
              onClick={() => setMonth("")}
              className="rounded-lg border px-2.5 py-1.5 text-xs"
              style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)" }}
            >
              {vi ? "Tháng này" : "Current"}
            </button>
          )}
          <button
            type="button"
            onClick={() => {
              void api
                .exportFinanceCsv(month)
                .then((csvText) => {
                  const blob = new Blob([csvText], { type: "text/csv;charset=utf-8;" });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement("a");
                  a.href = url;
                  a.download = month ? `finance-${month}.csv` : "finance-export.csv";
                  a.click();
                  URL.revokeObjectURL(url);
                })
                .catch((error) => {
                  setErr(error instanceof Error ? error.message : "Export failed");
                });
            }}
            className="inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium hover:opacity-80"
            style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)" }}
          >
            <Download className="h-3.5 w-3.5" />
            <span>Export CSV</span>
          </button>
        </div>
      </div>

      {/* Summary Tiles */}
      {summary && (
        <div className="grid gap-3 sm:grid-cols-3">
          {summary.totals.map((t, idx) => (
            <div
              key={`${t.kind}-${t.currency}-${idx}`}
              className="border p-4"
              style={{
                backgroundColor: "var(--surface)",
                borderColor: "var(--border)",
                borderRadius: "var(--radius-base)",
              }}
            >
              <div className="text-xs" style={{ color: "var(--muted)" }}>
                {t.kind === "expense"
                  ? vi
                    ? `Tổng chi (${summary.month})`
                    : `Expense (${summary.month})`
                  : vi
                    ? `Tổng thu (${summary.month})`
                    : `Income (${summary.month})`}
              </div>
              <div className="mt-1 font-mono text-lg font-semibold tabular-nums">
                {formatMoney(t.total_minor, t.currency)}
              </div>
            </div>
          ))}
          {balanceByCurrency.map((b) => (
            <div
              key={`net-${b.currency}`}
              className="border p-4"
              style={{
                backgroundColor: "var(--surface)",
                borderColor: "var(--border)",
                borderRadius: "var(--radius-base)",
              }}
            >
              <div className="text-xs" style={{ color: "var(--muted)" }}>
                {vi ? `Cân đối (${summary.month})` : `Net Balance (${summary.month})`}
              </div>
              <div
                className="mt-1 font-mono text-lg font-semibold tabular-nums"
                style={{ color: b.net >= 0 ? "var(--accent)" : "#fca5a5" }}
              >
                {b.net < 0 ? "-" : "+"}
                {formatMoney(Math.abs(b.net), b.currency)}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add Transaction */}
      <form
        onSubmit={(e) => void handleSubmit(e)}
        className="grid gap-3 border p-4 sm:grid-cols-5"
        style={{
          backgroundColor: "var(--surface)",
          borderColor: "var(--border)",
          borderRadius: "var(--radius-base)",
        }}
      >
        <select
          value={kind}
          onChange={(e) => setKind(e.target.value as "expense" | "income")}
          className="rounded-lg border px-2.5 py-2 text-xs outline-none"
          style={{ backgroundColor: "var(--bg)", borderColor: "var(--border)" }}
        >
          <option value="expense">{vi ? "Chi tiêu" : "Expense"}</option>
          <option value="income">{vi ? "Thu nhập" : "Income"}</option>
        </select>
        <input
          type="text"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          placeholder="55k / 1.5tr / 12.50 USD"
          className="rounded-lg border px-3 py-2 font-mono text-xs outline-none"
          style={{ backgroundColor: "var(--bg)", borderColor: "var(--border)" }}
        />
        <input
          type="text"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          placeholder={vi ? "Danh mục" : "Category"}
          className="rounded-lg border px-3 py-2 text-xs outline-none"
          style={{ backgroundColor: "var(--bg)", borderColor: "var(--border)" }}
        />
        <input
          type="text"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder={vi ? "Ghi chú..." : "Note..."}
          className="rounded-lg border px-3 py-2 text-xs outline-none"
          style={{ backgroundColor: "var(--bg)", borderColor: "var(--border)" }}
        />
        <button
          type="submit"
          className="inline-flex items-center justify-center gap-1 rounded-lg px-3 py-2 text-xs font-semibold"
          style={{ backgroundColor: "var(--accent)", color: "#040805" }}
        >
          <Plus className="h-3.5 w-3.5" />
          <span>{vi ? "Thêm" : "Add"}</span>
        </button>
      </form>
      {err && <p className="text-xs text-red-400">{err}</p>}

      {/* Ledger Table */}
      <div
        className="overflow-x-auto border"
        style={{
          backgroundColor: "var(--surface)",
          borderColor: "var(--border)",
          borderRadius: "var(--radius-base)",
        }}
      >
        <table className="w-full text-left text-xs">
          <thead style={{ color: "var(--muted)" }}>
            <tr className="border-b" style={{ borderColor: "var(--border)" }}>
              <th className="px-4 py-2.5 font-medium">{vi ? "Loại" : "Type"}</th>
              <th className="px-4 py-2.5 font-medium">{vi ? "Số tiền" : "Amount"}</th>
              <th className="px-4 py-2.5 font-medium">{vi ? "Danh mục" : "Category"}</th>
              <th className="px-4 py-2.5 font-medium">{vi ? "Ghi chú" : "Note"}</th>
              <th className="px-4 py-2.5 font-medium">{vi ? "Ngày" : "Date"}</th>
              <th className="px-4 py-2.5 text-right">{vi ? "Thao tác" : "Actions"}</th>
            </tr>
          </thead>
          <tbody className="divide-y" style={{ borderColor: "var(--border)" }}>
            {items.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center" style={{ color: "var(--muted)" }}>
                  {vi ? "Chưa có giao dịch nào trong kỳ này." : "No transactions found."}
                </td>
              </tr>
            ) : (
              items.map((tx) => {
                const isEditing = editingId === tx.id;
                return (
                  <tr key={tx.id}>
                    {isEditing ? (
                      <>
                        <td className="px-3 py-2">
                          <select
                            value={editKind}
                            onChange={(e) => setEditKind(e.target.value as "expense" | "income")}
                            className="rounded border px-2 py-1 text-xs outline-none"
                            style={{ backgroundColor: "var(--bg)", borderColor: "var(--border)" }}
                          >
                            <option value="expense">expense</option>
                            <option value="income">income</option>
                          </select>
                        </td>
                        <td className="px-3 py-2">
                          <input
                            type="text"
                            value={editAmount}
                            onChange={(e) => setEditAmount(e.target.value)}
                            className="w-28 rounded border px-2 py-1 font-mono text-xs outline-none"
                            style={{ backgroundColor: "var(--bg)", borderColor: "var(--border)" }}
                          />
                        </td>
                        <td className="px-3 py-2">
                          <input
                            type="text"
                            value={editCategory}
                            onChange={(e) => setEditCategory(e.target.value)}
                            className="w-32 rounded border px-2 py-1 text-xs outline-none"
                            style={{ backgroundColor: "var(--bg)", borderColor: "var(--border)" }}
                          />
                        </td>
                        <td className="px-3 py-2">
                          <input
                            type="text"
                            value={editNote}
                            onChange={(e) => setEditNote(e.target.value)}
                            className="w-full rounded border px-2 py-1 text-xs outline-none"
                            style={{ backgroundColor: "var(--bg)", borderColor: "var(--border)" }}
                          />
                        </td>
                        <td className="px-4 py-2 font-mono text-[11px] tabular-nums" style={{ color: "var(--muted)" }}>
                          {new Date(tx.occurred_at).toLocaleDateString()}
                        </td>
                        <td className="px-4 py-2 text-right">
                          <div className="inline-flex items-center gap-2">
                            <button
                              type="button"
                              onClick={() => void saveEdit(tx.id)}
                              title={vi ? "Lưu" : "Save"}
                              style={{ color: "var(--accent)" }}
                            >
                              <Check className="h-3.5 w-3.5" />
                            </button>
                            <button
                              type="button"
                              onClick={() => setEditingId(null)}
                              title={vi ? "Hủy" : "Cancel"}
                            >
                              <X className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        </td>
                      </>
                    ) : (
                      <>
                        <td
                          className="px-4 py-2.5 font-mono uppercase"
                          style={{ color: tx.kind === "income" ? "var(--accent)" : "#fca5a5" }}
                        >
                          {tx.kind}
                        </td>
                        <td className="px-4 py-2.5 font-mono font-medium tabular-nums">
                          {formatMoney(tx.amount_minor, tx.currency)}
                        </td>
                        <td className="px-4 py-2.5">{tx.category}</td>
                        <td className="px-4 py-2.5" style={{ color: "var(--muted)" }}>
                          {tx.note}
                        </td>
                        <td className="px-4 py-2.5 font-mono text-[11px] tabular-nums" style={{ color: "var(--muted)" }}>
                          {new Date(tx.occurred_at).toLocaleDateString()}
                        </td>
                        <td className="px-4 py-2.5 text-right">
                          <div className="inline-flex items-center gap-2">
                            <button
                              type="button"
                              onClick={() => startEdit(tx)}
                              title={vi ? "Sửa giao dịch" : "Edit transaction"}
                              className="opacity-60 hover:opacity-100"
                            >
                              <Pencil className="h-3.5 w-3.5" />
                            </button>
                            <button
                              type="button"
                              onClick={() => void api.deleteTransaction(tx.id).then(() => load(month))}
                              title={vi ? "Xóa giao dịch" : "Delete transaction"}
                              className="opacity-60 hover:opacity-100"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        </td>
                      </>
                    )}
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
