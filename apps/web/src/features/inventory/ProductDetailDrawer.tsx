import seed from "@ai-pos/catalog/seed.json";
import {
  GENDER_LABELS,
  PRICE_TIERS,
  PRICE_TIER_LABELS,
  Permission,
  unitLabel,
  formatMoney,
  type Availability,
  type Product,
  type ProductCosting,
  type ProductPurchaseHistory,
  type SerialStatus,
} from "@ai-pos/shared-types";
import { Download, MapPin, Pencil, ScanLine, X } from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../../lib/auth";
import {
  PurchasesTab,
  ResourceView,
  SalesTab,
  SerialsTab,
  SkeletonCards,
  SkeletonRows,
  TimelineTab,
} from "./ProductHistoryTabs";
import { PhotoGallery } from "./PhotoGallery";
import { printSpecSheet, type SpecRow } from "./specSheet";
import { useProductDetails, type Resource } from "./useProductDetails";

type TabId = "details" | "sales" | "purchases" | "serials" | "timeline";

const taxRateBps: number = seed.tax_rate_bps;

function specRows(product: Product, branches: Availability["branches"]): SpecRow[] {
  const bins = branches
    .filter((branch) => branch.aisle_shelf_location)
    .map((branch) => `${branch.store_code}: ${branch.aisle_shelf_location}`);
  return [
    { label: "Barcode", value: product.barcode },
    { label: "Model number", value: product.model_number ?? "—" },
    { label: "Brand", value: product.brand ?? "—" },
    { label: "Tax rate", value: `${(taxRateBps / 100).toFixed(2)}% standard` },
    { label: "Warranty months", value: "Not recorded" },
    { label: "Aisle / bin", value: bins.length ? bins.join(", ") : "—" },
    { label: "Tracking", value: product.is_serialized ? "Per unit (IMEI / serial)" : "By quantity" },
    ...fashionRows(product),
  ];
}

function fashionRows(product: Product): SpecRow[] {
  const rows: [string, string | null | undefined][] = [
    ["Season", product.season],
    ["Collection", product.collection],
    ["Gender", product.gender ? GENDER_LABELS[product.gender] : null],
    ["Material", product.material],
    ["Fit", product.fit],
    ["Care", product.care],
  ];
  return rows.flatMap(([label, value]) => (value ? [{ label, value }] : []));
}

function Stat({
  label,
  value,
  hint,
  tone = "light",
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "dark" | "light" | "accent";
}) {
  const styles = {
    dark: "bg-charcoal text-white",
    accent: "bg-accent text-white",
    light: "bg-surface text-charcoal",
  }[tone];
  return (
    <div className={`min-w-0 rounded-2xl p-4 ${styles}`}>
      <p
        className={`text-[11px] font-medium uppercase tracking-wide ${tone === "light" ? "text-charcoal/50" : "text-white/60"}`}
      >
        {label}
      </p>
      <p className="mt-1.5 truncate text-xl font-bold tabular-nums">{value}</p>
      {hint ? (
        <p className={`mt-0.5 truncate text-xs ${tone === "light" ? "text-charcoal/50" : "text-white/60"}`}>{hint}</p>
      ) : null}
    </div>
  );
}

function DetailsTab({
  product,
  availability,
  purchases,
  costing,
  canManagePhotos,
}: {
  product: Product;
  availability: Resource<Availability>;
  purchases: Resource<ProductPurchaseHistory>;
  costing: Resource<ProductCosting>;
  canManagePhotos: boolean;
}) {
  const latest = purchases.state === "ready" ? purchases.data.latest_unit_cost_cents : null;
  const costs = costing.state === "ready" ? costing.data : null;
  const lastPurchase = costs?.last_purchase_cost_cents ?? latest;
  const valuationUnit =
    costs && costs.on_hand > 0 ? Math.round(costs.inventory_value_cents / costs.on_hand) : lastPurchase;
  const margin =
    valuationUnit !== null && product.price_cents > 0
      ? ((product.price_cents - valuationUnit) / product.price_cents) * 100
      : null;
  const money = (cents: number | null | undefined) =>
    cents === null || cents === undefined ? "—" : formatMoney(cents, product.currency);

  return (
    <ResourceView
      resource={availability}
      skeleton={
        <div className="space-y-5">
          <SkeletonCards />
          <SkeletonRows rows={5} />
        </div>
      }
      forbiddenText="You cannot view stock levels."
    >
      {({ branches }) => {
        const onHand = branches.reduce((sum, branch) => sum + branch.quantity_on_hand, 0);
        const reserved = branches.reduce((sum, branch) => sum + branch.quantity_reserved, 0);
        const stocked = branches.filter((branch) => branch.quantity_on_hand > 0);
        return (
          <div className="space-y-6">
            <div className="grid grid-cols-2 gap-3 xl:grid-cols-3">
              <Stat
                label={`Retail price (${product.currency})`}
                value={formatMoney(product.price_cents, product.currency)}
                tone="dark"
              />
              <Stat label="Last purchase price" value={money(lastPurchase)} hint="Latest receipt. Older receipts keep their own cost." />
              <Stat
                label="Weighted average"
                value={money(costs?.weighted_average_cost_cents ?? null)}
                hint={costs ? `Running average. Valuation method: ${costs.method === "FIFO" ? "FIFO" : "Weighted average"}` : "Managers only"}
              />
              <Stat
                label="Default purchase cost"
                value={money(costs?.default_cost_cents ?? null)}
                hint="Reference for the next purchase"
              />
              <Stat
                label="Inventory value"
                value={costs ? formatMoney(costs.inventory_value_cents, product.currency) : "—"}
                hint={
                  costs
                    ? `${costs.on_hand} on hand, ${costs.available} available${costs.uncosted_quantity ? `, ${costs.uncosted_quantity} uncosted` : ""}`
                    : "From cost layers"
                }
              />
              <Stat
                label="Estimated margin"
                value={margin === null ? "—" : `${margin.toFixed(1)}%`}
                hint={
                  margin === null
                    ? "Needs a current cost"
                    : `${money(product.price_cents - (valuationUnit ?? 0))} per unsold unit. Not realized profit.`
                }
                tone={margin !== null && margin < 10 ? "accent" : "light"}
              />
              <Stat
                label="On hand"
                value={String(onHand)}
                hint={product.is_serialized ? "Serialized units" : "Units"}
              />
              <Stat label="Reserved" value={String(reserved)} hint={`${onHand - reserved} available`} />
              <Stat
                label="Branch locations"
                value={String(stocked.length)}
                hint={`of ${branches.length} branch${branches.length === 1 ? "" : "es"} stocked`}
              />
            </div>

            <PhotoGallery
              path={`/api/v1/inventory/products/${product.id}/images`}
              canManage={canManagePhotos}
              fallbackUrl={product.thumb_url}
            />

            <PriceTiers product={product} />

            <section>
              <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-charcoal/50">Specifications</h4>
              <dl className="grid gap-x-6 sm:grid-cols-2">
                {specRows(product, branches).map((row) => (
                  <div
                    key={row.label}
                    className="flex items-baseline justify-between gap-4 border-b border-line py-2.5 text-sm"
                  >
                    <dt className="shrink-0 text-charcoal/60">{row.label}</dt>
                    <dd
                      className={`min-w-0 truncate text-right font-medium ${
                        row.value === "Not recorded" || row.value === "—" ? "text-charcoal/40" : ""
                      } ${row.label === "Barcode" || row.label === "Model number" ? "font-mono text-xs" : ""}`}
                      title={row.value}
                    >
                      {row.value}
                    </dd>
                  </div>
                ))}
              </dl>
            </section>

            <section>
              <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-charcoal/50">Stock by branch</h4>
              {branches.length === 0 ? (
                <p className="rounded-2xl bg-surface px-4 py-6 text-center text-sm text-charcoal/60">
                  Not stocked at any branch yet.
                </p>
              ) : (
                <ul className="space-y-2">
                  {branches.map((branch) => {
                    const share = onHand === 0 ? 0 : (branch.quantity_on_hand / onHand) * 100;
                    return (
                      <li key={branch.store_id} className="rounded-2xl border border-line px-4 py-3">
                        <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                          <span className="flex min-w-0 items-center gap-2">
                            <MapPin size={14} aria-hidden="true" className="shrink-0 text-accent" />
                            <span className="font-semibold">{branch.store_code}</span>
                            <span className="truncate text-charcoal/60">{branch.store_name}</span>
                            {branch.is_warehouse ? (
                              <span className="rounded-full bg-surface px-2 py-0.5 text-[10px] font-semibold uppercase">
                                Warehouse
                              </span>
                            ) : null}
                          </span>
                          <span className="tabular-nums">
                            <span className="font-bold">{branch.quantity_on_hand}</span>
                            <span className="text-charcoal/50"> on hand · {branch.quantity_reserved} reserved</span>
                          </span>
                        </div>
                        <div className="mt-2 flex items-center gap-3">
                          <div className="h-1.5 flex-1 rounded-full bg-surface">
                            <div className="h-1.5 rounded-full bg-charcoal" style={{ width: `${share}%` }} />
                          </div>
                          <span className="shrink-0 font-mono text-[11px] text-charcoal/50">
                            {branch.aisle_shelf_location ?? "No bin"}
                          </span>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </section>
          </div>
        );
      }}
    </ResourceView>
  );
}

function PriceTiers({ product }: { product: Product }) {
  const rows = PRICE_TIERS.map((tier) => ({
    tier,
    row: product.prices?.find((item) => item.price_tier === tier) ?? null,
  })).filter(({ tier, row }) => tier === "RETAIL" || row !== null);
  return (
    <section>
      <div className="mb-2 flex items-center justify-between">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-charcoal/50">Price tiers</h4>
        <Link to="/inventory/pricing" className="text-xs font-semibold text-accent hover:underline">
          Manage pricing
        </Link>
      </div>
      <div className="overflow-hidden rounded-2xl border border-line">
        <table className="w-full text-left text-sm">
          <thead className="bg-surface text-[11px] uppercase tracking-wide text-charcoal/50">
            <tr>
              <th className="px-4 py-2 font-medium">Tier</th>
              <th className="px-4 py-2 text-right font-medium">Price</th>
              <th className="px-4 py-2 text-right font-medium">Min. order</th>
              <th className="px-4 py-2 font-medium">Volume breaks</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ tier, row }) => (
              <tr key={tier} className="border-t border-line">
                <td className="px-4 py-2.5 font-medium">{PRICE_TIER_LABELS[tier]}</td>
                <td className="px-4 py-2.5 text-right font-semibold tabular-nums">
                  {formatMoney(tier === "RETAIL" ? product.price_cents : (row?.price_cents ?? 0), product.currency)}
                </td>
                <td className="px-4 py-2.5 text-right tabular-nums">{row?.min_order_quantity ?? 1}</td>
                <td className="px-4 py-2.5 text-xs text-charcoal/70 tabular-nums">
                  {row?.volume_discounts.length
                    ? row.volume_discounts
                        .map((item) => `${item.min_qty}+ ${formatMoney(item.price_cents, product.currency)}`)
                        .join(" · ")
                    : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {product.sellable_units && product.sellable_units.length > 1 ? (
        <p className="mt-2 text-xs text-charcoal/60">
          Sold as {product.sellable_units.map((unit) => unitLabel(product, unit).toLowerCase()).join(", ")}.
        </p>
      ) : null}
    </section>
  );
}

function Tag({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-semibold ${className}`}>
      {children}
    </span>
  );
}

function HeaderButton({
  label,
  onClick,
  children,
  icon,
}: {
  label: string;
  onClick: () => void;
  children?: ReactNode;
  icon: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className={`inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-full border border-line bg-white text-sm font-semibold transition hover:border-charcoal ${
        children ? "px-4" : "w-10"
      }`}
    >
      {icon}
      {children}
    </button>
  );
}

export function ProductDetailDrawer({
  product: listed,
  closing,
  escapeEnabled,
  refreshKey,
  onClose,
  onEdit,
}: {
  product: Product;
  closing: boolean;
  escapeEnabled: boolean;
  refreshKey: number;
  onClose: () => void;
  onEdit: ((product: Product) => void) | null;
}) {
  const { can } = useAuth();
  const [tab, setTab] = useState<TabId>("details");
  const [serialStatus, setSerialStatus] = useState<SerialStatus | null>(null);
  const [serialQuery, setSerialQuery] = useState("");
  const detail = useProductDetails(
    listed.id,
    { enabled: listed.is_serialized, status: serialStatus, query: serialQuery },
    refreshKey,
  );
  const product = detail.product.state === "ready" ? detail.product.data : listed;
  const panelRef = useRef<HTMLElement>(null);
  const titleId = useId();

  useEffect(() => {
    if (!escapeEnabled) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [escapeEnabled, onClose]);

  useEffect(() => {
    panelRef.current?.focus({ preventScroll: true });
  }, [listed.id]);

  useEffect(() => {
    const overlay = window.matchMedia("(max-width: 1023px)");
    const apply = () => {
      document.body.style.overflow = overlay.matches ? "hidden" : "";
    };
    apply();
    overlay.addEventListener("change", apply);
    return () => {
      overlay.removeEventListener("change", apply);
      document.body.style.overflow = "";
    };
  }, []);

  const tabs: { id: TabId; label: string; locked?: boolean }[] = [
    { id: "details", label: "Details" },
    { id: "sales", label: "Sales History", locked: !can(Permission.PortalReportsRead) },
    { id: "purchases", label: "Purchase History", locked: !can(Permission.PortalInventoryManage) },
    ...(product.is_serialized ? [{ id: "serials" as const, label: "Serials / IMEIs" }] : []),
    { id: "timeline", label: "Stock Timeline" },
  ];
  const active = tabs.some((item) => item.id === tab) ? tab : "details";
  const branches = detail.availability.state === "ready" ? detail.availability.data.branches : [];

  return (
    <>
      <div
        className={`drawer-backdrop fixed inset-0 z-40 bg-charcoal/40 backdrop-blur-[8px] lg:hidden ${closing ? "opacity-0" : ""}`}
        onClick={onClose}
        aria-hidden="true"
      />
      <aside
        ref={panelRef}
        tabIndex={-1}
        role="dialog"
        aria-labelledby={titleId}
        data-state={closing ? "closing" : "open"}
        className="drawer-panel fixed inset-y-0 right-0 z-40 flex w-full flex-col overflow-hidden bg-white shadow-2xl outline-none sm:max-w-xl md:max-w-2xl split-drawer-h lg:sticky lg:top-5 lg:z-auto lg:w-auto lg:min-w-0 lg:max-w-none lg:basis-1/2 lg:self-start lg:rounded-card lg:border lg:border-line lg:shadow-none"
      >
        <header className="sticky top-0 z-20 flex-none border-b border-line bg-white px-5 pb-4 pt-5 sm:px-6">
          <div className="flex items-start justify-between gap-3">
            <div className="flex min-w-0 flex-wrap items-center gap-1.5">
              <Tag className="bg-charcoal font-mono text-white">{product.sku}</Tag>
              <Tag className="bg-surface text-charcoal">{product.category}</Tag>
              {product.sub_category ? <Tag className="bg-surface text-charcoal/70">{product.sub_category}</Tag> : null}
              {product.is_serialized ? (
                <Tag className="bg-accent text-white">
                  <ScanLine size={12} aria-hidden="true" /> IMEI Tracked
                </Tag>
              ) : null}
            </div>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close panel"
              title="Close panel (Esc)"
              className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-charcoal text-white transition hover:bg-accent"
            >
              <X size={17} aria-hidden="true" />
            </button>
          </div>
          <div className="mt-3 flex flex-wrap items-end justify-between gap-x-4 gap-y-3">
            <div className="min-w-0">
              <h3 id={titleId} className="text-2xl font-bold leading-tight tracking-tight">
                {product.name}
              </h3>
              <p className="mt-1 text-sm text-charcoal/60">
                {product.brand ?? "Unbranded"}
                {product.model_number ? (
                  <>
                    {" · "}
                    <span className="font-mono text-xs">{product.model_number}</span>
                  </>
                ) : null}
                {" · "}
                <span className="font-semibold text-charcoal">
                  {formatMoney(product.price_cents, product.currency)}
                </span>
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {onEdit ? (
                <HeaderButton
                  label="Edit Product"
                  onClick={() => onEdit(product)}
                  icon={<Pencil size={15} aria-hidden="true" />}
                >
                  Edit Product
                </HeaderButton>
              ) : null}
              <HeaderButton
                label="Download PDF Spec"
                onClick={() => printSpecSheet(product, specRows(product, branches), branches)}
                icon={<Download size={15} aria-hidden="true" />}
              >
                Download PDF Spec
              </HeaderButton>
            </div>
          </div>
          <nav
            className="mt-4 flex gap-1 overflow-x-auto rounded-full bg-charcoal p-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
            role="tablist"
            aria-label="Product sections"
          >
            {tabs.map((item) => (
              <button
                key={item.id}
                type="button"
                role="tab"
                aria-selected={active === item.id}
                onClick={(event) => {
                  setTab(item.id);
                  event.currentTarget.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" });
                }}
                className={`shrink-0 rounded-full px-3.5 py-2 text-[13px] font-semibold transition ${
                  active === item.id ? "bg-accent text-white" : "text-white/70 hover:bg-white/10 hover:text-white"
                } ${item.locked ? "opacity-50" : ""}`}
              >
                {item.label}
              </button>
            ))}
          </nav>
        </header>

        <div
          className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-5 sm:px-6"
          role="tabpanel"
          aria-label={tabs.find((item) => item.id === active)?.label}
        >
          {detail.product.state === "error" ? (
            <p className="mb-4 rounded-2xl bg-danger/10 px-4 py-3 text-sm text-danger" role="alert">
              {detail.product.message}{" "}
              <button type="button" className="font-semibold underline" onClick={detail.reload}>
                Retry
              </button>
            </p>
          ) : null}
          {active === "details" ? (
            <DetailsTab
              product={product}
              availability={detail.availability}
              purchases={detail.purchases}
              costing={detail.costing}
              canManagePhotos={can(Permission.PortalInventoryManage)}
            />
          ) : active === "sales" ? (
            <SalesTab resource={detail.sales} />
          ) : active === "purchases" ? (
            <PurchasesTab resource={detail.purchases} costing={detail.costing} currency={product.currency} />
          ) : active === "serials" ? (
            <SerialsTab
              resource={detail.serials}
              status={serialStatus}
              query={serialQuery}
              onStatus={setSerialStatus}
              onQuery={setSerialQuery}
            />
          ) : (
            <TimelineTab resource={detail.movements} />
          )}
        </div>
      </aside>
    </>
  );
}
