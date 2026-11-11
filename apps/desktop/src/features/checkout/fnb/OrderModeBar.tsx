import type { DeliveryChannel, DiningArea } from "@ai-pos/shared-types";
import { FloorBoard, Select, useLocale } from "@ai-pos/ui";
import { ArrowLeft, Bike, ChevronDown, ChevronUp, Minus, Plus, Search, Soup, UtensilsCrossed } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { staffApi, type RegisterStaff } from "../../../lib/retailClient";
import { channelsApi } from "../../orders/ordersClient";
import type { RegisterCustomer } from "../../../lib/tauri";
import type { CashierSession } from "../../auth/session";
import { createCustomer, searchCustomers } from "../wholesaleClient";
import { store } from "../catalog";
import { FloorTableCard } from "../../../components/FloorTableCard";
import { useBusinessCurrency } from "../currency";
import { layoutFallback, type TableChoice } from "./TableSelectorGrid";
import {
  FALLBACK_TABLES,
  unpackAddress,
  type OrderMode,
  type TableSession,
  type TicketDetails,
} from "./tableSessions";
import { changeTypeGate, sectionChoices, serviceLabel } from "./orderTypeNav";

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

function phoneDigits(value: string): string {
  return value.replace(/\D/g, "");
}

function uniqueCustomers(rows: RegisterCustomer[]): RegisterCustomer[] {
  const seen = new Set<string>();
  return rows.filter((row) => {
    if (seen.has(row.id)) return false;
    seen.add(row.id);
    return true;
  });
}

/** A phone match wins, including one unique partial number. A name matches only when no phone was typed. */
function exactCustomer(rows: RegisterCustomer[], guestName: string, guestPhone: string): RegisterCustomer | null {
  const unique = uniqueCustomers(rows);
  const typedPhone = phoneDigits(guestPhone);
  if (typedPhone.length >= 6) {
    const exact = unique.filter((row) => phoneDigits(row.phone ?? "") === typedPhone);
    if (exact.length === 1) return exact[0] ?? null;
    const partial = unique.filter((row) => phoneDigits(row.phone ?? "").includes(typedPhone));
    return partial.length === 1 ? (partial[0] ?? null) : null;
  }
  const named = guestName.trim().toLowerCase();
  if (!named) return null;
  const byName = unique.filter(
    (row) => row.name.trim().toLowerCase() === named || (row.company_name ?? "").trim().toLowerCase() === named,
  );
  return byName.length === 1 ? (byName[0] ?? null) : null;
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
  if (window.matchMedia("(min-width: 1280px)").matches) return false;
  return document.getElementById("current-sale")?.classList.contains("cart-sheet") ?? false;
}

function areasOf(areas: DiningArea[]): { id: string; name: string; tables: TableChoice[] }[] {
  const live = areas
    .filter((area) => area.is_active)
    .map((area) => ({
      id: area.id,
      name: area.name,
      tables: area.tables.map(
          (table): TableChoice => ({
            key: table.id,
            id: table.id,
            areaId: area.id,
            label: table.label,
            seats: table.seats,
            busy: table.order_id !== null,
            shape: table.shape,
            active: table.is_active,
            x: table.x,
            y: table.y,
            w: table.w,
            h: table.h,
            status: table.status,
            covers: table.covers,
            seatedAt: table.seated_at,
            openCents: table.open_cents,
            orderId: table.order_id,
            orderNumber: table.order_number,
            guestName: table.guest_name ?? null,
            kitchen: table.kitchen ?? "none",
            payment: table.payment ?? "none",
            orderProgress: table.order_progress ?? "none",
            search: [table.label, table.order_number ? `#${table.order_number}` : "", table.guest_name ?? ""].join(" "),
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
  pendingCount,
  cashier,
  onMode,
  onSeat,
  onTicket,
  onCancelOrder,
  onCustomer,
}: {
  mode: OrderMode;
  session: TableSession | null;
  areas: DiningArea[];
  storeId: string;
  pendingCount: number;
  cashier: CashierSession;
  onMode: (mode: OrderMode) => void;
  onSeat: (tableNumber: string, guestCount: number, tableId: string | null, orderId: string | null) => void;
  onTicket: (details: TicketDetails) => void;
  onCancelOrder?: () => void;
  onCustomer?: (customer: RegisterCustomer) => void;
}) {
  const { t } = useLocale();
  const floors = useMemo(() => areasOf(areas), [areas]);
  const sections = useMemo(() => sectionChoices(areas), [areas]);
  const currency = useBusinessCurrency();
  const [choosing, setChoosing] = useState(session === null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [blockedOpen, setBlockedOpen] = useState(false);
  const [channels, setChannels] = useState<DeliveryChannel[]>([]);
  const picking = useRef(false);
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
  const [searched, setSearched] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchSource, setSearchSource] = useState<"name" | "phone">("name");
  const [picked, setPicked] = useState<RegisterCustomer | null>(null);
  const [savingGuest, setSavingGuest] = useState(false);
  const [guestError, setGuestError] = useState<string | null>(null);
  const guestBox = useRef<HTMLDivElement>(null);
  const seated = session !== null && session.order_mode === mode;
  const [expanded, setExpanded] = useState(!seated);
  const listId = useId();
  const seatKey = seated && session ? `${session.id}:${session.table_number}:${mode}` : `open:${mode}`;
  const seatKeyRef = useRef(seatKey);
  const pendingRef = useRef(pending);
  pendingRef.current = pending;
  const floorTables = floors.flatMap((item) => item.tables);
  const keptLines = session?.items.filter((item) => item.kitchen_status !== "VOIDED").length ?? 0;
  const kitchen =
    session?.items.some((item) => item.kitchen_status === "SENT_TO_KDS" || item.kitchen_status === "SERVED") ?? false;

  useEffect(() => {
    if (picking.current) return;
    if (session && session.order_mode === mode) setChoosing(false);
  }, [session, mode]);

  const requestChange = () => {
    const gate = changeTypeGate(pendingCount, keptLines, kitchen);
    if (gate === "blocked") {
      setBlockedOpen(true);
      return;
    }
    if (gate === "confirm") {
      setConfirmOpen(true);
      return;
    }
    picking.current = true;
    setChoosing(true);
  };

  const pickMode = (next: OrderMode) => {
    picking.current = false;
    onMode(next);
    setChoosing(false);
  };

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
      setPicked(null);
      setGuestError(null);
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
    channelsApi
      .list()
      .then((rows) => {
        if (!cancelled) setChannels(rows.filter((row) => row.is_active && row.store_id === storeId));
      })
      .catch(() => {
        if (!cancelled) setChannels([]);
      });
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

  const lookupQuery = mode === "delivery" || mode === "takeaway" ? (searchSource === "phone" ? phone : name) : "";

  useEffect(() => {
    const query = lookupQuery.trim();
    if ((mode !== "delivery" && mode !== "takeaway") || query.length < 2) {
      setMatches([]);
      setSearched("");
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      searchCustomers(query)
        .then((rows) => {
          if (!cancelled) {
            setMatches(rows);
            setSearched(query);
          }
        })
        .catch(() => {
          if (!cancelled) {
            setMatches([]);
            setSearched(query);
          }
        });
    }, 160);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [mode, lookupQuery]);

  useEffect(() => {
    const onPointer = (event: PointerEvent) => {
      if (guestBox.current && !guestBox.current.contains(event.target as Node)) setSearchOpen(false);
    };
    window.addEventListener("pointerdown", onPointer);
    return () => window.removeEventListener("pointerdown", onPointer);
  }, []);

  const chooseCustomer = (customer: RegisterCustomer) => {
    setName(customer.name);
    setPhone(customer.phone ?? "");
    setAddress(customer.address ?? "");
    setPicked(customer);
    setGuestError(null);
    setSearchOpen(false);
    setMatches([]);
    setSearched("");
  };

  const resolveGuest = async (): Promise<RegisterCustomer | null> => {
    const guestName = name.trim();
    const guestPhone = phone.trim();
    let customer =
      picked &&
      picked.name.trim().toLowerCase() === guestName.toLowerCase() &&
      (phoneDigits(guestPhone).length < 6 || phoneDigits(picked.phone ?? "") === phoneDigits(guestPhone))
        ? picked
        : null;
    if (!customer) {
      const queries = [...new Set([guestName, guestPhone].filter((value) => value.length >= 2))];
      const groups = await Promise.all(queries.map((query) => searchCustomers(query).catch(() => [] as RegisterCustomer[])));
      const found = uniqueCustomers(groups.flat());
      customer = exactCustomer(found, guestName, guestPhone);
      if (!customer && found.length > 0) {
        setMatches(found);
        setSearched(guestPhone.length >= 2 ? guestPhone : guestName);
        setSearchSource(guestPhone.length >= 2 ? "phone" : "name");
        setSearchOpen(true);
        setGuestError("More than one guest matches. Pick one from the list.");
        return null;
      }
    }
    if (!customer) {
      customer = await createCustomer(cashier, {
        name: guestName || `Walk-in ${guestPhone}`,
        phone: guestPhone || null,
        email: null,
        customer_type: "RETAIL",
        company_name: null,
        trn_vat_number: null,
        price_tier: "RETAIL",
        credit_limit_cents: 0,
        payment_terms: "DUE_ON_RECEIPT",
      });
    }
    setName(customer.name);
    setPhone(customer.phone ?? guestPhone);
    setPicked(customer);
    onCustomer?.(customer);
    return customer;
  };

  const startService = async () => {
    if (savingGuest) return;
    if (mode === "delivery" && channels.length > 0 && zone === "") return;
    setSavingGuest(true);
    setGuestError(null);
    try {
      const customer = await resolveGuest();
      if (!customer) return;
      onTicket({
        guestName: customer.name,
        phone: customer.phone ?? phone.trim(),
        address: address.trim(),
        zone,
        driver,
        pickup,
        tag: tag.trim(),
      });
    } catch (caught) {
      setGuestError(caught instanceof Error ? caught.message : "Could not save this guest.");
    } finally {
      setSavingGuest(false);
    }
  };

  const guestQuery = lookupQuery.trim();
  const guestResolved = (mode === "takeaway" || mode === "delivery") && guestQuery.length >= 2 && searched === guestQuery;
  const guestListOpen = guestResolved && searchOpen;
  const addingNew = guestResolved && matches.length === 0 && picked === null;
  const zoneNames = channels.map((item) => item.name);
  const zones = zone && !zoneNames.includes(zone) ? [zone, ...zoneNames] : zoneNames;
  const drivers = driver && !staff.some((member) => member.full_name === driver) ? [driver, ...staff.map((member) => member.full_name)] : staff.map((member) => member.full_name);

  return (
    <section className="min-w-0 rounded-2xl border border-zinc-200 bg-white p-2 dark:border-zinc-800 dark:bg-zinc-900">
      {choosing ? (
        <div
          className="grid grid-cols-3 gap-3 max-[480px]:flex max-[480px]:snap-x max-[480px]:overflow-x-auto"
          role="group"
          aria-label="Order type"
        >
          {MODES.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => pickMode(item.id)}
                className="flex min-h-24 min-w-0 flex-col items-start justify-center gap-2 rounded-2xl border border-zinc-200 bg-zinc-50 px-5 py-4 text-left transition-colors hover:border-primary-500 hover:bg-primary-500/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 max-[480px]:min-w-40 max-[480px]:shrink-0 max-[480px]:snap-start dark:border-zinc-700 dark:bg-zinc-950 dark:hover:border-primary-500"
              >
                <Icon size={28} aria-hidden="true" className="text-primary-500" />
                <span className="text-lg font-semibold text-zinc-950 dark:text-white">{item.label}</span>
              </button>
            );
          })}
        </div>
      ) : (
      <div className="flex h-11 min-w-0 flex-nowrap items-center gap-2 overflow-hidden border-b border-zinc-100 dark:border-zinc-800">
        <button
          type="button"
          onClick={requestChange}
          className="inline-flex h-10 shrink-0 items-center gap-1.5 rounded-xl border border-zinc-300 bg-transparent px-3 text-sm font-semibold text-zinc-800 hover:bg-zinc-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:border-zinc-600 dark:text-zinc-100 dark:hover:bg-zinc-800"
        >
          <ArrowLeft size={16} aria-hidden="true" className="rtl:scale-x-[-1]" />
          {t("Change Order Type")}
        </button>
        <span className="inline-flex h-10 shrink-0 items-center rounded-full bg-zinc-950 px-4 text-sm font-semibold text-white dark:border dark:border-zinc-600 dark:bg-zinc-800">
          {t(serviceLabel(mode))}
        </span>
        {!expanded && seated && session ? (
          <span className="min-w-0 flex-1 truncate text-sm font-medium text-zinc-600 dark:text-zinc-300">
            {summaryDetail(session, floors)}
          </span>
        ) : (
          <span className="min-w-0 flex-1" />
        )}
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls="order-setup-panel"
          aria-keyshortcuts="Escape F2"
          aria-label={t(expanded ? "Collapse order setup" : "Expand order setup")}
          onClick={() => setExpanded((open) => !open)}
          className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-zinc-200 text-zinc-600 hover:bg-zinc-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
        >
          {expanded ? <ChevronUp size={16} aria-hidden="true" /> : <ChevronDown size={16} aria-hidden="true" />}
        </button>
      </div>
      )}
      <div id="order-setup-panel" className={choosing ? "hidden" : `order-setup-panel ${expanded ? "is-open" : ""}`}>
      <div className="order-setup-inner" inert={expanded ? undefined : true}>
      {mode === "dine_in" && sections.length === 0 ? (
        <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">{t("No sections are configured for this store.")}</p>
      ) : null}
      {mode === "takeaway" ? (
        <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
          {t("Search by name or phone. A new guest is added if nobody matches.")}
        </p>
      ) : null}
      {mode === "delivery" ? (
        channels.length === 0 ? (
          <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">{t("No delivery zones are configured.")}</p>
        ) : (
          <div className="mt-2 flex min-w-0 gap-2 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden" role="group" aria-label={t("Delivery zones")}>
            {channels.map((item) => (
              <button
                key={item.id}
                type="button"
                aria-pressed={zone === item.name}
                onClick={() => setZone(item.name)}
                className={`inline-flex h-10 shrink-0 items-center rounded-full px-3 text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 ${zone === item.name ? "bg-primary-500 text-white" : "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-200"}`}
              >
                {item.name}
              </button>
            ))}
          </div>
        )
      ) : null}

      <div key={mode} className="context-swap mt-2">
        {mode === "dine_in" ? (
          <div className="space-y-2">
            <FloorBoard
              sections={sections}
              items={floorTables}
              showSections
              renderItem={(table) => (
                <FloorTableCard
                  tableId={table.id}
                  label={table.label}
                  seats={table.seats}
                  shape={table.shape}
                  active={table.active}
                  covers={table.covers}
                  seatedAt={table.seatedAt}
                  openCents={table.openCents}
                  currency={currency}
                  status={table.status}
                  kitchen={table.kitchen}
                  payment={table.payment}
                  orderProgress={table.orderProgress}
                  orderNumber={table.orderNumber}
                  guestName={table.guestName}
                  selected={session?.order_mode === "dine_in" && session.table_number === table.label}
                  onClick={() => {
                    if (!table.active) return;
                    if (table.status === "free") {
                      setGuests(Math.min(Math.max(table.seats, 1), 2));
                      setPending(table);
                      return;
                    }
                    onSeat(table.label, table.covers || 1, table.id, table.orderId);
                  }}
                />
              )}
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
              void startService();
            }}
          >
            <div ref={guestBox} className="relative sm:col-span-2 xl:col-span-2">
              <div className="grid gap-2 sm:grid-cols-2">
                <label className={labelClass}>
                  Customer name
                  <input
                    required
                    value={name}
                    role="combobox"
                    aria-expanded={guestListOpen && searchSource === "name"}
                    aria-controls={listId}
                    aria-autocomplete="list"
                    autoComplete="off"
                    placeholder="Search name"
                    onChange={(event) => {
                      setName(event.target.value);
                      setSearchSource("name");
                      setSearchOpen(true);
                      setPicked(null);
                    }}
                    onFocus={() => {
                      setSearchSource("name");
                      setSearchOpen(true);
                    }}
                    className={`${field} mt-1`}
                  />
                </label>
                <label className={labelClass}>
                  Phone
                  <input
                    value={phone}
                    role="combobox"
                    aria-expanded={guestListOpen && searchSource === "phone"}
                    aria-controls={listId}
                    aria-autocomplete="list"
                    inputMode="tel"
                    autoComplete="off"
                    placeholder="Search phone"
                    onChange={(event) => {
                      setPhone(event.target.value);
                      setSearchSource("phone");
                      setSearchOpen(true);
                      setPicked(null);
                    }}
                    onFocus={() => {
                      setSearchSource("phone");
                      setSearchOpen(true);
                    }}
                    className={`${field} mt-1`}
                  />
                </label>
              </div>
              {guestListOpen ? (
                <ul
                  id={listId}
                  role="listbox"
                  className="absolute z-20 mt-1 max-h-48 w-full overflow-y-auto rounded-xl border border-zinc-200 bg-white py-1 shadow-lg dark:border-zinc-800 dark:bg-zinc-900"
                >
                  {matches.map((customer) => (
                    <li key={customer.id} role="option">
                      <button
                        type="button"
                        onClick={() => chooseCustomer(customer)}
                        className="flex w-full flex-col px-3 py-2 text-left text-sm hover:bg-zinc-100 dark:hover:bg-zinc-800"
                      >
                        <span className="font-medium">{customer.company_name ?? customer.name}</span>
                        <span dir="ltr" className="text-xs text-zinc-500">
                          {[customer.phone, customer.code === "NEW" ? "Not synced yet" : customer.code].filter(Boolean).join(" · ")}
                        </span>
                      </button>
                    </li>
                  ))}
                  {matches.length === 0 ? (
                    <li role="option">
                      <button
                        type="button"
                        onClick={() => setSearchOpen(false)}
                        className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm font-semibold text-emerald-700 hover:bg-emerald-50 dark:text-emerald-300 dark:hover:bg-emerald-500/10"
                      >
                        <Plus size={16} aria-hidden="true" className="shrink-0" />
                        <span className="min-w-0 truncate">Add "{guestQuery}" as a new customer</span>
                      </button>
                    </li>
                  ) : null}
                </ul>
              ) : null}
            </div>
            <label className={labelClass}>
              Order tag
              <input value={tag} onChange={(event) => setTag(event.target.value)} placeholder="Token" className={`${field} mt-1`} />
            </label>
            <label className={labelClass}>
              Pickup time
              <input type="time" value={pickup} onChange={(event) => setPickup(event.target.value)} className={`${field} mt-1`} />
            </label>
            <button
              type="submit"
              disabled={savingGuest}
              className="h-11 rounded-xl bg-emerald-600 px-4 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-60"
            >
              {savingGuest ? "Saving…" : session?.order_mode === "takeaway" ? "Update" : addingNew ? "Add & start" : "Start takeaway"}
            </button>
            {guestError ? <p className="text-sm text-red-600 sm:col-span-2 dark:text-red-300">{guestError}</p> : null}
          </form>
        ) : null}

        {mode === "delivery" ? (
          <form
            className="grid gap-3 md:grid-cols-2"
            onSubmit={(event) => {
              event.preventDefault();
              void startService();
            }}
          >
            <div ref={guestBox} className="relative md:col-span-2">
              <div className="grid gap-3 md:grid-cols-2">
                <label htmlFor="delivery-customer" className={labelClass}>
                  Customer
                  <span className="relative mt-1 block">
                    <Search aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 z-10 h-4 w-4 -translate-y-1/2 text-zinc-400" />
                    <input
                      id="delivery-customer"
                      required
                      type="search"
                      role="combobox"
                      aria-expanded={guestListOpen && searchSource === "name"}
                      aria-controls={listId}
                      aria-autocomplete="list"
                      value={name}
                      autoComplete="off"
                      placeholder="Search name or phone"
                      onChange={(event) => {
                        setName(event.target.value);
                        setSearchSource("name");
                        setSearchOpen(true);
                        setPicked(null);
                      }}
                      onFocus={() => {
                        setSearchSource("name");
                        setSearchOpen(true);
                      }}
                      className={`${field} !pl-9 [&::-webkit-search-cancel-button]:hidden`}
                    />
                  </span>
                </label>
                <label className={labelClass}>
                  Phone
                  <input
                    required
                    value={phone}
                    role="combobox"
                    aria-expanded={guestListOpen && searchSource === "phone"}
                    aria-controls={listId}
                    aria-autocomplete="list"
                    inputMode="tel"
                    autoComplete="off"
                    placeholder="Search phone"
                    onChange={(event) => {
                      setPhone(event.target.value);
                      setSearchSource("phone");
                      setSearchOpen(true);
                      setPicked(null);
                    }}
                    onFocus={() => {
                      setSearchSource("phone");
                      setSearchOpen(true);
                    }}
                    className={`${field} mt-1`}
                  />
                </label>
              </div>
              {guestListOpen ? (
                <ul
                  id={listId}
                  role="listbox"
                  className="absolute z-20 mt-1 max-h-48 w-full overflow-y-auto rounded-xl border border-zinc-200 bg-white py-1 shadow-lg dark:border-zinc-800 dark:bg-zinc-900"
                >
                  {matches.map((customer) => (
                    <li key={customer.id} role="option">
                      <button
                        type="button"
                        onClick={() => chooseCustomer(customer)}
                        className="flex w-full flex-col px-3 py-2 text-left text-sm hover:bg-zinc-100 dark:hover:bg-zinc-800"
                      >
                        <span className="font-medium">{customer.company_name ?? customer.name}</span>
                        <span dir="ltr" className="text-xs text-zinc-500">
                          {[customer.phone, customer.address, customer.code === "NEW" ? "Not synced yet" : customer.code].filter(Boolean).join(" · ")}
                        </span>
                      </button>
                    </li>
                  ))}
                  {matches.length === 0 ? (
                    <li role="option">
                      <button
                        type="button"
                        onClick={() => setSearchOpen(false)}
                        className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm font-semibold text-primary-600 hover:bg-primary-500/10"
                      >
                        <Plus size={16} aria-hidden="true" className="shrink-0" />
                        <span className="min-w-0 truncate">Add "{guestQuery}" as a new customer</span>
                      </button>
                    </li>
                  ) : null}
                </ul>
              ) : null}
            </div>
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
              <button
                type="submit"
                disabled={savingGuest}
                className="h-11 rounded-xl bg-primary-500 px-4 text-sm font-semibold text-white hover:bg-primary-600 disabled:opacity-60"
              >
                {savingGuest ? "Saving…" : session?.order_mode === "delivery" ? "Update delivery" : addingNew ? "Add & start" : "Start delivery"}
              </button>
            </div>
            {guestError ? <p className="text-sm text-red-600 md:col-span-2 dark:text-red-300">{guestError}</p> : null}
          </form>
        ) : null}
      </div>
      {session && session.items.length > 0 ? (
        <ul className="mt-3 flex flex-wrap gap-2" aria-label={t("Items on this order")}>
          {session.items
            .filter((item) => item.kitchen_status !== "VOIDED")
            .map((item) => (
              <li key={item.id} className="rounded-full bg-zinc-100 px-3 py-1 text-xs font-medium text-zinc-700 dark:bg-zinc-800 dark:text-zinc-200">
                {item.quantity}× {item.product_name}
                <span className="ms-1 text-zinc-500">{t(STATUS_LABEL[item.kitchen_status] ?? item.kitchen_status)}</span>
              </li>
            ))}
        </ul>
      ) : null}
      </div>
      </div>
      {confirmOpen ? (
        <div className="modal-backdrop" role="presentation" onClick={() => setConfirmOpen(false)}>
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="change-type-title"
            className="modal-card max-w-md"
            onClick={(event) => event.stopPropagation()}
          >
            <h2 id="change-type-title" className="text-xl font-semibold">Change Order Type?</h2>
            <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-300">
              Changing this order type may affect table assignment, pickup details, delivery information, charges, and kitchen routing. Do you want to continue?
            </p>
            <div className="mt-5 flex flex-wrap justify-end gap-2">
              <button type="button" onClick={() => setConfirmOpen(false)} className="h-12 rounded-full px-4 text-sm font-semibold text-zinc-700 dark:text-zinc-200">
                Keep Current Order
              </button>
              <button
                type="button"
                onClick={() => {
                  setConfirmOpen(false);
                  picking.current = true;
                  setChoosing(true);
                }}
                className="h-12 rounded-full bg-primary-500 px-4 text-sm font-semibold text-white"
              >
                Change Order Type
              </button>
            </div>
          </div>
        </div>
      ) : null}
      {blockedOpen ? (
        <div className="modal-backdrop" role="presentation" onClick={() => setBlockedOpen(false)}>
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="type-locked-title"
            className="modal-card max-w-md"
            onClick={(event) => event.stopPropagation()}
          >
            <h2 id="type-locked-title" className="text-xl font-semibold">This order cannot change type</h2>
            <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-300">
              It has already been sent to the kitchen or dispatched. Keep working in the current order type.
            </p>
            <div className="mt-5 flex flex-wrap justify-end gap-2">
              <button type="button" onClick={() => setBlockedOpen(false)} className="h-12 rounded-full bg-primary-500 px-4 text-sm font-semibold text-white">
                Keep Current Order
              </button>
              {onCancelOrder ? (
                <button
                  type="button"
                  onClick={() => {
                    setBlockedOpen(false);
                    onCancelOrder();
                  }}
                  className="h-12 rounded-full border border-red-300 px-4 text-sm font-semibold text-red-700 hover:bg-red-50 dark:border-red-500/40 dark:text-red-300 dark:hover:bg-red-500/10"
                >
                  Cancel Order
                </button>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
