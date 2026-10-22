import {
  Capability,
  GENDER_LABELS,
  ItemType,
  VARIANT_ATTRIBUTE_KEYS,
  variantAttributeLabel,
  type Gender,
  type ItemType as ItemTypeId,
  type Product,
  type ProductImage,
  type TaxCategory,
} from "@ai-pos/shared-types";
import { useEffect, useState } from "react";
import { ErrorNote, GhostButton, PrimaryButton, SelectField, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { Toggle } from "../../components/ui/Toggle";
import { apiDelete, apiGet, apiPatch, apiUpload } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useCapabilities } from "../../lib/capabilities";
import { useAutoCode } from "../../lib/codes";
import { useTenant } from "../../context/TenantContext";
import { inventoryApi, message } from "./api";
import { ProductImageDropzone, type ProductPhotoChoice } from "./ProductImageDropzone";
import { storeOptions, useBrands, useCategories, useModels, useStores } from "./shared";
import { useUnits } from "./units";

function toCents(value: string): number | null {
  const trimmed = value.trim();
  if (!/^\d+(\.\d{1,2})?$/.test(trimmed)) return null;
  return Math.round(Number(trimmed) * 100);
}

/** Pre-selected place in the catalog tree, e.g. when adding a variant from a model. */
export interface ProductPreset {
  categoryId: string;
  subCategoryId: string;
  brandId: string;
  modelId: string;
  serialized?: boolean;
}

const PRIMARY_ATTRIBUTES: readonly string[] = VARIANT_ATTRIBUTE_KEYS;

export function ProductFormModal({
  product,
  preset,
  onClose,
  onSaved,
}: {
  product: Product | null;
  preset?: ProductPreset;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { user } = useAuth();
  const { isFnB } = useTenant();
  const { categories } = useCategories();
  const { stores } = useStores();
  const editing = product !== null;
  const [barcode, setBarcode] = useState(product?.barcode ?? "");
  const [name, setName] = useState(product?.name ?? "");
  const [nameTouched, setNameTouched] = useState(editing);
  const { code: sku, setCode: setSku } = useAutoCode(name, product?.sku ?? "", 64);
  const [modelNumber, setModelNumber] = useState(product?.model_number ?? "");
  const [categoryId, setCategoryId] = useState(product?.category_id ?? preset?.categoryId ?? "");
  const [subCategoryId, setSubCategoryId] = useState(product?.sub_category_id ?? preset?.subCategoryId ?? "");
  const [brandId, setBrandId] = useState(product?.brand_id ?? preset?.brandId ?? "");
  const [modelId, setModelId] = useState(product?.product_model_id ?? preset?.modelId ?? "");
  const [attributes, setAttributes] = useState<Record<string, string>>(product?.variant_attributes ?? {});
  const [price, setPrice] = useState(product ? (product.price_cents / 100).toFixed(2) : "");
  const [serialized, setSerialized] = useState(product?.is_serialized ?? preset?.serialized ?? false);
  const [taxCategory, setTaxCategory] = useState<TaxCategory>(product?.tax_category ?? "STANDARD");
  const [openPrice, setOpenPrice] = useState(product?.is_open_price ?? false);
  const { has } = useCapabilities();
  const weighing = has(Capability.WeighedItems);
  const [byWeight, setByWeight] = useState(product?.sold_by_weight ?? false);
  const [plu, setPlu] = useState(product?.plu_code ?? "");
  const [tare, setTare] = useState(String(product?.tare_grams ?? 0));
  const recipesOn = has(Capability.Recipes);
  const [ingredient, setIngredient] = useState(product?.is_ingredient ?? false);
  const [itemType, setItemType] = useState<ItemTypeId>(
    product?.item_type ?? (isFnB ? ItemType.MadeToOrder : ItemType.PrePackaged),
  );
  // Standalone items carry their own season and collection; a model's variants take the model's.
  const fashionOn = has(Capability.VariantsMatrix);
  const [season, setSeason] = useState(product?.season ?? "");
  const [collection, setCollection] = useState(product?.collection ?? "");
  const [gender, setGender] = useState<string>(product?.gender ?? "");
  const { active: packOptions } = useUnits();
  const [packs, setPacks] = useState<string[]>((product?.sellable_units ?? []).filter((code) => code !== "PIECE"));
  const [storeId, setStoreId] = useState(user?.store_id ?? "");
  const [opening, setOpening] = useState("0");
  const [reorder, setReorder] = useState("0");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [persistedId, setPersistedId] = useState<string | null>(product?.id ?? null);
  const [photo, setPhoto] = useState<ProductPhotoChoice>({ file: null, removed: false });
  const { brands } = useBrands();
  const { models } = useModels(subCategoryId || null, brandId || null);
  const category = categories.find((item) => item.id === categoryId);
  const model = models.find((item) => item.id === modelId);
  const attributeKeys = [...PRIMARY_ATTRIBUTES, ...Object.keys(attributes).filter((key) => !PRIMARY_ATTRIBUTES.includes(key))];

  useEffect(() => {
    if (!nameTouched && model && name === "") setName(model.name);
  }, [model, name, nameTouched]);

  const suggestName = (modelName: string | undefined, next: Record<string, string>) => {
    if (nameTouched || !modelName) return;
    setName([modelName, ...Object.values(next).filter(Boolean)].join(" "));
  };

  const setAttribute = (key: string, value: string) => {
    const next = { ...attributes, [key]: value };
    setAttributes(next);
    suggestName(model?.name, next);
  };

  const brandOptions = (() => {
    const linked = brands.filter((brand) => subCategoryId !== "" && brand.sub_category_ids.includes(subCategoryId));
    const others = brands.filter((brand) => !linked.includes(brand));
    return [
      { value: "", label: "No brand" },
      ...linked.map((brand) => ({ value: brand.id, label: brand.name, hint: "Sells in this sub-category" })),
      ...others.map((brand) => ({ value: brand.id, label: brand.name })),
    ];
  })();

  const save = async () => {
    const cents = toCents(price);
    if (cents === null) return setError("Enter a price like 49.00.");
    if (categoryId === "") return setError("Choose a category.");
    if (name.trim() === "") return setError("Product name is required.");
    const variant_attributes = Object.fromEntries(
      Object.entries(attributes)
        .map(([key, value]) => [key, value.trim()])
        .filter(([, value]) => value !== ""),
    );
    const classification = {
      category_id: categoryId,
      brand_id: brandId || null,
      product_model_id: modelId || null,
      variant_attributes,
    };
    if (byWeight && plu.trim() !== "" && !/^\d{4,6}$/.test(plu.trim())) return setError("A scale PLU is 4 to 6 digits.");
    const weighed = weighing
      ? { sold_by_weight: byWeight, plu_code: byWeight && plu.trim() ? plu.trim() : null, tare_grams: byWeight ? Number(tare) || 0 : 0 }
      : {};
    const recipes =
      isFnB
        ? { item_type: itemType, is_ingredient: itemType === ItemType.RawIngredient }
        : recipesOn
          ? { is_ingredient: ingredient && !openPrice }
          : {};
    const fashion =
      fashionOn && modelId === ""
        ? { season: season.trim() || null, collection: collection.trim() || null, gender: (gender || null) as Gender | null }
        : {};
    const piecesOnly = (editing ? product.is_serialized : serialized) || byWeight || openPrice;
    const sellable_units = piecesOnly ? ["PIECE"] : ["PIECE", ...packs];
    setBusy(true);
    setError(null);
    try {
      let id = persistedId;
      if (id !== null) {
        await inventoryApi.updateProduct(id, {
          name: name.trim(),
          model_number: modelNumber.trim() || null,
          ...classification,
          ...(subCategoryId === "" ? { clear_sub_category: true } : { sub_category_id: subCategoryId }),
          price_cents: cents,
          tax_category: taxCategory,
          is_open_price: openPrice && !(product?.is_serialized ?? false),
          ...weighed,
          ...recipes,
          ...fashion,
          sellable_units,
        });
      } else {
        // Weighed stock is entered in kg and stored in grams.
        const openingQuantity =
          itemType === ItemType.MadeToOrder
            ? 0
            : serialized
              ? 0
              : byWeight
                ? Math.round((Number(opening) || 0) * 1000)
                : Number(opening) || 0;
        const finalSku = sku.replace(/-$/, "");
        if (finalSku === "" || barcode.trim() === "") {
          setBusy(false);
          return setError("SKU and barcode are required.");
        }
        const created = await inventoryApi.createProduct({
          sku: finalSku,
          barcode: barcode.trim(),
          name: name.trim(),
          model_number: modelNumber.trim() || null,
          ...classification,
          sub_category_id: subCategoryId || null,
          price_cents: cents,
          is_serialized: serialized,
          tax_category: taxCategory,
          is_open_price: openPrice && !serialized,
          ...weighed,
          ...recipes,
          ...fashion,
          sellable_units,
          opening_store_id: storeId || null,
          opening_quantity: openingQuantity,
          min_reorder_level: Number(reorder) || 0,
        });
        id = created.id;
        setPersistedId(created.id);
      }
      if (id !== null && photo.file) {
        const form = new FormData();
        form.append("file", photo.file);
        const image = await apiUpload<ProductImage>(`/api/v1/inventory/products/${id}/images`, form);
        if (!image.is_primary) await apiPatch(`/api/v1/inventory/images/${image.id}`, { is_primary: true });
      } else if (id !== null && photo.removed && product !== null) {
        const images = await apiGet<ProductImage[]>(`/api/v1/inventory/products/${id}/images`);
        const cover = images.find((image) => image.is_primary) ?? images[0];
        if (cover) await apiDelete(`/api/v1/inventory/images/${cover.id}`);
      }
      onSaved();
    } catch (caught) {
      setError(message(caught, "Could not save the product."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title={editing ? `Edit ${product.name}` : model ? `New ${model.name} variant` : "New product"}
      subtitle={
        editing ? `${product.sku} · ${product.barcode}` : "Products are shared by every branch; stock is per branch."
      }
      onClose={onClose}
      width="lg"
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy} onClick={() => void save()}>
            {busy ? "Saving…" : editing ? "Save changes" : "Create product"}
          </PrimaryButton>
        </>
      }
    >
      <ProductImageDropzone currentUrl={product?.thumb_url ?? product?.image_url ?? null} onChange={setPhoto} />
      <h3 className="mb-3 text-sm font-semibold">Catalog placement</h3>
      <div className="grid gap-4 md:grid-cols-2">
        <SelectField
          label="Category"
          value={categoryId}
          placeholder="Choose a category"
          options={categories.map((item) => ({ value: item.id, label: item.name }))}
          onChange={(next) => {
            setCategoryId(next);
            setSubCategoryId("");
            setModelId("");
          }}
        />
        <SelectField
          label="Sub-category"
          value={subCategoryId}
          disabled={!category || category.sub_categories.length === 0}
          options={[
            { value: "", label: "None" },
            ...(category?.sub_categories ?? []).map((sub) => ({ value: sub.id, label: sub.name })),
          ]}
          onChange={(next) => {
            setSubCategoryId(next);
            setModelId("");
          }}
        />
        <SelectField
          label="Brand"
          value={brandId}
          options={brandOptions}
          onChange={(next) => {
            setBrandId(next);
            setModelId("");
          }}
        />
        <SelectField
          label="Model"
          value={modelId}
          disabled={brandId === "" || subCategoryId === ""}
          placeholder={brandId === "" || subCategoryId === "" ? "Pick a sub-category and brand" : "Choose a model"}
          options={[
            { value: "", label: "No model (stand-alone product)" },
            ...models.map((item) => ({
              value: item.id,
              label: item.name,
              hint: [item.code, item.release_year].filter(Boolean).join(" · ") || undefined,
            })),
          ]}
          onChange={(next) => {
            setModelId(next);
            suggestName(models.find((item) => item.id === next)?.name, attributes);
          }}
        />
      </div>

      <h3 className="mb-3 mt-6 text-sm font-semibold">
        Variant (sub-model){model ? <span className="font-normal text-charcoal/50"> of {model.name}</span> : null}
      </h3>
      <div className="grid gap-4 md:grid-cols-3">
        {attributeKeys.map((key) => (
          <TextField
            key={key}
            label={variantAttributeLabel(key)}
            value={attributes[key] ?? ""}
            placeholder={{ storage: "256GB", ram: "8GB", color: "Natural Titanium", processor: "Apple M3", size: "46mm", connectivity: "Wi-Fi" }[key]}
            onChange={(event) => setAttribute(key, event.target.value)}
          />
        ))}
      </div>

      <h3 className="mb-3 mt-6 text-sm font-semibold">Product</h3>
      <div className="grid gap-4 md:grid-cols-2">
        <TextField
          label="Name"
          value={name}
          hint={!editing && model && !nameTouched ? "Follows the model and variant until you edit it." : undefined}
          onChange={(event) => {
            setNameTouched(true);
            setName(event.target.value);
          }}
        />
        <TextField
          label={byWeight ? "Price per kg" : "Price"}
          inputMode="decimal"
          value={price}
          onChange={(event) => setPrice(event.target.value)}
        />
        <TextField
          label="SKU"
          value={sku}
          disabled={editing}
          placeholder="Generated from the name"
          className="font-mono"
          maxLength={64}
          spellCheck={false}
          autoComplete="off"
          hint={editing ? "SKUs are fixed once a product exists." : "Letters, digits and dashes; follows the name until you edit it."}
          onChange={(event) => setSku(event.target.value)}
        />
        <TextField
          label="Barcode / UPC / EAN"
          value={barcode}
          disabled={editing}
          onChange={(event) => setBarcode(event.target.value)}
        />
        <TextField
          label="Manufacturer part number"
          value={modelNumber}
          placeholder="e.g. SM-S928B"
          onChange={(event) => setModelNumber(event.target.value)}
        />
        <SelectField<TaxCategory>
          label="VAT treatment"
          value={taxCategory}
          options={[
            { value: "STANDARD", label: "Standard rate" },
            { value: "ZERO", label: "Zero-rated (0%)" },
            { value: "EXEMPT", label: "Exempt" },
          ]}
          onChange={setTaxCategory}
        />
      </div>
      {fashionOn && modelId === "" ? (
        <div className="mt-4 grid gap-4 md:grid-cols-3">
          <TextField
            label="Season"
            placeholder="SS26"
            value={season}
            onChange={(event) => setSeason(event.target.value.toUpperCase())}
          />
          <TextField label="Collection" value={collection} onChange={(event) => setCollection(event.target.value)} />
          <SelectField
            label="Gender"
            value={gender}
            options={[
              { value: "", label: "Not set" },
              ...(Object.keys(GENDER_LABELS) as Gender[]).map((value) => ({ value, label: GENDER_LABELS[value] })),
            ]}
            onChange={setGender}
          />
        </div>
      ) : null}
      {!(editing ? product.is_serialized : serialized) && !byWeight ? (
        <div className="mt-4">
          <Toggle
            label="Open price"
            description="Cashiers type the price and a description at the till (labour, unlisted accessories). Not stocked."
            checked={openPrice}
            onChange={setOpenPrice}
          />
        </div>
      ) : null}
      {weighing && !(editing ? product.is_serialized : serialized) && !openPrice ? (
        <div className="mt-4 space-y-4">
          <Toggle
            label="Sold by weight"
            description="Priced per kg and weighed at the till, or scanned from a scale label. Stock is counted in grams."
            checked={byWeight}
            onChange={setByWeight}
          />
          {byWeight ? (
            <div className="grid gap-4 md:grid-cols-2">
              <TextField
                label="Scale PLU"
                value={plu}
                inputMode="numeric"
                maxLength={6}
                placeholder="e.g. 4016"
                hint="The code the scale prints into its labels."
                onChange={(event) => setPlu(event.target.value.replace(/\D/g, ""))}
              />
              <TextField
                label="Tare (grams)"
                type="number"
                min={0}
                value={tare}
                hint="Container weight taken off every live scale reading."
                onChange={(event) => setTare(event.target.value)}
              />
            </div>
          ) : null}
        </div>
      ) : null}
      {isFnB && !(editing ? product.is_serialized : serialized) ? (
        <div className="mt-4">
          <SelectField
            label="Item type"
            value={itemType}
            options={[
              { value: ItemType.MadeToOrder, label: "Prepared dish", hint: "Made to order. Stock lives on the recipe." },
              { value: ItemType.RawIngredient, label: "Raw ingredient", hint: "Tracked. Used by recipes, not sold on its own." },
              { value: ItemType.PrePackaged, label: "Pre-packaged", hint: "Tracked and sold as a unit, like bottled water." },
            ]}
            onChange={(next) => {
              setItemType(next as ItemTypeId);
              if (next !== ItemType.PrePackaged) setSerialized(false);
            }}
          />
        </div>
      ) : null}
      {recipesOn && !isFnB && !(editing ? product.is_serialized : serialized) && !openPrice ? (
        <div className="mt-4">
          <Toggle
            label="Ingredient"
            description="Kept in stock for recipes (coffee beans, milk, buns). Registers do not sell it on its own."
            checked={ingredient}
            onChange={setIngredient}
          />
        </div>
      ) : null}
      {!(editing ? product.is_serialized : serialized) && !byWeight && !openPrice && packOptions.length > 1 ? (
        <fieldset className="mt-4">
          <legend className="text-sm font-medium">Sells in</legend>
          <p className="text-xs text-charcoal/60">Always by the piece; tick the packs cashiers can also ring it up in.</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {packOptions
              .filter((unit) => unit.code !== "PIECE")
              .map((unit) => {
                const on = packs.includes(unit.code);
                return (
                  <button
                    key={unit.code}
                    type="button"
                    aria-pressed={on}
                    onClick={() => setPacks(on ? packs.filter((code) => code !== unit.code) : [...packs, unit.code])}
                    className={`h-8 rounded-full px-3 text-xs font-semibold transition-colors ${
                      on ? "bg-charcoal text-white" : "border border-line text-charcoal/60 hover:text-charcoal"
                    }`}
                  >
                    {unit.name} · {unit.factor} pcs
                  </button>
                );
              })}
          </div>
        </fieldset>
      ) : null}
      {!editing && itemType !== ItemType.MadeToOrder ? (
        <div className="mt-4 space-y-4">
          <Toggle
            label="Track IMEI / serial numbers"
            description="Serialized stock is added by receiving IMEIs on a purchase order."
            checked={serialized}
            onChange={setSerialized}
          />
          <div className="grid gap-4 md:grid-cols-3">
            <SelectField
              label="Opening stock at"
              value={storeId}
              disabled={user?.store_id !== null}
              options={[{ value: "", label: "No branch yet" }, ...storeOptions(stores)]}
              onChange={setStoreId}
            />
            <TextField
              label={byWeight ? "Opening stock (kg)" : "Opening quantity"}
              type="number"
              min={0}
              value={opening}
              disabled={serialized || storeId === ""}
              onChange={(event) => setOpening(event.target.value)}
            />
            <TextField
              label="Min reorder level"
              type="number"
              min={0}
              value={reorder}
              disabled={storeId === ""}
              onChange={(event) => setReorder(event.target.value)}
            />
          </div>
        </div>
      ) : null}
      <ErrorNote message={error} />
    </Modal>
  );
}
