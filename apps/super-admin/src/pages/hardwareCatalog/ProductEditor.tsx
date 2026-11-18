import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ErrorNote, Field, GhostButton, PrimaryButton } from "../../components/ui";
import { api, consoleUpload, errorText } from "../../lib/api";
import { useConfirm } from "../../components/ConfirmDialog";
import { useSession } from "../../lib/session";
import { aedFromFils, filsFromAed, productFieldErrors } from "./pricing";
import { STOCK, type CatalogCategory, type CatalogProduct } from "./types";

interface Draft {
  category_id: string;
  name: string;
  sku: string;
  brand: string;
  model_number: string;
  manufacturer: string;
  short_description: string;
  full_description: string;
  compatibility: string;
  displayPrice: string;
  purchasePrice: string;
  warranty_months: string;
  stock_status: string;
  display_order: string;
  is_featured: boolean;
  is_active: boolean;
  specifications: { label: string; value: string }[];
  reason: string;
}

const blank: Draft = {
  category_id: "",
  name: "",
  sku: "",
  brand: "",
  model_number: "",
  manufacturer: "",
  short_description: "",
  full_description: "",
  compatibility: "",
  displayPrice: "",
  purchasePrice: "",
  warranty_months: "12",
  stock_status: "on_request",
  display_order: "0",
  is_featured: false,
  is_active: true,
  specifications: [{ label: "", value: "" }],
  reason: "Catalogue update",
};

function fromProduct(row: CatalogProduct): Draft {
  return {
    ...blank,
    category_id: row.category_id,
    name: row.name,
    sku: row.sku,
    brand: row.brand,
    model_number: row.model_number,
    manufacturer: row.manufacturer,
    short_description: row.short_description,
    full_description: row.full_description,
    compatibility: row.compatibility,
    displayPrice: aedFromFils(row.display_price_fils),
    purchasePrice: aedFromFils(row.purchase_price_fils),
    warranty_months: String(row.warranty_months),
    stock_status: row.stock_status,
    display_order: String(row.display_order),
    is_featured: row.is_featured,
    is_active: row.is_active,
    specifications: row.specifications.length ? row.specifications : [{ label: "", value: "" }],
  };
}

export function HardwareProductEditor() {
  const { productId } = useParams();
  const navigate = useNavigate();
  const confirm = useConfirm();
  const { operator } = useSession();
  const admin = operator?.role === "ADMIN";
  const [categories, setCategories] = useState<CatalogCategory[]>([]);
  const [product, setProduct] = useState<CatalogProduct | null>(null);
  const [draft, setDraft] = useState<Draft>(blank);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get<CatalogCategory[]>("/hardware-catalog/categories").then(setCategories).catch(() => setError("Categories could not be loaded."));
  }, []);

  useEffect(() => {
    if (!productId || productId === "new") return;
    api
      .get<CatalogProduct>(`/hardware-catalog/products/${productId}`)
      .then((row) => {
        setProduct(row);
        setDraft(fromProduct(row));
      })
      .catch((caught) => setError(errorText(caught, "The product could not be loaded.")));
  }, [productId]);

  function patch(partial: Partial<Draft>) {
    setDraft((current) => ({ ...current, ...partial }));
  }

  async function save() {
    const next = productFieldErrors(draft);
    if (!draft.category_id) next.category_id = "Choose a category.";
    setErrors(next);
    if (Object.keys(next).length) return;
    setSaving(true);
    setError("");
    const body = {
      category_id: draft.category_id,
      name: draft.name.trim(),
      sku: draft.sku.trim().toUpperCase(),
      brand: draft.brand,
      model_number: draft.model_number,
      manufacturer: draft.manufacturer,
      short_description: draft.short_description,
      full_description: draft.full_description,
      compatibility: draft.compatibility,
      display_price_fils: filsFromAed(draft.displayPrice),
      purchase_price_fils: filsFromAed(draft.purchasePrice),
      warranty_months: Number(draft.warranty_months) || 0,
      stock_status: draft.stock_status,
      display_order: Number(draft.display_order) || 0,
      is_featured: draft.is_featured,
      is_active: draft.is_active,
      specifications: draft.specifications.filter((row) => row.label.trim() && row.value.trim()),
      reason: draft.reason.trim(),
    };
    try {
      const saved = product
        ? await api.put<CatalogProduct>(`/hardware-catalog/products/${product.id}`, body)
        : await api.post<CatalogProduct>("/hardware-catalog/products", body);
      navigate(`/hardware-catalog/products/${saved.id}`, { replace: true });
      setProduct(saved);
    } catch (caught) {
      setError(errorText(caught, "The product could not be saved."));
    } finally {
      setSaving(false);
    }
  }

  async function act(path: string, label: string) {
    if (!product) return;
    if (!(await confirm({ title: label, message: `This will ${label.toLowerCase()} ${product.name}.`, confirmLabel: label }))) return;
    try {
      const saved = await api.post<CatalogProduct>(`/hardware-catalog/products/${product.id}/${path}`, { reason: draft.reason.trim() || "Catalogue update" });
      setProduct(saved);
      setDraft(fromProduct(saved));
    } catch (caught) {
      setError(errorText(caught, "The product could not be updated."));
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_280px]">
      <div>
        <Link to="/hardware-catalog/products" className="text-sm text-charcoal/60">
          Back to products
        </Link>
        <h1 className="mt-2 text-2xl font-semibold">{product ? product.name : "New product"}</h1>
        <ErrorNote message={error} />
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <label className="text-sm">
            Category
            <select aria-label="Category" className="mt-1 h-10 w-full rounded-xl border border-line px-3" value={draft.category_id} onChange={(event) => patch({ category_id: event.target.value })}>
              <option value="">Choose</option>
              {categories.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.name}
                </option>
              ))}
            </select>
            {errors.category_id ? <span className="text-danger">{errors.category_id}</span> : null}
          </label>
          <Field label="Name" value={draft.name} error={errors.name} onChange={(event) => patch({ name: event.target.value })} required />
          <Field label="SKU" value={draft.sku} error={errors.sku} onChange={(event) => patch({ sku: event.target.value })} required />
          <Field label="Brand" value={draft.brand} onChange={(event) => patch({ brand: event.target.value })} />
          <Field label="Model" value={draft.model_number} onChange={(event) => patch({ model_number: event.target.value })} />
          <Field label="Manufacturer" value={draft.manufacturer} onChange={(event) => patch({ manufacturer: event.target.value })} />
          <Field label="Display price (AED)" value={draft.displayPrice} error={errors.displayPrice} onChange={(event) => patch({ displayPrice: event.target.value })} hint="Shown on the website. Leave blank to hide the price." />
          <Field label="Cost price (AED)" value={draft.purchasePrice} onChange={(event) => patch({ purchasePrice: event.target.value })} hint="Console only. Never sent to the website." />
          <Field label="Warranty months" value={draft.warranty_months} onChange={(event) => patch({ warranty_months: event.target.value })} />
          <label className="text-sm">
            Availability
            <select aria-label="Availability" className="mt-1 h-10 w-full rounded-xl border border-line px-3" value={draft.stock_status} onChange={(event) => patch({ stock_status: event.target.value })}>
              {STOCK.map(([id, label]) => (
                <option key={id} value={id}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <Field label="Short description" className="sm:col-span-2" value={draft.short_description} onChange={(event) => patch({ short_description: event.target.value })} />
          <Field label="Full description" className="sm:col-span-2" multiline value={draft.full_description} onChange={(event) => patch({ full_description: event.target.value })} />
          <Field label="Compatibility" className="sm:col-span-2" multiline value={draft.compatibility} onChange={(event) => patch({ compatibility: event.target.value })} />
          <fieldset className="sm:col-span-2 space-y-2">
            <legend className="text-sm font-medium">Technical specifications</legend>
            {draft.specifications.map((row, index) => (
              <div key={index} className="grid grid-cols-[1fr_1fr_auto] gap-2">
                <input aria-label={`Specification ${index + 1} label`} className="h-10 rounded-xl border border-line px-3 text-sm" placeholder="Label" value={row.label} onChange={(event) => {
                  const specifications = draft.specifications.slice();
                  specifications[index] = { ...row, label: event.target.value };
                  patch({ specifications });
                }} />
                <input aria-label={`Specification ${index + 1} value`} className="h-10 rounded-xl border border-line px-3 text-sm" placeholder="Value" value={row.value} onChange={(event) => {
                  const specifications = draft.specifications.slice();
                  specifications[index] = { ...row, value: event.target.value };
                  patch({ specifications });
                }} />
                <GhostButton onClick={() => patch({ specifications: draft.specifications.filter((_, item) => item !== index) })}>Remove</GhostButton>
              </div>
            ))}
            <GhostButton onClick={() => patch({ specifications: [...draft.specifications, { label: "", value: "" }] })}>Add specification</GhostButton>
          </fieldset>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={draft.is_featured} onChange={(event) => patch({ is_featured: event.target.checked })} />
            Featured
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={draft.is_active} onChange={(event) => patch({ is_active: event.target.checked })} />
            Active
          </label>
          <Field label="Reason" className="sm:col-span-2" value={draft.reason} error={errors.reason} onChange={(event) => patch({ reason: event.target.value })} required />
        </div>
        {admin ? (
          <div className="mt-4 flex flex-wrap gap-2">
            <PrimaryButton loading={saving} onClick={save}>
              Save
            </PrimaryButton>
            {product && !product.archived ? (
              <>
                <GhostButton onClick={() => act(product.is_published ? "unpublish" : "publish", product.is_published ? "Unpublish" : "Publish")}>
                  {product.is_published ? "Unpublish" : "Publish"}
                </GhostButton>
                <GhostButton onClick={() => act("archive", "Archive")}>Archive</GhostButton>
              </>
            ) : null}
          </div>
        ) : null}
      </div>
      <aside className="rounded-2xl border border-line bg-card p-4">
        <h2 className="text-sm font-semibold">Photos</h2>
        {product ? (
          <>
            <ul className="mt-3 space-y-2">
              {product.images.map((image) => (
                <li key={image.id} className="flex items-center gap-2">
                  <img src={image.thumb_url} alt={image.alt} className="h-14 w-14 rounded-lg object-cover" />
                  <span className="text-xs text-charcoal/60">{image.is_primary ? "Primary" : "Gallery"}</span>
                  {admin ? (
                    <GhostButton
                      onClick={async () => {
                        await api.del(`/hardware-catalog/images/${image.id}?reason=${encodeURIComponent(draft.reason || "Remove photo")}`);
                        const saved = await api.get<CatalogProduct>(`/hardware-catalog/products/${product.id}`);
                        setProduct(saved);
                      }}
                    >
                      Remove
                    </GhostButton>
                  ) : null}
                </li>
              ))}
            </ul>
            {admin ? (
              <input
                aria-label="Upload product image"
                className="mt-3 block text-sm"
                type="file"
                accept="image/jpeg,image/png,image/webp"
                onChange={async (event) => {
                  const file = event.target.files?.[0];
                  if (!file || !product) return;
                  try {
                    const saved = await consoleUpload<CatalogProduct>(`/hardware-catalog/products/${product.id}/images`, file, {
                      alt: draft.name || "Product photo",
                      reason: draft.reason || "Catalogue update",
                    });
                    setProduct(saved);
                  } catch (caught) {
                    setError(errorText(caught, "The image could not be uploaded."));
                  }
                }}
              />
            ) : null}
          </>
        ) : (
          <p className="mt-2 text-sm text-charcoal/60">Save the product before uploading photos.</p>
        )}
        {product ? <p className="mt-4 text-sm text-charcoal/60">{product.archived ? "Archived" : product.is_published ? "Published" : "Draft"}</p> : null}
      </aside>
    </div>
  );
}
