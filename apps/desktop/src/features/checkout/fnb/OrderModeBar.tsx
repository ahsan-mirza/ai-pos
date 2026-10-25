import type { DiningArea } from "@ai-pos/shared-types";
import { Select } from "@ai-pos/ui";
import { Bike, ChevronDown, ChevronUp, Minus, Plus, Search, Soup, UtensilsCrossed } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { staffApi, type RegisterStaff } from "../../../lib/retailClient";
import type { RegisterCustomer } from "../../../lib/tauri";
import { searchCustomers } from "../wholesaleClient";
import { store } from "../catalog";
import { layoutFallback, TableSelectorGrid, type TableChoice } from "./TableSelectorGrid";
import {
  DELIVERY_ZONES,
  FALLBACK_TABLES,
  unpackAddress,
  type OrderMode,
  type TableSession,
  type TicketDetails,
  sessionHeading,
} from "./tableSessions";

const MODES: { id: OrderMode; label: string; icon: typeof UtensilsCrossed }[] = [
  { id: "dine_in", label: "Dine-in", icon: UtensilsCrossed },
  { id: "takeaway", label: "Takeaway", icon: Soup },
  { id: "delivery", label: "Delivery", icon: Bike },
];

const STATUS_LABEL: Record<string, string> = {
  PENDING: "In this round",
  SENT_TO_KDS: "Sent to kitchen",
  SERVED: "Served",
  VOIDED: "Voided",
};

const field =
  "h-11 w-full rounded-xl border border-zinc-300 bg-white px-3 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500/20 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100 dark:placeholder:text-zinc-400 dark:[color-scheme:dark]";
const labelClass = "block text-xs font-medium text-zinc-600 dark:text-zinc-300";

function venueLabel(name: string): string {
  return /^restur[ae]nt$/i.test(name.trim()) ? "Restaurant" : name;
}

function coversLabel(count: number): string {
  return `${count} ${count === 1 ? "Person" : "People"}`;
}

function orderCode(session: TableSession): string {
  if (session.order_mode === "takeaway" && session.table_number && session.table_number !== "Takeaway") {
    return session.table_number;
  }
  return session.id.replace(/-/g, "").slice(0, 4).toUpperCase();
}

function summaryDetail(
  session: TableSession,
  floors: { name: string; tables: { label: string }[] }[],
): string {
  if (session.order_mode === "dine_in") {
    const area =
      floors.find((floor) => floor.tables.some((table) => table.label === session.table_number))?.name ??
      venueLabel(store.name);
    const table = /^table\b/i.test(session.table_number) ? session.table_number : `Table ${session.table_number}`;
    return `${area} • ${table} (${coversLabel(session.guest_count)})`;
  }
  const kind = session.order_mode === "delivery" ? "Delivery" : "Takeaway";
  return `${kind} - Order #${orderCode(session)}`;
}

function cartSheetOpen(): boolean {
  if (window.matchMedia("(min-width: 1024px)").matches) return false;
  return document.getElementById("current-sale")?.classList.contains("cart-sheet") ?? false;
}

function areasOf(areas: DiningArea[]): { id: string; name: string; tables: TableChoice[] }[] {
  const live = areas
    .filter((area) => area.is_active)
    .map((area) => ({
      id: area.id,
      name: area.name,
      tables: area.tables
        .filter((table) => table.is_active)
        .map(
          (table): TableChoice => ({
            id: table.id,
            label: table.label,
            seats: table.seats,
            busy: table.order_id !== null,
            shape: table.shape,
            x: table.x,
            y: table.y,
            w: table.w,
            h: table.h,
            status: table.status,
            covers: table.covers,
            seatedAt: table.seated_at,
            openCents: table.open_cents,
            orderId: table.order_id,
          }),
        ),
    }))
    .filter((area) => area.tables.length > 0);
  if (live.length > 0) return live;
  return [
    {
      id: "floor",
      name: "Floor",
      tables: layoutFallback(FALLBACK_TABLES),
    },
  ];
}

function GuestCounter({ value, onChange }: { value: number; onChange: (next: number) => void }) {
  return (
    <div className="inline-flex items-center gap-1 rounded-full border border-zinc-200 bg-white p-1 dark:border-zinc-800 dark:bg-zinc-900" role="group" aria-label="Guest count">
      <button
        type="button"
        aria-label="Fewer guests"
        onClick={() => onChange(Math.max(1, value - 1))}
        className="inline-flex h-9 w-9 items-center justify-center rounded-full text-zinc-700 hover:bg-zinc-100 dark:text-zinc-200 dark:hover:bg-zinc-800"
      >
        <Minus size={14} aria-hidden="true" />
      </button>
      <span className="min-w-6 text-center text-sm font-semibold tabular-nums" aria-live="polite">
        {value}
      </span>
      <button
        type="button"
        aria-label="More guests"
        onClick={() => onChange(Math.min(20, value + 1))}
        className="inline-flex h-9 w-9 items-center justify-center rounded-full text-zinc-700 hover:bg-zinc-100 dark:text-zinc-200 dark:hover:bg-zinc-800"
      >
        <Plus size={14} aria-hidden="true" />
      </button>
      <span className="pr-2 text-xs font-medium text-zinc-500 dark:text-zinc-400">guests</span>
    </div>
  );
}

export function OrderModeBar({
  mode,
  session,
  areas,
  storeId,
  onMode,
  onSeat,
  onTicket,
}: {
  mode: OrderMode;
  session: TableSession | null;
  areas: DiningArea[];
  storeId: string;
  onMode: (mode: OrderMode) => void;
  onSeat: (tableNumber: string, guestCount: number, tableId: string | null, orderId: string | null) => void;
  onTicket: (details: TicketDetails) => void;
}) {
  const floors = useMemo(() => areasOf(areas), [areas]);
  const [floorId, setFloorId] = useState("all");
  const [guests, setGuests] = useState(2);
  const [pending, setPending] = useState<TableChoice | null>(null);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [tag, setTag] = useState("");
  const [pickup, setPickup] = useState("");
  const [address, setAddress] = useState("");
  const [zone, setZone] = useState("");
  const [driver, setDriver] = useState("");
  const [staff, setStaff] = useState<RegisterStaff[]>([]);
  const [matches, setMatches] = useState<RegisterCustomer[]>([]);
  const [searchOpen, setSearchOpen] = useState(false);
  const seated = session !== null && session.order_mode === mode;
  const [expanded, setExpanded] = useState(!seated);
  const listId = useId();
  const seatKey = seated && session ? `${session.id}:${session.table_number}:${mode}` : `open:${mode}`;
  const seatKeyRef = useRef(seatKey);
  const pendingRef = useRef(pending);
  pendingRef.current = pending;
  const floor = floors.find((item) => item.id === floorId) ?? null;
  const visibleTables = floorId === "all" ? floors.flatMap((item) => item.tables) : (floor?.tables ?? []);
  const occupiedCount = visibleTables.filter((table) => table.status !== "free").length;

  useEffect(() => {
    if (floorId !== "all" && !floors.some((item) => item.id === floorId)) setFloorId("all");
  }, [floors, floorId]);

  useEffect(() => {
    if (seatKeyRef.current === seatKey) return;
    seatKeyRef.current = seatKey;
    if (pendingRef.current) return;
    setExpanded(!seated);
  }, [seatKey, seated]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key !== "Escape" && event.key !== "F2") return;
      if (event.key === "Escape" && pending) {
        event.preventDefault();
        setPending(null);
        return;
      }
      if (document.querySelector(".modal-backdrop")) return;
      if (event.key === "Escape" && cartSheetOpen()) return;
      if (event.key === "Escape") {
        const target = event.target;
        if (
          (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement) &&
          target.value !== ""
        ) {
          return;
        }
      }
      event.preventDefault();
      if (event.key === "F2") event.stopImmediatePropagation();
      setExpanded((open) => !open);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pending]);

  const ticketKey =
    session && session.order_mode === mode
      ? [session.guest_name, session.phone, session.address, session.table_number, String(session.guest_count), session.order_mode].join("\u001e")
      : `none:${mode}`;

  useEffect(() => {
    if (ticketKey.startsWith("none:")) {
      setName("");
      setPhone("");
      setTag("");
      setPickup("");
      setAddress("");
      setZone("");
      setDriver("");
      return;
    }
    const [guestName, phoneNumber, packed, tableNumber, guestCount, orderMode] = ticketKey.split("\u001e");
    const meta = unpackAddress(packed ?? "");
    setName(guestName ?? "");
    setPhone(phoneNumber ?? "");
    setAddress(meta.address);
    setZone(meta.zone);
    setDriver(meta.driver);
    setPickup(meta.pickup);
    setTag(orderMode === "takeaway" && tableNumber !== "Takeaway" ? (tableNumber ?? "") : "");
    setGuests(Number(guestCount) || 2);
  }, [ticketKey]);

  useEffect(() => {
    if (mode !== "delivery") return;
    let cancelled = false;
    staffApi
      .list(storeId)
      .then((rows) => {
        if (!cancelled) setStaff(rows);
      })
      .catch(() => {
        if (!cancelled) setStaff([]);
      });
    return () => {
      cancelled = true;
    };
  }, [mode, storeId]);

  useEffect(() => {
    if (mode !== "delivery" || name.trim().length < 2) {
      setMatches([]);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      searchCustomers(name)
        .then((rows) => {
          if (!cancelled) setMatches(rows);
        })
        .catch(() => {
          if (!cancelled) setMatches([]);
        });
    }, 160);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [mode, name]);

  const chooseCustomer = (customer: RegisterCustomer) => {
    setName(customer.name);
    setPhone(customer.phone ?? "");
    setAddress(customer.address ?? "");
    setSearchOpen(false);
    setMatches([]);
  };

  const submitTicket = () => {
    onTicket({
      guestName: name.trim(),
      phone: phone.trim(),
      address: address.trim(),
      zone,
      driver,
      pickup,
      tag: tag.trim(),
    });
  };

  const zones = zone && !(DELIVERY_ZONES as readonly string[]).includes(zone) ? [zone, ...DELIVERY_ZONES] : [...DELIVERY_ZONES];
  const drivers = driver && !staff.some((member) => member.full_name === driver) ? [driver, ...staff.map((member) => member.full_name)] : staff.map((member) => member.full_name);

  return (
    <section className="rounded-2xl border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-900">
      <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Order type">
        {MODES.map((item) => {
          const Icon = item.icon;
          const active = mode === item.id;
          return (
            <button
              key={item.id}
              type="button"
              aria-pressed={active}
              onClick={() => onMode(item.id)}
              className={`inline-flex h-11 items-center gap-2 rounded-full px-4 text-sm font-semibold ${
                active ? "bg-primary-500 text-white" : "border border-zinc-200 text-zinc-700 dark:border-zinc-700 dark:text-zinc-200"
              }`}
            >
              <Icon size={16} aria-hidden="true" />
              {item.label}
            </button>
          );
        })}
        {!expanded && seated && session ? (
          <span className="rounded-full bg-zinc-100 px-3 py-1 text-sm font-medium text-zinc-800 dark:bg-zinc-800 dark:text-zinc-100">
            {summaryDetail(session, floors)}
          </span>
        ) : null}
        {expanded && session ? (
          <span className="ml-auto rounded-full bg-primary-500/10 px-3 py-1.5 text-sm font-semibold text-primary-700 dark:text-primary-300">
            {sessionHeading(session)}
          </span>
        ) : null}
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls="order-setup-panel"
          aria-keyshortcuts="Escape F2"
          aria-label={expanded ? "Collapse order setup" : "Expand order setup"}
          onClick={() => setExpanded((open) => !open)}
          className={`${expanded && session ? "" : "ml-auto "}inline-flex h-9 w-9 items-center justify-center rounded-full border border-zinc-200 text-zinc-600 hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800`}
        >
          {expanded ? <ChevronUp size={16} aria-hidden="true" /> : <ChevronDown size={16} aria-hidden="true" />}
        </button>
      </div>
      <div id="order-setup-panel" className={`order-setup-panel ${expanded ? "is-open" : ""}`}>
      <div className="order-setup-inner" inert={expanded ? undefined : true}>

      {session && session.items.length > 0 ? (
        <ul className="mt-3 flex flex-wrap gap-2" aria-label="Items on this order">
          {session.items
            .filter((item) => item.kitchen_status !== "VOIDED")
            .map((item) => (
              <li key={item.id} className="rounded-full bg-zinc-100 px-3 py-1 text-xs font-medium text-zinc-700 dark:bg-zinc-800 dark:text-zinc-200">
                {item.quantity}× {item.product_name}
                <span className="ml-1 text-zinc-500">{STATUS_LABEL[item.kitchen_status]}</span>
              </li>
            ))}
        </ul>
      ) : null}

      <div key={mode} className="context-swap mt-3">
        {mode === "dine_in" ? (
          <div className="space-y-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-orange-500">{venueLabel(store.name)}</p>
              <h2 className="text-lg font-semibold text-zinc-900 dark:text-white">Choose a table</h2>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap gap-1.5" role="group" aria-label="Floor">
                <button
                  type="button"
                  aria-pressed={floorId === "all"}
                  onClick={() => setFloorId("all")}
                  className={`h-9 rounded-full px-4 text-sm font-semibold ${
                    floorId === "all" ? "bg-primary-500 text-white" : "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-200"
                  }`}
                >
                  All Tables
                </button>
                {floors.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    aria-pressed={item.id === floorId}
                    onClick={() => setFloorId(item.id)}
                    className={`h-9 rounded-full px-4 text-sm font-semibold ${
                      item.id === floorId ? "bg-primary-500 text-white" : "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-200"
                    }`}
                  >
                    {item.name}
                  </button>
                ))}
              </div>
              <div className="flex flex-wrap gap-1.5" aria-label="Table summary">
                <span className="rounded-full bg-zinc-100 px-3 py-1.5 text-xs font-semibold text-zinc-700 dark:bg-zinc-800 dark:text-zinc-200">
                  Total {visibleTables.length}
                </span>
                <span className="rounded-full bg-amber-500/15 px-3 py-1.5 text-xs font-semibold text-amber-800 dark:text-amber-200">
                  Occupied {occupiedCount}
                </span>
                <span className="rounded-full bg-emerald-500/15 px-3 py-1.5 text-xs font-semibold text-emerald-800 dark:text-emerald-200">
                  Available {visibleTables.length - occupiedCount}
                </span>
              </div>
            </div>
            <TableSelectorGrid
              tables={visibleTables}
              selected={session?.order_mode === "dine_in" ? session.table_number : null}
              onSelect={(table) => {
                if (table.status === "free") {
                  setGuests(Math.min(Math.max(table.seats, 1), 2));
                  setPending(table);
                  return;
                }
                onSeat(table.label, table.covers || 1, table.id, table.orderId);
              }}
            />
            {pending ? (
              <div className="modal-backdrop" role="presentation" onClick={() => setPending(null)}>
                <div
                  role="dialog"
                  aria-modal="true"
                  aria-labelledby="seat-guests-title"
                  className="modal-card max-w-sm"
                  onClick={(event) => event.stopPropagation()}
                >
                  <h2 id="seat-guests-title" className="text-xl font-semibold">
                    Seat {pending.label}
                  </h2>
                  <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">How many guests? This table seats {pending.seats}.</p>
                  <div className="mt-4">
                    <GuestCounter value={guests} onChange={(next) => setGuests(Math.min(Math.max(pending.seats, 1), next))} />
                  </div>
                  <div className="mt-5 flex justify-end gap-2">
                    <button type="button" onClick={() => setPending(null)} className="h-11 rounded-full px-4 text-sm font-semibold text-zinc-600 dark:text-zinc-300">
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        const table = pending;
                        setPending(null);
                        onSeat(table.label, guests, table.id, table.orderId);
                      }}
                      className="h-11 rounded-full bg-primary-500 px-5 text-sm font-semibold text-white"
                    >
                      Open table
                    </button>
                  </div>
                </div>
              </div>
            ) : null}
          </div>
        ) : null}

        {mode === "takeaway" ? (
          <form
            className="grid items-end gap-2 sm:grid-cols-2 xl:grid-cols-[1fr_1fr_8rem_9rem_auto]"
            onSubmit={(event) => {
              event.preventDefault();
              submitTicket();
            }}
          >
            <label className={labelClass}>
              Customer name
              <input required value={name} onChange={(event) => setName(event.target.value)} autoComplete="name" className={`${field} mt-1`} />
            </label>
            <label className={labelClass}>
              Phone
              <input value={phone} onChange={(event) => setPhone(event.target.value)} inputMode="tel" autoComplete="tel" className={`${field} mt-1`} />
            </label>
            <label className={labelClass}>
              Order tag
              <input value={tag} onChange={(event) => setTag(event.target.value)} placeholder="Token" className={`${field} mt-1`} />
            </label>
            <label className={labelClass}>
              Pickup time
              <input type="time" value={pickup} onChange={(event) => setPickup(event.target.value)} className={`${field} mt-1`} />
            </label>
            <button type="submit" className="h-11 rounded-xl bg-emerald-600 px-4 text-sm font-semibold text-white hover:bg-emerald-500">
              {session?.order_mode === "takeaway" ? "Update" : "Start takeaway"}
            </button>
          </form>
        ) : null}

        {mode === "delivery" ? (
          <form
            className="grid gap-3 md:grid-cols-2"
            onSubmit={(event) => {
              event.preventDefault();
              if (zone === "") return;
              submitTicket();
            }}
          >
            <div className="relative">
              <label htmlFor="delivery-customer" className={labelClass}>
                Customer
                <span className="relative mt-1 block">
                  <Search aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 z-10 h-4 w-4 -translate-y-1/2 text-zinc-400" />
                  <input
                    id="delivery-customer"
                    required
                    type="search"
                    role="combobox"
                    aria-expanded={searchOpen && matches.length > 0}
                    aria-controls={listId}
                    aria-autocomplete="list"
                    value={name}
                    autoComplete="off"
                    placeholder="Search name or phone"
                    onChange={(event) => {
                      setName(event.target.value);
                      setSearchOpen(true);
                    }}
                    onFocus={() => setSearchOpen(true)}
                    className={`${field} !pl-9 [&::-webkit-search-cancel-button]:hidden`}
                  />
                </span>
              </label>
              {searchOpen && matches.length > 0 ? (
                <ul id={listId} role="listbox" className="absolute z-20 mt-1 max-h-48 w-full overflow-y-auto rounded-xl border border-zinc-200 bg-white py-1 shadow-lg dark:border-zinc-800 dark:bg-zinc-900">
                  {matches.map((customer) => (
                    <li key={customer.id} role="option">
                      <button
                        type="button"
                        onClick={() => chooseCustomer(customer)}
                        className="flex w-full flex-col px-3 py-2 text-left text-sm hover:bg-zinc-100 dark:hover:bg-zinc-800"
                      >
                        <span className="font-medium">{customer.name}</span>
                        <span className="text-xs text-zinc-500">{[customer.phone, customer.address].filter(Boolean).join(" · ")}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
            <label className={labelClass}>
              Phone
              <input required value={phone} onChange={(event) => setPhone(event.target.value)} inputMode="tel" autoComplete="tel" className={`${field} mt-1`} />
            </label>
            <label className="block text-xs font-medium text-zinc-500 dark:text-zinc-400 md:col-span-2">
              Address
              <input required value={address} onChange={(event) => setAddress(event.target.value)} autoComplete="street-address" className={`${field} mt-1`} />
            </label>
            <label className={labelClass}>
              Delivery zone
              <Select
                className="mt-1"
                aria-label="Zone"
                placeholder="Select zone"
                value={zone}
                onChange={setZone}
                options={zones.map((item) => ({ value: item, label: item }))}
              />
            </label>
            <label className={labelClass}>
              Driver
              <Select
                className="mt-1"
                aria-label="Driver"
                placeholder="Unassigned"
                value={driver}
                onChange={setDriver}
                options={[{ value: "", label: "Unassigned" }, ...drivers.map((item) => ({ value: item, label: item }))]}
              />
            </label>
            <div className="md:col-span-2 flex justify-end">
              <button type="submit" className="h-11 rounded-xl bg-primary-500 px-4 text-sm font-semibold text-white hover:bg-primary-600">
                {session?.order_mode === "delivery" ? "Update delivery" : "Start delivery"}
              </button>
            </div>
          </form>
        ) : null}
      </div>
      </div>
      </div>
    </section>
  );
}
