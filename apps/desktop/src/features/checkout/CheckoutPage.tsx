import {
  Capability,
  PRICE_TIER_LABELS,
  Permission,
  formatMoney,
  noMatchesMessage,
  parseEmbeddedBarcode,
  resolveUnitPrice,
  type PaymentMethod,
  type PriceTier,
  type ProductUpsert,
  type Promotion,
} from "@ai-pos/shared-types";
import {
  AlertTriangle,
  ChevronUp,
  FileText,
  Gift,
  Inbox,
  PauseCircle,
  Percent,
  ReceiptText,
  ShoppingCart,
  Truck,
  UtensilsCrossed,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ManagerApprovalModal } from "../../components/ManagerApprovalModal";
import { DrawerHeader } from "../../components/shell/Drawer";
import type { SyncState } from "../../components/shell/HeaderBar";
import { PageFrame } from "../../components/shell/RegisterShell";
import { SearchInput } from "../../components/shell/SearchInput";
import { useShell, useShellPage } from "../../components/shell/ShellContext";
import { ui } from "../../components/shell/tokens";
import { useCapabilities } from "../../lib/capabilities";
import { inTauri, openDocumentPdf, recordCashMovement, refreshSeries, type RegisterCustomer } from "../../lib/tauri";
import { CashDrawerModal } from "../audit/CashDrawerModal";
import { logItemVoid } from "../audit/registerAudit";
import type { CashierSession } from "../auth/session";
import { printReceipt } from "../printing/print";
import { asGiftReceipt, type ReceiptDoc } from "@ai-pos/receipt";
import { exchangeByDate, saleReceipt } from "../printing/saleReceipt";
import { onDisplayReady, publishDisplay, republishDisplay } from "../display/displayChannel";
import { activeShiftId } from "../shifts/shift";
import { invoiceNumber } from "../returns/returnMath";
import { BarcodeWedge } from "./BarcodeWedge";
import { BranchCheckModal } from "./BranchCheckModal";
import { BulkImeiModal } from "./BulkImeiModal";
import {
  applyCart,
  cartRows,
  cartTier,
  cartTotals,
  emptyCart,
  lineGross,
  manualDiscountCents,
  type CartAction,
  type CartLine,
  type CartRow,
  type CartState,
} from "./cart";
import { DiscountModal } from "./DiscountModal";
import { GiftCardSellModal } from "./GiftCardSellModal";
import { CartList } from "./CartList";
import { CheckoutSidebar } from "./CheckoutSidebar";
import { loadCatalog, seedProducts, type Catalog } from "./catalog";
import { invoiceOf, prepareNumberedBatch, submitCharge, submitQuote, type ChargeBatch } from "./checkout";
import { activeStore, businessTax, customerTax, useBusinessCurrency } from "./currency";
import { refreshPricing } from "./customerPricing";
import { CustomerBar } from "./CustomerBar";
import { ServedByPicker } from "./ServedByPicker";
import { linesBelowFloor, loadFloors, type Floor } from "./floors";
import { holdCart } from "./held";
import { HeldCartsModal } from "./HeldCartsModal";
import { SerialPickerModal } from "./SerialPickerModal";
import { ModeSwitch } from "./ModeSwitch";
import { OpenPriceModal } from "./OpenPriceModal";
import { WeighModal } from "./WeighModal";
import { ComboBuilderModal } from "./ComboBuilderModal";
import { ModifierPickerModal } from "./ModifierPickerModal";
import { combosFor, groupsFor, refreshMenu, useMenu } from "./menu";
import { serviceCharge, takeSettlement, type SettlementIntent } from "../orders/settlement";
import { TipRow } from "../orders/TipRow";
import { PriceOverrideModal } from "./PriceOverrideModal";
import { ProductCard, type TierPreview } from "./ProductCard";
import { CouponRow } from "./CouponRow";
import { loadPromotions, withPromotions } from "./promotions";
import { QuoteModal } from "./QuoteModal";
import { buildSalesOrder, submitSalesOrder } from "./salesOrder";
import { buildQuote, type ChargeRequest } from "./queue";
import { SaleSummary } from "./SaleSummary";
import { TenderPanel } from "./TenderPanel";
import { emptyPayment, planTenders, splitEqually, tenderOptions, type PaymentDraft } from "./tenders";
import { useProductSearch } from "./useProductSearch";
import { useSyncEngine } from "./useSyncEngine";
import { takeExchange, type ExchangeIntent } from "./exchange";
import { groupHits, modelGroup, type ModelGroup } from "./variants";
import { ModelCard, VariantPickerModal } from "./VariantPicker";
import { syncWholesaleCaches, verifyManager } from "./wholesaleClient";

interface CheckoutPageProps {
  session: CashierSession;
}

/** Product cards rendered at once; supermarket catalogs run to tens of thousands of SKUs. */
const GRID_LIMIT = 120;

const SALE_METHOD_LABELS: Record<PaymentMethod, string> = {
  cash: "Cash",
  card: "Card",
  transfer: "Transfer",
  store_credit: "Store credit",
  on_account: "On-account",
  cheque: "Cheque",
  deposit: "Deposit",
  qr: "QR",
  loyalty: "Loyalty points",
  trade_in: "Trade-in",
  channel: "Delivery app",
  bnpl: "Pay later",
  gift_card: "Gift card",
};

interface CreditApprovalState {
  approvedById: string;
  approverName: string;
  note: string;
}

/** Wholesale price shown on a search card: the tier's base price and its deepest volume break. */
function tierPreview(product: ProductUpsert, tier: PriceTier): TierPreview | null {
  if (tier === "RETAIL") return null;
  const atMoq = resolveUnitPrice(product.price_cents, product.prices, tier, Number.MAX_SAFE_INTEGER);
  const base = resolveUnitPrice(
    product.price_cents,
    product.prices,
    tier,
    product.prices?.find((row) => row.price_tier === tier)?.min_order_quantity ?? 1,
  );
  if (base.tier === "RETAIL" && atMoq.tier === "RETAIL") return null;
  const row = product.prices?.find((item) => item.price_tier === base.tier);
  const deepest = [...(row?.volume_discounts ?? [])].sort((left, right) => right.min_qty - left.min_qty)[0];
  return {
    base: base.price_cents,
    label: `${PRICE_TIER_LABELS[base.tier]}${row && row.min_order_quantity > 1 ? ` · min ${row.min_order_quantity}` : ""}`,
    best: deepest ? `${deepest.min_qty}+` : null,
  };
}

export function CheckoutPage({ session }: CheckoutPageProps) {
  const currency = useBusinessCurrency();
  const [catalog, setCatalog] = useState<Catalog>({ products: seedProducts, source: "seed", message: null });
  const [catalogLoaded, setCatalogLoaded] = useState(false);
  const [cart, setCart] = useState<CartState>(emptyCart);
  const cartRef = useRef<CartState>(emptyCart);
  const [payment, setPayment] = useState<PaymentDraft>(emptyPayment);
  const [creditApproval, setCreditApproval] = useState<CreditApprovalState | null>(null);
  const [askCredit, setAskCredit] = useState(false);
  const [overrideRow, setOverrideRow] = useState<CartRow | null>(null);
  const [discountFor, setDiscountFor] = useState<{ lines: CartLine[]; title: string } | null>(null);
  const [giftCardOpen, setGiftCardOpen] = useState(false);
  const [notice, setNotice] = useState("Scan, or search by name, model, barcode, SKU, or IMEI.");
  const [query, setQuery] = useState("");
  const [pendingSerial, setPendingSerial] = useState<ProductUpsert | null>(null);
  const [openPriceFor, setOpenPriceFor] = useState<ProductUpsert | null>(null);
  const [weighFor, setWeighFor] = useState<ProductUpsert | null>(null);
  const [modifierFor, setModifierFor] = useState<ProductUpsert | null>(null);
  const [comboFor, setComboFor] = useState<ProductUpsert | null>(null);
  const menu = useMenu();
  const [floors, setFloors] = useState<Map<string, Floor>>(new Map());
  const [floorRow, setFloorRow] = useState<CartRow | null>(null);
  const [bulkFor, setBulkFor] = useState<ProductUpsert | null>(null);
  const [quoteOpen, setQuoteOpen] = useState(false);
  const [branchCheck, setBranchCheck] = useState<{ product: ProductUpsert | null } | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [heldOpen, setHeldOpen] = useState(false);
  const [lastReceipt, setLastReceipt] = useState<{ doc: ReceiptDoc; saleId: string } | null>(null);
  const [charging, setCharging] = useState(false);
  const [pulse, setPulse] = useState(0);
  const [cartOpen, setCartOpen] = useState(false);
  const [category, setCategory] = useState<string | null>(null);
  const [chargeError, setChargeError] = useState<string | null>(null);
  const batchRef = useRef<ChargeBatch | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const closeCartRef = useRef<HTMLButtonElement>(null);
  const closeCart = useCallback(() => setCartOpen(false), []);
  const { report, desktop } = useSyncEngine(pulse);
  const { hits, debouncedQuery, searching, resolve } = useProductSearch(query, catalog.products);

  const [promotions, setPromotions] = useState<Promotion[]>([]);
  const [coupon, setCoupon] = useState<string | null>(null);
  const tier = cartTier(cart);
  const pricedLines = useMemo(() => withPromotions(cart, promotions, coupon), [cart, promotions, coupon]);
  const totals = useMemo(() => cartTotals(pricedLines, customerTax(cart.customer)), [pricedLines, cart.customer]);
  const rows = useMemo(() => cartRows(pricedLines), [pricedLines]);
  const promoSavings = pricedLines.reduce((sum, line) => sum + (line.promotion?.discountCents ?? 0), 0);
  const manualSavings = pricedLines.reduce((sum, line) => sum + manualDiscountCents(line), 0);
  const discountable = pricedLines.filter((line) => !line.giftCardCode && !line.product.sold_by_weight && !line.orderItemId);
  const couponsOffered = cart.mode === "RETAIL" && promotions.some((promo) => promo.coupon_code !== null);
  const capabilities = useCapabilities();
  // Restaurant: a tab handed over from Orders, its automatic service charge, and the tip on top.
  const [settlement, setSettlement] = useState<SettlementIntent | null>(() => takeSettlement());
  const [tipCents, setTipCents] = useState(0);
  const tipsOn = capabilities.enabled.has(Capability.TipsServiceCharge);
  const service = useMemo(
    () =>
      tipsOn
        ? serviceCharge(capabilities.modules.tips_service_charge, settlement?.order ?? null, totals.subtotal, businessTax())
        : { charge: 0, tax: 0 },
    [tipsOn, capabilities.modules, settlement, totals.subtotal],
  );
  const saleTotal = totals.total + service.charge + service.tax;
  const dueCents = saleTotal + (tipsOn ? tipCents : 0);
  const plan = useMemo(() => planTenders(payment, dueCents, cart.customer), [payment, dueCents, cart.customer]);
  const wholesaleOn = capabilities.enabled.has(Capability.WholesalePricing);
  const quotesOn = capabilities.enabled.has(Capability.QuotesLayaway);
  const salesOrdersOn =
    capabilities.enabled.has(Capability.SalesOrders) && session.user.permissions.includes(Permission.SalesOrders);
  const [savingOrder, setSavingOrder] = useState(false);
  const promotionsOn = capabilities.enabled.has(Capability.Promotions);
  const canSellOnAccount =
    capabilities.enabled.has(Capability.B2bCredit) && session.user.permissions.includes(Permission.PosCreditSale);
  const online = catalog.source === "api";
  const [thanks, setThanks] = useState<string | null>(null);
  const showThanks = useCallback((text: string) => {
    setThanks(text);
    window.setTimeout(() => setThanks(null), 6000);
  }, []);

  useEffect(() => {
    const bnpl = payment.choice === "bnpl" ? (payment.bnplIntent ?? null) : null;
    const intent =
      payment.choice === "qr"
        ? (payment.qrIntent ?? null)
        : bnpl?.customerUrl && (bnpl.status === "PENDING" || bnpl.status === "PAID")
          ? { payload: bnpl.customerUrl, status: bnpl.status, amountCents: bnpl.amountCents }
          : null;
    publishDisplay({
      storeName: activeStore().name,
      currency,
      lines: rows.map((row) => ({
        name: row.lines[0]?.description || row.product.name,
        quantity: row.lines.reduce((sum, line) => sum + line.quantity, 0),
        totalCents: row.lines.reduce((sum, line) => sum + lineGross(line), 0),
      })),
      subtotalCents: totals.subtotal,
      taxCents: totals.tax,
      totalCents: totals.total,
      qr: intent && intent.status !== "CANCELLED" ? { payload: intent.payload, status: intent.status, amountCents: intent.amountCents } : null,
      thanks: rows.length === 0 ? thanks : null,
    });
  }, [currency, payment.choice, payment.qrIntent, payment.bnplIntent, rows, thanks, totals]);

  useEffect(() => onDisplayReady(republishDisplay), []);
  useShellPage(charging, setNotice);
  const { navigate } = useShell();
  const needsCredit = (plan.overLimitCents > 0 || plan.holdReason !== null) && creditApproval === null;
  const belowFloor = useMemo(() => linesBelowFloor(cart.lines, floors), [cart.lines, floors]);
  const chargeBlocked =
    cart.lines.length === 0 || charging || plan.blocker !== null || needsCredit || belowFloor.length > 0;
  const categories = useMemo(
    () =>
      [...new Set(catalog.products.map((product) => product.category).filter((name): name is string => Boolean(name)))].sort(
        (left, right) => left.localeCompare(right),
      ),
    [catalog.products],
  );
  const visibleHits = useMemo(
    () => (category === null ? hits : hits.filter((hit) => hit.product.category === category)),
    [hits, category],
  );
  const gridEntries = useMemo(() => groupHits(visibleHits, catalog.products), [visibleHits, catalog.products]);
  const [picker, setPicker] = useState<{ group: ModelGroup; title?: string } | null>(null);
  const [exchange, setExchange] = useState<ExchangeIntent | null>(() => takeExchange());

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && document.querySelector(".modal-backdrop") === null) {
        setCartOpen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  useEffect(() => {
    if (!cartOpen || window.matchMedia("(min-width: 1024px)").matches) return;
    closeCartRef.current?.focus();
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [cartOpen]);

  useEffect(() => {
    setChargeError(null);
  }, [cart.lines, payment]);

  const dispatch = useCallback((action: CartAction): boolean => {
    const result = applyCart(cartRef.current, action);
    if (result.error !== null) {
      setNotice(result.error);
      return false;
    }
    cartRef.current = result.state;
    setCart(result.state);
    if (result.notice !== null) setNotice(result.notice);
    return true;
  }, []);

  const reloadCatalog = useCallback(async () => {
    try {
      setCatalog(await loadCatalog());
    } catch (error) {
      setCatalog((current) => ({
        ...current,
        message: error instanceof Error ? error.message : "Could not load products.",
      }));
    } finally {
      setCatalogLoaded(true);
    }
  }, []);

  useEffect(() => {
    void reloadCatalog();
    void syncWholesaleCaches().catch(() => undefined);
    if (inTauri()) void refreshSeries().catch(() => undefined);
    void loadFloors().then(setFloors);
  }, [reloadCatalog]);

  useEffect(() => {
    void loadPromotions().then(setPromotions);
  }, [promotionsOn]);

  useEffect(() => {
    if (!wholesaleOn && cart.mode === "WHOLESALE") dispatch({ type: "set_mode", mode: "RETAIL" });
  }, [wholesaleOn, cart.mode]);

  useEffect(() => {
    if (payment.choice === "on_account" && cart.customer?.customer_type !== "WHOLESALE") {
      setPayment((current) => ({ ...current, choice: "cash" }));
    }
  }, [cart.customer, payment.choice]);

  useEffect(() => {
    setCreditApproval(null);
  }, [cart.customer?.id]);

  // Contract prices for the attached customer: cached ones price at once, a fresh copy re-prices when it lands.
  const attachedId = cart.customer?.id ?? null;
  useEffect(() => {
    if (attachedId === null || catalog.source !== "api") return;
    let current = true;
    void refreshPricing(attachedId).then((pricing) => {
      if (current && pricing) dispatch({ type: "refresh_prices" });
    });
    return () => {
      current = false;
    };
  }, [attachedId, catalog.source, dispatch]);

  const resetSale = useCallback(() => {
    batchRef.current = null;
    const next = { ...emptyCart, mode: cartRef.current.mode };
    cartRef.current = next;
    setCart(next);
    setPayment(emptyPayment);
    setCreditApproval(null);
    setCartOpen(false);
    setCoupon(null);
  }, []);

  const saveAsSalesOrder = async () => {
    setSavingOrder(true);
    try {
      const order = await submitSalesOrder(buildSalesOrder(cartRef.current, session.user.id));
      const waiting = order.lines.reduce((sum, line) => sum + line.backordered, 0);
      resetSale();
      setNotice(
        `Sales order ${order.number} saved for ${order.customer_name}.` +
          (waiting ? ` ${waiting} units are backordered.` : " All stock is reserved.") +
          " It is delivered and invoiced from the portal.",
      );
      void reloadCatalog();
    } catch (caught) {
      setNotice(`Order not saved: ${caught instanceof Error ? caught.message : String(caught)}`);
    } finally {
      setSavingOrder(false);
    }
  };

  const select = useCallback(
    (product: ProductUpsert) => {
      if (charging) return;
      if (product.is_open_price) {
        setOpenPriceFor(product);
        return;
      }
      if (product.sold_by_weight) {
        setWeighFor(product);
        return;
      }
      if (combosFor(menu, product.id).length > 0) {
        setComboFor(product);
        return;
      }
      if (groupsFor(menu, product.id).length > 0) {
        setModifierFor(product);
        return;
      }
      if (product.is_serialized) {
        if (cartRef.current.mode === "WHOLESALE") setBulkFor(product);
        else setPendingSerial(product);
        return;
      }
      dispatch({ type: "add_product", product });
    },
    [charging, dispatch, menu],
  );

  const menuModules = capabilities.enabled.has(Capability.MenuModifiers);
  useEffect(() => {
    if (menuModules) void refreshMenu();
  }, [menuModules]);

  // A tab handed over from Orders: its unpaid lines become the cart (each keeps its tab line id).
  const settlementLoaded = useRef(false);
  useEffect(() => {
    if (settlement === null || settlementLoaded.current || !catalogLoaded) return;
    settlementLoaded.current = true;
    const wanted = new Set(settlement.itemIds);
    const lines = settlement.order.items.flatMap((item) => {
      const product = catalog.products.find((candidate) => candidate.id === item.product_id);
      return product && wanted.has(item.id)
        ? [
            {
              product,
              quantity: item.quantity,
              modifiers: item.modifiers ?? [],
              components: item.components ?? [],
              orderItemId: item.id,
            },
          ]
        : [];
    });
    dispatch({ type: "load_order", lines });
    setNotice(`Paying ${settlement.label}.`);
    if (settlement.order.channel_id) {
      setPayment((current) => ({ ...current, choice: "channel", reference: settlement.order.channel_name ?? "" }));
    }
  }, [settlement, catalogLoaded, catalog.products, dispatch]);

  // "Split equally into N" from Orders: once the bill is in the cart, open the guest-by-guest split.
  const splitGuests = useRef(settlement?.guests ?? 0);
  useEffect(() => {
    if (splitGuests.current < 2 || dueCents <= 0 || !settlementLoaded.current) return;
    const guests = splitGuests.current;
    splitGuests.current = 0;
    setPayment((current) => ({ ...current, choice: "split", guests: splitEqually(dueCents, guests) }));
  }, [dueCents]);

  // A size exchange from Returns: apply the voucher it issued and open the picker on the returned model.
  useEffect(() => {
    if (exchange === null || !catalogLoaded) return;
    setPayment((current) => ({
      ...current,
      storeCredit: { code: exchange.voucherCode, balanceCents: exchange.balanceCents },
    }));
    const returned = catalog.products.find((product) => product.id === exchange.productId);
    const group = returned?.product_model_id ? modelGroup(returned.product_model_id, catalog.products) : null;
    if (group) setPicker({ group, title: `Exchange ${exchange.productName}: choose the replacement` });
    setNotice(`Exchange: store credit ${exchange.voucherCode} is applied to this sale.`);
    setExchange(null);
  }, [exchange, catalog.products, catalogLoaded]);

  /** Enter in the search field or a wedge scan: add the product when the input identifies exactly one. */
  const submitSearch = useCallback(
    async (raw: string) => {
      const value = raw.trim();
      if (charging || value === "") return;
      if (capabilities.enabled.has(Capability.WeighedItems)) {
        const label = parseEmbeddedBarcode(value, capabilities.modules.weighed_items.embedded_barcodes);
        const product = label ? catalog.products.find((item) => item.sold_by_weight && item.plu_code === label.plu) : undefined;
        if (label && product) {
          // Price labels carry the line price; the weight is derived from the per-kg price (within a gram).
          const grams =
            label.grams ?? (product.price_cents > 0 ? Math.round(((label.priceCents ?? 0) * 1000) / product.price_cents) : 0);
          dispatch({ type: "add_weighed", product, grams });
          setQuery("");
          return;
        }
      }
      const found = await resolve(value);
      const identifier = found.find((hit) => hit.match === "identifier");
      if (identifier) {
        const status = identifier.serial_status;
        if (status === "sold" || status === "defective") {
          setNotice(`${value} belongs to ${identifier.product.name} and is already ${status}.`);
          return;
        }
        const kind = identifier.serial_kind ?? "serial";
        dispatch({
          type: "add_serials",
          product: identifier.product,
          serials: [{ value: kind === "serial" ? value.toUpperCase() : value, kind }],
        });
        setQuery("");
        return;
      }
      const exact = found.filter((hit) => hit.match === "exact");
      const chosen = exact.length === 1 ? exact[0] : found.length === 1 ? found[0] : undefined;
      if (chosen) {
        select(chosen.product);
        setQuery("");
        return;
      }
      setNotice(
        found.length === 0
          ? noMatchesMessage(value)
          : `${found.length} products match "${value}". Pick one below or keep typing.`,
      );
    },
    [charging, dispatch, resolve, select, capabilities, catalog.products],
  );

  const charge = async () => {
    if (chargeBlocked) return;
    const chargedCart = { ...cartRef.current, lines: withPromotions(cartRef.current, promotions, coupon) };
    const request: ChargeRequest = {
      cart: chargedCart,
      couponCode: coupon,
      paymentMethod: plan.paymentMethod,
      tenders: plan.tenders,
      cashierId: session.user.id,
      creditApproval: creditApproval ? { approvedById: creditApproval.approvedById, note: creditApproval.note } : null,
      shiftId: activeShiftId(),
      loyaltyPoints: plan.loyaltyPoints ?? null,
      restaurant:
        settlement || service.charge || (tipsOn && tipCents)
          ? {
              orderId: settlement?.order.id ?? null,
              orderItemIds: chargedCart.lines.map((line) => line.orderItemId).filter((id): id is string => Boolean(id)),
              serviceChargeCents: service.charge,
              serviceChargeTaxCents: service.tax,
              tipCents: tipsOn ? tipCents : 0,
            }
          : null,
    };
    const batch = await prepareNumberedBatch(batchRef.current, request);
    batchRef.current = batch;
    const total = dueCents;
    const summary =
      payment.choice === "cash" && plan.changeCents !== null
        ? `Cash sale of ${formatMoney(total, currency)} recorded. Change due ${formatMoney(plan.changeCents, currency)}.`
        : payment.choice === "on_account"
          ? `Sale of ${formatMoney(total, currency)} recorded: ${formatMoney(plan.paidCents, currency)} paid, ${formatMoney(plan.onAccountCents, currency)} on account.`
          : `${SALE_METHOD_LABELS[plan.paymentMethod]} sale of ${formatMoney(total, currency)} recorded.`;
    const saleId = batch.events.find((event) => event.entity_type === "sale")?.payload.client_sale_id;
    const numbered = invoiceOf(batch);
    const invoice = numbered ? ` Invoice ${numbered}.` : typeof saleId === "string" ? ` Invoice ${invoiceNumber(saleId)}.` : "";
    const receipt = saleReceipt({
      number: numbered ?? (typeof saleId === "string" ? invoiceNumber(saleId) : "—"),
      lines: chargedCart.lines,
      totals,
      tenders: plan.tenders,
      onAccountCents: plan.onAccountCents,
      changeCents: plan.changeCents,
      cashier: session.user.full_name,
      servedBy: cartRef.current.associate?.name ?? null,
      customer: cartRef.current.customer,
    });
    const takesCash = plan.tenders.some((tender) => tender.method === "cash" && tender.amount_cents > 0);
    const printAfter = async (message: string) => {
      setLastReceipt({ doc: receipt, saleId: typeof saleId === "string" ? saleId : "" });
      showThanks(`${receipt.number} · ${formatMoney(receipt.totalCents, currency)}`);
      const printed = await printReceipt(receipt, { kickDrawer: takesCash });
      setNotice(printed.message ? `${message} Receipt not printed: ${printed.message}` : message);
    };
    setCharging(true);
    try {
      const outcome = await submitCharge(batch);
      if (outcome.kind === "recorded" || outcome.kind === "queued") {
        setSettlement(null);
        setTipCents(0);
      }
      if (outcome.kind === "recorded") {
        resetSale();
        await printAfter(summary + invoice);
        await reloadCatalog();
      } else if (outcome.kind === "rejected") {
        batchRef.current = null;
        setNotice(`Sale not recorded: ${outcome.message}`);
        setChargeError(`Sale not recorded: ${outcome.message}`);
        await reloadCatalog();
      } else if (outcome.kind === "queued") {
        resetSale();
        await printAfter(
          `Saved on this register but not in Postgres yet.${invoice} It will sync when the API is reachable. (${outcome.message})`,
        );
      } else {
        setNotice(`Sale not recorded: ${outcome.message} Charge again to retry.`);
        setChargeError(`Sale not recorded: ${outcome.message} Charge again to retry.`);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Could not complete the sale.";
      setNotice(message);
      setChargeError(message);
    } finally {
      setCharging(false);
      setPulse((value) => value + 1);
      void syncWholesaleCaches().catch(() => undefined);
    }
  };

  const statusText = desktop
    ? report.message
    : catalog.source === "api"
      ? "Sales post directly to the API."
      : `Catalog from the bundled sample. ${catalog.message ?? ""}`.trim();

  const itemCount = totals.pieces;
  const itemLabel = `${itemCount} item${itemCount === 1 ? "" : "s"}`;
  const syncLabel = desktop ? `${report.pending} unsynced` : online ? "Live" : "Offline";
  const sync: SyncState = desktop
    ? {
        tone: report.pending > 0 ? "pending" : "synced",
        label: report.pending > 0 ? `${report.pending} unsynced` : "Synced",
        title: statusText,
      }
    : { tone: online ? "live" : "offline", label: online ? "Live" : "Offline", title: statusText };

  return (
    <>
      <BarcodeWedge onScan={(scan) => void submitSearch(scan)} />
      <PageFrame
        title="Checkout"
        sync={sync}
        actions={
          <>
            {capabilities.enabled.has(Capability.OpenOrders) ? (
              <button
                type="button"
                disabled={charging}
                onClick={() => navigate("orders")}
                title="Tables and open tabs shared by every register"
                className="hidden h-9 items-center gap-1.5 rounded-full bg-primary/10 px-3 text-xs font-semibold text-primary sm:inline-flex"
              >
                <UtensilsCrossed size={14} aria-hidden="true" />
                {settlement ? `Paying ${settlement.label}` : "Orders & tables"}
              </button>
            ) : null}
            {wholesaleOn ? (
              <ModeSwitch mode={cart.mode} disabled={charging} onChange={(mode) => dispatch({ type: "set_mode", mode })} />
            ) : null}
            {capabilities.enabled.has(Capability.GiftCards) ? (
              <button
                type="button"
                disabled={charging}
                onClick={() => setGiftCardOpen(true)}
                title="Sell a gift card"
                className="hidden h-9 items-center gap-1.5 rounded-full bg-primary/10 px-3 text-xs font-semibold text-primary sm:inline-flex"
              >
                <Gift size={14} aria-hidden="true" />
                Gift card
              </button>
            ) : null}
            {cart.mode === "RETAIL" && discountable.length > 1 ? (
              <button
                type="button"
                disabled={charging}
                onClick={() => setDiscountFor({ lines: discountable, title: "the whole sale" })}
                title="Discount the whole sale"
                className="hidden h-9 items-center gap-1.5 rounded-full bg-primary/10 px-3 text-xs font-semibold text-primary sm:inline-flex"
              >
                <Percent size={14} aria-hidden="true" />
                Discount sale
              </button>
            ) : null}
            <button
              type="button"
              onClick={() => setDrawerOpen(true)}
              disabled={charging}
              aria-label="Cash drawer"
              title="Cash drawer"
              className={ui.iconButton}
            >
              <Inbox size={18} aria-hidden="true" />
            </button>
            {lastReceipt ? (
              <button
                type="button"
                disabled={charging}
                aria-label={`Reprint receipt ${lastReceipt.doc.number}`}
                title={`Reprint ${lastReceipt.doc.number}`}
                onClick={() =>
                  void printReceipt(lastReceipt.doc, { kickDrawer: false, manual: true }).then((outcome) =>
                    setNotice(outcome.message ?? `Receipt ${lastReceipt.doc.number} sent to the printer.`),
                  )
                }
                className={ui.iconButton}
              >
                <ReceiptText size={18} aria-hidden="true" />
              </button>
            ) : null}
            {lastReceipt?.saleId ? (
              <button
                type="button"
                disabled={charging}
                aria-label={`Gift receipt for ${lastReceipt.doc.number}`}
                title="Gift receipt (no prices)"
                onClick={() =>
                  void printReceipt(asGiftReceipt(lastReceipt.doc, lastReceipt.saleId, exchangeByDate()), {
                    kickDrawer: false,
                    manual: true,
                  }).then((outcome) => setNotice(outcome.message ?? `Gift receipt for ${lastReceipt.doc.number} printed.`))
                }
                className={ui.iconButton}
              >
                <Gift size={18} aria-hidden="true" />
              </button>
            ) : null}
            {lastReceipt?.saleId && inTauri() ? (
              <button
                type="button"
                disabled={charging}
                aria-label="Open A4 tax invoice"
                title="A4 tax invoice (once the sale has synced)"
                onClick={() =>
                  void openDocumentPdf("invoice", lastReceipt.saleId, lastReceipt.doc.number).catch((error: unknown) =>
                    setNotice(error instanceof Error ? error.message : String(error)),
                  )
                }
                className={ui.iconButton}
              >
                <FileText size={18} aria-hidden="true" />
              </button>
            ) : null}
          </>
        }
        footer={
          <div className="shrink-0 border-t border-zinc-200 bg-white px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3 lg:hidden dark:border-zinc-800 dark:bg-zinc-900">
            <button
              type="button"
              aria-controls="current-sale"
              aria-expanded={cartOpen}
              onClick={() => setCartOpen(true)}
              className="flex h-16 w-full items-center gap-4 rounded-xl bg-primary-500 px-5 text-white shadow-lg shadow-primary-500/25 transition-colors hover:bg-primary-600 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-primary-500/30 active:scale-[0.99]"
            >
              <span className="relative">
                <ShoppingCart size={22} aria-hidden="true" />
                {itemCount > 0 ? (
                  <span className="absolute -right-2.5 -top-2 flex h-5 min-w-5 items-center justify-center rounded-full bg-white px-1 text-[11px] font-bold tabular-nums text-primary-600">
                    {itemCount}
                  </span>
                ) : null}
              </span>
              <span className="text-left leading-tight">
                <span className="block text-xs font-medium text-white/80">{itemLabel}</span>
                <span className="block text-sm font-semibold">{itemCount > 0 ? "Review & charge" : "Open sale"}</span>
              </span>
              <span className="ml-auto text-xl font-bold tabular-nums">{formatMoney(dueCents, currency)}</span>
              <ChevronUp size={20} aria-hidden="true" className="md:rotate-90" />
            </button>
          </div>
        }
        drawer={
          <CheckoutSidebar
            open={cartOpen}
            onDismiss={() => setCartOpen(false)}
            header={
              <DrawerHeader
                title="Current sale"
                count={itemLabel}
                badge={
                  <span
                    className={`rounded-full px-2.5 py-1 text-[11px] font-semibold tabular-nums ring-1 ${
                      online
                        ? "bg-emerald-500/10 text-emerald-700 ring-emerald-500/20 dark:text-emerald-300"
                        : "bg-amber-500/10 text-amber-700 ring-amber-500/25 dark:text-amber-300"
                    }`}
                  >
                    {syncLabel}
                  </span>
                }
              >
                <button
                  ref={closeCartRef}
                  type="button"
                  aria-label="Back to products"
                  onClick={() => setCartOpen(false)}
                  className="-mr-2 flex h-11 w-11 items-center justify-center rounded-full text-zinc-500 transition-colors hover:bg-zinc-100 hover:text-zinc-900 lg:hidden dark:text-zinc-400 dark:hover:bg-white/10 dark:hover:text-white"
                >
                  <X size={20} aria-hidden="true" />
                </button>
              </DrawerHeader>
            }
            customer={
              <>
                <CustomerBar
                  session={session}
                  customer={cart.customer}
                  currency={currency}
                  disabled={charging}
                  pendingCents={payment.choice === "on_account" ? plan.onAccountCents : 0}
                  onAttach={(customer: RegisterCustomer | null) => dispatch({ type: "attach_customer", customer })}
                />
                {!capabilities.foodAndBeverage ? (
                  <ServedByPicker
                    storeId={activeStore().id}
                    cashierId={session.user.id}
                    cashierName={session.user.full_name}
                    associate={cart.associate ?? null}
                    disabled={charging}
                    onChange={(associate) => dispatch({ type: "set_associate", associate })}
                  />
                ) : null}
              </>
            }
            cart={
              <CartList
                rows={rows}
                currency={currency}
                tier={tier}
                disabled={charging}
                floorFor={(productId) => floors.get(productId)?.floor_cents ?? null}
                onPacks={(lineId, packs) => dispatch({ type: "set_packs", lineId, packs })}
                onUnit={(lineId, unitType) => dispatch({ type: "set_unit", lineId, unitType })}
                onRemove={(item) => {
                  const removed = dispatch(
                    item.groupId !== null ? { type: "remove_group", groupId: item.groupId } : { type: "remove_line", lineId: item.key },
                  );
                  if (removed) logItemVoid(item, cart.mode);
                }}
                onOverride={setOverrideRow}
                onClearOverride={(item) => dispatch({ type: "clear_override", lineIds: item.lines.map((line) => line.lineId) })}
                onAddSerials={(item) => setBulkFor(item.product)}
                onApproveFloor={setFloorRow}
                onDiscount={
                  cart.mode === "RETAIL"
                    ? (item) => {
                        const lines = pricedLines.filter((line) => item.lines.some((own) => own.lineId === line.lineId));
                        setDiscountFor({ lines, title: item.product.name });
                      }
                    : undefined
                }
                onClearDiscount={(item) => dispatch({ type: "clear_discounts", lineIds: item.lines.map((line) => line.lineId) })}
              />
            }
            summary={(foldToggle) => (
              <SaleSummary
                totals={totals}
                currency={currency}
                taxRateBps={businessTax().enforced ? businessTax().standard_rate_bps : null}
                promotionCents={promoSavings}
                discountCents={manualSavings}
                serviceChargeCents={service.charge}
                serviceChargeTaxCents={service.tax}
                tipCents={tipsOn ? tipCents : 0}
                settling={settlement?.label ?? null}
                action={foldToggle}
              />
            )}
            paymentLabel={tenderOptions.find((option) => option.value === payment.choice)?.label ?? "Payment"}
            payment={
              <>
              {tipsOn && cart.lines.length > 0 ? (
                <div className="mb-2">
                  <TipRow
                    billCents={saleTotal}
                    presetsBps={capabilities.modules.tips_service_charge.tip_presets_bps}
                    tipCents={tipCents}
                    currency={currency}
                    disabled={charging}
                    onChange={setTipCents}
                  />
                </div>
              ) : null}
              <TenderPanel
                coupon={
                  couponsOffered
                    ? {
                        applied: coupon !== null,
                        node: <CouponRow promotions={promotions} coupon={coupon} disabled={charging} onChange={setCoupon} />,
                      }
                    : null
                }
                draft={payment}
                plan={plan}
                totalCents={dueCents}
                currency={currency}
                customer={cart.customer}
                canSellOnAccount={canSellOnAccount}
                creditApprover={creditApproval?.approverName ?? null}
                disabled={charging}
                onChange={setPayment}
                onRequestCreditApproval={() => setAskCredit(true)}
                canTradeIn={online && session.user.permissions.includes(Permission.PosTradeIn)}
                cashierId={session.user.id}
                verifyManager={(username, pin) => verifyManager(session, username, pin, Permission.PosPriceOverride)}
                products={catalog.products}
                deliveryChannel={settlement?.order.channel_id ? (settlement.order.channel_name ?? "the delivery app") : null}
              />
              </>
            }
            notices={
              <>
                {/* The cash field itself asks for the amount; other tenders explain what they still need. */}
                {plan.blocker && cart.lines.length > 0 && payment.choice !== "cash" ? (
                  <p className="text-xs text-zinc-500 dark:text-zinc-400">{plan.blocker}</p>
                ) : null}
                {chargeError ? (
                  <p className="flex items-start gap-2 rounded-xl border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-700 dark:text-red-200">
                    <AlertTriangle size={14} aria-hidden="true" className="mt-0.5 shrink-0" />
                    {chargeError}
                  </p>
                ) : null}
              </>
            }
            footer={
              <div className="flex gap-2">
                {quotesOn ? (
                  <button
                    type="button"
                    disabled={cart.lines.length === 0 || charging || !online}
                    title={online ? "Reserve the stock and generate a PDF quotation" : "Quotes need a live connection to reserve stock."}
                    onClick={() => setQuoteOpen(true)}
                    className={`${ui.secondaryAction} h-14 w-16 shrink-0 flex-col gap-0.5 rounded-2xl text-[11px]`}
                  >
                    <FileText size={18} aria-hidden="true" />
                    Quote
                  </button>
                ) : null}
                {salesOrdersOn && cart.mode === "WHOLESALE" && cart.customer !== null ? (
                  <button
                    type="button"
                    disabled={cart.lines.length === 0 || charging || savingOrder || !online}
                    title={online ? "Save as a sales order to deliver and invoice later" : "Sales orders need a live connection."}
                    onClick={() => void saveAsSalesOrder()}
                    className={`${ui.secondaryAction} h-14 w-16 shrink-0 flex-col gap-0.5 rounded-2xl text-[11px]`}
                  >
                    <Truck size={18} aria-hidden="true" />
                    Order
                  </button>
                ) : null}
                <button
                  type="button"
                  disabled={charging}
                  title="Hold this sale or recall a held one"
                  onClick={() => setHeldOpen(true)}
                  className={`${ui.secondaryAction} h-14 w-16 shrink-0 flex-col gap-0.5 rounded-2xl text-[11px]`}
                >
                  <PauseCircle size={18} aria-hidden="true" />
                  {cart.lines.length > 0 ? "Hold" : "Recall"}
                </button>
                <button type="button" disabled={chargeBlocked} onClick={() => void charge()} className={`${ui.primaryAction} flex-1 rounded-full`}>
                  {charging ? "Recording sale…" : `Charge ${formatMoney(dueCents, currency)}`}
                </button>
              </div>
            }
          />
        }
      >
        <div className="space-y-4 p-5">
          <p className="flex items-center gap-2 text-xs text-zinc-500 dark:text-zinc-400">
            <span
              aria-hidden="true"
              className={`h-2 w-2 shrink-0 rounded-full ${online ? "bg-emerald-500" : "bg-amber-500"}`}
            />
            {statusText}
          </p>

          {cart.mode === "WHOLESALE" ? (
            <p className="rounded-xl border border-primary-500/20 bg-primary-500/10 px-4 py-3 text-sm text-zinc-700 dark:text-zinc-200">
              Wholesale pricing at <span className="font-semibold text-zinc-950 dark:text-white">{PRICE_TIER_LABELS[tier]}</span>
              {cart.customer ? ` for ${cart.customer.company_name ?? cart.customer.name}` : ""}. Volume breaks apply
              automatically as quantities grow.
            </p>
          ) : null}

          <div>
            <SearchInput
              id="product-search"
              label="Search Product, Model, Barcode, or IMEI"
              inputRef={searchRef}
              value={query}
              placeholder="Scan or search product, model, barcode, IMEI…"
              onChange={setQuery}
              onSubmit={(value) => void submitSearch(value)}
              onShortcut={closeCart}
              actionLabel="Search Catalog"
            />
            <p className="mt-2.5 min-h-5 text-sm text-zinc-600 dark:text-zinc-400" role="status">
              {notice}
            </p>
          </div>

          {categories.length > 0 ? (
            <div className="no-scrollbar -mx-5 flex gap-2 overflow-x-auto px-5" role="group" aria-label="Categories">
              {[null, ...categories].map((name) => {
                const active = category === name;
                return (
                  <button
                    key={name ?? "all"}
                    type="button"
                    aria-pressed={active}
                    onClick={() => setCategory(name)}
                    className={`h-10 shrink-0 rounded-full px-4 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/50 ${
                      active
                        ? "bg-primary-500 text-white shadow-sm shadow-primary-500/25"
                        : "border border-zinc-200 bg-white text-zinc-600 hover:border-zinc-300 hover:text-zinc-900 dark:border-zinc-800 dark:bg-zinc-900/60 dark:text-zinc-300 dark:hover:border-zinc-700 dark:hover:text-white"
                    }`}
                  >
                    {name ?? "All products"}
                  </button>
                );
              })}
            </div>
          ) : null}

          <p className={ui.label}>
            {searching
              ? "Searching…"
              : `${visibleHits.length} ${visibleHits.length === 1 ? "product" : "products"}${
                  debouncedQuery.trim() !== "" ? ` matching "${debouncedQuery.trim()}"` : ""
                }${category ? ` in ${category}` : ""}`}
          </p>
          {visibleHits.length === 0 && !searching ? (
            <p className="rounded-2xl border border-dashed border-zinc-300 p-8 text-center text-sm text-zinc-500 dark:border-zinc-700 dark:text-zinc-400">
              {debouncedQuery.trim() !== ""
                ? noMatchesMessage(debouncedQuery.trim())
                : category
                  ? `No products in ${category} at this register.`
                  : "No products in this register's catalog yet."}
            </p>
          ) : null}
          <ul className="grid grid-cols-1 gap-3 min-[420px]:grid-cols-2 md:grid-cols-3 2xl:grid-cols-4">
            {gridEntries.slice(0, GRID_LIMIT).map((entry) =>
              entry.kind === "model" ? (
                <ModelCard
                  key={`model-${entry.group.modelId}`}
                  group={entry.group}
                  currency={currency}
                  disabled={charging}
                  onOpen={() => setPicker({ group: entry.group })}
                />
              ) : (
                <ProductCard
                  key={entry.hit.product.id}
                  hit={entry.hit}
                  preview={tierPreview(entry.hit.product, tier)}
                  currency={currency}
                  disabled={charging}
                  onSelect={select}
                  onCheckBranches={(product) => setBranchCheck({ product })}
                />
              ),
            )}
          </ul>
          {gridEntries.length > GRID_LIMIT ? (
            <p className="mt-3 text-center text-sm text-zinc-500 dark:text-zinc-400">
              Showing the first {GRID_LIMIT} of {gridEntries.length.toLocaleString()}. Scan, search or pick a category to
              find the rest.
            </p>
          ) : null}
        </div>
      </PageFrame>

      {picker ? (
        <VariantPickerModal
          group={picker.group}
          currency={currency}
          title={picker.title}
          onClose={() => setPicker(null)}
          onPick={(product) => {
            setPicker(null);
            select(product);
          }}
        />
      ) : null}
      {modifierFor ? (
        <ModifierPickerModal
          product={modifierFor}
          groups={groupsFor(menu, modifierFor.id)}
          currency={currency}
          onClose={() => setModifierFor(null)}
          onConfirm={(modifiers) => {
            if (dispatch({ type: "add_product", product: modifierFor, modifiers })) setModifierFor(null);
          }}
        />
      ) : null}
      {comboFor ? (
        <ComboBuilderModal
          product={comboFor}
          slots={combosFor(menu, comboFor.id)}
          currency={currency}
          onClose={() => setComboFor(null)}
          onConfirm={(components) => {
            if (dispatch({ type: "add_product", product: comboFor, components })) setComboFor(null);
          }}
        />
      ) : null}
      {weighFor ? (
        <WeighModal
          product={weighFor}
          currency={currency}
          onClose={() => setWeighFor(null)}
          onConfirm={(grams) => {
            if (dispatch({ type: "add_weighed", product: weighFor, grams })) setWeighFor(null);
          }}
        />
      ) : null}
      {openPriceFor ? (
        <OpenPriceModal
          product={openPriceFor}
          currency={currency}
          allowed={session.user.permissions.includes(Permission.PosOpenPrice)}
          onClose={() => setOpenPriceFor(null)}
          onConfirm={(description, unitPriceCents) => {
            if (dispatch({ type: "add_open_price", product: openPriceFor, unitPriceCents, description })) setOpenPriceFor(null);
          }}
        />
      ) : null}
      {pendingSerial ? (
        <SerialPickerModal
          session={session}
          product={pendingSerial}
          inCart={cart.lines.map((line) => line.serialValue).filter((value): value is string => value !== null)}
          onClose={() => setPendingSerial(null)}
          onConfirm={(value, kind) => {
            dispatch({ type: "add_serials", product: pendingSerial, serials: [{ value, kind }] });
            setPendingSerial(null);
          }}
        />
      ) : null}
      {bulkFor ? (
        <BulkImeiModal
          product={bulkFor}
          inCart={cart.lines.map((line) => line.serialValue).filter((value): value is string => value !== null)}
          initialQuantity={Math.max(1, bulkFor.prices?.find((row) => row.price_tier === tier)?.min_order_quantity ?? 10)}
          onClose={() => setBulkFor(null)}
          onConfirm={(serials) => {
            if (dispatch({ type: "add_serials", product: bulkFor, serials })) setBulkFor(null);
          }}
        />
      ) : null}
      {discountFor ? (
        <DiscountModal
          session={session}
          lines={discountFor.lines}
          title={discountFor.title}
          currency={currency}
          onClose={() => setDiscountFor(null)}
          onApplied={(discounts) => {
            dispatch({ type: "set_discounts", discounts });
            setDiscountFor(null);
          }}
        />
      ) : null}
      {giftCardOpen ? (
        <GiftCardSellModal
          currency={currency}
          storeId={activeStore().id}
          onClose={() => setGiftCardOpen(false)}
          onAdd={(product, amountCents, code) => {
            dispatch({ type: "add_gift_card", product, amountCents, code });
            setGiftCardOpen(false);
          }}
        />
      ) : null}
      {overrideRow ? (
        <PriceOverrideModal
          session={session}
          row={overrideRow}
          currency={currency}
          onClose={() => setOverrideRow(null)}
          onApproved={(override) => {
            dispatch({ type: "override_price", lineIds: overrideRow.lines.map((line) => line.lineId), override });
            setOverrideRow(null);
          }}
        />
      ) : null}
      {floorRow ? (
        <ManagerApprovalModal
          reasons={[
            `${floorRow.product.name} at ${formatMoney(floorRow.lines[0]?.unitPriceCents ?? 0, currency)} is below the ${formatMoney(
              floors.get(floorRow.product.id)?.floor_cents ?? 0,
              currency,
            )} margin floor`,
          ]}
          subtitle="A manager allowed to sell below the margin floor must enter their PIN."
          verify={(username, pin) => verifyManager(session, username, pin, Permission.PosBelowFloorOverride)}
          remote={{
            kind: "BELOW_FLOOR",
            requestedById: session.user.id,
            title: `Below margin floor: ${floorRow.product.name}`,
            amountCents: floorRow.lines[0]?.unitPriceCents ?? 0,
          }}
          onClose={() => setFloorRow(null)}
          onApproved={(approver, note) => {
            dispatch({
              type: "approve_floor",
              lineIds: floorRow.lines.map((line) => line.lineId),
              override: {
                approvedById: approver.id,
                approverName: approver.full_name,
                note,
                unitPriceCents: floorRow.lines[0]?.unitPriceCents ?? 0,
              },
            });
            setFloorRow(null);
          }}
        />
      ) : null}
      {askCredit && cart.customer ? (
        <ManagerApprovalModal
          reasons={[
            ...(plan.holdReason ? [`${cart.customer.company_name ?? cart.customer.name} is on credit hold: ${plan.holdReason}`] : []),
            ...(plan.overLimitCents > 0
              ? [
                  `${cart.customer.company_name ?? cart.customer.name} goes ${formatMoney(plan.overLimitCents, currency)} over a ${formatMoney(cart.customer.credit_limit_cents, currency)} limit`,
                ]
              : []),
          ]}
          subtitle="A manager who manages customer accounts must enter their PIN."
          verify={(username, pin) => verifyManager(session, username, pin, Permission.CustomersManage)}
          remote={{
            kind: "CREDIT_LIMIT",
            requestedById: session.user.id,
            title: `Credit sale for ${cart.customer.company_name ?? cart.customer.name}`,
            amountCents: totals.total,
          }}
          onClose={() => setAskCredit(false)}
          onApproved={(approver, note) => {
            setCreditApproval({ approvedById: approver.id, approverName: approver.full_name, note });
            setAskCredit(false);
          }}
        />
      ) : null}
      {quoteOpen ? (
        <QuoteModal
          totalCents={totals.total}
          pieces={totals.pieces}
          currency={currency}
          customer={cart.customer}
          onClose={() => setQuoteOpen(false)}
          onSave={async (days, layaway) => {
            const body = buildQuote(cartRef.current, session.user.id, days);
            if (layaway) {
              body.quote_kind = "LAYAWAY";
              body.deposit =
                layaway.amountCents > 0
                  ? { id: crypto.randomUUID(), amount_cents: layaway.amountCents, method: layaway.method, shift_id: activeShiftId() }
                  : null;
            }
            const quote = await submitQuote(body);
            if (layaway && layaway.method === "cash" && layaway.amountCents > 0 && activeShiftId()) {
              await recordCashMovement({
                id: crypto.randomUUID(),
                kind: "PAY_IN",
                amount_cents: layaway.amountCents,
                reason: `Layaway deposit ${quote.number}`,
                occurred_at: new Date().toISOString(),
              }).catch(() => undefined);
            }
            resetSale();
            setNotice(
              layaway
                ? `Layaway ${quote.number} saved with ${formatMoney(layaway.amountCents, currency)} deposit. Goods are held until it is paid off or expires.`
                : `Quote ${quote.number} saved. Stock is reserved until it expires or converts.`,
            );
            void reloadCatalog();
            return quote;
          }}
        />
      ) : null}
      {branchCheck ? (
        <BranchCheckModal
          product={branchCheck.product}
          products={catalog.products}
          onClose={() => setBranchCheck(null)}
        />
      ) : null}
      {drawerOpen ? (
        <CashDrawerModal currency={currency} onClose={() => setDrawerOpen(false)} onLogged={setNotice} />
      ) : null}
      {heldOpen ? (
        <HeldCartsModal
          currency={currency}
          canHold={cart.lines.length > 0}
          cartEmpty={cart.lines.length === 0}
          onHold={async (label) => {
            await holdCart(cartRef.current, label, totals.total, session.user.full_name);
            resetSale();
            setNotice(`"${label}" is on hold. Recall it from Hold / Recall.`);
          }}
          onRecall={(held) => {
            batchRef.current = null;
            cartRef.current = held.payload;
            setCart(held.payload);
            setNotice(`Recalled "${held.label}". Prices and stock are checked again when you charge.`);
          }}
          onClose={() => setHeldOpen(false)}
        />
      ) : null}
    </>
  );
}
