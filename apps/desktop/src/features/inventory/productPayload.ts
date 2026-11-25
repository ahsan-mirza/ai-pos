import {
  ItemType,
  barcodeError,
  skuFromParts,
  type PharmacyDraft,
  type TaxCategory,
} from "@ai-pos/shared-types";

/** Fields the register product drawer edits. Names follow the Business Pro product form. */
export interface ProductFormState {
  name: string;
  sku: string;
  barcode: string;
  modelNumber: string;
  categoryId: string;
  subCategoryId: string;
  brandId: string;
  modelId: string;
  price: string;
  priceIncludesTax: boolean;
  taxCategory: TaxCategory;
  openPrice: boolean;
  weighed: boolean;
  plu: string;
  tare: string;
  minimumAge: string;
  ingredient: boolean;
  itemType: string;
  serialized: boolean;
  storeId: string;
  opening: string;
  reorder: string;
  season: string;
  collection: string;
  gender: string;
  material: string;
  fit: string;
  care: string;
  specs: Record<string, string>;
  packs: string[];
  active: boolean;
  /** Restaurant and cafe made-to-order items. Off means a recipe is required before the item can be sold. */
  sellWithoutRecipe: boolean;
  /** Loaded from the saved product. A new item has no recipe yet. */
  hasRecipe: boolean;
  skuPrefix: string;
  skuManual: boolean;
  autoBarcode: boolean;
  barcodePrefix: string;
  nameTouched: boolean;
}

export const emptyProductForm = (storeId: string | null, fnb: boolean): ProductFormState => ({
  name: "",
  sku: "",
  barcode: "",
  modelNumber: "",
  categoryId: "",
  subCategoryId: "",
  brandId: "",
  modelId: "",
  price: "",
  priceIncludesTax: false,
  taxCategory: "STANDARD",
  openPrice: false,
  weighed: false,
  plu: "",
  tare: "0",
  minimumAge: "",
  ingredient: false,
  itemType: fnb ? ItemType.MadeToOrder : ItemType.PrePackaged,
  serialized: false,
  storeId: storeId ?? "",
  opening: "0",
  reorder: "0",
  season: "",
  collection: "",
  gender: "",
  material: "",
  fit: "",
  care: "",
  specs: {},
  packs: [],
  active: true,
  sellWithoutRecipe: false,
  hasRecipe: false,
  skuPrefix: "",
  skuManual: false,
  autoBarcode: true,
  barcodePrefix: "200",
  nameTouched: false,
});

export function resolvedSku(state: ProductFormState, editing: boolean, optional = false): string {
  const sku = optional || editing || state.skuManual ? state.sku : skuFromParts(state.skuPrefix, state.name, state.specs);
  return sku.replace(/-$/, "");
}

export function centsFromPrice(value: string): number | null {
  const trimmed = value.trim();
  if (!/^\d+(\.\d{1,2})?$/.test(trimmed)) return null;
  return Math.round(Number(trimmed) * 100);
}

function whole(value: string): number | null {
  const trimmed = value.trim();
  if (!/^\d+$/.test(trimmed)) return null;
  return Number(trimmed);
}

function optionalText(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

export function validateProductForm(
  state: ProductFormState,
  options: { editing: boolean; pharmacy: boolean; dispensingClass: string; autoBarcode?: boolean; skuOptional?: boolean },
): Record<string, string> {
  const errors: Record<string, string> = {};
  if (state.name.trim() === "") errors.name = "Name is required.";
  if (!options.editing && !options.skuOptional && resolvedSku(state, false).trim() === "") errors.sku = "SKU is required.";
  if (!options.editing && state.barcode.trim() === "") {
    if (!options.autoBarcode) errors.barcode = "Barcode is required.";
  } else if (!options.editing && state.barcode.trim() !== "") {
    const problem = barcodeError(state.barcode, false);
    if (problem) errors.barcode = problem;
  }
  if (centsFromPrice(state.price) === null) errors.price = "Enter a price with up to two decimal places.";
  if (state.categoryId === "" && state.modelId === "") errors.category = "Choose a category or a model.";
  if (state.weighed && (state.serialized || state.openPrice)) {
    errors.weighed = "Weighed products cannot be serialized or open-price.";
  }
  if (state.plu.trim() !== "" && !state.weighed) errors.plu = "Only weighed products carry a scale PLU code.";
  if (state.weighed && state.plu.trim() !== "" && !/^\d{4,6}$/.test(state.plu.trim())) {
    errors.plu = "Scale PLU is 4 to 6 digits.";
  }
  const openingText = (state.opening || "0").trim();
  const opening = state.weighed ? (/^\d+(\.\d{1,3})?$/.test(openingText) ? Number(openingText) : null) : whole(openingText);
  if (opening === null) {
    errors.opening = state.weighed
      ? "Opening stock is kilograms, with up to three decimal places."
      : "Opening quantity must be a whole number.";
  } else if (opening > 0 && state.storeId === "") errors.store = "Choose the store that holds the opening stock.";
  else if (opening > 0 && state.serialized) {
    errors.opening = "Serialized stock is added by receiving IMEIs on a purchase order.";
  }
  if (whole(state.reorder || "0") === null) errors.reorder = "Reorder level must be a whole number.";
  if (state.minimumAge.trim() !== "") {
    const age = Number(state.minimumAge);
    if (!Number.isInteger(age) || age < 1 || age > 120) errors.minimumAge = "Minimum age must be between 1 and 120, or blank.";
  }
  if (options.pharmacy && options.dispensingClass.trim() === "") {
    errors.dispensing = "Choose a dispensing class.";
  }
  return errors;
}

function fashion(state: ProductFormState, enabled: boolean): Record<string, string | null> {
  if (!enabled || state.modelId !== "") return {};
  return {
    season: optionalText(state.season),
    collection: optionalText(state.collection),
    gender: optionalText(state.gender),
  };
}

function specifications(specs: Record<string, string>): Record<string, string> {
  return Object.fromEntries(
    Object.entries(specs)
      .map(([key, value]) => [key, value.trim()] as const)
      .filter((entry) => entry[1] !== ""),
  );
}

function variantAttributes(
  specs: Record<string, string>,
  variantKeys: readonly string[],
  keptKeys: readonly string[] = [],
): Record<string, string> {
  const saved = specifications(specs);
  const keys = [...variantKeys, ...keptKeys.filter((key) => !variantKeys.includes(key))];
  const attributes: Record<string, string> = {};
  for (const key of keys) {
    const value = saved[key];
    if (value) attributes[key] = value;
  }
  return attributes;
}

export function pharmacyBody(draft: PharmacyDraft): Record<string, unknown> {
  const official = (value: string) => (draft.price_control === "NONE" || value.trim() === "" ? null : centsFromPrice(value));
  const amount = (value: string) => (value.trim() === "" ? null : value.trim());
  return {
    product_kind: draft.product_kind,
    dispensing_class: draft.dispensing_class,
    generic_name: draft.generic_name.trim(),
    manufacturer: draft.manufacturer.trim(),
    marketing_authorization_holder: draft.marketing_authorization_holder.trim(),
    country_of_origin: draft.country_of_origin.trim(),
    description: draft.description.trim(),
    gtin: draft.gtin.trim(),
    manufacturer_product_ref: draft.manufacturer_product_ref.trim(),
    dosage_form: draft.dosage_form.trim(),
    route: draft.route.trim(),
    strength_amount: amount(draft.strength_amount),
    strength_unit: draft.strength_unit.trim(),
    concentration: draft.concentration.trim(),
    pack_size_label: draft.pack_size_label.trim(),
    units_per_pack: Number(draft.units_per_pack) || 1,
    base_unit_code: draft.base_unit_code.trim() || "PIECE",
    selling_unit_code: draft.selling_unit_code.trim() || "PIECE",
    storage_condition: draft.storage_condition.trim(),
    temp_min_c: amount(draft.temp_min_c),
    temp_max_c: amount(draft.temp_max_c),
    cold_chain: draft.cold_chain,
    handling_instructions: draft.handling_instructions.trim(),
    warnings_text: draft.warnings_text.trim(),
    registration_number: draft.registration_number.trim() || null,
    registration_authority: draft.registration_authority.trim() || null,
    price_control: draft.price_control,
    min_price_cents: official(draft.min_price_cents),
    max_price_cents: official(draft.max_price_cents),
    offline_policy: draft.offline_policy,
    ingredients: draft.ingredients
      .filter((row) => row.name.trim() !== "")
      .map((row) => ({
        name: row.name.trim(),
        strength_amount: amount(row.strength_amount),
        strength_unit: row.strength_unit.trim(),
        is_active_ingredient: row.is_active_ingredient,
      })),
    documents: draft.documents.filter((row) => row.title.trim() !== ""),
  };
}

export function productCreateBody(
  state: ProductFormState,
  options: { fashion: boolean; fnb?: boolean; variantKeys: readonly string[]; keptKeys?: readonly string[]; pharmacy: PharmacyDraft | null },
): Record<string, unknown> {
  const price = centsFromPrice(state.price);
  if (price === null) throw new Error("Enter a price with up to two decimal places.");
  const piecesOnly = state.serialized || state.weighed || state.openPrice;
  const body: Record<string, unknown> = {
    sku: state.sku.trim(),
    barcode: state.barcode.trim(),
    name: state.name.trim(),
    model_number: optionalText(state.modelNumber),
    brand_id: state.brandId || null,
    category_id: state.categoryId || null,
    sub_category_id: state.subCategoryId || null,
    product_model_id: state.modelId || null,
    variant_attributes: variantAttributes(state.specs, options.variantKeys, options.keptKeys),
    specifications: specifications(state.specs),
    price_cents: price,
    price_includes_tax: state.priceIncludesTax,
    is_serialized: state.serialized,
    tax_category: state.taxCategory,
    is_open_price: state.openPrice && !state.serialized,
    sold_by_weight: state.weighed,
    plu_code: state.weighed && state.plu.trim() ? state.plu.trim() : null,
    tare_grams: state.weighed ? whole(state.tare || "0") ?? 0 : 0,
    minimum_age: state.minimumAge.trim() === "" ? null : Number(state.minimumAge),
    is_ingredient: options.fnb ? state.itemType === ItemType.RawIngredient : state.ingredient && !state.openPrice,
    item_type: state.itemType,
    sell_without_recipe: Boolean(options.fnb && state.itemType === ItemType.MadeToOrder && state.sellWithoutRecipe),
    sellable_units: piecesOnly ? ["PIECE"] : ["PIECE", ...state.packs.filter((code) => code !== "PIECE")],
    opening_store_id: state.storeId || null,
    opening_quantity:
      state.itemType === ItemType.MadeToOrder || state.serialized
        ? 0
        : state.weighed
          ? Math.round((Number(state.opening) || 0) * 1000)
          : whole(state.opening || "0") ?? 0,
    min_reorder_level: whole(state.reorder || "0") ?? 0,
    ...fashion(state, options.fashion),
  };
  if (options.pharmacy) body.pharmacy = pharmacyBody(options.pharmacy);
  return body;
}

export function productUpdateBody(
  state: ProductFormState,
  options: { fashion: boolean; fnb?: boolean; variantKeys: readonly string[]; keptKeys?: readonly string[]; pharmacy: PharmacyDraft | null },
): Record<string, unknown> {
  const price = centsFromPrice(state.price);
  if (price === null) throw new Error("Enter a price with up to two decimal places.");
  const piecesOnly = state.serialized || state.weighed || state.openPrice;
  const body: Record<string, unknown> = {
    name: state.name.trim(),
    model_number: optionalText(state.modelNumber),
    brand_id: state.brandId || null,
    category_id: state.categoryId || null,
    sub_category_id: state.subCategoryId || null,
    clear_sub_category: state.subCategoryId === "",
    product_model_id: state.modelId || null,
    variant_attributes: variantAttributes(state.specs, options.variantKeys, options.keptKeys),
    specifications: specifications(state.specs),
    price_cents: price,
    price_includes_tax: state.priceIncludesTax,
    tax_category: state.taxCategory,
    is_open_price: state.openPrice && !state.serialized,
    sold_by_weight: state.weighed,
    plu_code: state.weighed && state.plu.trim() ? state.plu.trim() : null,
    tare_grams: state.weighed ? whole(state.tare || "0") ?? 0 : 0,
    minimum_age: state.minimumAge.trim() === "" ? null : Number(state.minimumAge),
    is_ingredient: options.fnb ? state.itemType === ItemType.RawIngredient : state.ingredient && !state.openPrice,
    item_type: state.itemType,
    sell_without_recipe: Boolean(options.fnb && state.itemType === ItemType.MadeToOrder && state.sellWithoutRecipe),
    sellable_units: piecesOnly ? ["PIECE"] : ["PIECE", ...state.packs.filter((code) => code !== "PIECE")],
    is_active: state.active,
    ...fashion(state, options.fashion),
  };
  if (options.pharmacy) body.pharmacy = pharmacyBody(options.pharmacy);
  return body;
}

/** Commercial and catalog fields the product drawer now collects. Used by the parity test. */
export const POS_PRODUCT_FIELDS = [
  "name",
  "sku",
  "barcode",
  "model_number",
  "category_id",
  "sub_category_id",
  "brand_id",
  "product_model_id",
  "specifications",
  "variant_attributes",
  "price_cents",
  "price_includes_tax",
  "tax_category",
  "is_open_price",
  "sold_by_weight",
  "plu_code",
  "tare_grams",
  "minimum_age",
  "is_ingredient",
  "item_type",
  "sell_without_recipe",
  "sellable_units",
  "is_serialized",
  "opening_store_id",
  "opening_quantity",
  "min_reorder_level",
  "season",
  "collection",
  "gender",
  "is_active",
  "pharmacy",
] as const;
