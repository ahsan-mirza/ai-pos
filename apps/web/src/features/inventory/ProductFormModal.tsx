import {
  allSpecKeys,
  Capability,
  compareVariantValues,
  draftsFromCells,
  formatMoney,
  GENDER_LABELS,
  ItemType,
  Permission,
  specSchemaFor,
  titleFromSpecs,
  variantCombinations,
  variantDraftKey,
  type Gender,
  type SpecSchema,
  type ItemType as ItemTypeId,
  type Product,
  type ProductImage,
  type ProductSearchHit,
  type TaxCategory,
  type VariantDraft,
} from "@ai-pos/shared-types";
import { Zap } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { ErrorNote, GhostButton, SelectField, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { Toggle } from "../../components/ui/Toggle";
import { apiGet, apiUpload } from "../../lib/api";
import { cleanCode } from "../../lib/codes";
import { compressImageToWebp } from "../../lib/imageFile";
import { useAuth } from "../../lib/auth";
import { useCurrency } from "../../lib/currency";
import { useCapabilities } from "../../lib/capabilities";
import { useTenant } from "../../context/TenantContext";
import { brandsApi, categoriesApi, inventoryApi, message, modelsApi } from "./api";
import { barcodeError, randomCode128, randomEan13, skuFromParts } from "./barcodeDraft";
import { FashionVariantComposer } from "./FashionVariantComposer";
import { SpecFields } from "./SpecFields";
import { fieldErrors, useInvalidFocus, type FieldErrors } from "./formErrors";
import { BarcodePrintFlow } from "./BarcodePrintFlow";
import { PhotoGallery } from "./PhotoGallery";
import { ProductImageDropzone, type PendingProductPhoto } from "./ProductImageDropzone";
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

function specsToSave(schema: SpecSchema, specs: Record<string, string>): Record<string, string> {
  const source =
    schema.id === "OTHER"
      ? specs
      : Object.fromEntries(schema.fields.map((field) => [field.key, specs[field.key] ?? ""]));
  return Object.fromEntries(
    Object.entries(source)
      .map(([key, value]) => [key, value.trim()] as const)
      .filter((entry) => entry[1] !== ""),
  );
}

function initialSpecs(product: Product | null): Record<string, string> {
  const specs = { ...(product?.specifications ?? {}) };
  for (const [key, value] of Object.entries(product?.variant_attributes ?? {})) {
    if (value && specs[key] === undefined) specs[key] = value;
  }
  return specs;
}

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
  const { user, can } = useAuth();
  const catalogAdmin = can(Permission.PortalInventoryManage) && user?.store_id === null;
  const { isFnB } = useTenant();
  const { categories, reload: reloadCategories } = useCategories();
  const { stores } = useStores();
  const editing = product !== null;
  const [barcode, setBarcode] = useState(product?.barcode ?? "");
  const [barcodePrefix, setBarcodePrefix] = useState("200");
  const [autoBarcode, setAutoBarcode] = useState(true);
  const [barcodeTaken, setBarcodeTaken] = useState(false);
  const [skuTaken, setSkuTaken] = useState(false);
  const [name, setName] = useState(product?.name ?? "");
  const [nameTouched, setNameTouched] = useState(editing);
  const [skuPrefix, setSkuPrefix] = useState("");
  const [skuTyped, setSkuTyped] = useState(product?.sku ?? "");
  const [skuManual, setSkuManual] = useState(editing);
  const [modelNumber, setModelNumber] = useState(product?.model_number ?? "");
  const [categoryId, setCategoryId] = useState(product?.category_id ?? preset?.categoryId ?? "");
  const [subCategoryId, setSubCategoryId] = useState(product?.sub_category_id ?? preset?.subCategoryId ?? "");
  const [brandId, setBrandId] = useState(product?.brand_id ?? preset?.brandId ?? "");
  const [modelId, setModelId] = useState(product?.product_model_id ?? preset?.modelId ?? "");
  const [specs, setSpecs] = useState<Record<string, string>>(() => initialSpecs(product));
  const [matrixAxes, setMatrixAxes] = useState<Record<string, string[]>>(() => {
    const axes: Record<string, string[]> = {};
    for (const key of ["size", "color"]) {
      const value = (product?.variant_attributes?.[key] || product?.specifications?.[key] || "").trim();
      if (value) axes[key] = [value];
    }
    return axes;
  });
  const [variantRows, setVariantRows] = useState<VariantDraft[]>([]);
  const sku = editing || skuManual ? skuTyped : skuFromParts(skuPrefix, name, specs);
  const [price, setPrice] = useState(product ? (product.price_cents / 100).toFixed(2) : "");
  const [active, setActive] = useState(product?.is_active !== false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [serialized, setSerialized] = useState(product?.is_serialized ?? preset?.serialized ?? false);
  const { currency, settings } = useCurrency();
  const [taxCategory, setTaxCategory] = useState<TaxCategory>(product?.tax_category ?? "STANDARD");
  const [includesTax, setIncludesTax] = useState(product?.price_includes_tax ?? Boolean(settings?.prices_include_vat));
  const [openPrice, setOpenPrice] = useState(product?.is_open_price ?? false);
  const { has, profile } = useCapabilities();
  const weighing = has(Capability.WeighedItems);
  const [byWeight, setByWeight] = useState(product?.sold_by_weight ?? false);
  const [plu, setPlu] = useState(product?.plu_code ?? "");
  const [tare, setTare] = useState(String(product?.tare_grams ?? 0));
  const [minimumAge, setMinimumAge] = useState(product?.minimum_age != null ? String(product.minimum_age) : "");
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
  const [serverFields, setServerFields] = useState<FieldErrors>({});
  const formRef = useRef<HTMLDivElement>(null);
  const focusInvalid = useInvalidFocus(formRef);
  const [submitted, setSubmitted] = useState(false);
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [printProduct, setPrintProduct] = useState<Product | null>(null);
  const [busy, setBusy] = useState(false);
  const [persistedId, setPersistedId] = useState<string | null>(product?.id ?? null);
  const [pendingPhotos, setPendingPhotos] = useState<PendingProductPhoto[]>([]);
  const [mainPhotoKey, setMainPhotoKey] = useState<string | null>(null);
  const [photoVersion, setPhotoVersion] = useState(0);
  const { brands, reload: reloadBrands } = useBrands();
  const { models, reload: reloadModels } = useModels(subCategoryId || null, brandId || null);
  const category = categories.find((item) => item.id === categoryId);
  const subCategory = category?.sub_categories.find((item) => item.id === subCategoryId);
  const model = models.find((item) => item.id === modelId);
  const schema = specSchemaFor(category?.name ?? product?.category ?? "", subCategory?.name ?? product?.sub_category ?? "", {
    productName: [name, model?.name].filter(Boolean).join(" "),
    profile,
  });
  const fashionMatrix = fashionOn && schema.id.startsWith("FASHION");
  const matrixKeys = fashionMatrix
    ? schema.fields.filter((field) => field.key === "size" || field.key === "color").map((field) => field.key)
    : [];
  const matrixKeyList = matrixKeys.join(",");

  useEffect(() => {
    if (!nameTouched && model && name === "") setName(model.name);
  }, [model, name, nameTouched]);

  useEffect(() => {
    if (!fashionMatrix || !product?.product_model_id) return;
    let cancel = false;
    void modelsApi.matrix(product.product_model_id).then(
      (grid) => {
        if (cancel) return;
        setMatrixAxes((current) => {
          const next = { ...current };
          for (const key of matrixKeyList.split(",").filter(Boolean)) {
            const axis = grid.axes.find((item) => item.key === key || (key === "color" && item.key === "colour"));
            if (axis && axis.values.length > 0) next[key] = axis.values;
          }
          return next;
        });
        setVariantRows(draftsFromCells(grid.cells));
      },
      () => undefined,
    );
    return () => {
      cancel = true;
    };
  }, [fashionMatrix, product?.product_model_id, matrixKeyList]);

  useEffect(() => {
    const value = barcode.trim();
    if (editing || value === "") {
      setBarcodeTaken(false);
      return;
    }
    const timer = window.setTimeout(() => {
      apiGet<ProductSearchHit[]>(`/api/v1/products/search?q=${encodeURIComponent(value)}&limit=5`)
        .then((hits) => setBarcodeTaken(hits.some((hit) => hit.product.barcode.toLowerCase() === value.toLowerCase())))
        .catch(() => setBarcodeTaken(false));
    }, 280);
    return () => window.clearTimeout(timer);
  }, [barcode, editing]);

  useEffect(() => {
    const value = sku.replace(/-$/, "").trim();
    if (editing || value === "") {
      setSkuTaken(false);
      return;
    }
    const timer = window.setTimeout(() => {
      apiGet<ProductSearchHit[]>(`/api/v1/products/search?q=${encodeURIComponent(value)}&limit=5`)
        .then((hits) => setSkuTaken(hits.some((hit) => hit.product.sku.toLowerCase() === value.toLowerCase())))
        .catch(() => setSkuTaken(false));
    }, 280);
    return () => window.clearTimeout(timer);
  }, [sku, editing]);

  const touch = (key: string) => setTouched((current) => ({ ...current, [key]: true }));
  const reveal = (key: string, text: string) => ((submitted || touched[key]) && text !== "" ? text : undefined);
  const clearServer = (key: string) =>
    setServerFields((current) => {
      if (!current[key]) return current;
      const next = { ...current };
      delete next[key];
      return next;
    });
  const fieldMessage = (key: string, text: string) => serverFields[key] || reveal(key, text) || undefined;

  const priceMessage = () => {
    if (price.trim().startsWith("-")) return "Price cannot be negative.";
    const cents = toCents(price);
    if (cents === null) return "Enter a price like 49.00.";
    if (!openPrice && cents <= 0) return "Price must be greater than 0.";
    return "";
  };

  const barcodeMessage = () => {
    if (editing) return "";
    if (barcode.trim() === "" && autoBarcode) return "";
    return barcodeError(barcode, barcodeTaken) ?? "";
  };

  const skuMessage = () => {
    if (editing) return "";
    if (sku.replace(/-$/, "") === "") return "SKU is required.";
    if (skuTaken) return "SKU must be unique.";
    return "";
  };

  const pluMessage = () =>
    byWeight && plu.trim() !== "" && !/^\d{4,6}$/.test(plu.trim()) ? "A scale PLU is 4 to 6 digits." : "";

  const storeMessage = () => {
    if (editing || serialized || itemType === ItemType.MadeToOrder) return "";
    if (Number(opening) > 0 && storeId === "") return "Choose the store that holds the opening stock.";
    return "";
  };

  const openingMessage = () => {
    if (editing || opening.trim() === "") return "";
    const quantity = Number(opening);
    if (Number.isNaN(quantity) || quantity < 0) return "Opening quantity cannot be negative.";
    return "";
  };

  const assignBarcode = async (kind: "ean13" | "code128") => {
    for (let attempt = 0; attempt < 6; attempt += 1) {
      const code = kind === "ean13" ? randomEan13(barcodePrefix) : randomCode128(barcodePrefix);
      const hits = await apiGet<ProductSearchHit[]>(`/api/v1/products/search?q=${encodeURIComponent(code)}&limit=5`).catch(
        () => [] as ProductSearchHit[],
      );
      if (!hits.some((hit) => hit.product.barcode.toLowerCase() === code.toLowerCase())) {
        setBarcode(code);
        touch("barcode");
        return code;
      }
    }
    setError("Could not find a unique barcode. Try another prefix.");
    return null;
  };

  const suggestName = (modelName: string | undefined, next: Record<string, string>) => {
    if (nameTouched || !modelName) return;
    setName([modelName, ...Object.values(next).filter(Boolean)].join(" "));
  };

  const setSpec = (next: Record<string, string>) => {
    setSpecs(next);
    suggestName(model?.name, next);
  };

  const setAxisValues = (key: string, values: string[]) => {
    const seen = new Set<string>();
    const next: string[] = [];
    for (const value of values) {
      const name = value.trim();
      const token = name.toLowerCase();
      if (name === "" || seen.has(token)) continue;
      seen.add(token);
      next.push(name);
    }
    next.sort(compareVariantValues);
    setMatrixAxes((current) => ({ ...current, [key]: next }));
  };

  const saveFashionVariants = async (cents: number) => {
    const payloadRows = variantRows.filter((row) => row.included || row.existingId);
    if (!payloadRows.some((row) => row.included)) {
      setError("Include at least one size and color combination.");
      return;
    }
    if (!modelId && (brandId === "" || subCategoryId === "")) {
      setError("Choose a brand and sub-category so the size and color variants stay under one style.");
      return;
    }
    for (const row of payloadRows) {
      if (!row.included) continue;
      if (toCents(row.price) === null) {
        setError(`Enter a selling price for ${Object.values(row.attributes).join(" ")}.`);
        return;
      }
      if (row.cost.trim() !== "" && toCents(row.cost) === null) {
        setError(`Enter a cost like 20.00 for ${Object.values(row.attributes).join(" ")}, or leave it blank.`);
        return;
      }
    }
    const adoptId = (row: VariantDraft): string | null => {
      if (row.existingId) return row.existingId;
      if (!product || product.product_model_id) return null;
      const current: Record<string, string> = {};
      for (const key of Object.keys(row.attributes)) {
        const value = (product.variant_attributes?.[key] || product.specifications?.[key] || "").trim();
        if (value) current[key] = value;
      }
      return variantDraftKey(current) === row.key ? product.id : null;
    };
    if (product && !product.product_model_id && product.stock_quantity > 0) {
      const kept = payloadRows.some((row) => row.included && adoptId(row) === product.id);
      if (!kept) {
        setError("Include this product's current size and color. Its stock stays on that variant.");
        return;
      }
    }
    const needsStore = payloadRows.some((row) => {
      if (row.existingId || adoptId(row) || !row.included) return false;
      return (Number(row.opening) || 0) > 0 || (Number(row.reorder) || 0) > 0 || row.cost.trim() !== "";
    });
    if (needsStore && storeId === "") {
      setError("Choose the store that holds the opening stock.");
      return;
    }
    const axisKeys = matrixKeys.filter((key) => payloadRows.every((row) => (row.attributes[key] ?? "").trim() !== ""));
    if (axisKeys.length === 0) {
      setError("Choose a size or a color before generating variants.");
      return;
    }
    const prefix = skuPrefix.toUpperCase().replace(/[^A-Z0-9-]/g, "").slice(0, 24);
    setBusy(true);
    setError(null);
    try {
      let targetModel = modelId;
      if (!targetModel) {
        const code = prefix && /^[A-Z0-9][A-Z0-9-]{0,31}$/.test(prefix) ? prefix : null;
        const createdModel = await modelsApi.create({
          name: name.trim(),
          brand_id: brandId,
          sub_category_id: subCategoryId,
          code,
          season: season.trim() || null,
          collection: collection.trim() || null,
          gender: (gender || null) as Gender | null,
        });
        targetModel = createdModel.id;
        setModelId(createdModel.id);
      }
      const specifications = specsToSave(schema, specs);
      for (const key of matrixKeys) delete specifications[key];
      await modelsApi.generateMatrix(targetModel, {
        axes: axisKeys.map((key) => ({
          key,
          values: [...new Set(payloadRows.map((row) => row.attributes[key]).filter((value): value is string => Boolean(value)))],
        })),
        price_cents: cents,
        sku_prefix: prefix || null,
        tax_category: taxCategory,
        price_includes_tax: includesTax,
        opening_store_id: needsStore ? storeId : null,
        specifications,
        variants: payloadRows.map((row) => {
          const adopted = adoptId(row);
          const cost = row.cost.trim() === "" ? null : toCents(row.cost);
          const fresh = adopted === null;
          return {
            attributes: Object.fromEntries(axisKeys.map((key) => [key, row.attributes[key] ?? ""])),
            ...(adopted ? { product_id: adopted } : {}),
            sku: row.sku.trim() || null,
            barcode: row.barcode.trim() || null,
            price_cents: toCents(row.price) ?? cents,
            is_active: row.included,
            ...(fresh
              ? {
                  ...(cost !== null ? { cost_cents: cost } : {}),
                  opening_quantity: Number(row.opening) || 0,
                  min_reorder_level: Number(row.reorder) || 0,
                }
              : {}),
          };
        }),
      });
      if (editing && product && product.name !== name.trim()) {
        await inventoryApi.updateProduct(product.id, { name: name.trim() });
      }
      if (pendingPhotos.length > 0) {
        const chosen = pendingPhotos.find((item) => item.key === mainPhotoKey) ?? pendingPhotos[0];
        if (chosen) {
          const ordered = [chosen, ...pendingPhotos.filter((item) => item.key !== chosen.key)];
          for (const item of ordered) {
            const form = new FormData();
            form.append("file", await compressImageToWebp(item.file));
            await apiUpload(`/api/v1/product-models/${targetModel}/images`, form);
          }
          setPendingPhotos([]);
        }
      }
      onSaved();
    } catch (caught) {
      setError(message(caught, "Could not save the variants."));
    } finally {
      setBusy(false);
    }
  };

  const generateFromSpecs = () => {
    const title = titleFromSpecs({
      brand: brands.find((item) => item.id === brandId)?.name ?? "",
      model: model?.name ?? "",
      schema,
      specs,
    });
    if (title !== "") {
      setName(title);
      setNameTouched(true);
    }
    if (!editing) {
      setSkuManual(true);
      setSkuTyped(skuFromParts(skuPrefix, title || name, {}));
    }
  };

  const rejectCreate = (caught: unknown, field: string, fallback: string) => {
    const apiFields = fieldErrors(caught);
    const text = apiFields.name || apiFields.code || message(caught, fallback);
    setServerFields((current) => ({ ...current, [field]: text }));
    setSubmitted(true);
    focusInvalid();
  };

  const addCategory = async (label: string) => {
    try {
      const created = await categoriesApi.create({ name: label.trim() });
      await reloadCategories();
      setCategoryId(created.id);
      setSubCategoryId("");
      setModelId("");
      clearServer("category");
    } catch (caught) {
      rejectCreate(caught, "category", "Could not add the category.");
    }
  };

  const addSubCategory = async (label: string) => {
    if (categoryId === "") return;
    try {
      const parent = await categoriesApi.createSub(categoryId, { name: label.trim() });
      await reloadCategories();
      const created = parent.sub_categories.find((sub) => sub.name.toLowerCase() === label.trim().toLowerCase());
      if (created) setSubCategoryId(created.id);
      setModelId("");
      clearServer("sub");
    } catch (caught) {
      rejectCreate(caught, "sub", "Could not add the sub-category.");
    }
  };

  const addBrand = async (label: string) => {
    if (subCategoryId === "") return;
    try {
      const created = await brandsApi.create({ name: label.trim(), sub_category_ids: [subCategoryId] });
      await reloadBrands();
      setBrandId(created.id);
      setModelId("");
      clearServer("brand");
    } catch (caught) {
      rejectCreate(caught, "brand", "Could not add the brand.");
    }
  };

  const addModel = async (label: string) => {
    if (brandId === "" || subCategoryId === "") return;
    try {
      const created = await modelsApi.create({
        name: label.trim(),
        brand_id: brandId,
        sub_category_id: subCategoryId,
      });
      await reloadModels();
      setModelId(created.id);
      suggestName(created.name, specs);
      clearServer("model");
    } catch (caught) {
      rejectCreate(caught, "model", "Could not add the model.");
    }
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
    setSubmitted(true);
    const cents = toCents(price);
    const nameProblem = name.trim() === "" ? "Name is required." : "";
    const priceProblem = priceMessage();
    const categoryProblem = categoryId || modelId ? "" : "Choose a category or a model.";
    const skuProblem = skuMessage();
    const barcodeProblem = barcodeMessage();
    const pluProblem = pluMessage();
    const storeProblem = storeMessage();
    const openingProblem = openingMessage();
    const possible = variantCombinations(
      matrixKeys.map((key) => ({ key, values: matrixAxes[key] ?? [] })),
    ).length;
    const matrixSave = fashionMatrix && variantRows.length > 0;
    if (fashionMatrix && possible > 1 && variantRows.length === 0) {
      setSubmitted(true);
      setError("Generate variants before saving. Each size and color is stocked on its own.");
      return;
    }
    if (
      nameProblem ||
      priceProblem ||
      categoryProblem ||
      (!matrixSave && skuProblem) ||
      (!matrixSave && barcodeProblem) ||
      pluProblem ||
      (!matrixSave && storeProblem) ||
      (!matrixSave && openingProblem) ||
      cents === null
    ) {
      focusInvalid();
      return;
    }
    if (matrixSave) {
      await saveFashionVariants(cents);
      return;
    }
    const specsForSave = { ...specs };
    if (fashionMatrix) {
      for (const key of matrixKeys) {
        const value = (matrixAxes[key] ?? [])[0];
        if (value) specsForSave[key] = value;
        else delete specsForSave[key];
      }
    }
    const specifications = specsToSave(schema, specsForSave);
    const specKeys = allSpecKeys();
    const kept = Object.fromEntries(
      Object.entries(product?.variant_attributes ?? {}).filter(([key]) => !specKeys.has(key) && key.trim() !== ""),
    );
    const variant_attributes = {
      ...kept,
      ...Object.fromEntries(
        schema.variantKeys.map((key) => [key, (specsForSave[key] ?? "").trim()]).filter(([, value]) => value !== ""),
      ),
    };
    const classification = {
      category_id: categoryId || null,
      brand_id: brandId || null,
      product_model_id: modelId || null,
      variant_attributes,
      specifications,
    };
    const ageValue = minimumAge.trim() === "" ? null : Number(minimumAge);
    if (ageValue !== null && (!Number.isInteger(ageValue) || ageValue < 1 || ageValue > 120)) {
      setError("Minimum age is a whole number from 1 to 120, or blank.");
      return;
    }
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
    setServerFields({});
    try {
      let id = persistedId;
      if (id !== null) {
        await inventoryApi.updateProduct(id, {
          name: name.trim(),
          model_number: modelNumber.trim() || null,
          ...classification,
          ...(subCategoryId === "" ? { clear_sub_category: true } : { sub_category_id: subCategoryId }),
          price_cents: cents,
          price_includes_tax: includesTax,
          tax_category: taxCategory,
          is_open_price: openPrice && !(product?.is_serialized ?? false),
          ...weighed,
          minimum_age: ageValue,
          ...recipes,
          ...fashion,
          sellable_units,
          is_active: active,
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
        let nextBarcode = barcode.trim();
        if (nextBarcode === "" && autoBarcode) {
          const generated = await assignBarcode("ean13");
          if (generated === null) {
            setBusy(false);
            return;
          }
          nextBarcode = generated;
        }
        const finalSku = sku.replace(/-$/, "");
        const created = await inventoryApi.createProduct({
          sku: finalSku,
          barcode: nextBarcode,
          name: name.trim(),
          model_number: modelNumber.trim() || null,
          ...classification,
          sub_category_id: subCategoryId || null,
          price_cents: cents,
          price_includes_tax: includesTax,
          is_serialized: serialized,
          tax_category: taxCategory,
          is_open_price: openPrice && !serialized,
          ...weighed,
          minimum_age: ageValue,
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
      if (id !== null && pendingPhotos.length > 0) {
        const chosen = pendingPhotos.find((item) => item.key === mainPhotoKey) ?? pendingPhotos[0];
        if (chosen) {
          const ordered = [chosen, ...pendingPhotos.filter((item) => item.key !== chosen.key)];
          let remaining = ordered;
          for (const item of ordered) {
            const form = new FormData();
            form.append("file", await compressImageToWebp(item.file));
            await apiUpload<ProductImage>(`/api/v1/inventory/products/${id}/images`, form);
            remaining = remaining.filter((photo) => photo.key !== item.key);
            setPendingPhotos(remaining);
            setMainPhotoKey(remaining[0]?.key ?? null);
          }
          setPhotoVersion((version) => version + 1);
        }
      }
      if (!editing && id !== null) {
        const created = await apiGet<Product>(`/api/v1/products/${id}`);
        setPrintProduct(created);
        return;
      }
      onSaved();
    } catch (caught) {
      const apiFields = fieldErrors(caught);
      if (Object.keys(apiFields).length > 0) {
        setServerFields(apiFields);
        focusInvalid();
      } else setError(message(caught, "Could not save the product."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
    <Modal
      title={editing ? `Edit ${product.name}` : model ? `New ${model.name} variant` : "New product"}
      subtitle={
        editing ? `${product.sku} · ${product.barcode}` : "Products are shared by every branch; stock is per branch."
      }
      onClose={onClose}
      width="xl"
      backdropClassName="bg-[#1A191D]/60 backdrop-blur-md"
      headerExtra={
        <div className="flex flex-wrap gap-2 pt-3">
          {[
            ["product-section-catalog", "Catalog"],
            ["product-section-specs", "Specifications"],
            ["product-section-product", "Product"],
            ["product-section-stock", "Stock"],
          ].map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => {
                if (id) document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
              }}
              className="rounded-full bg-gray-50 px-3 py-1 text-xs font-semibold text-charcoal/70 hover:bg-gray-100 dark:bg-[#2D2A32] dark:text-white/70"
            >
              {label}
            </button>
          ))}
        </div>
      }
      footer={
        <>
          {editing && confirmDelete ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                if (!product) return;
                setBusy(true);
                setError(null);
                void inventoryApi
                  .deleteProduct(product.id)
                  .then(() => onSaved())
                  .catch((caught: unknown) => {
                    setError(message(caught, "Could not delete this product."));
                    setBusy(false);
                  });
              }}
              className="mr-auto text-sm font-semibold text-danger disabled:opacity-40"
            >
              {busy ? "Deleting…" : "Confirm delete"}
            </button>
          ) : editing ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => setConfirmDelete(true)}
              className="mr-auto text-sm font-semibold text-charcoal/50 hover:text-danger disabled:opacity-40"
            >
              Delete product
            </button>
          ) : null}
          <GhostButton
            onClick={() => {
              if (confirmDelete) {
                setConfirmDelete(false);
                return;
              }
              onClose();
            }}
            disabled={busy}
          >
            {confirmDelete ? "Keep product" : "Cancel"}
          </GhostButton>
          <button
            type="button"
            disabled={busy}
            onClick={() => void save()}
            className="inline-flex items-center justify-center rounded-xl bg-accent px-6 py-2.5 text-sm font-bold text-white shadow-lg shadow-accent/20 transition-colors hover:bg-accent-hover disabled:opacity-40"
          >
            {busy ? "Saving…" : editing ? "Save changes" : "Create product"}
          </button>
        </>
      }
    >
      <div ref={formRef}>
      {persistedId && pendingPhotos.length === 0 ? (
        <div className="mb-5">
          <PhotoGallery
            path={`/api/v1/inventory/products/${persistedId}/images`}
            canManage
            version={photoVersion}
          />
        </div>
      ) : (
        <ProductImageDropzone
          photos={pendingPhotos}
          mainKey={mainPhotoKey}
          onChange={(photos, main) => {
            setPendingPhotos(photos);
            setMainPhotoKey(main);
          }}
        />
      )}
      <h3 id="product-section-catalog" className="mb-3 scroll-mt-4 text-sm font-semibold">
        Catalog placement
      </h3>
      <div className="grid gap-4 md:grid-cols-2">
        <SelectField
          label="Category"
          value={categoryId}
          placeholder="Choose a category"
          error={fieldMessage("category", categoryId || modelId ? "" : "Choose a category or a model.")}
          options={categories.map((item) => ({ value: item.id, label: item.name }))}
          onCreate={catalogAdmin ? (label) => void addCategory(label) : undefined}
          onChange={(next) => {
            setCategoryId(next);
            setSubCategoryId("");
            setModelId("");
            setSpecs({});
            setMatrixAxes({});
            setVariantRows([]);
            touch("category");
            clearServer("category");
          }}
        />
        <SelectField
          label="Sub-category"
          value={subCategoryId}
          disabled={!category || (!catalogAdmin && category.sub_categories.length === 0)}
          error={serverFields.sub}
          options={[
            { value: "", label: "None" },
            ...(category?.sub_categories ?? []).map((sub) => ({ value: sub.id, label: sub.name })),
          ]}
          onCreate={catalogAdmin && category ? (label) => void addSubCategory(label) : undefined}
          onChange={(next) => {
            setSubCategoryId(next);
            setModelId("");
            setSpecs({});
            setMatrixAxes({});
            setVariantRows([]);
            clearServer("sub");
          }}
        />
        <SelectField
          label="Brand"
          value={brandId}
          error={serverFields.brand}
          options={brandOptions}
          createHint={catalogAdmin && subCategoryId === "" ? "Pick a sub-category first." : undefined}
          onCreate={catalogAdmin && subCategoryId !== "" ? (label) => void addBrand(label) : undefined}
          onChange={(next) => {
            setBrandId(next);
            setModelId("");
            clearServer("brand");
          }}
        />
        <SelectField
          label="Model"
          value={modelId}
          disabled={brandId === "" || subCategoryId === ""}
          placeholder={brandId === "" || subCategoryId === "" ? "Pick a sub-category and brand first." : "Choose a model"}
          hint={brandId === "" || subCategoryId === "" ? "Pick a sub-category and brand first." : undefined}
          error={serverFields.model}
          options={[
            { value: "", label: "No model (stand-alone product)" },
            ...models.map((item) => ({
              value: item.id,
              label: item.name,
              hint: [item.code, item.release_year].filter(Boolean).join(" · ") || undefined,
            })),
          ]}
          onCreate={catalogAdmin && brandId !== "" && subCategoryId !== "" ? (label) => void addModel(label) : undefined}
          createMinLength={1}
          onChange={(next) => {
            setModelId(next);
            suggestName(models.find((item) => item.id === next)?.name, specs);
            clearServer("model");
          }}
        />
      </div>

      <div id="product-section-specs" className="mt-6 scroll-mt-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold">
              {schema.id.startsWith("FASHION")
                ? "Product attributes"
                : schema.id === "OTHER"
                  ? "Details"
                  : schema.id.startsWith("RESTAURANT") || schema.id.startsWith("CAFE")
                    ? "Menu details"
                    : "Specifications"}
            </h3>
            <p className="text-xs text-charcoal/50">{schema.title}</p>
          </div>
          <button
            type="button"
            onClick={generateFromSpecs}
            className="inline-flex h-9 items-center gap-1 rounded-full bg-charcoal px-3 text-xs font-semibold text-white"
          >
            <Zap size={12} aria-hidden="true" />
            Auto-Generate Name & SKU from Specs
          </button>
        </div>
        <SpecFields
          schema={schema}
          specs={specs}
          onChange={setSpec}
          multiKeys={matrixKeys}
          multiValues={matrixAxes}
          onMultiChange={setAxisValues}
        />
        {fashionMatrix ? (
          <FashionVariantComposer
            axes={matrixKeys.map((key) => ({
              key,
              label: schema.fields.find((field) => field.key === key)?.label ?? key,
              values: matrixAxes[key] ?? [],
            }))}
            productName={name}
            skuPrefix={skuPrefix}
            defaultPrice={price}
            defaultOpening={opening}
            defaultReorder={reorder}
            rows={variantRows}
            onChange={setVariantRows}
          />
        ) : null}
      </div>

      <h3 id="product-section-product" className="mb-3 mt-6 scroll-mt-4 text-sm font-semibold">
        Product
      </h3>
      <div className="grid gap-4 md:grid-cols-2">
        <TextField
          label="Name"
          value={name}
          error={fieldMessage("name", name.trim() === "" ? "Name is required." : "")}
          hint={!editing && model && !nameTouched ? "Follows the model and variant until you edit it." : undefined}
          onBlur={() => touch("name")}
          onChange={(event) => {
            setNameTouched(true);
            setName(event.target.value);
            clearServer("name");
          }}
        />
        <div>
          <TextField
            label={byWeight ? "Price per kg" : "Price"}
            inputMode="decimal"
            value={price}
            error={fieldMessage("price", priceMessage())}
            hint={
              product?.price_source && product.price_source !== "override"
                ? "Inherited from the model. Changing it makes this an override."
                : undefined
            }
            onBlur={() => touch("price")}
            onChange={(event) => {
              setPrice(event.target.value);
              clearServer("price");
            }}
          />
          <label className="mt-2 flex items-start gap-2.5 text-sm text-charcoal dark:text-white">
            <input
              type="checkbox"
              checked={includesTax}
              onChange={(event) => setIncludesTax(event.target.checked)}
              className="mt-0.5 h-4 w-4 shrink-0 rounded border-gray-300 text-accent focus:ring-accent dark:border-gray-600 dark:bg-[#2D2A32]"
            />
            <span>
              <span className="font-medium">Price includes tax</span>
              <span className="mt-0.5 block text-xs leading-5 text-charcoal/60 dark:text-white/50">
                When enabled, the entered selling price already includes the applicable tax.{" "}
                {includesTax
                  ? `Customers pay ${formatMoney(toCents(price) ?? 0, currency)}. Applicable tax is calculated within this price.`
                  : "Applicable tax will be added to the entered price at checkout."}
              </span>
            </span>
          </label>
        </div>
        <div>
          <label className="block text-sm font-medium" htmlFor="product-sku">
            SKU
            <span className="relative mt-1.5 block">
              <input
                id="product-sku"
                value={sku}
                disabled={editing}
                placeholder="Generated from the name"
                maxLength={64}
                spellCheck={false}
                autoComplete="off"
                aria-invalid={fieldMessage("sku", skuMessage()) ? true : undefined}
                onBlur={() => touch("sku")}
                onChange={(event) => {
                  setSkuManual(true);
                  setSkuTyped(cleanCode(event.target.value, 64));
                  clearServer("sku");
                }}
                className={`h-12 w-full rounded-xl border bg-gray-50 py-3 pl-4 pr-36 font-mono text-sm tabular-nums focus:border-accent focus:bg-white focus:outline-none focus:ring-1 focus:ring-accent disabled:text-charcoal/50 dark:border-gray-700/80 dark:bg-[#2D2A32] ${
                  fieldMessage("sku", skuMessage())
                    ? "border-danger bg-danger/10 focus:border-danger focus:ring-2 focus:ring-danger"
                    : "border-transparent focus:border-accent"
                }`}
              />
              {editing ? null : (
                <button
                  type="button"
                  onClick={() => {
                    setSkuManual(true);
                    setSkuTyped(skuFromParts(skuPrefix, name, specs));
                  }}
                  className="absolute right-1.5 top-1/2 inline-flex h-8 -translate-y-1/2 items-center gap-1 rounded-full bg-charcoal px-3 text-xs font-semibold text-white"
                >
                  <Zap size={12} aria-hidden="true" />
                  Auto Generate
                </button>
              )}
            </span>
          </label>
          {fieldMessage("sku", skuMessage()) ? (
            <span role="alert" className="mt-1.5 block text-xs font-medium text-danger">
              {fieldMessage("sku", skuMessage())}
            </span>
          ) : (
            <span className="mt-1.5 block text-xs text-charcoal/50">
              {editing ? "SKUs are fixed once a product exists." : "Letters, digits and dashes. Follows the name and variant until you edit it."}
            </span>
          )}
          {editing ? null : (
            <label className="mt-2 block text-xs font-medium text-charcoal/70">
              SKU prefix
              <input
                value={skuPrefix}
                maxLength={8}
                placeholder="HP"
                onChange={(event) => setSkuPrefix(cleanCode(event.target.value, 8))}
                className="mt-1 h-9 w-full rounded-xl border border-line bg-white px-3 font-mono text-sm uppercase"
              />
            </label>
          )}
        </div>
        <div>
          <label className="block text-sm font-medium" htmlFor="product-barcode">
            Barcode / UPC / EAN
            <span className="relative mt-1.5 block">
              <input
                id="product-barcode"
                value={barcode}
                disabled={editing}
                aria-invalid={fieldMessage("barcode", barcodeMessage()) ? true : undefined}
                onBlur={() => touch("barcode")}
                onChange={(event) => {
                  setBarcode(event.target.value.trim());
                  clearServer("barcode");
                }}
                className={`h-12 w-full rounded-xl border bg-surface py-3 pl-4 pr-40 font-mono text-sm focus:bg-white focus:outline-none disabled:text-charcoal/50 ${
                  fieldMessage("barcode", barcodeMessage())
                    ? "border-danger bg-danger/10 focus:border-danger focus:ring-2 focus:ring-danger"
                    : "border-transparent focus:border-accent"
                }`}
              />
              {editing ? null : (
                <button
                  type="button"
                  onClick={() => void assignBarcode("ean13")}
                  className="absolute right-1.5 top-1/2 inline-flex h-8 -translate-y-1/2 items-center gap-1 rounded-full bg-charcoal px-3 text-xs font-semibold text-white"
                >
                  <Zap size={12} aria-hidden="true" />
                  EAN-13
                </button>
              )}
            </span>
          </label>
          {fieldMessage("barcode", barcodeMessage()) ? (
            <span role="alert" className="mt-1.5 block text-xs font-medium text-danger">
              {fieldMessage("barcode", barcodeMessage())}
            </span>
          ) : null}
          {editing ? null : (
            <div className="mt-2 flex flex-wrap items-end gap-2">
              <button
                type="button"
                onClick={() => void assignBarcode("code128")}
                className="inline-flex h-9 items-center gap-1 rounded-full border border-line px-3 text-xs font-semibold"
              >
                <Zap size={12} aria-hidden="true" />
                Code 128
              </button>
              <label className="text-xs font-medium text-charcoal/70">
                Barcode prefix
                <input
                  value={barcodePrefix}
                  maxLength={11}
                  onChange={(event) => setBarcodePrefix(event.target.value.replace(/[^\dA-Za-z]/g, "").slice(0, 11))}
                  className="mt-1 h-9 w-28 rounded-xl border border-line bg-white px-3 font-mono text-sm"
                />
              </label>
            </div>
          )}
          {editing ? null : (
            <div className="mt-3">
              <Toggle
                label="Auto-assign a unique barcode if left blank"
                checked={autoBarcode}
                onChange={setAutoBarcode}
              />
            </div>
          )}
        </div>
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
            description="Cashiers type the price and a description at the till. Only staff with Sell open price can ring it up."
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
                error={fieldMessage("plu", pluMessage())}
                onChange={(event) => {
                  setPlu(event.target.value.replace(/\D/g, ""));
                  clearServer("plu");
                }}
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
      <div className="mt-4 max-w-xs">
        <TextField
          label="Minimum age"
          value={minimumAge}
          inputMode="numeric"
          placeholder="Blank if anyone can buy it"
          hint="The till asks before payment. Leave blank when no check is required."
          onChange={(event) => setMinimumAge(event.target.value)}
        />
      </div>
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
      {itemType !== ItemType.MadeToOrder && (!editing || variantRows.some((row) => row.included && !row.existingId)) ? (
        <div id="product-section-stock" className="mt-4 scroll-mt-4 space-y-4">
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
              error={fieldMessage("store", storeMessage())}
              options={[{ value: "", label: "No branch yet" }, ...storeOptions(stores)]}
              onChange={(next) => {
                setStoreId(next);
                clearServer("store");
              }}
            />
            {variantRows.length > 0 ? (
              <p className="text-sm text-charcoal/60 md:col-span-2">
                Opening stock and reorder level are set on each size and color. The branch above is where that stock is received.
              </p>
            ) : (
              <>
                <TextField
                  label={byWeight ? "Opening stock (kg)" : "Opening quantity"}
                  type="number"
                  min={0}
                  value={opening}
                  disabled={serialized || storeId === ""}
                  error={fieldMessage("opening", openingMessage())}
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
              </>
            )}
          </div>
        </div>
      ) : null}
      {editing ? (
        <div className="mt-4">
          <Toggle
            label="Active"
            description="Inactive products stay in the catalog and in past sales. The register does not show or sell them."
            checked={active}
            onChange={setActive}
          />
        </div>
      ) : null}
      <ErrorNote message={error} />
      </div>
    </Modal>
    {printProduct ? <BarcodePrintFlow product={printProduct} onDone={onSaved} /> : null}
    </>
  );
}
