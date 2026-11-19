import {
  DISPENSING_CLASS_LABELS,
  DISPENSING_CLASSES,
  DOSAGE_FORMS,
  GENDER_LABELS,
  ItemType,
  PHARMACY_KIND_LABELS,
  PHARMACY_PRODUCT_KINDS,
  PRICE_CONTROL_LABELS,
  PRICE_CONTROLS,
  STRENGTH_UNITS,
  cleanCode,
  compareVariantValues,
  emptyPharmacyDraft,
  allSpecKeys,
  randomCode128,
  randomEan13,
  skuFromParts,
  specSchemaFor,
  titleFromSpecs,
  type Gender,
  type PharmacyDraft,
  type PharmacyProductDetail,
  type TaxCategory,
  type VariantDraft,
} from "@ai-pos/shared-types";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  inventoryApi,
  inventoryError,
  type BrandRow,
  type CategoryRow,
  type ModelRow,
  type ProductDetail,
  type ProductRow,
  type StoreRow,
  type UnitRow,
} from "./api";
import { CreatableLookupField } from "./creatableLookup";
import { compressImageToWebp } from "./imageFile";
import { SavedPhotoGallery } from "./photoGallery";
import { FashionMatrix } from "./fashionMatrix";
import { ProductPhotos, type PendingPhoto } from "./productPhotos";
import { SpecEditor } from "./specEditor";
import type { WorkspaceAccess } from "./panels";
import {
  emptyProductForm,
  centsFromPrice,
  productCreateBody,
  productUpdateBody,
  resolvedSku,
  validateProductForm,
  type ProductFormState,
} from "./productPayload";
import { Banner, Field, FormModal, PrimaryButton, QuietButton, control } from "./ui";

function section(title: string) {
  return <h3 className="pt-2 text-sm font-semibold text-zinc-800 dark:text-zinc-100">{title}</h3>;
}

function draftFromDetail(row: PharmacyProductDetail): PharmacyDraft {
  const base = emptyPharmacyDraft();
  return {
    ...base,
    product_kind: row.product_kind,
    dispensing_class: row.dispensing_class,
    generic_name: row.generic_name ?? "",
    manufacturer: row.manufacturer ?? "",
    marketing_authorization_holder: row.marketing_authorization_holder ?? "",
    country_of_origin: row.country_of_origin ?? "",
    description: row.description ?? "",
    gtin: row.gtin ?? "",
    manufacturer_product_ref: row.manufacturer_product_ref ?? "",
    dosage_form: row.dosage_form ?? "",
    route: row.route ?? "",
    strength_amount: row.strength_amount == null ? "" : String(row.strength_amount),
    strength_unit: row.strength_unit ?? "",
    concentration: row.concentration ?? "",
    pack_size_label: row.pack_size_label ?? "",
    units_per_pack: String(row.units_per_pack ?? 1),
    base_unit_code: row.base_unit_code || "PIECE",
    selling_unit_code: row.selling_unit_code || "PIECE",
    storage_condition: row.storage_condition ?? "",
    temp_min_c: row.temp_min_c == null ? "" : String(row.temp_min_c),
    temp_max_c: row.temp_max_c == null ? "" : String(row.temp_max_c),
    cold_chain: row.cold_chain,
    handling_instructions: row.handling_instructions ?? "",
    warnings_text: row.warnings_text ?? "",
    registration_number: row.registration_number ?? "",
    registration_authority: row.registration_authority ?? "",
    price_control: row.price_control,
    min_price_cents: row.min_price_cents == null ? "" : (row.min_price_cents / 100).toFixed(2),
    max_price_cents: row.max_price_cents == null ? "" : (row.max_price_cents / 100).toFixed(2),
    offline_policy: row.offline_policy,
    ingredients: row.ingredients.map((item) => ({
      name: item.name,
      strength_amount: item.strength_amount == null ? "" : String(item.strength_amount),
      strength_unit: item.strength_unit,
      is_active_ingredient: item.is_active_ingredient,
    })),
    documents: row.documents.map((item) => ({
      kind: (item.kind as PharmacyDraft["documents"][number]["kind"]) || "other",
      title: item.title,
      reference: item.reference,
    })),
  };
}

function fromProduct(product: ProductDetail, fnb: boolean): ProductFormState {
  const base = emptyProductForm(product.store_id, fnb);
  return {
    ...base,
    name: product.name,
    sku: product.sku,
    barcode: product.barcode ?? "",
    modelNumber: product.model_number ?? "",
    categoryId: product.category_id ?? "",
    subCategoryId: product.sub_category_id ?? "",
    brandId: product.brand_id ?? "",
    modelId: product.product_model_id ?? "",
    price: (product.price_cents / 100).toFixed(2),
    priceIncludesTax: Boolean(product.price_includes_tax),
    taxCategory: product.tax_category ?? "STANDARD",
    openPrice: Boolean(product.is_open_price),
    weighed: Boolean(product.sold_by_weight),
    plu: product.plu_code ?? "",
    tare: String(product.tare_grams ?? 0),
    minimumAge: product.minimum_age == null ? "" : String(product.minimum_age),
    ingredient: Boolean(product.is_ingredient),
    itemType: product.item_type ?? base.itemType,
    serialized: product.is_serialized,
    opening: "0",
    reorder: "0",
    season: product.season ?? "",
    collection: product.collection ?? "",
    gender: product.gender ?? "",
    specs: { ...(product.specifications ?? {}), ...(product.variant_attributes ?? {}) },
    packs: (product.sellable_units ?? []).filter((code) => code !== "PIECE"),
    active: product.is_active !== false,
    skuManual: true,
    nameTouched: true,
    autoBarcode: false,
    storeId: product.store_id ?? "",
  };
}

export function ProductDrawer({
  access,
  product,
  onClose,
  onSaved,
}: {
  access: WorkspaceAccess;
  product: ProductRow | null;
  onClose: () => void;
  onSaved: (message: string) => void;
}) {
  const editing = product !== null;
  const [state, setState] = useState<ProductFormState>(() => emptyProductForm(access.storeId, access.fnb));
  const [pharmacy, setPharmacy] = useState<PharmacyDraft>(() => emptyPharmacyDraft());
  const [categories, setCategories] = useState<CategoryRow[]>([]);
  const [brands, setBrands] = useState<BrandRow[]>([]);
  const [models, setModels] = useState<ModelRow[]>([]);
  const [photos, setPhotos] = useState<PendingPhoto[]>([]);
  const [mainPhoto, setMainPhoto] = useState<string | null>(null);
  const [matrixAxes, setMatrixAxes] = useState<Record<string, string[]>>({});
  const [variantRows, setVariantRows] = useState<VariantDraft[]>([]);
  const [units, setUnits] = useState<UnitRow[]>([]);
  const [stores, setStores] = useState<StoreRow[]>([]);
  const [keptKeys, setKeptKeys] = useState<string[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const catalogAdmin = access.manage && access.storeId === null;
  const patch = (part: Partial<ProductFormState>) => setState((current) => ({ ...current, ...part }));
  const patchPharmacy = (part: Partial<PharmacyDraft>) => setPharmacy((current) => ({ ...current, ...part }));

  useEffect(() => {
    if (!access.online) return;
    void inventoryApi.categories().then(setCategories).catch(() => setCategories([]));
    void inventoryApi.brands().then(setBrands).catch(() => setBrands([]));
    void inventoryApi.units().then(setUnits).catch(() => setUnits([]));
    void inventoryApi.stores().then(setStores).catch(() => setStores([]));
  }, [access.online]);

  useEffect(() => {
    if (!access.online || state.brandId === "" || state.subCategoryId === "") {
      setModels([]);
      return;
    }
    void inventoryApi
      .models({ brand_id: state.brandId, sub_category_id: state.subCategoryId })
      .then(setModels)
      .catch(() => setModels([]));
  }, [access.online, state.brandId, state.subCategoryId]);

  useEffect(() => {
    if (!product || !access.online) return;
    void inventoryApi.product(product.id).then((detail) => {
      setState(fromProduct(detail, access.fnb));
      const known = allSpecKeys();
      setKeptKeys(Object.keys(detail.variant_attributes ?? {}).filter((key) => !known.has(key)));
    }).catch(() => setError("The saved product could not be loaded. The list values stay in the form."));
    if (access.pharmacy) {
      void inventoryApi.pharmacyProduct(product.id).then((detail) => setPharmacy(draftFromDetail(detail))).catch(() => undefined);
    }
  }, [access.fnb, access.online, access.pharmacy, product]);

  const category = categories.find((item) => item.id === state.categoryId);
  const schema = useMemo(
    () =>
      specSchemaFor(category?.name ?? "", category?.sub_categories.find((item) => item.id === state.subCategoryId)?.name ?? "", {
        productName: state.name,
        profile: access.profile,
      }),
    [access.profile, category, state.name, state.subCategoryId],
  );
  const visibleModels = models.filter(
    (item) => item.brand_id === state.brandId && item.sub_category_id === state.subCategoryId,
  );
  const skuValue = resolvedSku(state, editing);

  function jump(id: string) {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function uniqueBarcode(kind: "ean13" | "code128"): Promise<string | null> {
    for (let attempt = 0; attempt < 6; attempt += 1) {
      const code = kind === "ean13" ? randomEan13(state.barcodePrefix) : randomCode128(state.barcodePrefix);
      const hits = await inventoryApi.searchProducts(code, access.storeId).catch(() => []);
      if (!hits.some((hit) => (hit.product.barcode ?? "").toLowerCase() === code.toLowerCase())) return code;
    }
    setError("Could not find a unique barcode. Try another prefix.");
    return null;
  }

  async function uploadPhotos(productId: string) {
    const chosen = photos.find((item) => item.key === mainPhoto) ?? photos[0];
    if (!chosen) return;
    const ordered = [chosen, ...photos.filter((item) => item.key !== chosen.key)];
    for (const item of ordered) await inventoryApi.uploadProductImage(productId, await compressImageToWebp(item.file));
  }

  async function addRecord(kind: "category" | "sub" | "brand" | "model", label: string) {
    try {
      if (kind === "category") {
        const created = await inventoryApi.createCategory({ name: label });
        setCategories(await inventoryApi.categories());
        patch({ categoryId: created.id, subCategoryId: "", modelId: "", specs: {} });
      } else if (kind === "sub" && state.categoryId) {
        const parent = await inventoryApi.createSubCategory(state.categoryId, { name: label });
        setCategories(await inventoryApi.categories());
        const created = parent.sub_categories.find((item) => item.name.toLowerCase() === label.toLowerCase());
        patch({ subCategoryId: created?.id ?? "", modelId: "", specs: {} });
      } else if (kind === "brand" && state.subCategoryId) {
        const created = await inventoryApi.createBrand({ name: label, sub_category_ids: [state.subCategoryId] });
        setBrands(await inventoryApi.brands());
        patch({ brandId: created.id, modelId: "" });
      } else if (kind === "model" && state.brandId && state.subCategoryId) {
        const created = await inventoryApi.createModel({ name: label, brand_id: state.brandId, sub_category_id: state.subCategoryId });
        setModels(await inventoryApi.models());
        patch({ modelId: created.id });
        if (!state.nameTouched) patch({ name: created.name });
      }
    } catch (caught) {
      setError(inventoryError(caught, "That record was not created."));
    }
  }

  function generateFromSpecs() {
    const title = titleFromSpecs({
      brand: brands.find((item) => item.id === state.brandId)?.name ?? "",
      model: visibleModels.find((item) => item.id === state.modelId)?.name ?? "",
      schema,
      specs: state.specs,
    });
    const nextName = title !== "" ? title : state.name;
    patch({
      ...(title !== "" ? { name: nextName, nameTouched: true } : {}),
      ...(!editing ? { skuManual: true, sku: skuFromParts(state.skuPrefix, nextName, {}) } : {}),
    });
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!access.online) return;
    let draft = { ...state, sku: skuValue };
    if (!editing && draft.barcode.trim() === "" && state.autoBarcode) {
      const code = await uniqueBarcode("ean13");
      if (!code) return;
      draft = { ...draft, barcode: code };
      patch({ barcode: code, sku: skuValue });
    } else if (draft.sku !== state.sku) {
      patch({ sku: skuValue });
    }
    const nextErrors = validateProductForm(draft, {
      editing,
      pharmacy: access.pharmacy,
      dispensingClass: pharmacy.dispensing_class,
      autoBarcode: state.autoBarcode,
    });
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) return;
    setBusy(true);
    setError(null);
    const options = {
      fashion: access.fashion,
      fnb: access.fnb,
      variantKeys: schema.variantKeys,
      keptKeys,
      pharmacy: access.pharmacy ? pharmacy : null,
    };
    try {
      const included = variantRows.filter((row) => row.included);
      if (included.length > 0) {
        const cents = centsFromPrice(draft.price);
        if (cents === null) throw new Error("Enter a price with up to two decimal places.");
        let modelId = draft.modelId;
        if (modelId === "") {
          if (draft.brandId === "" || draft.subCategoryId === "") {
            throw new Error("Choose a brand and sub-category so the size and color variants stay under one style.");
          }
          const createdModel = await inventoryApi.createModel({
            name: draft.name.trim(),
            brand_id: draft.brandId,
            sub_category_id: draft.subCategoryId,
            season: draft.season.trim() || null,
            collection: draft.collection.trim() || null,
            gender: draft.gender || null,
          });
          modelId = createdModel.id;
        }
        const axisKeys = schema.variantKeys.filter((key) => included.every((row) => (row.attributes[key] ?? "").trim() !== ""));
        await inventoryApi.generateMatrix(modelId, {
          axes: axisKeys.map((key) => ({
            key,
            values: [...new Set(included.map((row) => row.attributes[key]).filter((value): value is string => Boolean(value)))],
          })),
          price_cents: cents,
          sku_prefix: draft.skuPrefix || null,
          tax_category: draft.taxCategory,
          price_includes_tax: draft.priceIncludesTax,
          opening_store_id: draft.storeId || null,
          specifications: Object.fromEntries(
            Object.entries(draft.specs).filter(([key, value]) => value.trim() !== "" && !axisKeys.includes(key)),
          ),
          variants: included.map((row) => ({
            attributes: Object.fromEntries(axisKeys.map((key) => [key, row.attributes[key] ?? ""])),
            ...(row.existingId ? { product_id: row.existingId } : {}),
            sku: row.sku.trim() || null,
            barcode: row.barcode.trim() || null,
            price_cents: centsFromPrice(row.price) ?? cents,
            is_active: row.included,
            ...(row.existingId
              ? {}
              : {
                  opening_quantity: Number(row.opening) || 0,
                  min_reorder_level: Number(row.reorder) || 0,
                  ...(centsFromPrice(row.cost) !== null && row.cost.trim() !== "" ? { cost_cents: centsFromPrice(row.cost) } : {}),
                }),
          })),
        });
        if (photos.length > 0 && modelId) {
          for (const item of [photos.find((photo) => photo.key === mainPhoto) ?? photos[0], ...photos.filter((photo) => photo.key !== mainPhoto)]) {
            if (item) await inventoryApi.uploadModelImage(modelId, await compressImageToWebp(item.file));
          }
        }
        onSaved("Variants created.");
        return;
      }
      if (product) {
        await inventoryApi.updateProduct(product.id, productUpdateBody(draft, options));
        if (photos.length > 0) await uploadPhotos(product.id);
        onSaved(state.active ? "Product updated." : "Product archived. Historical sales stay on the ledger.");
      } else {
        const created = await inventoryApi.createProduct(productCreateBody(draft, options));
        if (photos.length > 0) await uploadPhotos(created.id);
        onSaved(access.pharmacy ? "Medicine created." : "Product created.");
      }
    } catch (caught) {
      setError(inventoryError(caught, "The product was not saved."));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!product) return;
    setBusy(true);
    try {
      await inventoryApi.deleteProduct(product.id);
      onSaved("Product removed. It had no sales, stock movements or lot allocations.");
    } catch (caught) {
      setError(inventoryError(caught, "Deletion is blocked while sales, stock movements or lots still reference this product. Archive it instead."));
    } finally {
      setBusy(false);
    }
  }

  const showWeight = access.weighed && !state.serialized && !state.openPrice;
  const showSerial = access.serialized && !access.pharmacy && !state.weighed && !state.openPrice && state.itemType !== ItemType.MadeToOrder;

  return (
    <FormModal
      title={editing ? `Edit ${product.name}` : "New product"}
      subtitle={editing ? `${product.sku} · ${product.barcode ?? ""}` : "Products are shared by every branch; stock is per branch."}
      onClose={onClose}
      headerExtra={
        <div className="mt-3 flex flex-wrap gap-2">
          {[
            ["product-section-catalog", "Catalog"],
            ["product-section-specs", "Specifications"],
            ["product-section-product", "Product"],
            ["product-section-stock", "Stock"],
          ].map(([id, label]) => (
            <button key={id} type="button" onClick={() => jump(id ?? "")} className="rounded-full bg-zinc-100 px-3 py-1 text-xs font-semibold text-zinc-700">
              {label}
            </button>
          ))}
        </div>
      }
      footer={
        <div className="flex flex-wrap justify-end gap-2">
          <QuietButton onClick={onClose} disabled={busy}>Cancel</QuietButton>
          <PrimaryButton type="submit" form="product-form" disabled={busy || !access.online}>
            {busy ? "Saving…" : editing ? "Save changes" : "Create product"}
          </PrimaryButton>
        </div>
      }
    >
      <form id="product-form" className="space-y-4" onSubmit={(event) => void save(event)}>
        {error ? <Banner tone="error">{error}</Banner> : null}
        {!access.online ? <Banner tone="info">Product changes stay closed until the connection returns.</Banner> : null}
        {editing && product ? <SavedPhotoGallery productId={product.id} /> : <ProductPhotos photos={photos} mainKey={mainPhoto} onChange={(next, main) => { setPhotos(next); setMainPhoto(main); }} />}

        <h3 id="product-section-catalog" className="scroll-mt-4 pt-2 text-sm font-semibold">Catalog placement</h3>
        <div className="grid gap-3 sm:grid-cols-2">
          <CreatableLookupField
            label="Category"
            value={state.categoryId}
            error={errors.category}
            placeholder="Choose a category"
            options={categories.map((item) => ({ value: item.id, label: item.name }))}
            onCreate={catalogAdmin ? (label) => void addRecord("category", label) : undefined}
            onChange={(next) => patch({ categoryId: next, subCategoryId: "", modelId: "", specs: {} })}
          />
          <CreatableLookupField
            label="Sub-category"
            value={state.subCategoryId}
            disabled={!category}
            placeholder="None"
            options={[{ value: "", label: "None" }, ...(category?.sub_categories ?? []).map((item) => ({ value: item.id, label: item.name }))]}
            onCreate={catalogAdmin && category ? (label) => void addRecord("sub", label) : undefined}
            onChange={(next) => patch({ subCategoryId: next, modelId: "", specs: {} })}
          />
          <CreatableLookupField
            label="Brand"
            value={state.brandId}
            placeholder="None"
            hint={catalogAdmin && state.subCategoryId === "" ? "Pick a sub-category first." : undefined}
            options={[{ value: "", label: "None" }, ...brands.map((item) => ({ value: item.id, label: item.name }))]}
            onCreate={catalogAdmin && state.subCategoryId !== "" ? (label) => void addRecord("brand", label) : undefined}
            onChange={(next) => patch({ brandId: next, modelId: "" })}
          />
          <CreatableLookupField
            label="Model"
            value={state.modelId}
            disabled={state.brandId === "" || state.subCategoryId === ""}
            placeholder={state.brandId === "" || state.subCategoryId === "" ? "Pick a sub-category and brand first." : "Choose a model"}
            hint={state.brandId === "" || state.subCategoryId === "" ? "Pick a sub-category and brand first." : undefined}
            options={[{ value: "", label: "No model (stand-alone product)" }, ...visibleModels.map((item) => ({ value: item.id, label: item.name }))]}
            onCreate={catalogAdmin && state.brandId !== "" && state.subCategoryId !== "" ? (label) => void addRecord("model", label) : undefined}
            createMinLength={1}
            onChange={(next) => {
              patch({ modelId: next });
              const modelName = visibleModels.find((item) => item.id === next)?.name;
              if (!state.nameTouched && modelName) patch({ name: modelName, nameTouched: false });
            }}
          />
        </div>

        {access.pharmacy ? (
          <>
            {section("Medicine identity")}
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Product kind" required>
                <select className={control} value={pharmacy.product_kind} onChange={(event) => patchPharmacy({ product_kind: event.target.value as PharmacyDraft["product_kind"] })}>
                  {PHARMACY_PRODUCT_KINDS.map((kind) => <option key={kind} value={kind}>{PHARMACY_KIND_LABELS[kind]}</option>)}
                </select>
              </Field>
              <Field label="Dispensing class" required error={errors.dispensing}>
                <select className={control} value={pharmacy.dispensing_class} onChange={(event) => patchPharmacy({ dispensing_class: event.target.value as PharmacyDraft["dispensing_class"] })}>
                  <option value="">Choose a class</option>
                  {DISPENSING_CLASSES.map((item) => <option key={item} value={item}>{DISPENSING_CLASS_LABELS[item]}</option>)}
                </select>
              </Field>
              <Field label="Generic name"><input className={control} value={pharmacy.generic_name} onChange={(event) => patchPharmacy({ generic_name: event.target.value })} /></Field>
              <Field label="Manufacturer"><input className={control} value={pharmacy.manufacturer} onChange={(event) => patchPharmacy({ manufacturer: event.target.value })} /></Field>
              <Field label="Marketing authorization holder"><input className={control} value={pharmacy.marketing_authorization_holder} onChange={(event) => patchPharmacy({ marketing_authorization_holder: event.target.value })} /></Field>
              <Field label="Country of origin"><input className={control} value={pharmacy.country_of_origin} onChange={(event) => patchPharmacy({ country_of_origin: event.target.value })} /></Field>
            </div>
            {section("Active ingredients")}
            <QuietButton onClick={() => patchPharmacy({ ingredients: [...pharmacy.ingredients, { name: "", strength_amount: "", strength_unit: "mg", is_active_ingredient: true }] })}>
              Add ingredient
            </QuietButton>
            {pharmacy.ingredients.map((row, index) => (
              <div key={index} className="grid gap-3 sm:grid-cols-[1fr_8rem_8rem_auto]">
                <Field label={index === 0 ? "Ingredient" : "Ingredient"}>
                  <input className={control} value={row.name} onChange={(event) => patchPharmacy({ ingredients: pharmacy.ingredients.map((item, itemIndex) => itemIndex === index ? { ...item, name: event.target.value } : item) })} />
                </Field>
                <Field label="Strength">
                  <input className={control} value={row.strength_amount} onChange={(event) => patchPharmacy({ ingredients: pharmacy.ingredients.map((item, itemIndex) => itemIndex === index ? { ...item, strength_amount: event.target.value } : item) })} />
                </Field>
                <Field label="Unit">
                  <select className={control} value={row.strength_unit} onChange={(event) => patchPharmacy({ ingredients: pharmacy.ingredients.map((item, itemIndex) => itemIndex === index ? { ...item, strength_unit: event.target.value } : item) })}>
                    {STRENGTH_UNITS.map((item) => <option key={item} value={item}>{item}</option>)}
                  </select>
                </Field>
                <QuietButton onClick={() => patchPharmacy({ ingredients: pharmacy.ingredients.filter((_, itemIndex) => itemIndex !== index) })}>Remove</QuietButton>
              </div>
            ))}
            {pharmacy.product_kind === "MEDICINE" ? (
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Strength"><input className={control} inputMode="decimal" value={pharmacy.strength_amount} onChange={(event) => patchPharmacy({ strength_amount: event.target.value })} /></Field>
                <Field label="Strength unit">
                  <select className={control} value={pharmacy.strength_unit} onChange={(event) => patchPharmacy({ strength_unit: event.target.value })}>
                    <option value="">Not set</option>
                    {STRENGTH_UNITS.map((item) => <option key={item} value={item}>{item}</option>)}
                  </select>
                </Field>
                <Field label="Concentration"><input className={control} value={pharmacy.concentration} onChange={(event) => patchPharmacy({ concentration: event.target.value })} /></Field>
                <Field label="Dosage form">
                  <select className={control} value={pharmacy.dosage_form} onChange={(event) => patchPharmacy({ dosage_form: event.target.value })}>
                    <option value="">Choose a form</option>
                    {DOSAGE_FORMS.map((item) => <option key={item} value={item}>{item}</option>)}
                  </select>
                </Field>
                <Field label="Route"><input className={control} value={pharmacy.route} onChange={(event) => patchPharmacy({ route: event.target.value })} /></Field>
              </div>
            ) : null}
            {section("Pack and units")}
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Pack size"><input className={control} value={pharmacy.pack_size_label} onChange={(event) => patchPharmacy({ pack_size_label: event.target.value })} /></Field>
              <Field label="Units per pack" hint="Whole number of base units. One box of 10 is 10, not 0.1.">
                <input className={control} inputMode="numeric" value={pharmacy.units_per_pack} onChange={(event) => patchPharmacy({ units_per_pack: event.target.value })} />
              </Field>
              <Field label="Base unit"><input className={control} value={pharmacy.base_unit_code} onChange={(event) => patchPharmacy({ base_unit_code: event.target.value })} /></Field>
              <Field label="Selling unit"><input className={control} value={pharmacy.selling_unit_code} onChange={(event) => patchPharmacy({ selling_unit_code: event.target.value })} /></Field>
            </div>
            {section("Registration and storage")}
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="GTIN"><input className={control} value={pharmacy.gtin} onChange={(event) => patchPharmacy({ gtin: event.target.value })} /></Field>
              <Field label="Manufacturer reference"><input className={control} value={pharmacy.manufacturer_product_ref} onChange={(event) => patchPharmacy({ manufacturer_product_ref: event.target.value })} /></Field>
              <Field label="Registration number" hint="Leave blank when it has not been supplied. Nothing is generated.">
                <input className={control} value={pharmacy.registration_number} onChange={(event) => patchPharmacy({ registration_number: event.target.value })} />
              </Field>
              <Field label="Registration authority"><input className={control} value={pharmacy.registration_authority} onChange={(event) => patchPharmacy({ registration_authority: event.target.value })} /></Field>
              <Field label="Storage"><input className={control} value={pharmacy.storage_condition} onChange={(event) => patchPharmacy({ storage_condition: event.target.value })} /></Field>
              <Field label="Minimum °C"><input className={control} value={pharmacy.temp_min_c} onChange={(event) => patchPharmacy({ temp_min_c: event.target.value })} /></Field>
              <Field label="Maximum °C"><input className={control} value={pharmacy.temp_max_c} onChange={(event) => patchPharmacy({ temp_max_c: event.target.value })} /></Field>
            </div>
            {section("Official price")}
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Price control">
                <select className={control} value={pharmacy.price_control} onChange={(event) => patchPharmacy({ price_control: event.target.value as PharmacyDraft["price_control"] })}>
                  {PRICE_CONTROLS.map((item) => <option key={item} value={item}>{PRICE_CONTROL_LABELS[item]}</option>)}
                </select>
              </Field>
              {pharmacy.price_control === "MINIMUM" || pharmacy.price_control === "FIXED" ? (
                <Field label="Official minimum" hint="Leave blank to keep the official price missing.">
                  <input className={control} inputMode="decimal" value={pharmacy.min_price_cents} onChange={(event) => patchPharmacy({ min_price_cents: event.target.value })} />
                </Field>
              ) : null}
              {pharmacy.price_control === "MAXIMUM" || pharmacy.price_control === "FIXED" ? (
                <Field label="Official maximum" hint="Leave blank to keep the official price missing.">
                  <input className={control} inputMode="decimal" value={pharmacy.max_price_cents} onChange={(event) => patchPharmacy({ max_price_cents: event.target.value })} />
                </Field>
              ) : null}
            </div>
            {section("Documents")}
            <QuietButton onClick={() => patchPharmacy({ documents: [...pharmacy.documents, { kind: "leaflet", title: "", reference: "" }] })}>Add document</QuietButton>
            {pharmacy.documents.length === 0 ? <p className="text-xs text-zinc-500">No leaflet or registration file is attached.</p> : null}
            {pharmacy.documents.map((row, index) => (
              <div key={index} className="grid gap-3 sm:grid-cols-2">
                <Field label="Kind">
                  <select className={control} value={row.kind} onChange={(event) => patchPharmacy({ documents: pharmacy.documents.map((item, itemIndex) => itemIndex === index ? { ...item, kind: event.target.value as PharmacyDraft["documents"][number]["kind"] } : item) })}>
                    <option value="leaflet">Leaflet</option>
                    <option value="registration">Registration</option>
                    <option value="supplier">Supplier</option>
                    <option value="other">Other</option>
                  </select>
                </Field>
                <Field label="Title"><input className={control} value={row.title} onChange={(event) => patchPharmacy({ documents: pharmacy.documents.map((item, itemIndex) => itemIndex === index ? { ...item, title: event.target.value } : item) })} /></Field>
                <Field label="Reference"><input className={control} value={row.reference} onChange={(event) => patchPharmacy({ documents: pharmacy.documents.map((item, itemIndex) => itemIndex === index ? { ...item, reference: event.target.value } : item) })} /></Field>
                <QuietButton onClick={() => patchPharmacy({ documents: pharmacy.documents.filter((_, itemIndex) => itemIndex !== index) })}>Remove</QuietButton>
              </div>
            ))}
            <p className="text-xs text-zinc-500">Manufacturer lot and expiry are recorded on the stock batch, not on this product.</p>
          </>
        ) : (
          <div id="product-section-specs" className="scroll-mt-4">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
              <h3 className="text-sm font-semibold">{schema.title || "Specifications"}</h3>
              <button type="button" className="h-9 rounded-full bg-zinc-900 px-3 text-xs font-semibold text-white" onClick={generateFromSpecs}>
                Auto-Generate Name & SKU from Specs
              </button>
            </div>
            <SpecEditor
              schema={schema}
              specs={state.specs}
              onChange={(specs) => patch({ specs })}
              multiKeys={access.fashion ? schema.variantKeys : []}
              multiValues={matrixAxes}
              onMultiChange={(key, values) => {
                const seen = new Set<string>();
                const next = values.filter((value) => {
                  const token = value.trim().toLowerCase();
                  if (value.trim() === "" || seen.has(token)) return false;
                  seen.add(token);
                  return true;
                }).sort(compareVariantValues);
                setMatrixAxes((current) => ({ ...current, [key]: next }));
              }}
            />
            {access.fashion && schema.variantKeys.length > 0 ? (
              <FashionMatrix
                axes={schema.variantKeys.map((key) => ({ key, label: key, values: matrixAxes[key] ?? [] }))}
                productName={state.name}
                skuPrefix={state.skuPrefix}
                defaultPrice={state.price}
                defaultOpening={state.opening}
                defaultReorder={state.reorder}
                rows={variantRows}
                onChange={setVariantRows}
              />
            ) : null}
          </div>
        )}

        <h3 id="product-section-product" className="scroll-mt-4 pt-2 text-sm font-semibold">Product</h3>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Name" required error={errors.name}>
            <input className={control} value={state.name} onChange={(event) => patch({ name: event.target.value, nameTouched: true })} />
          </Field>
          <Field label={state.weighed ? "Price per kg" : "Price"} required error={errors.price}>
            <input className={control} inputMode="decimal" value={state.price} onChange={(event) => patch({ price: event.target.value })} />
          </Field>
          <Field label="SKU" required error={errors.sku} hint={editing ? "SKUs are fixed once a product exists." : "Letters, digits and dashes. Follows the name until you edit it."}>
            <div className="flex gap-2">
              <input className={control} value={skuValue} disabled={editing} placeholder="Generated from the name" onChange={(event) => patch({ skuManual: true, sku: cleanCode(event.target.value, 64) })} />
              {editing ? null : <button type="button" className="h-12 shrink-0 rounded-full bg-zinc-900 px-3 text-xs font-semibold text-white" onClick={() => patch({ skuManual: true, sku: skuFromParts(state.skuPrefix, state.name, state.specs) })}>Auto Generate</button>}
            </div>
            {editing ? null : <input className={`${control} mt-2`} value={state.skuPrefix} maxLength={8} placeholder="SKU prefix" onChange={(event) => patch({ skuPrefix: cleanCode(event.target.value, 8) })} />}
          </Field>
          <Field label="Barcode / UPC / EAN" required={!editing && !state.autoBarcode} error={errors.barcode} hint={editing ? "Barcodes are fixed once a product exists." : "Leave blank to assign a unique EAN-13."}>
            <div className="flex gap-2">
              <input className={control} value={state.barcode} disabled={editing} onChange={(event) => patch({ barcode: event.target.value.trim(), autoBarcode: event.target.value.trim() === "" })} />
              {editing ? null : <button type="button" className="h-12 shrink-0 rounded-full bg-zinc-900 px-3 text-xs font-semibold text-white" onClick={() => void uniqueBarcode("ean13").then((code) => { if (code) patch({ barcode: code, autoBarcode: false }); })}>EAN-13</button>}
            </div>
            {editing ? null : (
              <div className="mt-2 flex flex-wrap gap-2">
                <button type="button" className="h-9 rounded-full px-3 text-xs font-semibold ring-1 ring-zinc-300" onClick={() => void uniqueBarcode("code128").then((code) => { if (code) patch({ barcode: code, autoBarcode: false }); })}>Code 128</button>
                <input className="h-9 w-28 rounded-xl border border-zinc-300 px-3 font-mono text-sm" value={state.barcodePrefix} maxLength={11} onChange={(event) => patch({ barcodePrefix: event.target.value.replace(/[^\dA-Za-z]/g, "").slice(0, 11) })} />
                <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={state.autoBarcode} onChange={(event) => patch({ autoBarcode: event.target.checked })} /> Auto-assign if blank</label>
              </div>
            )}
          </Field>
          <Field label="Manufacturer part number">
            <input className={control} value={state.modelNumber} onChange={(event) => patch({ modelNumber: event.target.value })} />
          </Field>
          <Field label="VAT treatment">
            <select className={control} value={state.taxCategory} onChange={(event) => patch({ taxCategory: event.target.value as TaxCategory })}>
              <option value="STANDARD">Standard rate</option>
              <option value="ZERO">Zero-rated (0%)</option>
              <option value="EXEMPT">Exempt</option>
            </select>
          </Field>
        </div>
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" className="mt-1 h-5 w-5" checked={state.priceIncludesTax} onChange={(event) => patch({ priceIncludesTax: event.target.checked })} />
          <span>Price includes tax. When off, tax is added at checkout.</span>
        </label>

        {access.fashion && state.modelId === "" ? (
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Season"><input className={control} value={state.season} onChange={(event) => patch({ season: event.target.value.toUpperCase() })} /></Field>
            <Field label="Collection"><input className={control} value={state.collection} onChange={(event) => patch({ collection: event.target.value })} /></Field>
            <Field label="Gender">
              <select className={control} value={state.gender} onChange={(event) => patch({ gender: event.target.value })}>
                <option value="">Not set</option>
                {(Object.keys(GENDER_LABELS) as Gender[]).map((value) => <option key={value} value={value}>{GENDER_LABELS[value]}</option>)}
              </select>
            </Field>
          </div>
        ) : null}

        {!state.serialized && !state.weighed ? (
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1 h-5 w-5" checked={state.openPrice} onChange={(event) => patch({ openPrice: event.target.checked })} />
            <span>Open price. Cashiers type the price at the till.</span>
          </label>
        ) : null}
        {showWeight ? (
          <>
            <label className="flex items-start gap-2 text-sm">
              <input type="checkbox" className="mt-1 h-5 w-5" checked={state.weighed} onChange={(event) => patch({ weighed: event.target.checked })} />
              <span>Sold by weight. Priced per kg. Stock is counted in grams.</span>
            </label>
            {errors.weighed ? <p className="text-xs font-medium text-red-700">{errors.weighed}</p> : null}
            {state.weighed ? (
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Scale PLU" error={errors.plu} hint="The code the scale prints into its labels.">
                  <input className={control} inputMode="numeric" maxLength={6} value={state.plu} onChange={(event) => patch({ plu: event.target.value.replace(/\D/g, "") })} />
                </Field>
                <Field label="Tare (grams)" hint="Container weight taken off every live scale reading.">
                  <input className={control} inputMode="numeric" value={state.tare} onChange={(event) => patch({ tare: event.target.value })} />
                </Field>
              </div>
            ) : null}
          </>
        ) : null}
        <Field label="Minimum age" error={errors.minimumAge} hint="The till asks before payment. Leave blank when no check is required.">
          <input className={control} inputMode="numeric" value={state.minimumAge} onChange={(event) => patch({ minimumAge: event.target.value })} />
        </Field>
        {access.fnb && !state.serialized ? (
          <Field label="Item type">
            <select className={control} value={state.itemType} onChange={(event) => patch({ itemType: event.target.value, serialized: event.target.value === ItemType.PrePackaged ? state.serialized : false })}>
              <option value={ItemType.MadeToOrder}>Prepared dish</option>
              <option value={ItemType.RawIngredient}>Raw ingredient</option>
              <option value={ItemType.PrePackaged}>Pre-packaged</option>
            </select>
          </Field>
        ) : null}
        {access.recipes && !access.fnb && !state.serialized && !state.openPrice ? (
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1 h-5 w-5" checked={state.ingredient} onChange={(event) => patch({ ingredient: event.target.checked })} />
            <span>Ingredient. Kept for recipes. Registers do not sell it on its own.</span>
          </label>
        ) : null}
        {!state.serialized && !state.weighed && !state.openPrice && units.filter((unit) => unit.code !== "PIECE" && unit.is_active).length > 0 ? (
          <fieldset>
            <legend className="text-sm font-medium">Sells in</legend>
            <p className="text-xs text-zinc-500">Always by the piece. Tick the packs cashiers can also ring it up in.</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {units.filter((unit) => unit.code !== "PIECE" && unit.is_active).map((unit) => {
                const on = state.packs.includes(unit.code);
                return (
                  <button key={unit.code} type="button" aria-pressed={on} className={`h-10 rounded-full px-3 text-sm font-semibold ${on ? "bg-zinc-900 text-white" : "ring-1 ring-zinc-300"}`} onClick={() => patch({ packs: on ? state.packs.filter((code) => code !== unit.code) : [...state.packs, unit.code] })}>
                    {unit.name} · {unit.factor} pcs
                  </button>
                );
              })}
            </div>
          </fieldset>
        ) : null}

        {!editing && state.itemType !== ItemType.MadeToOrder ? (
          <>
            <h3 id="product-section-stock" className="scroll-mt-4 pt-2 text-sm font-semibold">Stock</h3>
            {showSerial ? (
              <label className="flex items-start gap-2 text-sm">
                <input type="checkbox" className="mt-1 h-5 w-5" checked={state.serialized} onChange={(event) => patch({ serialized: event.target.checked, opening: event.target.checked ? "0" : state.opening })} />
                <span>Track IMEI / serial numbers. Serialized stock is added by receiving IMEIs on a purchase order.</span>
              </label>
            ) : null}
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label="Opening stock at" error={errors.store}>
                <select className={control} value={state.storeId} disabled={access.storeId !== null} onChange={(event) => patch({ storeId: event.target.value })}>
                  <option value="">No branch yet</option>
                  {stores.map((store) => <option key={store.id} value={store.id}>{store.name}</option>)}
                </select>
              </Field>
              <Field label={state.weighed ? "Opening stock (kg)" : "Opening quantity"} error={errors.opening}>
                <input className={control} inputMode="decimal" value={state.opening} disabled={state.serialized || state.storeId === ""} onChange={(event) => patch({ opening: event.target.value })} />
              </Field>
              <Field label="Min reorder level" error={errors.reorder}>
                <input className={control} inputMode="numeric" value={state.reorder} disabled={state.storeId === ""} onChange={(event) => patch({ reorder: event.target.value })} />
              </Field>
            </div>
          </>
        ) : null}
        {editing ? (
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1 h-5 w-5" checked={state.active} onChange={(event) => patch({ active: event.target.checked })} />
            <span>Active. Inactive products stay in past sales. The register does not sell them.</span>
          </label>
        ) : null}
        {editing && access.manage && !access.pharmacy ? (
          <QuietButton onClick={() => void remove()} disabled={busy}>Delete if unused</QuietButton>
        ) : null}
      </form>
    </FormModal>
  );
}
