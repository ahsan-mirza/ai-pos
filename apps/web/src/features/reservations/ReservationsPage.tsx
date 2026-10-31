import type { Floor } from "@ai-pos/shared-types";
import { CalendarRange } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ErrorNote, GhostButton, PrimaryButton, SelectField, TextField } from "../../components/ui/Field";
import { useTenant } from "../../context/TenantContext";
import { apiGet, apiPost, apiPut, getAccessToken } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { message } from "../customers/api";
import { storeOptions, useStores } from "../inventory/shared";
import { listenForTableEvents } from "../table-order/live";

type Tab = "overview" | "calendar" | "availability" | "active" | "history" | "settings";

interface Reservation {
  id: string;
  reservation_number: string;
  customer_name: string;
  customer_phone: string | null;
  guest_count: number;
  status: string;
  table_id: string | null;
  table_label: string | null;
  area_name: string | null;
  starts_at: string;
  ends_at: string;
  special_requests: string | null;
  notification_status: string;
  order_id: string | null;
}

interface Activity {
  id: string;
  event_type: string;
  description: string;
  created_at: string;
}

interface Settings {
  enabled: boolean;
  duration_minutes: number;
  buffer_minutes: number;
  grace_minutes: number;
  min_notice_minutes: number;
  max_advance_days: number;
  max_guests: number;
  allow_same_day: boolean;
  allow_walk_in: boolean;
  allow_guest_profiles: boolean;
  require_phone: boolean;
  confirm_on_create: boolean;
  notify_confirmation: boolean;
  notify_updates: boolean;
  notify_cancellation: boolean;
  notify_reminder: boolean;
  open_time: string;
  close_time: string;
  timezone: string;
}

const TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "calendar", label: "Calendar" },
  { id: "availability", label: "Availability" },
  { id: "active", label: "Active" },
  { id: "history", label: "History" },
  { id: "settings", label: "Settings" },
];

const TONE: Record<string, string> = {
  pending: "bg-amber-100 text-amber-950",
  confirmed: "bg-sky-100 text-sky-950",
  arrived: "bg-indigo-100 text-indigo-950",
  seated: "bg-emerald-100 text-emerald-950",
  completed: "bg-zinc-100 text-zinc-700",
  cancelled: "bg-rose-100 text-rose-950",
  no_show: "bg-orange-100 text-orange-950",
  rejected: "bg-stone-200 text-stone-700",
};

const ACTIVE = new Set(["pending", "confirmed", "arrived", "seated"]);

function clock(value: string): string {
  return new Date(value).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function dayKey(value: string): string {
  const date = new Date(value);
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
}

function localInput(date: Date): string {
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function ReservationsPage() {
  const { user, can } = useAuth();
  const { allows } = useTenant();
  const { stores } = useStores();
  const [params] = useSearchParams();
  const [storeId, setStoreId] = useState(params.get("store") ?? user?.store_id ?? "");
  const [tab, setTab] = useState<Tab>(params.get("table") ? "history" : "overview");
  const [rows, setRows] = useState<Reservation[]>([]);
  const [floor, setFloor] = useState<Floor | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [creating, setCreating] = useState(false);
  const [status, setStatus] = useState("");
  const [when, setWhen] = useState(localInput(new Date(Date.now() + 60 * 60 * 1000)));
  const [guests, setGuests] = useState("2");
  const [tableId, setTableId] = useState(params.get("table") ?? "");
  const [customerQuery, setCustomerQuery] = useState("");
  const [customerId, setCustomerId] = useState("");
  const [matches, setMatches] = useState<{ id: string; name: string; phone: string | null; code: string }[]>([]);
  const [newName, setNewName] = useState("");
  const [newPhone, setNewPhone] = useState("");
  const [requests, setRequests] = useState("");
  const [view, setView] = useState<"day" | "week" | "month">("day");
  const [history, setHistory] = useState<Activity[]>([]);
  const [historyLabel, setHistoryLabel] = useState("");
  const [range, setRange] = useState("24h");
  const [settings, setSettings] = useState<Settings | null>(null);
  const open = allows(["restaurant", "cafe"]);

  useEffect(() => {
    if (storeId === "" && stores.length > 0) setStoreId(stores.find((store) => !store.is_warehouse)?.id ?? stores[0]!.id);
  }, [stores, storeId]);

  const load = useCallback(async () => {
    if (!open || storeId === "") return;
    try {
      const [list, plan] = await Promise.all([
        apiGet<Reservation[]>(`/api/v1/reservations?store_id=${storeId}`),
        apiGet<Floor>(`/api/v1/dining/floor?store_id=${storeId}`),
      ]);
      setRows(list);
      setFloor(plan);
      setError(null);
    } catch (caught) {
      setError(message(caught, "Reservations could not be loaded."));
    }
  }, [open, storeId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const token = getAccessToken();
    if (!open || storeId === "" || token === null) return;
    return listenForTableEvents(
      storeId,
      token,
      (event) => {
        if (event.type === "RESERVATION_CHANGED") void load();
      },
      "pos",
    );
  }, [load, open, storeId]);

  const tables = useMemo(
    () => floor?.areas.flatMap((area) => area.tables.map((table) => ({ ...table, area: area.name }))) ?? [],
    [floor],
  );
  const shown = rows.filter((row) => (tab === "active" ? ACTIVE.has(row.status) : status === "" || row.status === status));

  async function run(action: () => Promise<void>, done: string) {
    setBusy(true);
    setError(null);
    try {
      await action();
      setNotice(done);
      await load();
    } catch (caught) {
      setError(message(caught, "That reservation could not be updated."));
    } finally {
      setBusy(false);
    }
  }

  async function searchCustomers() {
    if (customerQuery.trim().length < 2) return;
    try {
      setMatches(
        await apiGet(`/api/v1/reservations/customers?store_id=${storeId}&q=${encodeURIComponent(customerQuery.trim())}`),
      );
    } catch (caught) {
      setError(message(caught, "Customer search failed."));
    }
  }

  async function createReservation() {
    const body: Record<string, unknown> = {
      store_id: storeId,
      starts_at: new Date(when).toISOString(),
      guest_count: Number(guests) || 1,
      source: "portal",
      special_requests: requests.trim() || null,
      table_id: tableId || null,
    };
    if (customerId) body.customer_id = customerId;
    else body.customer = { name: newName.trim(), phone: newPhone.trim() || null };
    await run(async () => {
      await apiPost("/api/v1/reservations", body);
      setCreating(false);
      setNewName("");
      setNewPhone("");
      setRequests("");
    }, "Reservation saved.");
  }

  async function loadHistory(preset: string) {
    if (tableId === "") return;
    const now = new Date();
    const query = new URLSearchParams();
    if (preset === "today") {
      const start = new Date(now);
      start.setHours(0, 0, 0, 0);
      query.set("from", start.toISOString());
    } else if (preset === "yesterday") {
      const start = new Date(now);
      start.setDate(start.getDate() - 1);
      start.setHours(0, 0, 0, 0);
      const end = new Date(start);
      end.setDate(end.getDate() + 1);
      query.set("from", start.toISOString());
      query.set("to", end.toISOString());
    }
    const suffix = query.size ? `?${query}` : "";
    try {
      const body = await apiGet<{ table_label: string; events: Activity[] }>(
        `/api/v1/reservations/tables/${tableId}/history${suffix}`,
      );
      setHistory(body.events);
      setHistoryLabel(body.table_label);
      setError(null);
    } catch (caught) {
      setError(message(caught, "Table history could not be loaded."));
    }
  }

  useEffect(() => {
    if (tab === "history" && tableId) void loadHistory(range);
  }, [tab, tableId, range]);

  async function loadSettings() {
    try {
      setSettings(await apiGet<Settings>(`/api/v1/reservations/settings?store_id=${storeId}`));
    } catch (caught) {
      setError(message(caught, "Reservation settings could not be loaded."));
    }
  }

  useEffect(() => {
    if (tab === "settings" && storeId) void loadSettings();
  }, [tab, storeId]);

  if (!open) {
    return <p className="p-6 text-sm text-charcoal/70">Table reservations are available for restaurant and cafe businesses.</p>;
  }

  const anchor = new Date(when);
  const week = Array.from({ length: 7 }, (_, index) => {
    const date = new Date(anchor);
    date.setDate(anchor.getDate() - anchor.getDay() + index);
    return date;
  });

  return (
    <section className="space-y-4 p-4 md:p-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-charcoal text-white">
            <CalendarRange size={20} aria-hidden="true" />
          </span>
          <div>
            <h2 className="text-xl font-semibold">Table reservations</h2>
            <p className="text-sm text-charcoal/60">Book a table, seat the guest, and keep the table's history.</p>
          </div>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <SelectField label="Branch" value={storeId} options={storeOptions(stores)} onChange={setStoreId} />
          <PrimaryButton onClick={() => setCreating((openForm) => !openForm)}>New reservation</PrimaryButton>
        </div>
      </div>
      <ErrorNote message={error} />
      {notice ? <p className="text-sm text-emerald-800">{notice}</p> : null}
      <div className="flex gap-1 overflow-x-auto" role="tablist" aria-label="Reservation sections">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            className={`shrink-0 rounded-full px-3 py-1.5 text-sm ${tab === item.id ? "bg-charcoal text-white" : "text-charcoal/70"}`}
            onClick={() => setTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>

      {creating ? (
        <form
          className="grid gap-3 rounded-2xl border border-line bg-white p-4 md:grid-cols-2"
          onSubmit={(event) => {
            event.preventDefault();
            void createReservation();
          }}
        >
          <TextField label="Find customer" value={customerQuery} onChange={(event) => setCustomerQuery(event.target.value)} />
          <div className="flex items-end">
            <GhostButton type="button" onClick={() => void searchCustomers()}>
              Search
            </GhostButton>
          </div>
          {matches.length > 0 ? (
            <SelectField
              label="Existing customer"
              value={customerId}
              options={[{ value: "", label: "None" }, ...matches.map((item) => ({ value: item.id, label: `${item.name} · ${item.phone ?? item.code}` }))]}
              onChange={setCustomerId}
            />
          ) : null}
          <TextField label="New customer name" value={newName} onChange={(event) => setNewName(event.target.value)} />
          <TextField label="Phone" value={newPhone} onChange={(event) => setNewPhone(event.target.value)} />
          <TextField label="Date and time" type="datetime-local" value={when} onChange={(event) => setWhen(event.target.value)} required />
          <TextField label="Guests" type="number" min={1} value={guests} onChange={(event) => setGuests(event.target.value)} required />
          <SelectField
            label="Table"
            value={tableId}
            options={[{ value: "", label: "Assign later" }, ...tables.map((table) => ({ value: table.id, label: `${table.area} · ${table.label} (${table.seats})` }))]}
            onChange={setTableId}
          />
          <TextField label="Special requests" value={requests} onChange={(event) => setRequests(event.target.value)} />
          <div className="md:col-span-2">
            <PrimaryButton type="submit" disabled={busy || storeId === "" || (customerId === "" && newName.trim() === "")}>
              Save reservation
            </PrimaryButton>
          </div>
        </form>
      ) : null}

      {tab === "overview" || tab === "active" ? (
        <div className="space-y-3">
          {tab === "overview" ? (
            <SelectField
              label="Status"
              value={status}
              options={[
                { value: "", label: "All" },
                ...Object.keys(TONE).map((item) => ({ value: item, label: item.replace("_", " ") })),
              ]}
              onChange={setStatus}
            />
          ) : null}
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {shown.map((row) => (
              <article key={row.id} className="rounded-2xl border border-line bg-white p-4">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h3 className="font-semibold">{row.customer_name}</h3>
                    <p className="text-sm text-charcoal/60">
                      {clock(row.starts_at)} · {row.guest_count} guests · {row.table_label ?? "No table"}
                    </p>
                  </div>
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${TONE[row.status] ?? ""}`}>
                    {row.status.replace("_", " ")}
                  </span>
                </div>
                <p className="mt-2 text-sm text-charcoal/70">
                  {row.customer_phone ?? "No phone"}
                  {row.special_requests ? " · Request" : ""}
                  {row.notification_status ? ` · Notice ${row.notification_status}` : ""}
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {row.status === "pending" && can("reservations:confirm") ? (
                    <GhostButton disabled={busy} onClick={() => void run(() => apiPost(`/api/v1/reservations/${row.id}/confirm`, {}), "Confirmed.")}>
                      Confirm
                    </GhostButton>
                  ) : null}
                  {row.status === "confirmed" && can("reservations:seat") ? (
                    <GhostButton disabled={busy} onClick={() => void run(() => apiPost(`/api/v1/reservations/${row.id}/arrive`, {}), "Marked arrived.")}>
                      Arrived
                    </GhostButton>
                  ) : null}
                  {row.status === "arrived" && can("reservations:seat") ? (
                    <GhostButton disabled={busy} onClick={() => void run(() => apiPost(`/api/v1/reservations/${row.id}/seat`, {}), "Seated.")}>
                      Seat
                    </GhostButton>
                  ) : null}
                  {["pending", "confirmed", "arrived"].includes(row.status) && can("reservations:cancel") ? (
                    <GhostButton
                      disabled={busy}
                      onClick={() =>
                        void run(
                          () => apiPost(`/api/v1/reservations/${row.id}/cancel`, { reason: "customer_request", notified: false }),
                          "Cancelled.",
                        )
                      }
                    >
                      Cancel
                    </GhostButton>
                  ) : null}
                  {row.status === "confirmed" && can("reservations:mark_no_show") ? (
                    <GhostButton disabled={busy} onClick={() => void run(() => apiPost(`/api/v1/reservations/${row.id}/no-show`, {}), "Marked no-show.")}>
                      No-show
                    </GhostButton>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
          {shown.length === 0 ? <p className="text-sm text-charcoal/60">No reservations in this view.</p> : null}
        </div>
      ) : null}

      {tab === "calendar" ? (
        <div className="space-y-3">
          <div className="flex flex-wrap gap-2">
            {(["day", "week", "month"] as const).map((item) => (
              <GhostButton key={item} onClick={() => setView(item)}>
                {item}
              </GhostButton>
            ))}
            <TextField label="Focus" type="datetime-local" value={when} onChange={(event) => setWhen(event.target.value)} />
          </div>
          {view === "day" ? (
            <ul className="space-y-2">
              {rows
                .filter((row) => dayKey(row.starts_at) === dayKey(anchor.toISOString()))
                .map((row) => (
                  <li key={row.id} className="rounded-xl border border-line px-3 py-2 text-sm">
                    {clock(row.starts_at)} · {row.customer_name} · {row.table_label ?? "Unassigned"} · {row.status}
                  </li>
                ))}
            </ul>
          ) : null}
          {view === "week" ? (
            <div className="grid gap-2 md:grid-cols-7">
              {week.map((date) => (
                <div key={date.toISOString()} className="rounded-xl border border-line p-2">
                  <p className="text-xs font-semibold">{date.toLocaleDateString([], { weekday: "short", day: "numeric" })}</p>
                  {rows
                    .filter((row) => dayKey(row.starts_at) === dayKey(date.toISOString()))
                    .map((row) => (
                      <p key={row.id} className="mt-1 text-xs">
                        {clock(row.starts_at)} {row.customer_name}
                      </p>
                    ))}
                </div>
              ))}
            </div>
          ) : null}
          {view === "month" ? (
            <div className="grid grid-cols-7 gap-1 text-xs">
              {Array.from({ length: 35 }, (_, index) => {
                const date = new Date(anchor.getFullYear(), anchor.getMonth(), 1 + index - new Date(anchor.getFullYear(), anchor.getMonth(), 1).getDay());
                const count = rows.filter((row) => dayKey(row.starts_at) === dayKey(date.toISOString())).length;
                return (
                  <div key={date.toISOString()} className="rounded-lg border border-line p-2">
                    <span>{date.getDate()}</span>
                    {count > 0 ? <span className="mt-1 block font-medium">{count}</span> : null}
                  </div>
                );
              })}
            </div>
          ) : null}
        </div>
      ) : null}

      {tab === "availability" ? (
        <Availability storeId={storeId} when={when} guests={Number(guests) || 2} onWhen={setWhen} onGuests={setGuests} />
      ) : null}

      {tab === "history" ? (
        <div className="space-y-3">
          <div className="flex flex-wrap items-end gap-2">
            <SelectField
              label="Table"
              value={tableId}
              options={[{ value: "", label: "Choose" }, ...tables.map((table) => ({ value: table.id, label: `${table.area} · ${table.label}` }))]}
              onChange={setTableId}
            />
            <SelectField
              label="Range"
              value={range}
              options={[
                { value: "24h", label: "Previous 24 hours" },
                { value: "today", label: "Today" },
                { value: "yesterday", label: "Yesterday" },
              ]}
              onChange={setRange}
            />
          </div>
          <h3 className="font-semibold">{historyLabel ? `Table ${historyLabel}` : "Activity"}</h3>
          <ol className="space-y-2">
            {history.map((item) => (
              <li key={item.id} className="rounded-xl border border-line px-3 py-2 text-sm">
                <span className="font-medium">{clock(item.created_at)}</span> — {item.description}
              </li>
            ))}
          </ol>
          {history.length === 0 ? <p className="text-sm text-charcoal/60">No activity in this range.</p> : null}
        </div>
      ) : null}

      {tab === "settings" && settings ? (
        <form
          className="grid max-w-xl gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            void run(async () => {
              setSettings(await apiPut<Settings>(`/api/v1/reservations/settings?store_id=${storeId}`, settings));
            }, "Settings saved.");
          }}
        >
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={settings.enabled} onChange={(event) => setSettings({ ...settings, enabled: event.target.checked })} />
            Reservations enabled
          </label>
          <TextField label="Default duration (minutes)" type="number" value={String(settings.duration_minutes)} onChange={(event) => setSettings({ ...settings, duration_minutes: Number(event.target.value) })} />
          <TextField label="Cleaning buffer (minutes)" type="number" value={String(settings.buffer_minutes)} onChange={(event) => setSettings({ ...settings, buffer_minutes: Number(event.target.value) })} />
          <TextField label="Arrival grace (minutes)" type="number" value={String(settings.grace_minutes)} onChange={(event) => setSettings({ ...settings, grace_minutes: Number(event.target.value) })} />
          <TextField label="Opens" value={settings.open_time} onChange={(event) => setSettings({ ...settings, open_time: event.target.value })} />
          <TextField label="Closes" value={settings.close_time} onChange={(event) => setSettings({ ...settings, close_time: event.target.value })} />
          <TextField label="Timezone" value={settings.timezone} onChange={(event) => setSettings({ ...settings, timezone: event.target.value })} />
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={settings.allow_walk_in} onChange={(event) => setSettings({ ...settings, allow_walk_in: event.target.checked })} />
            Allow walk-ins
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={settings.allow_guest_profiles} onChange={(event) => setSettings({ ...settings, allow_guest_profiles: event.target.checked })} />
            Allow a name-only guest profile
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={settings.require_phone} onChange={(event) => setSettings({ ...settings, require_phone: event.target.checked })} />
            Require a phone number
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={settings.confirm_on_create} onChange={(event) => setSettings({ ...settings, confirm_on_create: event.target.checked })} />
            Confirm when a table is assigned
          </label>
          {can("reservations:manage_settings") ? <PrimaryButton type="submit" disabled={busy}>Save settings</PrimaryButton> : null}
        </form>
      ) : null}
    </section>
  );
}

function Availability({
  storeId,
  when,
  guests,
  onWhen,
  onGuests,
}: {
  storeId: string;
  when: string;
  guests: number;
  onWhen: (value: string) => void;
  onGuests: (value: string) => void;
}) {
  const [tables, setTables] = useState<{ table_id: string; label: string; area_name: string; seats: number; available: boolean; reason: string | null }[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function check() {
    try {
      const body = await apiGet<{ tables: typeof tables }>(
        `/api/v1/reservations/availability?store_id=${storeId}&starts_at=${encodeURIComponent(new Date(when).toISOString())}&guest_count=${guests}`,
      );
      setTables(body.tables);
      setError(null);
    } catch (caught) {
      setError(message(caught, "Availability could not be checked."));
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-2">
        <TextField label="When" type="datetime-local" value={when} onChange={(event) => onWhen(event.target.value)} />
        <TextField label="Guests" type="number" min={1} value={String(guests)} onChange={(event) => onGuests(event.target.value)} />
        <GhostButton onClick={() => void check()}>Check</GhostButton>
      </div>
      <ErrorNote message={error} />
      <div className="grid gap-2 md:grid-cols-3">
        {tables.map((table) => (
          <div key={table.table_id} className="rounded-xl border border-line px-3 py-2 text-sm">
            <p className="font-medium">
              {table.area_name} · {table.label}
            </p>
            <p className="text-charcoal/60">{table.available ? `Free · ${table.seats} seats` : table.reason}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
