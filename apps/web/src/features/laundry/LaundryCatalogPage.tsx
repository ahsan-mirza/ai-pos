import { useCallback, useEffect, useState } from "react";
import { ApiRequestError, apiGet, apiPatch, apiPost, apiPut } from "../../lib/api";

interface LaundrySettings {
  operating_modes: string[];
  tracking_mode: string;
  weight_precision: number;
  express_daily_capacity: number | null;
}

interface NamedRow {
  id: string;
  code: string;
  name: string;
  is_active: boolean;
}

interface ServiceRow extends NamedRow {
  category_id: string;
  pricing_unit: string;
  base_rate_cents: number;
  min_charge_cents: number;
  min_quantity: number;
  weight_precision: number;
  express_surcharge_cents: number | null;
  tax_category: string;
  workflow_code: string;
}

interface StoreRow {
  id: string;
  code: string;
  name: string;
}

interface CustomerRow {
  id: string;
  name: string;
}

interface PriceListRow {
  id: string;
  code: string;
  name: string;
  kind: string;
  store_id: string | null;
  customer_id: string | null;
  valid_from: string | null;
  valid_to: string | null;
  is_active: boolean;
}

interface QuoteRow {
  total_cents: number;
  tax_cents: number;
  net_cents: number;
  rate_bps: number;
  minimum_charge_applied: boolean;
}

const TEMPLATES = [
  ["laundry_shop", "Small shop"],
  ["laundry_dry_cleaner", "Dry cleaner"],
  ["laundry_multi_branch", "Multi-branch"],
  ["laundry_commercial", "Commercial"],
] as const;

const MODES = [
  "DRY_CLEANING",
  "WASH_AND_FOLD",
  "WASH_AND_IRON",
  "PRESSING_ONLY",
  "ALTERATIONS",
  "COMMERCIAL_LAUNDRY",
  "SELF_SERVICE_LAUNDROMAT",
  "PICKUP_AND_DELIVERY",
  "CENTRAL_PLANT",
];

function message(error: unknown): string {
  return error instanceof ApiRequestError ? error.message : "The laundry catalog could not be loaded.";
}

function money(cents: number): string {
  return (cents / 100).toFixed(2);
}

export function LaundryCatalogPage() {
  const [settings, setSettings] = useState<LaundrySettings | null>(null);
  const [categories, setCategories] = useState<NamedRow[]>([]);
  const [services, setServices] = useState<ServiceRow[]>([]);
  const [stores, setStores] = useState<StoreRow[]>([]);
  const [customers, setCustomers] = useState<CustomerRow[]>([]);
  const [lists, setLists] = useState<PriceListRow[]>([]);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [activeOnly, setActiveOnly] = useState(false);
  const [categoryName, setCategoryName] = useState("");
  const [serviceName, setServiceName] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [unit, setUnit] = useState("PIECE");
  const [rate, setRate] = useState("0");
  const [selectedId, setSelectedId] = useState("");
  const [editName, setEditName] = useState("");
  const [editRate, setEditRate] = useState("0");
  const [editMinimum, setEditMinimum] = useState("0");
  const [editExpress, setEditExpress] = useState("");
  const [editPrecision, setEditPrecision] = useState("0");
  const [listCode, setListCode] = useState("");
  const [listKind, setListKind] = useState("standard");
  const [listStore, setListStore] = useState("");
  const [listCustomer, setListCustomer] = useState("");
  const [listUntil, setListUntil] = useState("");
  const [listRate, setListRate] = useState("1000");
  const [branchStore, setBranchStore] = useState("");
  const [branchCapacity, setBranchCapacity] = useState("0");
  const [tenantCapacity, setTenantCapacity] = useState("");
  const [quote, setQuote] = useState<QuoteRow | null>(null);

  const load = useCallback(async () => {
    const params = new URLSearchParams();
    if (query.trim()) params.set("q", query.trim());
    if (activeOnly) params.set("active", "true");
    const suffix = params.size ? `?${params.toString()}` : "";
    const [nextSettings, nextCategories, nextServices, nextStores, nextCustomers, nextLists] = await Promise.all([
      apiGet<LaundrySettings>("/api/v1/laundry/settings"),
      apiGet<NamedRow[]>("/api/v1/laundry/categories"),
      apiGet<ServiceRow[]>(`/api/v1/laundry/services${suffix}`),
      apiGet<StoreRow[]>("/api/v1/stores"),
      apiGet<CustomerRow[]>("/api/v1/customers?limit=100"),
      apiGet<PriceListRow[]>("/api/v1/laundry/price-lists"),
    ]);
    setSettings(nextSettings);
    setCategories(nextCategories);
    setServices(nextServices);
    setStores(nextStores);
    setCustomers(nextCustomers);
    setLists(nextLists);
    setCategoryId((current) => current || nextCategories[0]?.id || "");
    setTenantCapacity(nextSettings.express_daily_capacity === null ? "" : String(nextSettings.express_daily_capacity));
    setBranchStore((current) => current || nextStores[0]?.id || "");
    setListStore((current) => current || nextStores[0]?.id || "");
    setListCustomer((current) => current || nextCustomers[0]?.id || "");
  }, [activeOnly, query]);

  useEffect(() => {
    load().catch((caught) => setError(message(caught)));
  }, [load]);

  async function run(action: () => Promise<unknown>) {
    setError("");
    setQuote(null);
    try {
      await action();
      await load();
    } catch (caught) {
      setError(message(caught));
    }
  }

  const selected = services.find((service) => service.id === selectedId) ?? null;

  return (
    <section className="space-y-6 p-6">
      <header>
        <h1 className="text-2xl font-semibold">Laundry catalog</h1>
        <p className="text-sm text-charcoal/70">Services and prices for garment care. Clothes in process are not stock for sale.</p>
      </header>
      {error ? <p role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</p> : null}
      {settings === null ? <p>Loading laundry settings…</p> : null}
      {settings ? (
        <div className="flex flex-wrap gap-2">
          {TEMPLATES.map(([code, label]) => (
            <button key={code} type="button" className="rounded-full border border-line px-4 py-2 text-sm" onClick={() => run(() => apiPost(`/api/v1/laundry/templates/${code}`, {}))}>
              {label}
            </button>
          ))}
        </div>
      ) : null}
      {settings ? (
        <form
          key={settings.operating_modes.join("|")}
          className="space-y-3 rounded-2xl border border-line p-4"
          onSubmit={(event) => {
            event.preventDefault();
            const selectedModes = new FormData(event.currentTarget).getAll("mode").map(String);
            const capacity = tenantCapacity.trim();
            void run(() =>
              apiPut("/api/v1/laundry/settings", {
                operating_modes: selectedModes,
                tracking_mode: settings.tracking_mode,
                weight_precision: settings.weight_precision,
                express_daily_capacity: capacity === "" ? null : Number(capacity),
              }),
            );
          }}
        >
          <h2 className="font-medium">Operating modes</h2>
          <div className="grid gap-2 sm:grid-cols-2">
            {MODES.map((mode) => (
              <label key={mode} className="flex items-center gap-2 text-sm">
                <input type="checkbox" name="mode" value={mode} defaultChecked={settings.operating_modes.includes(mode)} />
                {mode.replaceAll("_", " ")}
              </label>
            ))}
          </div>
          <label className="block text-sm">
            Tenant express capacity
            <input className="mt-1 block rounded-xl border border-line px-3 py-2" value={tenantCapacity} onChange={(event) => setTenantCapacity(event.target.value)} inputMode="numeric" aria-label="Tenant express capacity" />
          </label>
          <button type="submit" className="rounded-full bg-accent px-4 py-2 text-sm text-white">Save modes</button>
        </form>
      ) : null}
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          void run(() => apiPut(`/api/v1/laundry/branches/${branchStore}/express-capacity`, { express_daily_capacity: Number(branchCapacity) }));
        }}
      >
        <label className="text-sm">
          Branch
          <select className="mt-1 block rounded-xl border border-line px-3 py-2" value={branchStore} onChange={(event) => setBranchStore(event.target.value)} aria-label="Capacity branch">
            {stores.map((store) => <option key={store.id} value={store.id}>{store.name}</option>)}
          </select>
        </label>
        <label className="text-sm">
          Branch express capacity
          <input className="mt-1 block w-28 rounded-xl border border-line px-3 py-2" value={branchCapacity} onChange={(event) => setBranchCapacity(event.target.value)} aria-label="Branch express capacity" />
        </label>
        <button type="submit" className="rounded-full border border-line px-4 py-2 text-sm">Save branch capacity</button>
      </form>
      <form className="flex flex-wrap gap-2" onSubmit={(event) => { event.preventDefault(); void load(); }}>
        <input className="rounded-xl border border-line px-3 py-2" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search services" aria-label="Search services" />
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={activeOnly} onChange={(event) => setActiveOnly(event.target.checked)} />
          Active only
        </label>
        <button type="submit" className="rounded-full border border-line px-4 py-2 text-sm">Search</button>
      </form>
      <form
        className="flex flex-wrap gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          const code = categoryName.trim().toLowerCase().replaceAll(" ", "_");
          void run(async () => {
            await apiPost("/api/v1/laundry/categories", { code, name: categoryName.trim() });
            setCategoryName("");
          });
        }}
      >
        <input className="rounded-xl border border-line px-3 py-2" value={categoryName} onChange={(event) => setCategoryName(event.target.value)} placeholder="New category" aria-label="New category" />
        <button type="submit" className="rounded-full border border-line px-4 py-2 text-sm">Add category</button>
      </form>
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          const code = serviceName.trim().toLowerCase().replaceAll(" ", "_");
          const cents = Number(rate);
          void run(async () => {
            await apiPost("/api/v1/laundry/services", {
              category_id: categoryId,
              code,
              name: serviceName.trim(),
              pricing_unit: unit,
              base_rate_cents: Number.isFinite(cents) ? cents : 0,
              allow_zero_rate: cents === 0,
              weight_precision: unit === "KG" || unit === "METER" || unit === "SQUARE_METER" || unit === "HOUR" ? 3 : 0,
            });
            setServiceName("");
          });
        }}
      >
        <select className="rounded-xl border border-line px-3 py-2" value={categoryId} onChange={(event) => setCategoryId(event.target.value)} aria-label="Service category">
          {categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}
        </select>
        <input className="rounded-xl border border-line px-3 py-2" value={serviceName} onChange={(event) => setServiceName(event.target.value)} placeholder="New service" aria-label="New service" />
        <select className="rounded-xl border border-line px-3 py-2" value={unit} onChange={(event) => setUnit(event.target.value)} aria-label="Pricing unit">
          {["PIECE", "KG", "BAG", "LOAD", "SET", "PAIR", "METER", "SQUARE_METER", "HOUR"].map((item) => <option key={item}>{item}</option>)}
        </select>
        <input className="w-32 rounded-xl border border-line px-3 py-2" value={rate} onChange={(event) => setRate(event.target.value)} inputMode="numeric" aria-label="Base rate in cents" />
        <button type="submit" className="rounded-full border border-line px-4 py-2 text-sm">Add service</button>
      </form>
      {services.length === 0 ? <p className="text-sm text-charcoal/70">No services yet. Apply a template or add one.</p> : (
        <ul className="divide-y divide-line rounded-2xl border border-line">
          {services.map((service) => (
            <li key={service.id} className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
              <button type="button" className="text-left" onClick={() => { setSelectedId(service.id); setEditName(service.name); setEditRate(String(service.base_rate_cents)); setEditMinimum(String(service.min_charge_cents)); setEditExpress(service.express_surcharge_cents === null ? "" : String(service.express_surcharge_cents)); setEditPrecision(String(service.weight_precision)); }}>
                {service.name}
              </button>
              <span>{service.pricing_unit} · {money(service.base_rate_cents)} · {service.is_active ? "Active" : "Inactive"}</span>
            </li>
          ))}
        </ul>
      )}
      {selected ? (
        <form
          className="flex flex-wrap items-end gap-2 rounded-2xl border border-line p-4"
          onSubmit={(event) => {
            event.preventDefault();
            void run(() => apiPatch(`/api/v1/laundry/services/${selected.id}`, {
              name: editName,
              base_rate_cents: Number(editRate),
              min_charge_cents: Number(editMinimum),
              weight_precision: Number(editPrecision),
              express_surcharge_cents: editExpress.trim() === "" ? null : Number(editExpress),
              allow_zero_rate: Number(editRate) === 0,
            }));
          }}
        >
          <h2 className="w-full font-medium">Edit {selected.code}</h2>
          <input className="rounded-xl border border-line px-3 py-2" value={editName} onChange={(event) => setEditName(event.target.value)} aria-label="Service name" />
          <input className="w-32 rounded-xl border border-line px-3 py-2" value={editRate} onChange={(event) => setEditRate(event.target.value)} aria-label="Edited rate in cents" />
          <input className="w-32 rounded-xl border border-line px-3 py-2" value={editMinimum} onChange={(event) => setEditMinimum(event.target.value)} aria-label="Minimum charge in cents" />
          <input className="w-32 rounded-xl border border-line px-3 py-2" value={editExpress} onChange={(event) => setEditExpress(event.target.value)} aria-label="Express surcharge in cents" />
          <input className="w-24 rounded-xl border border-line px-3 py-2" value={editPrecision} onChange={(event) => setEditPrecision(event.target.value)} aria-label="Weight precision" />
          <button type="submit" className="rounded-full bg-accent px-4 py-2 text-sm text-white">Save service</button>
          <button type="button" className="rounded-full border border-line px-4 py-2 text-sm" onClick={() => run(() => apiPatch(`/api/v1/laundry/services/${selected.id}`, { is_active: !selected.is_active }))}>
            {selected.is_active ? "Deactivate service" : "Activate service"}
          </button>
        </form>
      ) : null}
      <form
        className="grid gap-2 rounded-2xl border border-line p-4 sm:grid-cols-2"
        onSubmit={(event) => {
          event.preventDefault();
          void run(async () => {
            const created = await apiPost<PriceListRow>("/api/v1/laundry/price-lists", {
              code: listCode.trim().toLowerCase().replaceAll(" ", "_"),
              name: listCode.trim(),
              kind: listKind,
              store_id: listKind === "branch" ? listStore : null,
              customer_id: listKind === "customer" || listKind === "corporate" ? listCustomer : null,
              valid_from: null,
              valid_to: listUntil || null,
            });
            if (selected) {
              await apiPut(`/api/v1/laundry/price-lists/${created.id}/rates`, { service_id: selected.id, unit_price_cents: Number(listRate) });
            }
            setListCode("");
          });
        }}
      >
        <h2 className="font-medium sm:col-span-2">Price list</h2>
        <input className="rounded-xl border border-line px-3 py-2" value={listCode} onChange={(event) => setListCode(event.target.value)} placeholder="List name" aria-label="Price list name" />
        <select className="rounded-xl border border-line px-3 py-2" value={listKind} onChange={(event) => setListKind(event.target.value)} aria-label="Price list kind">
          {["standard", "premium", "express", "branch", "customer", "corporate"].map((kind) => <option key={kind}>{kind}</option>)}
        </select>
        <select className="rounded-xl border border-line px-3 py-2" value={listStore} onChange={(event) => setListStore(event.target.value)} aria-label="Price list branch">
          {stores.map((store) => <option key={store.id} value={store.id}>{store.name}</option>)}
        </select>
        <select className="rounded-xl border border-line px-3 py-2" value={listCustomer} onChange={(event) => setListCustomer(event.target.value)} aria-label="Price list customer">
          {customers.map((customer) => <option key={customer.id} value={customer.id}>{customer.name}</option>)}
        </select>
        <input className="rounded-xl border border-line px-3 py-2" type="date" value={listUntil} onChange={(event) => setListUntil(event.target.value)} aria-label="Price list valid to" />
        <input className="rounded-xl border border-line px-3 py-2" value={listRate} onChange={(event) => setListRate(event.target.value)} aria-label="List rate in cents" />
        <button type="submit" className="rounded-full border border-line px-4 py-2 text-sm">Add price list</button>
      </form>
      {lists.length === 0 ? <p className="text-sm text-charcoal/70">No price lists yet.</p> : (
        <ul className="divide-y divide-line rounded-2xl border border-line">
          {lists.map((row) => (
            <li key={row.id} className="px-4 py-3 text-sm">{row.name} · {row.kind}{row.valid_to ? ` · until ${row.valid_to}` : ""}</li>
          ))}
        </ul>
      )}
      {selected ? (
        <form
          className="space-y-2"
          onSubmit={(event) => {
            event.preventDefault();
            const body = new FormData(event.currentTarget);
            const gross = String(body.get("gross") || "");
            const tare = String(body.get("tare") || "");
            let quantity = Number(body.get("quantity"));
            setQuote(null);
            if (gross !== "" || tare !== "") {
              const net = Number(gross) - Number(tare);
              if (!Number.isFinite(net) || net <= 0) {
                setError("Net weight must be greater than zero.");
                return;
              }
              quantity = net;
            }
            const priceListId = String(body.get("price_list_id") || "") || null;
            const chosen = lists.find((row) => row.id === priceListId) ?? null;
            void run(async () => {
              const priced = await apiPost<QuoteRow>("/api/v1/laundry/quotes", {
                service_id: selected.id,
                quantity,
                on: String(body.get("on")),
                store_id: chosen?.store_id ?? null,
                customer_id: chosen?.customer_id ?? null,
                price_list_id: priceListId,
                extras_cents: Number(body.get("extras") || 0),
                discount_cents: Number(body.get("discount") || 0),
                express: body.get("express") === "on",
              });
              setQuote(priced);
            });
          }}
        >
          <h2 className="font-medium">Quote {selected.name}</h2>
          <input className="rounded-xl border border-line px-3 py-2" name="quantity" defaultValue="1" aria-label="Quote quantity" />
          <input className="rounded-xl border border-line px-3 py-2" name="gross" placeholder="Gross" aria-label="Gross weight" />
          <input className="rounded-xl border border-line px-3 py-2" name="tare" placeholder="Tare" aria-label="Tare weight" />
          <input className="rounded-xl border border-line px-3 py-2" name="on" type="date" defaultValue={new Date().toISOString().slice(0, 10)} aria-label="Quote date" />
          <select className="rounded-xl border border-line px-3 py-2" name="price_list_id" aria-label="Quote price list">
            <option value="">Base rate</option>
            {lists.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
          </select>
          <input className="rounded-xl border border-line px-3 py-2" name="extras" defaultValue="0" aria-label="Extras in cents" />
          <input className="rounded-xl border border-line px-3 py-2" name="discount" defaultValue="0" aria-label="Discount in cents" />
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" name="express" /> Express</label>
          <button type="submit" className="rounded-full border border-line px-4 py-2 text-sm">Calculate quote</button>
          {quote ? <p aria-label="Quote total">Total {money(quote.total_cents)} · tax {money(quote.tax_cents)} · rate {quote.rate_bps}</p> : null}
        </form>
      ) : null}
    </section>
  );
}
