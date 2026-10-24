import type { GuestSuggestion } from "@ai-pos/shared-types";
import { TableGridNode } from "@ai-pos/ui";
import { Bell, Receipt, Sparkles } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import { ApiRequestError, apiPublicPost, apiTerminal } from "../../lib/api";
import { emitTableEvent, listenForTableEvents, type TableEvent } from "./live";

const STORAGE_KEY = "table.device";
const COURSES = ["Starters", "Mains", "Beverages", "Desserts"] as const;

interface TableDevice {
  token: string;
  store_id: string;
  store_name: string;
  register_name: string;
}

interface Activation {
  device_token: string;
  store_id: string;
  store_name: string;
  register_name: string;
}

interface FloorTable {
  id: string;
  label: string;
  status: string;
  open_cents: number;
  seats: number;
  covers: number;
  seated_at: string | null;
}

interface FloorArea {
  id: string;
  name: string;
  tables: FloorTable[];
}

interface Floor {
  areas: FloorArea[];
}

/** The restaurant tenant was saved as "resturent". Show the corrected name on this screen. */
function venueLabel(name: string): string {
  return /^restur[ae]nt$/i.test(name.trim()) ? "Restaurant" : name;
}

function minutesOpen(iso: string | null, now: number): number {
  return iso ? Math.max(0, Math.floor((now - new Date(iso).getTime()) / 60_000)) : 0;
}

interface ModifierOption {
  id: string;
  name: string;
  price_delta_cents: number;
  is_active: boolean;
}

interface ModifierGroup {
  id: string;
  name: string;
  min_select: number;
  max_select: number;
  options: ModifierOption[];
}

interface MenuItem {
  id: string;
  name: string;
  course: (typeof COURSES)[number];
  price_cents: number;
  currency: string;
  image_url: string | null;
  groups: ModifierGroup[];
}

interface OrderItem {
  id: string;
  product_id: string;
  product_name: string;
  quantity: number;
  unit_price_cents: number;
  note: string | null;
  sent_at: string | null;
  voided_at: string | null;
  kitchen_status: string | null;
  modifiers: { option?: string }[];
}

interface OpenOrder {
  id: string;
  customer_id: string | null;
  open_cents: number;
  revision: number;
  bill_requested_at: string | null;
  items: OrderItem[];
}

interface Session {
  status: string;
  table_id: string;
  table_label: string;
  customer_name: string | null;
  phone: string | null;
  loyalty_points: number;
  order: OpenOrder | null;
}

type BasketTab = "round" | "ordered";

interface DraftLine {
  key: string;
  product_id: string;
  name: string;
  quantity: number;
  note: string;
  unit_cents: number;
  modifiers: { group_id: string; option_id: string; group: string; option: string; price_delta_cents: number }[];
}

function loadDevice(): TableDevice | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as TableDevice) : null;
  } catch {
    return null;
  }
}

function price(cents: number, currency: string): string {
  return `${currency || "AED"} ${(cents / 100).toFixed(2)}`;
}

function sameModifiers(left: DraftLine["modifiers"], right: DraftLine["modifiers"]): boolean {
  return left.length === right.length && left.every((choice, index) => choice.option_id === right[index]?.option_id);
}

function lineCents(line: DraftLine): number {
  return line.unit_cents * line.quantity;
}

function guestChip(item: OrderItem): { label: string; className: string } {
  if (item.voided_at) return { label: "Voided", className: "bg-slate-800 text-slate-400" };
  if (item.kitchen_status === "bumped") return { label: "Served", className: "bg-emerald-400/15 text-emerald-200" };
  if (item.kitchen_status === "ready") return { label: "Ready", className: "bg-emerald-400/15 text-emerald-200" };
  if (item.kitchen_status === "preparing") return { label: "Preparing", className: "bg-amber-400/15 text-amber-200" };
  return { label: "In Kitchen", className: "bg-sky-400/15 text-sky-200" };
}

function patchSession(session: Session | null, event: TableEvent): Session | null {
  if (!session?.order || event.order_id !== session.order.id || !event.kitchen_status) return session;
  const ids = new Set(event.item_ids ?? []);
  return {
    ...session,
    order: {
      ...session.order,
      items: session.order.items.map((item) =>
        ids.has(item.id)
          ? { ...item, kitchen_status: event.kitchen_status ?? item.kitchen_status, sent_at: item.sent_at ?? event.updated_at ?? null }
          : item,
      ),
    },
  };
}

function errorText(caught: unknown, fallback: string): string {
  return caught instanceof Error && caught.message ? caught.message : fallback;
}

/** Handheld waiter and table-tablet app. Open it at /table on a phone or a tablet at the table. */
export function TableOrderApp() {
  const [device, setDevice] = useState<TableDevice | null>(loadDevice);
  const forget = useCallback(() => {
    window.localStorage.removeItem(STORAGE_KEY);
    setDevice(null);
  }, []);
  if (device === null) {
    return (
      <Activate
        onActivated={(next) => {
          window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
          setDevice(next);
        }}
      />
    );
  }
  return <Service device={device} onForget={forget} />;
}

function Shell({ children }: { children: ReactNode }) {
  return <div className="min-h-screen bg-zinc-950 text-zinc-100">{children}</div>;
}

function Activate({ onActivated }: { onActivated: (device: TableDevice) => void }) {
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await apiPublicPost<Activation>("/api/v1/terminals/activate", {
        activation_key: key.trim(),
        machine_name: "Table order",
      });
      onActivated({
        token: result.device_token,
        store_id: result.store_id,
        store_name: result.store_name,
        register_name: result.register_name,
      });
    } catch (caught) {
      setError(errorText(caught, "That activation key was not accepted."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Shell>
      <form onSubmit={(event) => void submit(event)} className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-4 px-6">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-orange-400">Table order</p>
        <h1 className="text-3xl font-semibold">Activate this tablet</h1>
        <p className="text-sm text-zinc-400">Use a one-time key from Administration, Registers. It works once.</p>
        <input
          autoFocus
          value={key}
          onChange={(event) => setKey(event.target.value.toUpperCase())}
          placeholder="ABCD-EFGH-JKLM"
          className="h-14 rounded-2xl border border-zinc-800 bg-zinc-900 px-4 font-mono text-lg tracking-widest"
        />
        {error ? <p className="text-sm text-red-300">{error}</p> : null}
        <button type="submit" disabled={busy || key.replace(/-/g, "").length < 8} className="h-14 rounded-2xl bg-orange-500 text-lg font-bold text-white disabled:opacity-40">
          {busy ? "Activating…" : "Activate"}
        </button>
      </form>
    </Shell>
  );
}

function Service({ device, onForget }: { device: TableDevice; onForget: () => void }) {
  const [areas, setAreas] = useState<FloorArea[]>([]);
  const [zoneId, setZoneId] = useState("all");
  const [seating, setSeating] = useState<FloorTable | null>(null);
  const [opening, setOpening] = useState(false);
  const [covers, setCovers] = useState(2);
  const [now, setNow] = useState(() => Date.now());
  const [menu, setMenu] = useState<MenuItem[]>([]);
  const [table, setTable] = useState<FloorTable | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [phone, setPhone] = useState("");
  const [course, setCourse] = useState<(typeof COURSES)[number]>("Mains");
  const [draft, setDraft] = useState<DraftLine[]>([]);
  const [suggestions, setSuggestions] = useState<GuestSuggestion[]>([]);
  const [picking, setPicking] = useState<MenuItem | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [basketOpen, setBasketOpen] = useState(false);
  const [basketTab, setBasketTab] = useState<BasketTab>("round");
  const tableRef = useRef(table);
  const sessionRef = useRef(session);
  tableRef.current = table;
  sessionRef.current = session;

  const loadFloor = useCallback(async () => {
    const floor = await apiTerminal<Floor>("GET", `/api/v1/dining/floor?store_id=${device.store_id}`, device.token);
    setAreas(
      floor.areas.map((area) => ({
        id: area.id,
        name: area.name,
        tables: area.tables.map((table) => ({
          ...table,
          seats: table.seats || 4,
          covers: table.covers || 0,
          seated_at: table.seated_at ?? null,
          open_cents: table.open_cents || 0,
        })),
      })),
    );
  }, [device.store_id, device.token]);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 30_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    void loadFloor().catch((caught) => setError(errorText(caught, "Could not load tables.")));
    void apiTerminal<{ items: MenuItem[] }>("GET", `/api/v1/fnb/menu?store_id=${device.store_id}`, device.token)
      .then((body) => setMenu(body.items))
      .catch((caught) => setError(errorText(caught, "Could not load the menu.")));
  }, [device.store_id, device.token, loadFloor]);

  const onCheck = (session?.order?.items ?? [])
    .filter((item) => item.voided_at === null)
    .map((item) => item.product_id)
    .sort()
    .join(",");
  useEffect(() => {
    if (table === null) {
      setSuggestions([]);
      return;
    }
    const params = new URLSearchParams({ store_id: device.store_id });
    if (session?.order?.customer_id) params.set("customer_id", session.order.customer_id);
    for (const id of onCheck ? onCheck.split(",") : []) params.append("product_id", id);
    let cancelled = false;
    void apiTerminal<{ suggestions: GuestSuggestion[] }>("GET", `/api/v1/orders/suggestions?${params.toString()}`, device.token)
      .then((body) => {
        if (!cancelled) setSuggestions(body.suggestions);
      })
      .catch(() => {
        if (!cancelled) setSuggestions([]);
      });
    return () => {
      cancelled = true;
    };
  }, [table, device.store_id, device.token, session?.order?.customer_id, onCheck]);

  const refreshSession = useCallback(
    async (tableId: string) => {
      try {
        setSession(await apiTerminal<Session>("GET", `/api/v1/fnb/tables/${tableId}/active-session`, device.token));
      } catch (caught) {
        if (caught instanceof ApiRequestError && caught.status === 404) setSession(null);
        else setError(errorText(caught, "Could not load this table."));
      }
    },
    [device.token],
  );

  useEffect(() => {
    return listenForTableEvents(device.store_id, device.token, (event: TableEvent) => {
      const open = tableRef.current;
      const watching = open !== null && (event.table_id === open.id || event.order_id === sessionRef.current?.order?.id);
      if (event.type === "ORDER_STATUS_CHANGED") {
        if (event.message) setNotice(event.message);
        if (watching) setSession((current) => patchSession(current, event));
      }
      if (event.type === "KDS_ITEM_READY" && event.message) setNotice(event.message);
      if (event.type === "TABLE_SESSION_CLOSED") {
        if (open && event.table_id === open.id) {
          setSession(null);
          setDraft([]);
          setTable(null);
          setNotice(`${event.table_label ?? "Table"} is free for the next guest.`);
        }
      }
      if (event.type === "table:alert-rejected" && event.message) {
        setError(event.message);
        setNotice(null);
      }
      if (event.type === "BILL_REQUESTED" && watching && open) void refreshSession(open.id);
      if (event.type === "TABLE_ITEMS_ADDED" || event.type === "TABLE_SESSION_CLOSED" || event.type === "ORDER_STATUS_CHANGED" || event.type === "KDS_ITEM_READY" || event.type === "BILL_REQUESTED") {
        void loadFloor();
        if (watching && open && event.type !== "BILL_REQUESTED") void refreshSession(open.id);
      }
    });
  }, [device.store_id, device.token, loadFloor, refreshSession]);

  const tables = useMemo(() => {
    const source = zoneId === "all" ? areas : areas.filter((area) => area.id === zoneId);
    return source.flatMap((area) => area.tables);
  }, [areas, zoneId]);
  const occupiedCount = tables.filter((item) => item.status !== "free").length;

  function chooseTable(item: FloorTable) {
    if (item.status === "free") {
      setCovers(Math.min(2, Math.max(1, item.seats || 4)));
      setPhone("");
      setError(null);
      setSeating(item);
      return;
    }
    void openTable(item);
  }

  async function confirmSeat() {
    if (seating === null) return;
    const digits = phone.replace(/\D/g, "");
    if (digits.length > 0 && digits.length < 8) {
      setError("Enter a full mobile number, or leave it blank for a walk-in.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const body = digits.length >= 8 ? { phone: phone.trim(), covers } : { covers };
      setSession(await apiTerminal<Session>("POST", `/api/v1/fnb/tables/${seating.id}/session/start`, device.token, body));
      setTable(seating);
      setDraft([]);
      setSeating(null);
    } catch (caught) {
      setError(errorText(caught, "Could not start this table."));
    } finally {
      setBusy(false);
    }
  }

  async function openTable(next: FloorTable) {
    setOpening(true);
    setTable(next);
    setError(null);
    setDraft([]);
    await refreshSession(next.id);
    setOpening(false);
  }

  async function begin(asGuest: boolean) {
    if (table === null) return;
    const digits = phone.replace(/\D/g, "");
    if (!asGuest && digits.length < 8) {
      setError("Enter a mobile number, or continue as a walk-in guest.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const body = asGuest ? { covers: 1 } : { phone: phone.trim(), covers: 1 };
      setSession(await apiTerminal<Session>("POST", `/api/v1/fnb/tables/${table.id}/session/start`, device.token, body));
    } catch (caught) {
      setError(errorText(caught, "Could not start this table."));
    } finally {
      setBusy(false);
    }
  }

  function offer(suggestion: GuestSuggestion) {
    const item = menu.find((dish) => dish.id === suggestion.product_id) ?? {
      id: suggestion.product_id,
      name: suggestion.name,
      course: "Mains" as const,
      price_cents: suggestion.price_cents,
      currency: suggestion.currency,
      image_url: null,
      groups: [],
    };
    const modifiers = suggestion.modifiers.map((choice) => ({
      group_id: choice.group_id,
      option_id: choice.option_id,
      group: choice.group ?? "",
      option: choice.option ?? "",
      price_delta_cents: choice.price_delta_cents,
    }));
    if (modifiers.length > 0) {
      addDish(item, modifiers);
      return;
    }
    if (item.groups.some((group) => group.min_select > 0)) {
      setPicking(item);
      return;
    }
    addDish(item, []);
  }

  function addDish(item: MenuItem, modifiers: DraftLine["modifiers"]) {
    setDraft((current) => {
      const unit = item.price_cents + modifiers.reduce((sum, choice) => sum + choice.price_delta_cents, 0);
      const match = current.find((line) => line.product_id === item.id && line.note === "" && sameModifiers(line.modifiers, modifiers));
      if (match) return current.map((line) => (line.key === match.key ? { ...line, quantity: line.quantity + 1 } : line));
      return [...current, { key: crypto.randomUUID(), product_id: item.id, name: item.name, quantity: 1, note: "", unit_cents: unit, modifiers }];
    });
    setPicking(null);
    setBasketTab("round");
  }

  function changeQty(key: string, delta: number) {
    setDraft((current) =>
      current.flatMap((line) => {
        if (line.key !== key) return [line];
        const quantity = line.quantity + delta;
        return quantity < 1 ? [] : [{ ...line, quantity }];
      }),
    );
  }

  async function sendRound() {
    if (table === null || draft.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const next = await apiTerminal<Session>("POST", `/api/v1/fnb/tables/${table.id}/orders/add-round`, device.token, {
        client_round_id: crypto.randomUUID(),
        items: draft.map((line) => ({
          product_id: line.product_id,
          quantity: line.quantity,
          note: line.note || null,
          modifiers: line.modifiers,
        })),
      });
      setSession(next);
      setDraft([]);
      setBasketTab("ordered");
      setNotice("Sent to the kitchen.");
    } catch (caught) {
      setError(errorText(caught, "Could not send this round."));
    } finally {
      setBusy(false);
    }
  }

  async function callWaiter() {
    if (table === null) return;
    setError(null);
    const sent = emitTableEvent(device.store_id, device.token, "table:call-waiter", {
      tableId: table.id,
      tableName: table.label,
    });
    if (sent) {
      setNotice(`Table ${table.label} is calling for a waiter.`);
      return;
    }
    try {
      const result = await apiTerminal<{ message: string }>("POST", `/api/v1/fnb/tables/${table.id}/call-waiter`, device.token);
      setNotice(result.message);
    } catch (caught) {
      setError(errorText(caught, "Could not call a waiter."));
    }
  }

  async function requestBill() {
    if (table === null || session?.order == null) return;
    setBusy(true);
    setError(null);
    const sent = emitTableEvent(device.store_id, device.token, "table:request-bill", {
      tableId: table.id,
      tableName: table.label,
      totalAmount: session.order.open_cents,
    });
    if (sent) {
      setNotice("Bill requested. A server will bring it over.");
      setBusy(false);
      return;
    }
    try {
      setSession(await apiTerminal<Session>("POST", `/api/v1/fnb/tables/${table.id}/request-bill`, device.token));
      setNotice("Bill requested. A server will bring it over.");
    } catch (caught) {
      setError(errorText(caught, "Could not request the bill."));
    } finally {
      setBusy(false);
    }
  }

  const visible = useMemo(() => menu.filter((item) => item.course === course), [course, menu]);
  const liveItems = session?.order?.items.filter((item) => item.sent_at && !item.voided_at) ?? [];
  const currency = menu.find((item) => item.currency)?.currency || "AED";
  const roundCents = draft.reduce((sum, line) => sum + lineCents(line), 0);
  const roundCount = draft.reduce((sum, line) => sum + line.quantity, 0);

  if (table === null) {
    return (
      <Shell>
        <header className="px-6 pt-5">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-orange-400">{venueLabel(device.store_name)}</p>
              <h1 className="text-2xl font-semibold">Choose a table</h1>
            </div>
            <button type="button" onClick={onForget} className="text-sm text-zinc-400">
              Sign out
            </button>
          </div>
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <div className="flex gap-1.5 overflow-x-auto" role="group" aria-label="Floor">
              <button
                type="button"
                aria-pressed={zoneId === "all"}
                onClick={() => setZoneId("all")}
                className={`h-9 shrink-0 rounded-full px-4 text-sm font-semibold ${zoneId === "all" ? "bg-orange-500 text-white" : "bg-slate-800 text-slate-200"}`}
              >
                All Tables
              </button>
              {areas.map((area) => (
                <button
                  key={area.id}
                  type="button"
                  aria-pressed={zoneId === area.id}
                  onClick={() => setZoneId(area.id)}
                  className={`h-9 shrink-0 rounded-full px-4 text-sm font-semibold ${zoneId === area.id ? "bg-orange-500 text-white" : "bg-slate-800 text-slate-200"}`}
                >
                  {area.name}
                </button>
              ))}
            </div>
            <div className="flex flex-wrap gap-1.5" aria-label="Table summary">
              <span className="rounded-full bg-slate-800 px-3 py-1.5 text-xs font-semibold text-slate-200">Total {tables.length}</span>
              <span className="rounded-full bg-amber-500/15 px-3 py-1.5 text-xs font-semibold text-amber-200">Occupied {occupiedCount}</span>
              <span className="rounded-full bg-emerald-500/15 px-3 py-1.5 text-xs font-semibold text-emerald-200">Available {tables.length - occupiedCount}</span>
            </div>
          </div>
        </header>
        {notice ? <p className="mx-6 mt-4 rounded-2xl bg-emerald-500/15 px-4 py-3 text-sm text-emerald-200">{notice}</p> : null}
        {error && seating === null ? <p className="mx-6 mt-3 text-sm text-red-300">{error}</p> : null}
        <div className="grid grid-cols-2 gap-4 p-6 md:grid-cols-3 lg:grid-cols-4">
          {tables.map((item) => (
            <TableGridNode
              key={item.id}
              label={item.label}
              seats={item.seats}
              status={item.status}
              minutes={item.status === "free" ? null : minutesOpen(item.seated_at, now)}
              total={item.status === "free" ? null : price(item.open_cents, currency)}
              onClick={() => chooseTable(item)}
            />
          ))}
        </div>
        {seating ? (
          <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-4 sm:items-center" role="presentation" onClick={() => setSeating(null)}>
            <div
              role="dialog"
              aria-modal="true"
              aria-labelledby="guest-count-title"
              className="w-full max-w-sm rounded-3xl bg-slate-900 p-5 text-white shadow-2xl"
              onClick={(event) => event.stopPropagation()}
            >
              <h2 id="guest-count-title" className="text-xl font-semibold">Seat {seating.label}</h2>
              <p className="mt-1 text-sm text-slate-400">How many guests? This table seats {seating.seats}.</p>
              <div className="mt-4 flex flex-wrap gap-2" role="group" aria-label="Guest count">
                {Array.from({ length: Math.min(Math.max(seating.seats, 1), 12) }, (_, index) => index + 1).map((count) => (
                  <button
                    key={count}
                    type="button"
                    aria-pressed={covers === count}
                    onClick={() => setCovers(count)}
                    className={`h-12 min-w-12 rounded-2xl px-3 text-base font-semibold tabular-nums ${covers === count ? "bg-orange-500 text-white" : "bg-slate-800 text-slate-100"}`}
                  >
                    {count}
                  </button>
                ))}
              </div>
              <label className="mt-4 block text-sm text-slate-300">
                Mobile number, optional
                <input
                  inputMode="tel"
                  value={phone}
                  onChange={(event) => setPhone(event.target.value)}
                  placeholder="Walk-in if left blank"
                  className="mt-1 h-12 w-full rounded-2xl border border-slate-700 bg-slate-950 px-3 text-base"
                />
              </label>
              {error ? <p className="mt-3 text-sm text-red-300">{error}</p> : null}
              <div className="mt-5 flex justify-end gap-2">
                <button type="button" onClick={() => setSeating(null)} className="h-11 rounded-full px-4 text-sm font-semibold text-slate-300">
                  Cancel
                </button>
                <button type="button" disabled={busy} onClick={() => void confirmSeat()} className="h-11 rounded-full bg-orange-500 px-5 text-sm font-semibold text-white disabled:opacity-40">
                  {busy ? "Opening…" : "Open table"}
                </button>
              </div>
            </div>
          </div>
        ) : null}
      </Shell>
    );
  }

  if (session === null) {
    if (opening) {
      return (
        <Shell>
          <p className="px-6 py-10 text-lg">Opening {table.label}…</p>
        </Shell>
      );
    }
    return (
      <Shell>
        <div className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-4 px-6">
          <button type="button" onClick={() => setTable(null)} className="self-start text-sm text-zinc-400">
            All tables
          </button>
          <h1 className="text-3xl font-semibold">Table {table.label}</h1>
          <p className="text-sm text-zinc-400">Ask for a mobile number to keep loyalty and dining history. Walk-ins can skip it.</p>
          <input
            inputMode="tel"
            value={phone}
            onChange={(event) => setPhone(event.target.value)}
            placeholder="055XXXXXXX"
            className="h-14 rounded-2xl border border-zinc-800 bg-zinc-900 px-4 text-2xl tracking-wide"
          />
          {error ? <p className="text-sm text-red-300">{error}</p> : null}
          <button type="button" disabled={busy} onClick={() => void begin(false)} className="h-14 rounded-2xl bg-orange-500 text-lg font-bold">
            Start table
          </button>
          <button type="button" disabled={busy} onClick={() => void begin(true)} className="h-12 rounded-2xl border border-zinc-700 text-sm">
            Continue as Walk-in Guest
          </button>
        </div>
      </Shell>
    );
  }

  const basket = (
    <OrderDrawer
      tab={basketTab}
      onTab={setBasketTab}
      draft={draft}
      ordered={liveItems}
      currency={currency}
      roundCents={roundCents}
      busy={busy}
      onQty={changeQty}
      onNote={(key, note) => setDraft((current) => current.map((line) => (line.key === key ? { ...line, note } : line)))}
      onSend={() => void sendRound()}
    />
  );

  return (
    <Shell>
      <div className="sticky top-0 z-10 border-b border-slate-800 bg-slate-900/90 backdrop-blur-md">
        <header className="flex items-center gap-3 px-4 py-3">
          <button type="button" onClick={() => setTable(null)} className="text-sm text-slate-400">
            Tables
          </button>
          <div className="min-w-0 flex-1 text-center">
            <p className="truncate font-semibold">Table {session.table_label}</p>
            <p className="truncate text-xs text-slate-400">
              {session.customer_name}
              {session.loyalty_points > 0 ? ` · ${session.loyalty_points} pts` : ""}
            </p>
          </div>
          <div className="flex shrink-0 gap-2">
            <button
              type="button"
              aria-label="Call Waiter"
              onClick={() => void callWaiter()}
              className="flex h-10 items-center gap-1.5 rounded-full border border-slate-700 px-3 text-xs font-semibold"
            >
              <Bell size={14} aria-hidden="true" /> <span className="hidden sm:inline">Call Waiter</span>
            </button>
            <button
              type="button"
              aria-label={session.order?.bill_requested_at ? "Bill requested" : "Request Bill"}
              disabled={busy || session.order === null || session.order.bill_requested_at !== null}
              onClick={() => void requestBill()}
              className="flex h-10 items-center gap-1.5 rounded-full bg-orange-500 px-3 text-xs font-semibold text-white disabled:opacity-40"
            >
              <Receipt size={14} aria-hidden="true" />
              <span className="hidden sm:inline">{session.order?.bill_requested_at ? "Bill requested" : "Request Bill"}</span>
            </button>
          </div>
        </header>
        {suggestions.some((item) => !draft.some((line) => line.product_id === item.product_id)) ? (
          <div className="flex gap-2 overflow-x-auto px-4 pb-3">
            {suggestions
              .filter((item) => !draft.some((line) => line.product_id === item.product_id))
              .map((item) => (
                <button
                  key={`${item.kind}-${item.product_id}`}
                  type="button"
                  onClick={() => offer(item)}
                  className="min-w-[11rem] max-w-[16rem] shrink-0 rounded-2xl bg-slate-800 px-3 py-2 text-left"
                >
                  <span className="flex items-center gap-1.5 truncate text-sm font-semibold">
                    <Sparkles size={13} aria-hidden="true" className="shrink-0 text-orange-400" />
                    <span className="truncate">{item.name}</span>
                  </span>
                  <span className="mt-0.5 block text-xs text-slate-400">{item.pitch}</span>
                </button>
              ))}
          </div>
        ) : null}
        <nav className="sticky top-0 z-10 flex gap-2 overflow-x-auto bg-slate-900/90 px-4 pb-3 backdrop-blur-md">
          {COURSES.map((name) => (
            <button
              key={name}
              type="button"
              onClick={() => setCourse(name)}
              className={`h-11 shrink-0 rounded-full px-4 text-sm font-semibold ${course === name ? "bg-orange-500 text-white" : "bg-slate-800 text-slate-200"}`}
            >
              {name}
            </button>
          ))}
        </nav>
      </div>
      {notice ? <p className="mx-4 mt-3 rounded-2xl bg-emerald-500/15 px-4 py-3 text-sm text-emerald-200">{notice}</p> : null}
      {error ? <p className="mx-4 mt-3 text-sm text-red-300">{error}</p> : null}
      <div className="grid gap-4 p-4 pb-28 lg:grid-cols-[1fr_22rem] lg:pb-4">
        <section>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {visible.map((item) => (
              <DishCard key={item.id} item={item} onAdd={() => (item.groups.length > 0 ? setPicking(item) : addDish(item, []))} />
            ))}
          </div>
          {visible.length === 0 ? <p className="py-10 text-center text-sm text-slate-500">Nothing in {course} yet.</p> : null}
        </section>
        <aside className="hidden lg:block">
          <div className="sticky top-28">{basket}</div>
        </aside>
      </div>
      <div className="fixed inset-x-0 bottom-0 z-20 border-t border-slate-800 bg-slate-950/95 p-3 backdrop-blur-md lg:hidden">
        <button
          type="button"
          onClick={() => {
            setBasketTab(draft.length > 0 ? "round" : "ordered");
            setBasketOpen(true);
          }}
          className="flex h-14 w-full items-center justify-between rounded-2xl bg-orange-500 px-4 font-bold text-white"
        >
          <span>
            {roundCount} {roundCount === 1 ? "item" : "items"} · {price(roundCents, currency)}
          </span>
          <span>View Basket</span>
        </button>
      </div>
      {basketOpen ? (
        <div className="fixed inset-0 z-30 flex items-end bg-black/60 lg:hidden" onClick={() => setBasketOpen(false)}>
          <div
            className="max-h-[85vh] w-full overflow-y-auto rounded-t-3xl bg-slate-950 p-4"
            onClick={(event) => event.stopPropagation()}
            role="dialog"
            aria-label="Your order"
          >
            <div className="mx-auto mb-3 h-1.5 w-12 rounded-full bg-slate-700" />
            {basket}
          </div>
        </div>
      ) : null}
      {picking ? (
        <ModifierSheet item={picking} onClose={() => setPicking(null)} onAdd={(modifiers) => addDish(picking, modifiers)} />
      ) : null}
    </Shell>
  );
}

function DishPlaceholder({ name }: { name: string }) {
  const tones = ["text-orange-300", "text-amber-200", "text-emerald-300", "text-sky-300"];
  const tone = tones[name.length % tones.length];
  return (
    <div className={`flex h-full w-full items-center justify-center bg-slate-800 ${tone}`} aria-hidden="true">
      <svg viewBox="0 0 80 80" className="h-16 w-16">
        <ellipse cx="40" cy="46" rx="26" ry="10" fill="currentColor" opacity="0.25" />
        <circle cx="40" cy="38" r="18" fill="none" stroke="currentColor" strokeWidth="3" />
        <circle cx="40" cy="38" r="8" fill="currentColor" opacity="0.7" />
        <path d="M18 22c6 8 6 16 0 24M62 22c-6 8-6 16 0 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
      </svg>
    </div>
  );
}

function DishCard({ item, onAdd }: { item: MenuItem; onAdd: () => void }) {
  return (
    <article className="flex flex-col overflow-hidden rounded-3xl border border-slate-800 bg-slate-900">
      <div className="relative aspect-[4/3] bg-slate-800">
        {item.image_url ? (
          <img src={item.image_url} alt="" className="h-full w-full object-cover" />
        ) : (
          <DishPlaceholder name={item.name} />
        )}
        {item.groups.length > 0 ? (
          <span className="absolute left-2 top-2 rounded-full bg-slate-950/80 px-2 py-1 text-[11px] font-semibold uppercase tracking-wide text-orange-200">
            Modifiers
          </span>
        ) : null}
      </div>
      <div className="flex flex-1 flex-col gap-3 p-3">
        <div>
          <h3 className="font-semibold leading-tight">{item.name}</h3>
          <p className="mt-1 text-sm font-semibold text-orange-300">{price(item.price_cents, item.currency)}</p>
        </div>
        <button type="button" onClick={onAdd} className="mt-auto h-11 rounded-2xl bg-orange-500 text-sm font-bold text-white">
          + Add
        </button>
      </div>
    </article>
  );
}

function OrderDrawer({
  tab,
  onTab,
  draft,
  ordered,
  currency,
  roundCents,
  busy,
  onQty,
  onNote,
  onSend,
}: {
  tab: BasketTab;
  onTab: (tab: BasketTab) => void;
  draft: DraftLine[];
  ordered: OrderItem[];
  currency: string;
  roundCents: number;
  busy: boolean;
  onQty: (key: string, delta: number) => void;
  onNote: (key: string, note: string) => void;
  onSend: () => void;
}) {
  return (
    <div className="rounded-3xl border border-slate-800 bg-slate-900 p-4">
      <div className="grid grid-cols-2 gap-1 rounded-full bg-slate-950 p-1">
        {(
          [
            ["round", "This Round"],
            ["ordered", "Already Ordered"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => onTab(id)}
            className={`h-10 rounded-full text-sm font-semibold ${tab === id ? "bg-orange-500 text-white" : "text-slate-300"}`}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "round" ? (
        <div className="mt-4">
          {draft.length === 0 ? <p className="text-sm text-slate-500">Tap + Add on a dish. This round has not been sent yet.</p> : null}
          <ul className="space-y-3">
            {draft.map((line) => (
              <li key={line.key} className="rounded-2xl bg-slate-950 p-3">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-semibold">{line.name}</p>
                    {line.modifiers.length > 0 ? (
                      <p className="text-xs text-slate-400">{line.modifiers.map((choice) => choice.option).join(", ")}</p>
                    ) : null}
                  </div>
                  <p className="text-sm font-semibold tabular-nums">{price(lineCents(line), currency)}</p>
                </div>
                <div className="mt-2 flex items-center gap-2">
                  <button type="button" aria-label={`Fewer ${line.name}`} onClick={() => onQty(line.key, -1)} className="h-9 w-9 rounded-full bg-slate-800 text-lg">
                    −
                  </button>
                  <span className="w-6 text-center font-semibold tabular-nums">{line.quantity}</span>
                  <button type="button" aria-label={`More ${line.name}`} onClick={() => onQty(line.key, 1)} className="h-9 w-9 rounded-full bg-slate-800 text-lg">
                    +
                  </button>
                </div>
                <input
                  value={line.note}
                  onChange={(event) => onNote(line.key, event.target.value)}
                  placeholder="Note for the kitchen"
                  className="mt-2 h-10 w-full rounded-xl border border-slate-800 bg-slate-900 px-3 text-sm"
                />
              </li>
            ))}
          </ul>
          <div className="mt-4 flex items-center justify-between text-sm">
            <span className="text-slate-400">Round total</span>
            <span className="font-semibold tabular-nums">{price(roundCents, currency)}</span>
          </div>
          <button type="button" disabled={busy || draft.length === 0} onClick={onSend} className="mt-3 h-14 w-full rounded-2xl bg-orange-500 font-bold text-white disabled:opacity-40">
            Send to Kitchen
          </button>
        </div>
      ) : (
        <ul className="mt-4 space-y-3">
          {ordered.length === 0 ? <li className="text-sm text-slate-500">Nothing has been sent yet.</li> : null}
          {ordered.map((item) => {
            const chip = guestChip(item);
            return (
              <li key={item.id} className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-medium">
                    {item.quantity}× {item.product_name}
                  </p>
                  {item.modifiers.length > 0 ? (
                    <p className="text-xs text-slate-400">{item.modifiers.map((choice) => choice.option).filter(Boolean).join(", ")}</p>
                  ) : null}
                  {item.note ? <p className="text-xs italic text-slate-400">{item.note}</p> : null}
                </div>
                <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ${chip.className}`}>{chip.label}</span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function ModifierSheet({
  item,
  onClose,
  onAdd,
}: {
  item: MenuItem;
  onClose: () => void;
  onAdd: (modifiers: DraftLine["modifiers"]) => void;
}) {
  const [chosen, setChosen] = useState<Record<string, string>>({});
  const ready = item.groups.every((group) => group.min_select === 0 || chosen[group.id]);
  return (
    <div className="fixed inset-0 z-20 flex items-end bg-black/60 p-4 sm:items-center sm:justify-center">
      <div className="w-full max-w-md rounded-3xl bg-zinc-900 p-5">
        <h2 className="text-xl font-semibold">{item.name}</h2>
        {item.groups.map((group) => (
          <div key={group.id} className="mt-4">
            <p className="text-sm text-zinc-400">{group.name}</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {group.options.filter((option) => option.is_active).map((option) => (
                <button
                  key={option.id}
                  type="button"
                  onClick={() => setChosen((current) => ({ ...current, [group.id]: option.id }))}
                  className={`h-10 rounded-full px-3 text-sm ${chosen[group.id] === option.id ? "bg-orange-500" : "bg-zinc-800"}`}
                >
                  {option.name}
                  {option.price_delta_cents > 0 ? ` +${price(option.price_delta_cents, item.currency)}` : ""}
                </button>
              ))}
            </div>
          </div>
        ))}
        <div className="mt-5 flex gap-2">
          <button type="button" onClick={onClose} className="h-12 flex-1 rounded-2xl border border-zinc-700">
            Cancel
          </button>
          <button
            type="button"
            disabled={!ready}
            onClick={() =>
              onAdd(
                item.groups.flatMap((group) => {
                  const option = group.options.find((candidate) => candidate.id === chosen[group.id]);
                  return option
                    ? [{ group_id: group.id, option_id: option.id, group: group.name, option: option.name, price_delta_cents: option.price_delta_cents }]
                    : [];
                }),
              )
            }
            className="h-12 flex-1 rounded-2xl bg-orange-500 font-bold disabled:opacity-40"
          >
            Add
          </button>
        </div>
      </div>
    </div>
  );
}
