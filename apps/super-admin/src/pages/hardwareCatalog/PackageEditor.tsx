import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useConfirm } from "../../components/ConfirmDialog";
import { ErrorNote, Field, GhostButton, PrimaryButton } from "../../components/ui";
import { api, consoleUpload, errorText } from "../../lib/api";
import { money } from "../../lib/format";
import { useSession } from "../../lib/session";
import { aedFromFils, componentValueFils, filsFromAed, savingsFils } from "./pricing";
import { PACKAGE_TYPES, type CatalogPackage, type CatalogPlan, type CatalogProduct } from "./types";

interface ItemDraft {
  product_id: string;
  quantity: number;
  is_optional: boolean;
}

export function HardwarePackageEditor() {
  const { packageId } = useParams();
  const navigate = useNavigate();
  const confirm = useConfirm();
  const { operator } = useSession();
  const admin = operator?.role === "ADMIN";
  const [plans, setPlans] = useState<CatalogPlan[]>([]);
  const [products, setProducts] = useState<CatalogProduct[]>([]);
  const [saved, setSaved] = useState<CatalogPackage | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [full, setFull] = useState("");
  const [price, setPrice] = useState("");
  const [planId, setPlanId] = useState("");
  const [packageType, setPackageType] = useState("hardware_only");
  const [featured, setFeatured] = useState(false);
  const [items, setItems] = useState<ItemDraft[]>([]);
  const [pick, setPick] = useState("");
  const [reason, setReason] = useState("Catalogue update");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get<CatalogPlan[]>("/hardware-catalog/plans").then(setPlans).catch(() => undefined);
    api.page<CatalogProduct>("/hardware-catalog/products?limit=100&status=published").then((page) => setProducts(page.rows)).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!packageId || packageId === "new") return;
    api
      .get<CatalogPackage>(`/hardware-catalog/packages/${packageId}`)
      .then((row) => {
        setSaved(row);
        setName(row.name);
        setDescription(row.short_description);
        setFull(row.full_description);
        setPrice(aedFromFils(row.display_price_fils));
        setPlanId(row.billing_plan_id ?? "");
        setPackageType(row.package_type);
        setFeatured(row.is_featured);
        setItems(row.items.map((item) => ({ product_id: item.product_id, quantity: item.quantity, is_optional: item.is_optional })));
      })
      .catch((caught) => setError(errorText(caught, "The package could not be loaded.")));
  }, [packageId]);

  const priced = useMemo(
    () =>
      items.map((item) => ({
        quantity: item.quantity,
        optional: item.is_optional,
        displayPriceFils: products.find((product) => product.id === item.product_id)?.display_price_fils ?? saved?.items.find((row) => row.product_id === item.product_id)?.display_price_fils ?? null,
      })),
    [items, products, saved],
  );
  const componentTotal = componentValueFils(priced);
  const packageFils = filsFromAed(price);
  const difference = savingsFils(priced, packageFils);
  const plan = plans.find((row) => row.id === planId) ?? saved?.plan ?? null;

  async function save() {
    if (name.trim().length < 1 || reason.trim().length < 3) {
      setError("Enter a package name and a short reason.");
      return;
    }
    if (packageType === "hardware_software" && !planId) {
      setError("Choose an existing AxizPOS billing plan.");
      return;
    }
    setSaving(true);
    setError("");
    const body = {
      name: name.trim(),
      short_description: description,
      full_description: full,
      display_price_fils: packageFils,
      billing_plan_id: planId || null,
      package_type: packageType,
      is_featured: featured,
      is_active: true,
      items: items.map((item, index) => ({ ...item, display_order: index })),
      reason: reason.trim(),
    };
    try {
      const row = saved
        ? await api.put<CatalogPackage>(`/hardware-catalog/packages/${saved.id}`, body)
        : await api.post<CatalogPackage>("/hardware-catalog/packages", body);
      setSaved(row);
      navigate(`/hardware-catalog/packages/${row.id}`, { replace: true });
    } catch (caught) {
      setError(errorText(caught, "The package could not be saved."));
    } finally {
      setSaving(false);
    }
  }

  async function publish(path: "publish" | "unpublish") {
    if (!saved) return;
    const label = path === "publish" ? "Publish" : "Unpublish";
    if (!(await confirm({ title: label, message: `${label} ${saved.name} on the website.`, confirmLabel: label }))) return;
    try {
      setSaved(await api.post<CatalogPackage>(`/hardware-catalog/packages/${saved.id}/${path}`, { reason }));
    } catch (caught) {
      setError(errorText(caught, "The package could not be updated."));
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_300px]">
      <div>
        <Link to="/hardware-catalog/packages" className="text-sm text-charcoal/60">
          Back to packages
        </Link>
        <h1 className="mt-2 text-2xl font-semibold">{saved ? saved.name : "New package"}</h1>
        <ErrorNote message={error} />
        <div className="mt-4 grid gap-3">
          <Field label="Name" value={name} onChange={(event) => setName(event.target.value)} required />
          <label className="text-sm font-medium">
            Package type
            <select aria-label="Package type" className="mt-1 h-10 w-full rounded-xl border border-line px-3" value={packageType} onChange={(event) => setPackageType(event.target.value)}>
              {PACKAGE_TYPES.map(([id, label]) => (
                <option key={id} value={id}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm font-medium">
            AxizPOS software plan
            <select aria-label="Billing plan" className="mt-1 h-10 w-full rounded-xl border border-line px-3" value={planId} onChange={(event) => setPlanId(event.target.value)}>
              <option value="">Hardware only</option>
              {plans.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.name} · {money(row.monthly_fils, "AED")} / month
                </option>
              ))}
            </select>
          </label>
          <Field label="Package price (AED)" value={price} onChange={(event) => setPrice(event.target.value)} hint="This price is what the website shows. It is not recalculated from the components." />
          <Field label="Short description" value={description} onChange={(event) => setDescription(event.target.value)} />
          <Field label="Full description" multiline value={full} onChange={(event) => setFull(event.target.value)} />
          <div className="flex flex-wrap gap-2">
            <select aria-label="Add product" className="h-10 min-w-48 flex-1 rounded-xl border border-line px-3 text-sm" value={pick} onChange={(event) => setPick(event.target.value)}>
              <option value="">Add a product</option>
              {products.filter((product) => !items.some((item) => item.product_id === product.id)).map((product) => (
                <option key={product.id} value={product.id}>
                  {product.name}
                </option>
              ))}
            </select>
            <GhostButton
              onClick={() => {
                if (!pick) return;
                setItems((current) => [...current, { product_id: pick, quantity: 1, is_optional: false }]);
                setPick("");
              }}
            >
              Add
            </GhostButton>
          </div>
          <ul className="space-y-2">
            {items.map((item, index) => {
              const product = products.find((row) => row.id === item.product_id) ?? saved?.items.find((row) => row.product_id === item.product_id);
              const label = product && "name" in product ? product.name : product?.product_name ?? "Product";
              return (
                <li key={item.product_id} className="flex flex-wrap items-center gap-2 rounded-xl border border-line px-3 py-2 text-sm">
                  <span className="min-w-32 flex-1">{label}</span>
                  <label>
                    Qty
                    <input aria-label={`Quantity for ${label}`} className="ml-2 h-9 w-16 rounded-lg border border-line px-2" type="number" min={1} max={99} value={item.quantity} onChange={(event) => {
                      const quantity = Math.max(1, Number(event.target.value) || 1);
                      setItems((current) => current.map((row, rowIndex) => (rowIndex === index ? { ...row, quantity } : row)));
                    }} />
                  </label>
                  <label className="flex items-center gap-1">
                    <input type="checkbox" checked={item.is_optional} onChange={(event) => setItems((current) => current.map((row, rowIndex) => (rowIndex === index ? { ...row, is_optional: event.target.checked } : row)))} />
                    Optional
                  </label>
                  <GhostButton onClick={() => setItems((current) => current.filter((_, rowIndex) => rowIndex !== index))}>Remove</GhostButton>
                </li>
              );
            })}
          </ul>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={featured} onChange={(event) => setFeatured(event.target.checked)} />
            Featured
          </label>
          <Field label="Reason" value={reason} onChange={(event) => setReason(event.target.value)} required />
        </div>
        {admin ? (
          <div className="mt-4 flex flex-wrap gap-2">
            <PrimaryButton loading={saving} onClick={save}>
              Save
            </PrimaryButton>
            {saved ? <GhostButton onClick={() => publish(saved.is_published ? "unpublish" : "publish")}>{saved.is_published ? "Unpublish" : "Publish"}</GhostButton> : null}
          </div>
        ) : null}
        {saved && admin ? (
          <input
            aria-label="Upload package image"
            className="mt-4 block text-sm"
            type="file"
            accept="image/jpeg,image/png,image/webp"
            onChange={async (event) => {
              const file = event.target.files?.[0];
              if (!file || !saved) return;
              try {
                setSaved(await consoleUpload<CatalogPackage>(`/hardware-catalog/packages/${saved.id}/images`, file, { alt: name, reason }));
              } catch (caught) {
                setError(errorText(caught, "The image could not be uploaded."));
              }
            }}
          />
        ) : null}
      </div>
      <aside className="h-fit rounded-2xl border border-line bg-card p-4 text-sm">
        <h2 className="font-semibold">Preview</h2>
        <p className="mt-3 text-charcoal/60">Hardware components</p>
        <p className="text-lg font-semibold">{componentTotal == null ? "Add prices to compare" : money(componentTotal, "AED")}</p>
        <p className="mt-3 text-charcoal/60">Software plan</p>
        <p className="font-medium">{plan ? `${plan.name} · ${money(plan.monthly_fils, "AED")} / month` : "Not included"}</p>
        <p className="mt-3 text-charcoal/60">Package price</p>
        <p className="text-lg font-semibold">{packageFils == null ? "On request" : money(packageFils, "AED")}</p>
        {difference != null ? <p className="mt-3 text-accent">Difference {money(difference, "AED")} against the required hardware.</p> : <p className="mt-3 text-charcoal/50">No discount is shown until the components cost more than the package price.</p>}
        {saved?.images[0] ? <img src={saved.images[0].url} alt={saved.images[0].alt} className="mt-4 aspect-video w-full rounded-xl object-cover" /> : null}
      </aside>
    </div>
  );
}
