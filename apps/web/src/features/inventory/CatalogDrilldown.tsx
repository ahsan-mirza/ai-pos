import {
  Capability,
  Permission,
  formatMoney,
  type Brand,
  type Category,
  type Product,
  type ProductModel,
  type SubCategory,
} from "@ai-pos/shared-types";
import { ChevronRight, Link2, Pencil, Plus, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ErrorNote, GhostButton, PrimaryButton, SelectField, TextField } from "../../components/ui/Field";
import { useConfirm } from "../../components/ui/ConfirmDialog";
import { Modal } from "../../components/ui/Modal";
import { useAuth } from "../../lib/auth";
import { useCapability } from "../../lib/capabilities";
import { brandsApi, message, modelsApi } from "./api";
import { codeError, fieldErrors, useInvalidFocus, type FieldErrors } from "./formErrors";
import { ModelFashionPanel } from "./ModelFashionPanel";
import { VariantMatrixPanel } from "./VariantMatrixPanel";
import { ProductFormModal } from "./ProductFormModal";
import { useBrands, useModels, variantSummary } from "./shared";
import { IconButton } from "./StockPage";

export interface CatalogPath {
  brandId?: string;
  modelId?: string;
}

/** Sub-category > Brand > Model > Variant browser shown inside the Categories page. */
export function CatalogDrilldown({
  category,
  sub,
  path,
  manage,
  onNavigate,
  onExit,
}: {
  category: Category;
  sub: SubCategory;
  path: CatalogPath;
  manage: boolean;
  onNavigate: (path: CatalogPath) => void;
  onExit: () => void;
}) {
  const { brands, error: brandError, reload: reloadBrands } = useBrands(sub.id);
  const { models, error: modelError, reload: reloadModels } = useModels(sub.id, null);
  const brand = brands.find((item) => item.id === path.brandId);
  const model = models.find((item) => item.id === path.modelId);
  const [dialog, setDialog] = useState<"link" | "model" | null>(null);
  const [modelBrand, setModelBrand] = useState<Brand | null>(null);
  const [editingModel, setEditingModel] = useState<ProductModel | null>(null);
  const [error, setError] = useState<string | null>(null);
  const confirm = useConfirm();

  const modelsByBrand = useMemo(() => {
    const counts = new Map<string, number>();
    for (const item of models) counts.set(item.brand_id, (counts.get(item.brand_id) ?? 0) + 1);
    return counts;
  }, [models]);

  const refresh = async () => {
    await Promise.all([reloadBrands(), reloadModels()]);
  };

  const unlink = async (item: Brand) => {
    const accepted = await confirm({
      title: "Remove brand",
      message: `Remove ${item.name} from ${sub.name}?`,
      confirmLabel: "Remove",
      tone: "danger",
    });
    if (!accepted) return;
    try {
      await brandsApi.unlink(item.id, sub.id);
      await refresh();
    } catch (caught) {
      setError(message(caught, "Could not remove the brand."));
    }
  };

  const removeModel = async (item: ProductModel) => {
    const accepted = await confirm({
      title: "Delete model",
      message: `Delete the ${item.name} model?`,
      confirmLabel: "Delete",
      tone: "danger",
    });
    if (!accepted) return;
    try {
      await modelsApi.remove(item.id);
      onNavigate({ brandId: item.brand_id });
      await refresh();
    } catch (caught) {
      setError(message(caught, "Could not delete the model."));
    }
  };

  const crumbs = [
    { label: category.name, onClick: onExit },
    { label: sub.name, onClick: () => onNavigate({}) },
    ...(brand ? [{ label: brand.name, onClick: () => onNavigate({ brandId: brand.id }) }] : []),
    ...(model ? [{ label: model.name, onClick: () => undefined }] : []),
  ];

  return (
    <div>
      <nav aria-label="Catalog path" className="mb-4 flex flex-wrap items-center gap-1 text-sm">
        {crumbs.map((crumb, index) => {
          const last = index === crumbs.length - 1;
          return (
            <span key={crumb.label + index} className="inline-flex items-center gap-1">
              {last ? (
                <span className="font-semibold text-charcoal" aria-current="page">
                  {crumb.label}
                </span>
              ) : (
                <button type="button" onClick={crumb.onClick} className="text-charcoal/60 hover:text-accent">
                  {crumb.label}
                </button>
              )}
              {last ? null : <ChevronRight size={14} aria-hidden="true" className="text-charcoal/30" />}
            </span>
          );
        })}
      </nav>
      <ErrorNote message={error ?? brandError ?? modelError} />

      {model ? (
        <VariantList model={model} onModelSaved={() => void reloadModels()} />
      ) : brand ? (
        <>
          <Header
            title={`${brand.name} in ${sub.name}`}
            subtitle={brand.description || "Models this brand sells in this sub-category."}
            action={
              manage ? (
                <PrimaryButton onClick={() => setDialog("model")}>
                  <span className="inline-flex items-center gap-2">
                    <Plus size={16} aria-hidden="true" /> Add model
                  </span>
                </PrimaryButton>
              ) : null
            }
          />
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {models
              .filter((item) => item.brand_id === brand.id)
              .map((item) => (
                <Card
                  key={item.id}
                  code={[item.code, item.release_year].filter(Boolean).join(" · ") || "MODEL"}
                  title={item.name}
                  detail={item.description}
                  footer={`${item.variant_count} ${item.variant_count === 1 ? "variant" : "variants"}`}
                  onOpen={() => onNavigate({ brandId: brand.id, modelId: item.id })}
                  actions={
                    manage ? (
                      <>
                        <IconButton label={`Edit ${item.name}`} onClick={() => setEditingModel(item)}>
                          <Pencil size={14} />
                        </IconButton>
                        <IconButton label={`Delete ${item.name}`} onClick={() => void removeModel(item)}>
                          <Trash2 size={14} />
                        </IconButton>
                      </>
                    ) : null
                  }
                />
              ))}
            {(modelsByBrand.get(brand.id) ?? 0) === 0 ? (
              <p className="text-sm text-charcoal/60">No {brand.name} models in {sub.name} yet.</p>
            ) : null}
          </div>
        </>
      ) : (
        <>
          <Header
            title={sub.name}
            subtitle={sub.description || `Brands sold under ${category.name} › ${sub.name}.`}
            action={
              manage ? (
                <PrimaryButton onClick={() => setDialog("link")}>
                  <span className="inline-flex items-center gap-2">
                    <Link2 size={16} aria-hidden="true" /> Add brand
                  </span>
                </PrimaryButton>
              ) : null
            }
          />
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {brands.map((item) => {
              const count = modelsByBrand.get(item.id) ?? 0;
              return (
                <Card
                  key={item.id}
                  code={item.code}
                  title={item.name}
                  detail={item.description}
                  footer={`${count} ${count === 1 ? "model" : "models"}`}
                  onOpen={() => onNavigate({ brandId: item.id })}
                  actions={
                    manage ? (
                      <>
                        <button
                          type="button"
                          className="h-8 rounded-full border border-line bg-white px-2.5 text-xs font-semibold text-charcoal hover:border-charcoal"
                          onClick={() => setModelBrand(item)}
                        >
                          Add model
                        </button>
                        {count === 0 ? (
                          <IconButton label={`Remove ${item.name} from ${sub.name}`} onClick={() => void unlink(item)}>
                            <Trash2 size={14} />
                          </IconButton>
                        ) : null}
                      </>
                    ) : null
                  }
                />
              );
            })}
            {brands.length === 0 ? <p className="text-sm text-charcoal/60">No brands in {sub.name} yet.</p> : null}
          </div>
        </>
      )}

      {dialog === "link" ? (
        <LinkBrandModal
          sub={sub}
          linked={brands}
          onClose={() => setDialog(null)}
          onSaved={async () => {
            setDialog(null);
            await refresh();
          }}
        />
      ) : null}
      {(dialog === "model" && (brand ?? modelBrand)) || modelBrand || editingModel ? (
        <ModelModal
          brand={brand ?? modelBrand}
          sub={sub}
          model={editingModel}
          onClose={() => {
            setDialog(null);
            setEditingModel(null);
            setModelBrand(null);
          }}
          onSaved={async () => {
            setDialog(null);
            setEditingModel(null);
            setModelBrand(null);
            await refresh();
          }}
        />
      ) : null}
    </div>
  );
}

function Header({ title, subtitle, action }: { title: string; subtitle: string; action: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h2 className="text-2xl font-semibold">{title}</h2>
        <p className="text-sm text-charcoal/60">{subtitle}</p>
      </div>
      {action}
    </div>
  );
}

function Card({
  code,
  title,
  detail,
  footer,
  onOpen,
  actions,
}: {
  code: string;
  title: string;
  detail: string;
  footer: string;
  onOpen: () => void;
  actions: ReactNode;
}) {
  return (
    <article className="group relative rounded-2xl border border-line p-4 transition-colors hover:border-accent">
      <div className="flex items-start justify-between gap-2">
        <button type="button" onClick={onOpen} className="min-w-0 text-left after:absolute after:inset-0 after:content-['']">
          <p className="truncate font-mono text-[11px] text-charcoal/50">{code}</p>
          <h3 className="font-semibold group-hover:text-accent">{title}</h3>
        </button>
        {actions ? <div className="relative z-10 flex gap-1">{actions}</div> : null}
      </div>
      <p className="mt-2 line-clamp-2 text-sm text-charcoal/60">{detail || "—"}</p>
      <p className="mt-3 flex items-center justify-between text-xs font-semibold tabular-nums">
        {footer}
        <ChevronRight size={14} aria-hidden="true" className="text-charcoal/30 group-hover:text-accent" />
      </p>
    </article>
  );
}

function VariantList({ model, onModelSaved }: { model: ProductModel; onModelSaved: () => void }) {
  const { can } = useAuth();
  const canEdit = can(Permission.PortalInventoryManage);
  const matrixModule = useCapability(Capability.VariantsMatrix);
  const [variants, setVariants] = useState<Product[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Product | "new" | null>(null);
  const [revision, setRevision] = useState(0);

  const load = useCallback(async () => {
    try {
      setVariants(await modelsApi.variants(model.id));
      setError(null);
    } catch (caught) {
      setError(message(caught, "Could not load variants."));
    }
  }, [model.id]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <>
      <Header
        title={`${model.brand_name} ${model.name}`}
        subtitle={[model.code, model.release_year ? `Released ${model.release_year}` : null, "Sub-models are the sellable variants."]
          .filter(Boolean)
          .join(" · ")}
        action={
          canEdit ? (
            <PrimaryButton onClick={() => setEditing("new")}>
              <span className="inline-flex items-center gap-2">
                <Plus size={16} aria-hidden="true" /> Add variant
              </span>
            </PrimaryButton>
          ) : null
        }
      />
      <ErrorNote message={error} />
      {matrixModule && !(variants ?? []).some((variant) => variant.is_serialized) ? (
        <>
          <ModelFashionPanel
            model={model}
            variants={variants ?? []}
            canEdit={canEdit}
            onSaved={() => {
              onModelSaved();
              void load();
            }}
          />
          <VariantMatrixPanel model={model} canEdit={canEdit} refreshKey={revision} onChanged={() => void load()} />
        </>
      ) : null}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-charcoal/50">
            <tr>
              <th className="pb-3 font-medium">Variant</th>
              <th className="pb-3 font-medium">SKU</th>
              <th className="pb-3 font-medium">Barcode</th>
              <th className="pb-3 text-right font-medium">Price</th>
              <th className="pb-3 text-right font-medium">Stock</th>
              {canEdit ? <th className="pb-3 text-right font-medium">Edit</th> : null}
            </tr>
          </thead>
          <tbody>
            {(variants ?? []).map((variant) => (
              <tr key={variant.id} className="border-t border-line">
                <td className="py-3">
                  <span className="flex items-center gap-3">
                    {variant.thumb_url ? (
                      <img src={variant.thumb_url} alt="" loading="lazy" className="h-10 w-10 shrink-0 rounded-lg object-cover" />
                    ) : null}
                    <span>
                      <span className="block font-medium">{variantSummary(variant.variant_attributes) || variant.name}</span>
                      <span className="block text-xs text-charcoal/50">
                        {variant.name}
                        {variant.is_serialized ? " · IMEI tracked" : ""}
                      </span>
                    </span>
                  </span>
                </td>
                <td className="py-3 font-mono text-xs">{variant.sku}</td>
                <td className="py-3 font-mono text-xs tabular-nums">{variant.barcode}</td>
                <td className="py-3 text-right tabular-nums">{formatMoney(variant.price_cents, variant.currency)}</td>
                <td className="py-3 text-right tabular-nums">{variant.stock_quantity}</td>
                {canEdit ? (
                  <td className="py-3">
                    <div className="flex justify-end">
                      <IconButton label={`Edit ${variant.name}`} onClick={() => setEditing(variant)}>
                        <Pencil size={14} />
                      </IconButton>
                    </div>
                  </td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
        {variants !== null && variants.length === 0 ? (
          <p className="py-8 text-sm text-charcoal/60">No variants of {model.name} yet.</p>
        ) : null}
      </div>
      {editing !== null ? (
        <ProductFormModal
          product={editing === "new" ? null : editing}
          preset={{
            categoryId: model.category_id,
            subCategoryId: model.sub_category_id,
            brandId: model.brand_id,
            modelId: model.id,
            serialized: (variants ?? []).some((variant) => variant.is_serialized),
          }}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            setRevision((value) => value + 1);
            void load();
          }}
        />
      ) : null}
    </>
  );
}

function LinkBrandModal({
  sub,
  linked,
  onClose,
  onSaved,
}: {
  sub: SubCategory;
  linked: Brand[];
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const { brands } = useBrands();
  const available = brands.filter((brand) => !linked.some((item) => item.id === brand.id));
  const [brandId, setBrandId] = useState("");
  const [name, setName] = useState("");
  const [fields, setFields] = useState<FieldErrors>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const formRef = useRef<HTMLDivElement>(null);
  const focusInvalid = useInvalidFocus(formRef);

  const save = async () => {
    const next: FieldErrors = {};
    if (brandId === "") {
      if (name.trim() === "") next.name = "Pick a brand or type a new brand name.";
      else if (name.trim().length < 2) next.name = "Name must be at least 2 characters.";
    }
    setFields(next);
    setError(null);
    if (Object.keys(next).length > 0) {
      focusInvalid();
      return;
    }
    setBusy(true);
    try {
      if (brandId !== "") await brandsApi.link(brandId, sub.id);
      else await brandsApi.create({ name: name.trim(), sub_category_ids: [sub.id] });
      await onSaved();
    } catch (caught) {
      const apiFields = fieldErrors(caught);
      if (Object.keys(apiFields).length > 0) {
        setFields(apiFields);
        focusInvalid();
      } else setError(message(caught, "Could not add the brand."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title={`Add a brand to ${sub.name}`}
      subtitle="Brands are one global list; link an existing brand or create a new one."
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy} onClick={() => void save()}>
            {busy ? "Saving…" : "Add brand"}
          </PrimaryButton>
        </>
      }
    >
      <div ref={formRef} className="space-y-4">
        <SelectField
          label="Existing brand"
          value={brandId}
          options={[{ value: "", label: "Create a new brand instead" }, ...available.map((brand) => ({ value: brand.id, label: brand.name }))]}
          onChange={(next) => {
            setBrandId(next);
            setFields({});
          }}
        />
        {brandId === "" ? (
          <TextField
            label="New brand name"
            value={name}
            placeholder="e.g. OnePlus"
            error={fields.name}
            onChange={(event) => {
              setName(event.target.value);
              setFields((current) => {
                if (!current.name) return current;
                const next = { ...current };
                delete next.name;
                return next;
              });
            }}
          />
        ) : null}
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}

function ModelModal({
  brand,
  sub,
  model,
  onClose,
  onSaved,
}: {
  brand: Brand | null;
  sub: SubCategory;
  model: ProductModel | null;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const [name, setName] = useState(model?.name ?? "");
  const [code, setCode] = useState(model?.code ?? "");
  const [year, setYear] = useState(model?.release_year ? String(model.release_year) : "");
  const [description, setDescription] = useState(model?.description ?? "");
  const [fields, setFields] = useState<FieldErrors>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const formRef = useRef<HTMLDivElement>(null);
  const focusInvalid = useInvalidFocus(formRef);

  const clearField = (key: string) =>
    setFields((current) => {
      if (!current[key]) return current;
      const next = { ...current };
      delete next[key];
      return next;
    });

  const save = async () => {
    const next: FieldErrors = {};
    if (name.trim() === "") next.name = "Model name is required.";
    const codeProblem = codeError(code);
    if (codeProblem) next.code = codeProblem;
    const releaseYear = year.trim() === "" ? null : Number(year);
    if (releaseYear !== null && (!Number.isInteger(releaseYear) || releaseYear < 1980 || releaseYear > 2100)) {
      next.year = "Release year must be between 1980 and 2100.";
    }
    setFields(next);
    setError(null);
    if (Object.keys(next).length > 0) {
      focusInvalid();
      return;
    }
    const body = {
      name: name.trim(),
      code: code.trim() || null,
      release_year: releaseYear,
      description: description.trim(),
    };
    setBusy(true);
    try {
      if (model) await modelsApi.update(model.id, body);
      else if (brand) await modelsApi.create({ ...body, brand_id: brand.id, sub_category_id: sub.id });
      await onSaved();
    } catch (caught) {
      const apiFields = fieldErrors(caught);
      if (Object.keys(apiFields).length > 0) {
        setFields(apiFields);
        focusInvalid();
      } else setError(message(caught, "Could not save the model."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title={model ? `Edit ${model.name}` : `New ${brand?.name ?? ""} model`}
      subtitle={`${model?.brand_name ?? brand?.name ?? ""} · ${sub.name}`}
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy} onClick={() => void save()}>
            {busy ? "Saving…" : "Save"}
          </PrimaryButton>
        </>
      }
    >
      <div ref={formRef} className="grid gap-4 md:grid-cols-2">
        <TextField
          label="Model name"
          value={name}
          autoFocus
          placeholder="e.g. iPhone 16 Pro"
          error={fields.name}
          onChange={(event) => {
            setName(event.target.value);
            clearField("name");
          }}
        />
        <TextField
          label="Model code"
          value={code}
          className="font-mono"
          placeholder="e.g. SM-S928B"
          hint="Optional manufacturer code."
          error={fields.code}
          onChange={(event) => {
            setCode(event.target.value);
            clearField("code");
          }}
        />
        <TextField
          label="Release year"
          inputMode="numeric"
          value={year}
          placeholder="2024"
          error={fields.year}
          onChange={(event) => {
            setYear(event.target.value);
            clearField("year");
          }}
        />
        <TextField label="Description" value={description} onChange={(event) => setDescription(event.target.value)} />
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}
