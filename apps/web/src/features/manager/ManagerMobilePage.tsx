import {
  APPROVAL_KIND_LABELS,
  Permission,
  formatMoney,
  type ApprovalRequest,
  type CreditHoldRow,
  type ManagerDashboard,
  type PendingTimeEntry,
} from "@ai-pos/shared-types";
import { BellRing, Check, CreditCard, LayoutDashboard, LogOut, Monitor, Timer, X } from "lucide-react";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { apiGet, apiPost } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { errorMessage } from "../users/api";

type Tab = "today" | "approvals" | "staff" | "credit";

const QUICK_NOTES = ["Regular customer", "Price match", "Bulk order", "Manager discretion"];
const DASHBOARD_REFRESH_MS = 30_000;
const APPROVALS_REFRESH_MS = 5_000;

const time = (value: string) => new Date(value).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
const hours = (minutes: number) => `${Math.floor(minutes / 60)}h ${String(minutes % 60).padStart(2, "0")}m`;

export function ManagerMobilePage() {
  const { user, can, logout } = useAuth();
  const [tab, setTab] = useState<Tab>("today");
  const [board, setBoard] = useState<ManagerDashboard | null>(null);
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
  const [error, setError] = useState<string | null>(null);

  const loadBoard = useCallback(async () => {
    try {
      setBoard(await apiGet<ManagerDashboard>(`/api/v1/manager/dashboard?tz_offset_minutes=${-new Date().getTimezoneOffset()}`));
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "Could not load today's numbers."));
    }
  }, []);

  const loadApprovals = useCallback(async () => {
    try {
      setApprovals(await apiGet<ApprovalRequest[]>("/api/v1/approvals"));
    } catch {
      // The next poll retries; a phone on a weak signal should not flash errors.
    }
  }, []);

  useEffect(() => {
    void loadBoard();
    const timer = window.setInterval(() => void loadBoard(), DASHBOARD_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [loadBoard]);

  useEffect(() => {
    void loadApprovals();
    const timer = window.setInterval(() => void loadApprovals(), APPROVALS_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [loadApprovals]);

  const tabs: { id: Tab; label: string; icon: ReactNode; badge?: number; show: boolean }[] = [
    { id: "today", label: "Today", icon: <LayoutDashboard size={20} aria-hidden="true" />, show: true },
    { id: "approvals", label: "Approvals", icon: <BellRing size={20} aria-hidden="true" />, badge: approvals.length, show: true },
    {
      id: "staff",
      label: "Timesheets",
      icon: <Timer size={20} aria-hidden="true" />,
      badge: board?.attention.timesheets ?? undefined,
      show: can(Permission.StaffManage),
    },
    {
      id: "credit",
      label: "Credit",
      icon: <CreditCard size={20} aria-hidden="true" />,
      badge: board?.attention.credit_holds ?? undefined,
      show: can(Permission.CustomersManage),
    },
  ];

  return (
    <div className="mx-auto flex min-h-screen max-w-lg flex-col bg-canvas">
      <header className="sticky top-0 z-10 flex items-center justify-between border-b border-line bg-white/95 px-4 py-3 backdrop-blur">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-charcoal/50">Manager</p>
          <p className="text-sm font-semibold">{user?.full_name}</p>
        </div>
        <div className="flex items-center gap-1">
          <Link to="/" aria-label="Open the full portal" className="rounded-full p-2 text-charcoal/60 hover:bg-surface">
            <Monitor size={18} aria-hidden="true" />
          </Link>
          <button type="button" aria-label="Sign out" onClick={logout} className="rounded-full p-2 text-charcoal/60 hover:bg-surface">
            <LogOut size={18} aria-hidden="true" />
          </button>
        </div>
      </header>

      <main className="flex-1 space-y-4 px-4 pb-28 pt-4">
        {error ? <p className="rounded-2xl bg-accent/10 px-4 py-3 text-sm font-medium text-accent">{error}</p> : null}
        {tab === "today" ? <TodayView board={board} onOpen={setTab} /> : null}
        {tab === "approvals" ? <ApprovalsView approvals={approvals} currency={board?.currency ?? "AED"} onChanged={() => void loadApprovals()} /> : null}
        {tab === "staff" ? <TimesheetsView onChanged={() => void loadBoard()} /> : null}
        {tab === "credit" ? <CreditView currency={board?.currency ?? "AED"} onChanged={() => void loadBoard()} /> : null}
      </main>

      <nav className="fixed inset-x-0 bottom-0 z-10 mx-auto flex max-w-lg border-t border-line bg-white pb-[env(safe-area-inset-bottom)]">
        {tabs
          .filter((item) => item.show)
          .map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setTab(item.id)}
              aria-current={tab === item.id ? "page" : undefined}
              className={`relative flex flex-1 flex-col items-center gap-1 py-3 text-[11px] font-semibold ${
                tab === item.id ? "text-accent" : "text-charcoal/50"
              }`}
            >
              {item.icon}
              {item.label}
              {item.badge ? (
                <span className="absolute right-[calc(50%-22px)] top-2 min-w-[18px] rounded-full bg-accent px-1 text-[10px] leading-[18px] text-white">
                  {item.badge}
                </span>
              ) : null}
            </button>
          ))}
      </nav>
    </div>
  );
}

function TodayView({ board, onOpen }: { board: ManagerDashboard | null; onOpen: (tab: Tab) => void }) {
  if (board === null) return <p className="py-10 text-center text-sm text-charcoal/60">Loading today…</p>;
  const money = (cents: number) => formatMoney(cents, board.currency);
  const change = board.yesterday_net_cents ? Math.round(((board.net_cents - board.yesterday_net_cents) / Math.abs(board.yesterday_net_cents)) * 100) : null;
  const peak = Math.max(...board.hourly_cents, 1);
  const currentHour = new Date().getHours();
  const attention = [
    { label: ["approval waiting", "approvals waiting"], value: board.attention.approvals, tab: "approvals" as Tab },
    { label: ["timesheet to approve", "timesheets to approve"], value: board.attention.timesheets, tab: "staff" as Tab },
    { label: ["customer on credit hold", "customers on credit hold"], value: board.attention.credit_holds, tab: "credit" as Tab },
  ].filter((item) => item.value);

  return (
    <>
      <article className="rounded-card bg-charcoal p-5 text-white">
        <p className="text-sm text-white/60">Net sales today</p>
        <p className="mt-2 text-4xl font-semibold tabular-nums">{money(board.net_cents)}</p>
        <p className="mt-2 text-xs text-white/60">
          {board.sales} sale{board.sales === 1 ? "" : "s"}
          {change !== null ? (
            <span className={change >= 0 ? "text-emerald-300" : "text-red-300"}>
              {" "}
              · {change >= 0 ? "+" : ""}
              {change}% vs this time yesterday
            </span>
          ) : null}
        </p>
        <div className="mt-4 flex h-16 items-end gap-[3px]" aria-label="Sales by hour">
          {board.hourly_cents.map((cents, hour) => (
            <div
              key={hour}
              title={`${hour}:00 · ${money(cents)}`}
              className={`flex-1 rounded-sm ${hour === currentHour ? "bg-accent" : "bg-white/25"}`}
              style={{ height: `${Math.max((cents / peak) * 100, hour <= currentHour ? 4 : 2)}%` }}
            />
          ))}
        </div>
      </article>

      {attention.length ? (
        <div className="space-y-2">
          {attention.map((item) => (
            <button
              key={item.tab}
              type="button"
              onClick={() => onOpen(item.tab)}
              className="flex w-full items-center justify-between rounded-2xl bg-accent px-4 py-3 text-left text-sm font-semibold text-white"
            >
              <span>
                {item.value} {item.label[item.value === 1 ? 0 : 1]}
              </span>
              <span aria-hidden="true">›</span>
            </button>
          ))}
        </div>
      ) : null}

      <section className="rounded-card border border-line bg-white p-4">
        <h2 className="mb-3 text-sm font-semibold">By branch</h2>
        {board.branches.length === 0 ? <p className="text-sm text-charcoal/60">No sales yet today.</p> : null}
        <ul className="space-y-3">
          {board.branches.map((branch) => (
            <li key={branch.store_id}>
              <div className="flex items-baseline justify-between">
                <span className="text-sm font-medium">
                  {branch.store_name} <span className="font-mono text-xs text-charcoal/50">{branch.store_code}</span>
                </span>
                <span className="text-sm font-semibold tabular-nums">{money(branch.net_cents)}</span>
              </div>
              <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface">
                <div className="h-full rounded-full bg-accent" style={{ width: `${board.net_cents > 0 ? Math.max((branch.net_cents / board.net_cents) * 100, 2) : 0}%` }} />
              </div>
              <p className="mt-1 text-xs text-charcoal/50 tabular-nums">
                {branch.sales} sales · avg {money(branch.average_basket_cents)}
                {branch.refunds_cents ? ` · refunds ${money(branch.refunds_cents)}` : ""}
                {branch.last_sale_at ? ` · last ${time(branch.last_sale_at)}` : ""}
              </p>
            </li>
          ))}
        </ul>
      </section>

      {board.top_products.length ? (
        <section className="rounded-card border border-line bg-white p-4">
          <h2 className="mb-3 text-sm font-semibold">Top sellers today</h2>
          <ol className="space-y-2">
            {board.top_products.map((product, index) => (
              <li key={product.product_id} className="flex items-center justify-between gap-3 text-sm">
                <span className="min-w-0 truncate">
                  <span className="mr-2 text-charcoal/40 tabular-nums">{index + 1}</span>
                  {product.name}
                </span>
                <span className="shrink-0 tabular-nums text-charcoal/70">
                  {product.quantity} · {money(product.revenue_cents)}
                </span>
              </li>
            ))}
          </ol>
        </section>
      ) : null}
      <p className="text-center text-[11px] text-charcoal/40">Updated {time(board.as_of)} · refreshes every 30 seconds</p>
    </>
  );
}

function ApprovalsView({ approvals, currency, onChanged }: { approvals: ApprovalRequest[]; currency: string; onChanged: () => void }) {
  if (approvals.length === 0) {
    return (
      <div className="rounded-card border border-line bg-white px-6 py-12 text-center">
        <Check size={28} aria-hidden="true" className="mx-auto text-charcoal/30" />
        <p className="mt-3 text-sm font-medium">Nothing waiting</p>
        <p className="mt-1 text-xs text-charcoal/60">When a cashier asks for approval it appears here within seconds.</p>
      </div>
    );
  }
  return (
    <ul className="space-y-3">
      {approvals.map((request) => (
        <ApprovalCard key={request.id} request={request} currency={currency} onChanged={onChanged} />
      ))}
    </ul>
  );
}

function ApprovalCard({ request, currency, onChanged }: { request: ApprovalRequest; currency: string; onChanged: () => void }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const left = Math.max(0, Math.round((new Date(request.expires_at).getTime() - now) / 1000));

  const answer = async (approve: boolean) => {
    if (approve && note.trim().length < 3) return setError("Pick or type a short reason.");
    setBusy(true);
    try {
      await apiPost(`/api/v1/approvals/${request.id}/${approve ? "approve" : "decline"}`, { note: note.trim() });
      onChanged();
    } catch (caught) {
      setError(errorMessage(caught, "Could not send your answer."));
      setBusy(false);
    }
  };

  return (
    <li className="rounded-card border border-line bg-white p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-accent">{APPROVAL_KIND_LABELS[request.kind]}</p>
          <p className="mt-0.5 font-semibold">{request.title}</p>
          <p className="text-xs text-charcoal/50">
            {request.requested_by_name ?? "Cashier"}
            {request.store_code ? ` · ${request.store_code}` : ""} · {time(request.created_at)}
          </p>
        </div>
        <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold tabular-nums ${left < 60 ? "bg-accent text-white" : "bg-surface"}`}>
          {Math.floor(left / 60)}:{String(left % 60).padStart(2, "0")}
        </span>
      </div>
      {request.details.length ? (
        <ul className="mt-3 space-y-1 rounded-2xl bg-surface px-3 py-2 text-sm">
          {request.details.map((detail) => (
            <li key={detail}>{detail}</li>
          ))}
        </ul>
      ) : null}
      {request.amount_cents !== null ? <p className="mt-2 text-sm font-semibold tabular-nums">{formatMoney(request.amount_cents, currency)}</p> : null}
      <div className="mt-3 flex flex-wrap gap-1.5">
        {QUICK_NOTES.map((quick) => (
          <button
            key={quick}
            type="button"
            onClick={() => setNote(quick)}
            className={`rounded-full px-3 py-1 text-xs font-medium ring-1 ${note === quick ? "bg-charcoal text-white ring-charcoal" : "ring-line"}`}
          >
            {quick}
          </button>
        ))}
      </div>
      <input
        aria-label="Reason"
        placeholder="Reason (goes on the audit trail)"
        value={note}
        maxLength={250}
        onChange={(event) => setNote(event.target.value)}
        className="mt-2 w-full rounded-xl bg-surface px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40"
      />
      {error ? <p className="mt-2 text-xs font-medium text-accent">{error}</p> : null}
      <div className="mt-3 grid grid-cols-2 gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => void answer(false)}
          className="flex items-center justify-center gap-1.5 rounded-full border border-line py-3 text-sm font-semibold disabled:opacity-50"
        >
          <X size={16} aria-hidden="true" /> Decline
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void answer(true)}
          className="flex items-center justify-center gap-1.5 rounded-full bg-accent py-3 text-sm font-semibold text-white disabled:opacity-50"
        >
          <Check size={16} aria-hidden="true" /> Approve
        </button>
      </div>
    </li>
  );
}

function TimesheetsView({ onChanged }: { onChanged: () => void }) {
  const [entries, setEntries] = useState<PendingTimeEntry[] | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const rows = await apiGet<PendingTimeEntry[]>("/api/v1/manager/timesheets");
      setEntries(rows);
      setSelected(new Set(rows.map((row) => row.id)));
    } catch (caught) {
      setError(errorMessage(caught, "Could not load timesheets."));
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  const approve = async () => {
    try {
      await apiPost("/api/v1/timesheets/approve", { entry_ids: [...selected] });
      onChanged();
      void load();
    } catch (caught) {
      setError(errorMessage(caught, "Could not approve."));
    }
  };

  if (entries === null) return <p className="py-10 text-center text-sm text-charcoal/60">Loading timesheets…</p>;
  return (
    <section className="space-y-3">
      {error ? <p className="text-sm font-medium text-accent">{error}</p> : null}
      {entries.length === 0 ? <p className="rounded-card border border-line bg-white px-6 py-12 text-center text-sm text-charcoal/60">Every finished shift is approved.</p> : null}
      <ul className="divide-y divide-line rounded-card border border-line bg-white">
        {entries.map((entry) => (
          <li key={entry.id}>
            <label className="flex items-center gap-3 px-4 py-3">
              <input
                type="checkbox"
                checked={selected.has(entry.id)}
                onChange={(event) => {
                  const next = new Set(selected);
                  if (event.target.checked) next.add(entry.id);
                  else next.delete(entry.id);
                  setSelected(next);
                }}
                className="h-5 w-5 accent-accent"
              />
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-medium">{entry.user_name}</span>
                <span className="block text-xs text-charcoal/50">
                  {entry.store_code} · {new Date(entry.clock_in_at).toLocaleDateString(undefined, { day: "numeric", month: "short" })} ·{" "}
                  {time(entry.clock_in_at)}–{time(entry.clock_out_at)}
                  {entry.break_minutes ? ` · ${entry.break_minutes}m break` : ""}
                </span>
              </span>
              <span className="text-sm font-semibold tabular-nums">{hours(entry.worked_minutes)}</span>
            </label>
          </li>
        ))}
      </ul>
      {entries.length ? (
        <button
          type="button"
          disabled={selected.size === 0}
          onClick={() => void approve()}
          className="w-full rounded-full bg-accent py-3 text-sm font-semibold text-white disabled:opacity-50"
        >
          Approve {selected.size} shift{selected.size === 1 ? "" : "s"}
        </button>
      ) : null}
    </section>
  );
}

function CreditView({ currency, onChanged }: { currency: string; onChanged: () => void }) {
  const [rows, setRows] = useState<CreditHoldRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const money = (cents: number) => formatMoney(cents, currency);

  const load = useCallback(async () => {
    try {
      setRows(await apiGet<CreditHoldRow[]>("/api/v1/manager/credit-holds"));
    } catch (caught) {
      setError(errorMessage(caught, "Could not load credit holds."));
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  const lift = async (row: CreditHoldRow) => {
    try {
      await apiPost(`/api/v1/customers/${row.customer_id}/credit-hold`, { hold: false, reason: "Lifted from the manager app" });
      onChanged();
      void load();
    } catch (caught) {
      setError(errorMessage(caught, "Could not lift the hold."));
    }
  };

  if (rows === null) return <p className="py-10 text-center text-sm text-charcoal/60">Loading…</p>;
  return (
    <section className="space-y-3">
      {error ? <p className="text-sm font-medium text-accent">{error}</p> : null}
      {rows.length === 0 ? <p className="rounded-card border border-line bg-white px-6 py-12 text-center text-sm text-charcoal/60">No customer is on credit hold.</p> : null}
      {rows.map((row) => (
        <article key={row.customer_id} className="rounded-card border border-line bg-white p-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="font-semibold">{row.name}</p>
              <p className="text-xs text-charcoal/50">{row.reason ?? (row.manual ? "Put on hold by a manager" : "Overdue invoices")}</p>
            </div>
            <div className="text-right text-sm tabular-nums">
              <p className="font-semibold">{money(row.balance_cents)}</p>
              <p className="text-xs text-charcoal/50">limit {money(row.credit_limit_cents)}</p>
            </div>
          </div>
          <button type="button" onClick={() => void lift(row)} className="mt-3 w-full rounded-full border border-line py-2.5 text-sm font-semibold">
            Lift hold
          </button>
        </article>
      ))}
    </section>
  );
}
