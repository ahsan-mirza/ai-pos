import {
  Capability,
  Permission,
  comboDelta,
  comboSummary,
  formatMoney,
  modifierDelta,
  modifierSummary,
  type ComboChoice,
  unpaidItems,
  type DeliveryChannel,
  type DiningTable,
  type Floor,
  type ModifierChoice,
  type KitchenStatus,
  type Order,
  type OrderItem,
  type ProductUpsert,
  type ServiceType,
} from "@ai-pos/shared-types";
import { FloorTableCard, serviceOf } from "../../components/FloorTableCard";
import { FloorBoard, aggregateService, formatSeatedDuration, KITCHEN_LABEL as floorKitchenLabel, tableDisplayNumber } from "@ai-pos/ui";
import { ChefHat, CreditCard, Merge, Minus, MoveRight, Plus, Receipt, Search, Send, Split, Truck, Users, UtensilsCrossed, X } from "lucide-react";
import { useCallback, useEffect, useId, useMemo, useState } from "react";
import { ManagerApprovalModal } from "../../components/ManagerApprovalModal";
import { DrawerHeader } from "../../components/shell/Drawer";
import { PageFrame } from "../../components/shell/RegisterShell";
import { useShell } from "../../components/shell/ShellContext";
import { ui } from "../../components/shell/tokens";
import { useCapabilities } from "../../lib/capabilities";
import type { CashierSession } from "../auth/session";
import { loadCatalog, seedProducts, useCatalogUpdates } from "../checkout/catalog";
import { activeStore, useBusinessCurrency } from "../checkout/currency";
import { combosFor, groupsFor, refreshMenu, useMenu } from "../checkout/menu";
import { ComboBuilderModal } from "../checkout/ComboBuilderModal";
import { ModifierPickerModal } from "../checkout/ModifierPickerModal";
import { QuantityModal } from "../checkout/QuantityModal";
import { verifyManager } from "../checkout/wholesaleClient";
import { printKitchenTickets } from "./kitchenPrint";
import { SplitChecksModal } from "./SplitChecksModal";
import { IncomingDeliveries, KeyInDeliveryModal } from "./IncomingDeliveries";
import { OrderRequestError, channelsApi, ordersApi, queueOfflineOrder } from "./ordersClient";
import { listenForTableEvents } from "./tableSync";
import { startSettlement } from "./settlement";

const POLL_MS = 3000;

/** A tab is ready only when every sent line is ready. One finished plate while another is cooking stays partial. */
function tabKitchen(order: Order): string | null {
  const live = order.items.filter((item) => item.voided_at === null);
  const sent = live.filter((item) => item.sent_at !== null || item.kitchen_status);
  if (sent.length === 0) return null;
  const kitchen = aggregateService({
    sent: sent.length,
    marks: sent.map((item) => item.kitchen_status ?? ""),
    paid: 0,
    unpaid: 0,
    billRequested: false,
    hasItems: true,
  }).kitchen;
  return floorKitchenLabel[kitchen] || null;
}

function itemStatus(item: OrderItem): string {
  if (item.voided_at) return "Cancelled";
  if (item.paid_sale_id) return "Completed";
  if (!item.sent_at) return "New";
  if (item.kitchen_status === "preparing") return "Preparing";
  if (item.kitchen_status === "ready") return "Ready";
  if (item.kitchen_status === "bumped") return "Served";
  return "Sent to kitchen";
}

function orderKitchenLabel(order: Order): string {
  const live = order.items.filter((item) => item.voided_at === null);
  if (live.length === 0) return "New";
  const sent = live.filter((item) => item.sent_at !== null);
  if (sent.length === 0) return "New";
  const served = sent.filter((item) => item.kitchen_status === "bumped").length;
  const ready = sent.filter((item) => item.kitchen_status === "ready" || item.kitchen_status === "bumped").length;
  const preparing = sent.filter((item) => item.kitchen_status === "preparing").length;
  if (served === sent.length) return "Served";
  if (ready === sent.length) return "Ready";
  if (ready > 0 || (preparing > 0 && sent.length > preparing)) return "Partially ready";
  if (preparing > 0) return "Preparing";
  return "Sent to kitchen";
}

function handoffLabel(service: ServiceType): string {
  if (service === "TAKEAWAY") return "Picked up";
  if (service === "DELIVERY") return "Dispatched";
  return "Served";
}

function minutesSince(iso: string | null): number {
  return iso ? Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 60_000)) : 0;
}

function GuestCountModal({
  table,
  onClose,
  onConfirm,
}: {
  table: DiningTable;
  onClose: () => void;
  onConfirm: (covers: number) => void;
}) {
  const titleId = useId();
  const [covers, setCovers] = useState(Math.min(2, Math.max(1, table.seats)));
  const seats = Math.max(1, table.seats);
  const choices = Array.from({ length: Math.min(seats, 12) }, (_, index) => index + 1);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-backdrop" role="presentation">
      <div role="dialog" aria-modal="true" aria-labelledby={titleId} className="modal-card max-w-md">
        <div className="flex items-start gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-charcoal text-white dark:bg-zinc-100 dark:text-zinc-900">
            <Users size={20} aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="text-xl font-semibold">
              Seat {table.label}
            </h2>
            <p className="text-sm text-charcoal/60 dark:text-zinc-400">
              How many guests? This table seats {table.seats}.
            </p>
          </div>
          <button type="button" aria-label="Close" onClick={onClose} className="modal-close">
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        <form
          className="mt-5 space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            if (covers >= 1 && covers <= seats) onConfirm(covers);
          }}
        >
          <div className="flex flex-wrap gap-2" role="group" aria-label="Guest count">
            {choices.map((count) => (
              <button
                key={count}
                type="button"
                aria-pressed={covers === count}
                onClick={() => setCovers(count)}
                className={`h-12 min-w-12 rounded-2xl px-3 text-base font-semibold tabular-nums ${
                  covers === count ? "bg-primary text-white" : "bg-zinc-100 text-zinc-800 dark:bg-white/10 dark:text-zinc-100"
                }`}
              >
                {count}
              </button>
            ))}
          </div>
          {seats > 12 ? (
            <label className="block text-sm font-medium" htmlFor="guest-count">
              Guests
              <input
                id="guest-count"
                inputMode="numeric"
                autoComplete="off"
                value={covers}
                onChange={(event) => {
                  const next = Number(event.target.value.replace(/\D/g, ""));
                  if (Number.isFinite(next)) setCovers(Math.min(seats, next));
                }}
                className="modal-input mt-1.5 text-lg font-semibold tabular-nums"
              />
            </label>
          ) : null}
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="modal-cancel">
              Cancel
            </button>
            <button type="submit" className="modal-save" disabled={covers < 1}>
              Seat {covers} {covers === 1 ? "guest" : "guests"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function lineLabel(item: OrderItem): string {
  const extras = [comboSummary(item.components), modifierSummary(item.modifiers)].filter(Boolean).join(" · ");
  return extras ? `${item.product_name} · ${extras}` : item.product_name;
}

interface DraftLine {
  id: string;
  product: ProductUpsert;
  quantity: number;
  modifiers: ModifierChoice[];
  components: ComboChoice[];
  seat: number | null;
  note: string;
}

/** Restaurant floor: tables and open tabs shared by every register, with kitchen sending, voids, merges and pay. */
const VOID_REASONS = [
  ["changed_mind", "Customer changed mind"],
  ["wrong_item", "Incorrect item"],
  ["wrong_quantity", "Incorrect quantity"],
  ["stock", "Unavailable"],
  ["prep_delay", "Preparation delay"],
  ["entry_mistake", "Entered by mistake"],
  ["other", "Other"],
] as const;

function voidCode(reason: string): string {
  const match = /^\[([a-z_]+)\]/.exec(reason);
  return match?.[1] ?? "entry_mistake";
}

function VoidReasonFields({ reason, onChange }: { reason: string; onChange: (reason: string) => void }) {
  const code = voidCode(reason);
  const note = reason.replace(/^\[[a-z_]+\]\s*/, "");
  return (
    <>
      <select value={code} onChange={(event) => onChange(`[${event.target.value}] ${note}`)} className="modal-input">
        {VOID_REASONS.map(([value, label]) => (
          <option key={value} value={value}>{label}</option>
        ))}
      </select>
      <input
        autoFocus
        value={note}
        onChange={(event) => onChange(`[${code}] ${event.target.value}`)}
        placeholder="Explanation"
        className="modal-input"
      />
    </>
  );
}

export function OrdersPage({ session }: { session: CashierSession }) {
  const { navigate } = useShell();
  const currency = useBusinessCurrency();
  const capabilities = useCapabilities();
  const tablesOn = capabilities.enabled.has(Capability.Tables);
  const kitchenOn = capabilities.enabled.has(Capability.Kds);
  const menu = useMenu();
  const storeId = activeStore().id;
  const userId = session.user.id;

  const [orders, setOrders] = useState<Order[]>([]);
  const [floor, setFloor] = useState<Floor | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [offline, setOffline] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [products, setProducts] = useState<ProductUpsert[]>(seedProducts);
  const [query, setQuery] = useState("");
  const [draft, setDraft] = useState<DraftLine[]>([]);
  const [seat, setSeat] = useState<number | null>(null);
  const [modifierFor, setModifierFor] = useState<ProductUpsert | null>(null);
  const [comboFor, setComboFor] = useState<ProductUpsert | null>(null);
  const [quantityFor, setQuantityFor] = useState<ProductUpsert | null>(null);
  const [voiding, setVoiding] = useState<{ item: OrderItem | null; reason: string } | null>(null);
  const [mergeFrom, setMergeFrom] = useState<Order | null>(null);
  const [moving, setMoving] = useState<Order | null>(null);
  const [splitting, setSplitting] = useState(false);
  const splitOn = capabilities.enabled.has(Capability.SplitBills);
  const channelsOn = capabilities.enabled.has(Capability.DeliveryChannels);
  const [channels, setChannels] = useState<DeliveryChannel[]>([]);
  const [keyingIn, setKeyingIn] = useState(false);
  const [busy, setBusy] = useState(false);
  const [seating, setSeating] = useState<DiningTable | null>(null);
  const [adding, setAdding] = useState(false);

  const selected = orders.find((order) => order.id === selectedId) ?? null;

  const refresh = useCallback(async () => {
    try {
      const [next, nextFloor] = await Promise.all([ordersApi.list(storeId), tablesOn ? ordersApi.floor(storeId) : Promise.resolve(null)]);
      setOrders(next);
      setFloor(nextFloor);
      setOffline(false);
    } catch (caught) {
      if (caught instanceof OrderRequestError && caught.offline) setOffline(true);
      else setNotice(caught instanceof Error ? caught.message : String(caught));
    }
  }, [storeId, tablesOn]);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), POLL_MS);
    const stopLive = listenForTableEvents(storeId, (event) => {
      if (
        event.message &&
        (event.type === "KDS_ITEM_READY" ||
          event.type === "ORDER_STATUS_CHANGED" ||
          event.type === "ORDER_ITEM_VOIDED" ||
          event.type === "ORDER_CANCELLED")
      ) {
        setNotice(event.message);
      }
      if (event.type === "ORDER_STATUS_CHANGED" && event.order_id && event.kitchen_status) {
        const ids = new Set(event.item_ids ?? []);
        setOrders((current) =>
          current.map((order) =>
            order.id !== event.order_id
              ? order
              : {
                  ...order,
                  items: order.items.map((item) =>
                    ids.has(item.id)
                      ? { ...item, kitchen_status: event.kitchen_status as KitchenStatus, sent_at: item.sent_at ?? event.updated_at ?? null }
                      : item,
                  ),
                },
          ),
        );
      }
      if (
        event.type === "TABLE_ITEMS_ADDED" ||
        event.type === "TABLE_SESSION_CLOSED" ||
        event.type === "KDS_ITEM_READY" ||
        event.type === "ORDER_STATUS_CHANGED" ||
        event.type === "ORDER_ITEM_VOIDED" ||
        event.type === "ORDER_CANCELLED" ||
        event.type === "BILL_REQUESTED"
      ) {
        void refresh();
      }
    });
    return () => {
      stopLive();
      window.clearInterval(timer);
    };
  }, [refresh, storeId]);

  const refreshCatalog = useCallback(() => {
    void loadCatalog().then((catalog) => setProducts(catalog.products));
  }, []);
  useCatalogUpdates(refreshCatalog);

  useEffect(() => {
    refreshCatalog();
    if (capabilities.enabled.has(Capability.MenuModifiers)) void refreshMenu();
  }, [capabilities.enabled, refreshCatalog]);

  useEffect(() => {
    if (channelsOn) void channelsApi.list().then(setChannels).catch(() => setChannels([]));
  }, [channelsOn]);

  /** Runs a write; a stale order refreshes and asks the cashier to try again. */
  const write = useCallback(
    async (action: () => Promise<Order>, success?: string) => {
      setBusy(true);
      try {
        const order = await action();
        setOrders((current) => [...current.filter((item) => item.id !== order.id), order].filter((item) => item.status === "OPEN"));
        setSelectedId(order.status === "OPEN" ? order.id : null);
        if (success) setNotice(success);
        void refresh();
        return order;
      } catch (caught) {
        if (caught instanceof OrderRequestError && caught.stale) {
          await refresh();
          setNotice("Another register changed this order. It is refreshed: check it and try again.");
        } else {
          setNotice(caught instanceof Error ? caught.message : String(caught));
        }
        return null;
      } finally {
        setBusy(false);
      }
    },
    [refresh],
  );

  async function openTab(serviceType: ServiceType, table: DiningTable | null, covers = 0) {
    const id = crypto.randomUUID();
    const input = { storeId, userId, serviceType, tableId: table?.id ?? null, covers };
    setBusy(true);
    try {
      const order = await ordersApi.create(input, id);
      setOrders((current) => [...current.filter((item) => item.id !== order.id), order]);
      setSelectedId(order.id);
      setAdding(false);
      setNotice(table ? `Table ${table.label} seated.` : "New tab opened.");
    } catch (caught) {
      if (caught instanceof OrderRequestError && caught.code === "table_occupied" && caught.orderId) {
        const existing = await ordersApi.get(caught.orderId).catch(() => null);
        if (existing && existing.status === "OPEN") {
          setOrders((current) => [...current.filter((item) => item.id !== existing.id), existing]);
          setSelectedId(existing.id);
          setAdding(false);
          setNotice(`Table ${table?.label ?? ""} already has order #${existing.number}. It is open here.`);
        } else {
          setNotice("That table already has an open order. Refresh and open it from the floor.");
        }
      } else if (caught instanceof OrderRequestError && caught.offline) {
        await queueOfflineOrder({ ...input, id }, false);
        setNotice("Offline: the tab is saved on this register and syncs when the connection is back.");
      } else {
        setNotice(caught instanceof Error ? caught.message : String(caught));
      }
    } finally {
      setBusy(false);
      void refresh();
    }
  }

  function addDraft(product: ProductUpsert, modifiers: ModifierChoice[], components: ComboChoice[] = [], quantity = 1) {
    setDraft((current) => {
      const plain = modifiers.length === 0 && components.length === 0;
      const same = plain
        ? current.find(
            (line) =>
              line.product.id === product.id && line.seat === seat && line.modifiers.length === 0 && line.components.length === 0,
          )
        : undefined;
      if (same) return current.map((line) => (line === same ? { ...line, quantity: line.quantity + quantity } : line));
      return [...current, { id: crypto.randomUUID(), product, quantity, modifiers, components, seat, note: "" }];
    });
  }

  function pick(product: ProductUpsert) {
    if (product.is_serialized || product.sold_by_weight) {
      setNotice(`${product.name} is sold at checkout, not on a tab.`);
      return;
    }
    if (combosFor(menu, product.id).length > 0) setComboFor(product);
    else if (groupsFor(menu, product.id).length > 0) setModifierFor(product);
    else setQuantityFor(product);
  }

  async function resumeOrder(orderId: string) {
    const known = orders.find((item) => item.id === orderId) ?? null;
    setBusy(true);
    try {
      const order = await ordersApi.get(orderId);
      if (order.status !== "OPEN") {
        setNotice("This order is already completed. The floor is refreshing.");
        setSelectedId(null);
        return;
      }
      setOrders((current) => [...current.filter((item) => item.id !== order.id), order]);
      setSelectedId(order.id);
      setAdding(false);
      setDraft([]);
    } catch (caught) {
      if (known && known.status === "OPEN" && caught instanceof OrderRequestError && caught.offline) {
        setSelectedId(known.id);
        setAdding(false);
        setNotice("Offline: showing the order saved on this register.");
        return;
      }
      setNotice(caught instanceof Error ? caught.message : "This order could not be opened.");
    } finally {
      setBusy(false);
      void refresh();
    }
  }

  async function changeQuantity(item: OrderItem, quantity: number) {
    if (selected === null) return;
    if (item.sent_at) {
      setNotice("This item is already in the kitchen. Void it with a reason instead of changing the quantity.");
      return;
    }
    await write(() => ordersApi.setQuantity(selected, item.id, userId, quantity));
  }

  async function addAndMaybeSend(send: boolean) {
    if (selected === null || draft.length === 0) return;
    const items = draft.map((line) => ({
      id: line.id,
      product_id: line.product.id,
      quantity: line.quantity,
      unit_price_cents: line.product.price_cents + modifierDelta(line.modifiers) + comboDelta(line.components),
      modifiers: line.modifiers,
      ...(line.components.length ? { components: line.components } : {}),
      seat: line.seat,
      ...(line.note.trim() ? { note: line.note.trim() } : {}),
    }));
    let added: Order | null = null;
    try {
      added = await ordersApi.addItems(selected, userId, items);
    } catch (caught) {
      if (caught instanceof OrderRequestError && caught.offline) {
        await queueOfflineOrder(
          { id: selected.id, storeId, userId, serviceType: selected.service_type, tableId: selected.table_id, covers: selected.covers, items, openedAt: selected.opened_at },
          send,
        );
        setDraft([]);
        setNotice(
          send
            ? "Offline: the lines are saved on this register and reach the kitchen when the connection is back."
            : "Offline: the lines are saved on this register and sync when the connection is back.",
        );
        return;
      }
      if (caught instanceof OrderRequestError && caught.stale) {
        await refresh();
        setNotice("Another register changed this order. It is refreshed: add the lines again.");
        return;
      }
      setNotice(caught instanceof Error ? caught.message : String(caught));
      return;
    }
    setDraft([]);
    const fresh = added;
    if (send) await sendToKitchen(fresh);
    else await write(async () => fresh, `${items.length} line${items.length === 1 ? "" : "s"} added.`);
  }

  async function sendToKitchen(order: Order) {
    const sent = await write(() => ordersApi.send(order, userId), "Sent to the kitchen.");
    if (sent && capabilities.enabled.has(Capability.Kds)) void printKitchenTickets(sent.id);
  }

  function pay(itemIds: string[], label: string, guests?: number) {
    if (selected === null || itemIds.length === 0) return;
    startSettlement({ order: selected, itemIds, label, guests });
    navigate("checkout");
  }

  async function keyIn(channelId: string, externalRef: string, customerName: string | null) {
    setKeyingIn(false);
    await write(() => channelsApi.keyIn(channelId, externalRef, userId, customerName), "Delivery order opened. Add its items, then send.");
  }

  const floorCards = useMemo(() => {
    if (floor === null) return [];
    return floor.areas.flatMap((area) =>
      area.tables.map((table) => {
        const order = orders.find((item) => item.id === table.order_id) ?? null;
        const service = serviceOf(table, order);
        return {
          key: table.id,
          areaId: area.id,
          search: [table.label, tableDisplayNumber(table.label), table.order_number ? `#${table.order_number}` : "", service.guestName ?? ""].join(" "),
          active: table.is_active,
          status: table.status,
          ...service,
          table,
          order,
        };
      }),
    );
  }, [floor, orders]);
  const incoming = orders.filter((order) => order.channel_status === "PENDING");
  const tabs = orders.filter((order) => order.table_id === null && order.channel_status !== "PENDING");
  const sectionName =
    selected?.table_id == null
      ? null
      : (floor?.areas.find((area) => area.tables.some((table) => table.id === selected.table_id))?.name ?? null);
  const unpaid = selected ? unpaidItems(selected) : [];
  const seats = [...new Set(unpaid.map((item) => item.seat).filter((value): value is number => value !== null))].sort((a, b) => a - b);
  const hits = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const sellable = products.filter(
      (product) => product.is_active !== false && !product.is_serialized && !product.sold_by_weight,
    );
    return (needle ? sellable.filter((product) => `${product.name} ${product.sku} ${product.category}`.toLowerCase().includes(needle)) : sellable).slice(0, 24);
  }, [products, query]);

  return (
    <PageFrame
      title="Orders & Tables"
      sync={{ tone: offline ? "offline" : "live", label: offline ? "Offline" : "Live", title: offline ? "Orders sync when the connection returns." : "Shared with every register." }}
      actions={
        <div className="flex gap-2">
          <button type="button" className={`${ui.secondaryAction} h-12 px-4`} disabled={busy} onClick={() => void openTab("TAKEAWAY", null)}>
            <Plus size={16} aria-hidden="true" /> Takeaway tab
          </button>
          {!tablesOn ? (
            <button type="button" className={`${ui.secondaryAction} h-12 px-4`} disabled={busy} onClick={() => void openTab("DINE_IN", null)}>
              <UtensilsCrossed size={16} aria-hidden="true" /> Dine-in tab
            </button>
          ) : null}
          {channelsOn ? (
            <button type="button" className={`${ui.secondaryAction} h-12 px-4`} disabled={busy} onClick={() => setKeyingIn(true)}>
              <Truck size={16} aria-hidden="true" /> Delivery order
            </button>
          ) : null}
        </div>
      }
      drawer={
        <aside
          aria-label={selected ? "Active order" : "Order"}
          className={`${selected ? "flex" : "hidden lg:flex"} fixed inset-0 z-30 min-h-0 flex-col border-zinc-200 bg-white lg:static lg:z-auto lg:w-[420px] lg:border-l dark:border-white/10 dark:bg-charcoal`}
        >
          {selected === null ? (
            <div className="flex flex-1 flex-col items-center justify-center p-8 text-center text-sm text-zinc-500 dark:text-white/50">
              <UtensilsCrossed size={28} aria-hidden="true" />
              <p className="mt-3 font-semibold text-zinc-700 dark:text-white/80">Pick a table or a tab</p>
              <p className="mt-1">
                {kitchenOn
                  ? "Seat a free table, or open a takeaway tab, then add items. Send a round or pay."
                  : "Seat a free table, or open a takeaway tab, then add items and pay."}
              </p>
            </div>
          ) : (
            <>
              <DrawerHeader title={selected.table_label ? `Table ${tableDisplayNumber(selected.table_label)}` : selected.name || `Tab #${selected.number}`} count={`#${selected.number}`}>
                <button type="button" aria-label="Close order" onClick={() => { setSelectedId(null); setAdding(false); }} className="flex h-9 w-9 items-center justify-center rounded-full hover:bg-zinc-100 dark:hover:bg-white/10">
                  <X size={18} aria-hidden="true" />
                </button>
              </DrawerHeader>
              <div className="custom-scrollbar min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3">
                <div className="flex flex-wrap items-center gap-1.5 text-xs">
                  {selected.table_id ? <span className="rounded-full bg-violet-100 px-2 py-0.5 font-semibold text-violet-800 dark:bg-violet-500/20 dark:text-violet-200">Occupied</span> : null}
                  {sectionName ? <span className="text-zinc-500 dark:text-white/50">{sectionName}</span> : null}
                  <span className="inline-flex items-center gap-1 text-zinc-500 dark:text-white/50"><Users size={13} aria-hidden="true" /> {selected.covers} {selected.covers === 1 ? "guest" : "guests"}</span>
                  <span className="text-zinc-500 dark:text-white/50">· {formatSeatedDuration(minutesSince(selected.opened_at))}</span>
                  <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 font-semibold text-primary">
                    <ChefHat size={12} aria-hidden="true" /> {orderKitchenLabel(selected)}
                  </span>
                </div>
                <p className="text-xs text-zinc-500 dark:text-white/50">
                  Opened {new Date(selected.opened_at).toLocaleString()}
                  {selected.opened_by_name ? ` · ${selected.opened_by_name}` : ""}
                  {selected.name ? ` · Customer ${selected.name}` : ""}
                  {selected.channel_name ? ` · ${selected.channel_name} ${selected.external_ref ?? ""}` : ""}
                  {selected.bill_requested_at ? " · Bill requested" : ""}
                </p>
                <ul className="space-y-1.5">
                  {selected.items.map((item) => {
                    const editable = !item.voided_at && !item.paid_sale_id && !item.sent_at;
                    return (
                    <li key={item.id} className={`rounded-2xl border px-3 py-2 text-sm ${item.voided_at ? "border-dashed border-zinc-200 opacity-50 dark:border-white/10" : "border-zinc-200 bg-zinc-50 dark:border-white/[0.06] dark:bg-[#1A191D]"}`}>
                      <div className="flex items-baseline justify-between gap-2">
                        <span className={`min-w-0 truncate font-semibold ${item.voided_at ? "line-through" : ""}`}>{lineLabel(item)}</span>
                        <span className="shrink-0 font-bold tabular-nums">{formatMoney(item.unit_price_cents * item.quantity, currency)}</span>
                      </div>
                      <p className="mt-0.5 text-[11px] text-zinc-500 dark:text-white/50">
                        {item.quantity} × {formatMoney(item.unit_price_cents, currency)}
                        {item.note ? ` · ${item.note}` : ""}
                      </p>
                      <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-zinc-500 dark:text-white/50">
                        <span className="rounded-full bg-primary/10 px-1.5 font-semibold text-primary">{itemStatus(item)}</span>
                        {item.seat ? <span className="rounded-full bg-zinc-200/70 px-1.5 dark:bg-white/10">Seat {item.seat}</span> : null}
                        {editable ? (
                          <span className="ml-auto inline-flex items-center gap-1">
                            <button type="button" aria-label={`Decrease ${item.product_name}`} disabled={busy || item.quantity <= 1} onClick={() => void changeQuantity(item, item.quantity - 1)} className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-zinc-200/80 dark:bg-white/10"><Minus size={12} aria-hidden="true" /></button>
                            <span className="min-w-4 text-center font-semibold tabular-nums text-zinc-800 dark:text-white">{item.quantity}</span>
                            <button type="button" aria-label={`Increase ${item.product_name}`} disabled={busy} onClick={() => void changeQuantity(item, item.quantity + 1)} className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-zinc-200/80 dark:bg-white/10"><Plus size={12} aria-hidden="true" /></button>
                          </span>
                        ) : null}
                        {!item.voided_at && !item.paid_sale_id ? (
                          <button type="button" disabled={busy} onClick={() => setVoiding({ item, reason: "[entry_mistake] " })} className={`${editable ? "" : "ml-auto "}font-semibold text-zinc-500 hover:text-red-600`}>
                            {item.sent_at ? "Void" : "Remove"}
                          </button>
                        ) : null}
                      </div>
                      {item.sent_at && !item.voided_at ? (
                        <p className="mt-1 text-[11px] text-zinc-500 dark:text-white/50">Already in the kitchen. Void it with a reason to correct it. New items do not change this line.</p>
                      ) : null}
                    </li>
                    );
                  })}
                </ul>

                {draft.length > 0 ? (
                  <div className="rounded-2xl border border-primary/40 p-2">
                    <p className="px-1 text-[11px] font-semibold uppercase tracking-wide text-primary">Adding</p>
                    <ul className="mt-1 space-y-1 text-sm">
                      {draft.map((line) => (
                        <li key={line.id} className="px-1">
                          <div className="flex items-center justify-between gap-2">
                            <span className="min-w-0 truncate">
                              {line.quantity} × {line.product.name}
                              {line.components.length ? ` · ${comboSummary(line.components)}` : ""}
                              {line.modifiers.length ? ` · ${modifierSummary(line.modifiers)}` : ""}
                              {line.seat ? ` · seat ${line.seat}` : ""}
                            </span>
                            <button type="button" aria-label={`Remove ${line.product.name}`} onClick={() => setDraft(draft.filter((item) => item.id !== line.id))} className="text-zinc-400 hover:text-red-600">
                              <X size={14} aria-hidden="true" />
                            </button>
                          </div>
                          <input
                            value={line.note}
                            onChange={(event) => setDraft(draft.map((item) => (item.id === line.id ? { ...item, note: event.target.value.slice(0, 160) } : item)))}
                            placeholder="Special instructions"
                            aria-label={`Note for ${line.product.name}`}
                            className="mt-1 h-8 w-full rounded-xl border border-zinc-200 bg-white px-2 text-xs focus:border-primary focus:outline-none dark:border-white/10 dark:bg-zinc-900/60"
                          />
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {adding ? (
                <>
                <div className="flex items-center gap-1.5 text-[11px] font-semibold">
                  <span className="text-zinc-500 dark:text-white/50">Seat</span>
                  {[null, 1, 2, 3, 4, 5, 6].map((value) => (
                    <button key={value ?? "all"} type="button" aria-pressed={seat === value} onClick={() => setSeat(value)}
                      className={`h-7 min-w-7 rounded-full px-2 ${seat === value ? "bg-primary text-white" : "bg-zinc-200/70 dark:bg-white/10"}`}>
                      {value ?? "—"}
                    </button>
                  ))}
                </div>
                <label className="relative block">
                  <span className="sr-only">Find a menu item</span>
                  <Search size={15} aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400" />
                  <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Find a menu item"
                    className="h-10 w-full rounded-2xl border border-zinc-200 bg-white pl-9 pr-3 text-sm focus:border-primary focus:outline-none dark:border-white/10 dark:bg-zinc-900/60" />
                </label>
                <div className="grid grid-cols-2 gap-1.5">
                  {hits.map((product) => (
                    <button key={product.id} type="button" disabled={busy} onClick={() => pick(product)}
                      className="rounded-2xl border border-zinc-200 px-2.5 py-2 text-left text-xs hover:border-primary dark:border-white/10">
                      <span className="block truncate font-semibold">{product.name}</span>
                      <span className="block tabular-nums text-zinc-500 dark:text-white/50">{formatMoney(product.price_cents, currency)}</span>
                    </button>
                  ))}
                </div>
                </>
                ) : (
                  <p className="text-xs text-zinc-500 dark:text-white/50">
                    {selected.table_id
                      ? "Add more items to this same order, or check it out. Closing this panel leaves the table occupied."
                      : "Add more items to this same order, or check it out. Closing this panel keeps the tab open."}
                  </p>
                )}
              </div>
              <div className="shrink-0 space-y-2 border-t border-zinc-200 px-4 py-3 dark:border-white/10">
                <p className="flex items-baseline justify-between text-sm">
                  <span className="font-semibold">Open to pay</span>
                  <span className="text-2xl font-bold tabular-nums text-primary">{formatMoney(selected.open_cents, currency)}</span>
                </p>
                <div className="grid grid-cols-2 gap-2">
                  <button type="button" disabled={busy} onClick={() => setAdding(true)} className={`${ui.secondaryAction} h-14 rounded-2xl text-sm`}>
                    <Plus size={16} aria-hidden="true" /> Add More Items
                  </button>
                  <button type="button" disabled={busy || unpaid.length === 0} onClick={() => pay(unpaid.map((item) => item.id), `order #${selected.number}`)} className={`${ui.primaryAction} h-12 rounded-2xl text-sm`}>
                    <CreditCard size={16} aria-hidden="true" /> Checkout
                  </button>
                </div>
                {adding ? (
                  <div className={`grid gap-2 ${kitchenOn ? "grid-cols-2" : "grid-cols-1"}`}>
                    <button type="button" disabled={busy || draft.length === 0} onClick={() => void addAndMaybeSend(false)} className={`${ui.secondaryAction} h-11 rounded-2xl text-xs`}>
                      <Plus size={15} aria-hidden="true" /> Add to this order
                    </button>
                    {kitchenOn ? (
                      <button type="button" disabled={busy || (draft.length === 0 && !selected.items.some((item) => !item.sent_at && !item.voided_at))}
                        onClick={() => (draft.length > 0 ? void addAndMaybeSend(true) : void sendToKitchen(selected))}
                        className={`${ui.secondaryAction} h-11 rounded-2xl text-xs`}>
                        <Send size={15} aria-hidden="true" /> Send to kitchen
                      </button>
                    ) : null}
                  </div>
                ) : null}
                {selected.items.some((item) => !item.voided_at && item.kitchen_status === "ready") ? (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void write(() => ordersApi.handOver(selected, userId), `${handoffLabel(selected.service_type)}.`)}
                    className={`${ui.secondaryAction} h-11 w-full rounded-2xl text-xs`}
                  >
                    <UtensilsCrossed size={15} aria-hidden="true" /> {handoffLabel(selected.service_type)}
                  </button>
                ) : null}
                {splitOn && seats.length > 1 ? (
                  <div className="flex flex-wrap gap-1.5">
                    {seats.map((value) => (
                      <button key={value} type="button" onClick={() => pay(unpaid.filter((item) => item.seat === value).map((item) => item.id), `seat ${value} of #${selected.number}`)}
                        className="h-8 rounded-full bg-zinc-200/70 px-3 text-xs font-semibold dark:bg-white/10">
                        Pay seat {value}
                      </button>
                    ))}
                  </div>
                ) : null}
                <div className="flex gap-2">
                  {tablesOn ? (
                    <button type="button" disabled={busy} onClick={() => setMoving(selected)} className={`${ui.secondaryAction} h-12 w-14 shrink-0 flex-col rounded-2xl text-[10px]`}>
                      <MoveRight size={16} aria-hidden="true" /> Move
                    </button>
                  ) : null}
                  {orders.length > 1 ? (
                    <button type="button" disabled={busy} onClick={() => setMergeFrom(selected)} className={`${ui.secondaryAction} h-12 w-14 shrink-0 flex-col rounded-2xl text-[10px]`}>
                      <Merge size={16} aria-hidden="true" /> Merge
                    </button>
                  ) : null}
                  {splitOn ? (
                    <button type="button" disabled={busy || unpaid.length === 0} onClick={() => setSplitting(true)} className={`${ui.secondaryAction} h-12 w-14 shrink-0 flex-col rounded-2xl text-[10px]`}>
                      <Split size={16} aria-hidden="true" /> Split
                    </button>
                  ) : null}
                  <button type="button" disabled={busy || unpaid.length === 0} onClick={() => void write(() => ordersApi.bill(selected, userId), "Bill requested.")} className={`${ui.secondaryAction} h-12 flex-1 rounded-2xl text-xs`}>
                    <Receipt size={15} aria-hidden="true" /> Bill
                  </button>
                </div>
              </div>
            </>
          )}
        </aside>
      }
    >
      <div className="space-y-4 p-5">
        {notice ? (
          <p role="status" className="rounded-2xl bg-zinc-100 px-4 py-2.5 text-sm dark:bg-white/[0.06]">
            {notice}
          </p>
        ) : null}
        {channelsOn ? (
          <IncomingDeliveries
            orders={incoming}
            currency={currency}
            busy={busy}
            onAccept={(order, minutes) => void write(() => channelsApi.accept(order, userId, minutes), `#${order.number} accepted: ready in ${minutes} min.`).then((done) => {
              if (done && capabilities.enabled.has(Capability.Kds)) void printKitchenTickets(done.id);
            })}
            onReject={(order, reason) => void write(() => channelsApi.reject(order, userId, reason), `#${order.number} rejected.`)}
          />
        ) : null}
        {moving ? (
          <p className="rounded-2xl border border-sky-400/50 bg-sky-500/10 px-4 py-2.5 text-sm">
            Move #{moving.number} to which free table?{" "}
            <button type="button" className="font-semibold underline" onClick={() => setMoving(null)}>Cancel</button>
          </p>
        ) : null}
        {mergeFrom ? (
          <p className="rounded-2xl border border-primary/50 bg-primary/10 px-4 py-2.5 text-sm">
            Merge #{mergeFrom.number} into which order? Tap a table or tab.{" "}
            <button type="button" className="font-semibold underline" onClick={() => setMergeFrom(null)}>Cancel</button>
          </p>
        ) : null}

        {tablesOn && floor ? (
          <section aria-label="Floor plan">
            {floor.areas.length === 0 ? <p className="mb-2 text-sm text-zinc-500">No dining areas yet. Add them in the portal under Inventory › Floor plan.</p> : null}
            <FloorBoard
              sections={floor.areas.map((item) => ({ id: item.id, name: item.name }))}
              items={floorCards}
              empty="No tables match this floor."
              renderItem={(card) => (
                <FloorTableCard
                  tableId={card.table.id}
                  label={card.table.label}
                  seats={card.table.seats}
                  shape={card.table.shape}
                  active={card.active}
                  covers={card.table.covers}
                  seatedAt={card.table.seated_at}
                  openCents={card.table.open_cents}
                  currency={currency}
                  status={card.table.status}
                  kitchen={card.kitchen}
                  payment={card.payment}
                  orderProgress={card.orderProgress}
                  orderNumber={card.table.order_number}
                  guestName={card.guestName}
                  readyCount={card.readyCount}
                  sentCount={card.sentCount}
                  selected={Boolean(selectedId && card.table.order_id === selectedId)}
                  disabled={busy}
                  onClick={() => {
                    if (!card.active) return;
                    const order = card.order;
                    if (moving) {
                      if (!order) {
                        const from = moving;
                        setMoving(null);
                        void write(() => ordersApi.move(from, userId, card.table.id), `#${from.number} moved to ${card.table.label}.`);
                      }
                      return;
                    }
                    if (mergeFrom) {
                      if (order && order.id !== mergeFrom.id) {
                        const from = mergeFrom;
                        setMergeFrom(null);
                        void write(() => ordersApi.merge(from, order, userId), `#${from.number} merged into ${card.table.label}.`);
                      }
                      return;
                    }
                    const occupied = card.table.status !== "free" || card.table.order_id !== null;
                    if (occupied) {
                      const orderId = order?.id ?? card.table.order_id;
                      if (orderId) void resumeOrder(orderId);
                      else setNotice("This table is occupied, but its order could not be found. The floor is refreshing.");
                      return;
                    }
                    setSeating(card.table);
                  }}
                />
              )}
            />
          </section>
        ) : null}

        <section aria-label="Open tabs">
          <h2 className="mb-2 text-sm font-semibold">{tablesOn ? "Tabs without a table" : "Open tabs"}</h2>
          <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
            {(tablesOn ? tabs : orders.filter((order) => order.channel_status !== "PENDING")).map((order) => {
              const phase = tabKitchen(order);
              return (
              <button key={order.id} type="button" onClick={() => {
                if (mergeFrom) {
                  if (order.id !== mergeFrom.id) {
                    const from = mergeFrom;
                    setMergeFrom(null);
                    void write(() => ordersApi.merge(from, order, userId), `#${from.number} merged into #${order.number}.`);
                  }
                  return;
                }
                setAdding(false);
                setSelectedId(order.id);
              }}
                className={`rounded-2xl border p-3 text-left ${order.id === selectedId ? "border-primary" : "border-zinc-200 dark:border-white/10"}`}>
                <span className="flex items-baseline justify-between gap-2">
                  <span className="font-semibold">{order.table_label ? `Table ${order.table_label}` : order.name || `#${order.number}`}</span>
                  <span className="text-sm font-bold tabular-nums">{formatMoney(order.open_cents, currency)}</span>
                </span>
                <span className="mt-1 block text-xs text-zinc-500 dark:text-white/50">
                  {order.service_type === "DELIVERY" ? `${order.channel_name ?? "Delivery"} ${order.external_ref ?? ""}` : order.service_type === "TAKEAWAY" ? "Takeaway" : "Dine-in"} · {order.items.filter((item) => !item.voided_at).length} lines · {formatSeatedDuration(minutesSince(order.opened_at))}
                  {phase ? ` · ${phase}` : ""}
                </span>
              </button>
              );
            })}
            {(tablesOn ? tabs : orders.filter((order) => order.channel_status !== "PENDING")).length === 0 ? <p className="text-sm text-zinc-500 dark:text-white/50">No open tabs.</p> : null}
          </div>
        </section>
      </div>

      {quantityFor ? (
        <QuantityModal
          product={quantityFor}
          onClose={() => setQuantityFor(null)}
          onConfirm={(quantity) => {
            addDraft(quantityFor, [], [], quantity);
            return true;
          }}
        />
      ) : null}
      {modifierFor ? (
        <ModifierPickerModal product={modifierFor} groups={groupsFor(menu, modifierFor.id)} currency={currency}
          onClose={() => setModifierFor(null)}
          onConfirm={(choices, quantity) => {
            addDraft(modifierFor, choices, [], quantity);
            setModifierFor(null);
          }} />
      ) : null}
      {comboFor ? (
        <ComboBuilderModal product={comboFor} slots={combosFor(menu, comboFor.id)} currency={currency}
          onClose={() => setComboFor(null)}
          onConfirm={(components, quantity) => {
            addDraft(comboFor, [], components, quantity);
            setComboFor(null);
          }} />
      ) : null}

      {seating ? (
        <GuestCountModal
          table={seating}
          onClose={() => setSeating(null)}
          onConfirm={(covers) => {
            const table = seating;
            setSeating(null);
            void openTab("DINE_IN", table, covers);
          }}
        />
      ) : null}

      {keyingIn ? <KeyInDeliveryModal channels={channels} onClose={() => setKeyingIn(false)} onSubmit={(id, ref, name) => void keyIn(id, ref, name)} /> : null}

      {splitting && selected ? (
        <SplitChecksModal
          order={selected}
          currency={currency}
          onClose={() => setSplitting(false)}
          onPayCheck={(itemIds, label) => {
            setSplitting(false);
            pay(itemIds, label);
          }}
          onPayEqually={(guests) => {
            setSplitting(false);
            pay(unpaid.map((item) => item.id), `order #${selected.number}, ${guests} ways`, guests);
          }}
        />
      ) : null}

      {voiding && selected ? (
        voiding.item?.sent_at ? (
          <ManagerApprovalModal
            reasons={[`Void ${voiding.item.quantity} × ${voiding.item.product_name} already sent to the kitchen`]}
            subtitle="A manager allowed to void sent items must approve. Add the reason in the note."
            verify={(username, pin) => verifyManager(session, username, pin, Permission.PosVoidSentItem)}
            onClose={() => setVoiding(null)}
            onApproved={(approver, note) => {
              const item = voiding.item!;
              setVoiding(null);
              void write(() => ordersApi.voidItem(selected, item.id, userId, note || "Voided after sending", approver.id), "Line voided.");
            }}
          />
        ) : (
          <div className="modal-backdrop" role="presentation">
            <form className="modal-card max-w-sm space-y-3" onSubmit={(event) => {
              event.preventDefault();
              const item = voiding.item!;
              setVoiding(null);
              void write(
                () => ordersApi.voidItem(selected, item.id, userId, (voiding.reason.trim() || "[entry_mistake] Removed before sending").slice(0, 160), null),
                "Line removed.",
              );
            }}>
              <h2 className="text-lg font-semibold">Remove {voiding.item?.product_name}?</h2>
              <VoidReasonFields reason={voiding.reason} onChange={(reason) => setVoiding({ ...voiding, reason })} />
              <div className="flex justify-end gap-2">
                <button type="button" className="modal-cancel" onClick={() => setVoiding(null)}>Cancel</button>
                <button type="submit" className="modal-save">Remove</button>
              </div>
            </form>
          </div>
        )
      ) : null}
    </PageFrame>
  );
}
