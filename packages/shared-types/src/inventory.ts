import type { FashionAttributes } from "./catalogue.js";
import type { SerialKind, SerialStatus } from "./enums.js";
import type { TaxCategory } from "./tax.js";

export const MovementType = {
  PurchaseIn: "PURCHASE_IN",
  SaleOut: "SALE_OUT",
  ReturnIn: "RETURN_IN",
  TransferIn: "TRANSFER_IN",
  TransferOut: "TRANSFER_OUT",
  DamageShrinkage: "DAMAGE_SHRINKAGE",
  AuditAdjustment: "AUDIT_ADJUSTMENT",
  PurchaseReversal: "PURCHASE_REVERSAL",
  RecipeOut: "RECIPE_OUT",
} as const;
export type MovementType = (typeof MovementType)[keyof typeof MovementType];

export const StockStatus = { Ok: "ok", Low: "low", Out: "out", Over: "over", Unavailable: "unavailable" } as const;
export type StockStatus = (typeof StockStatus)[keyof typeof StockStatus];

export const ItemType = {
  MadeToOrder: "MADE_TO_ORDER",
  RawIngredient: "RAW_INGREDIENT",
  PrePackaged: "PRE_PACKAGED",
} as const;
export type ItemType = (typeof ItemType)[keyof typeof ItemType];

export type MenuStatus = "available" | "unavailable" | "no_recipe" | "meal";
export type StockView = "stock" | "menu";

export type PurchaseOrderStatus = "draft" | "ordered" | "partially_received" | "received" | "cancelled";
export type TransferStatus = "requested" | "in_transit" | "received" | "cancelled";

// --- Categories ----------------------------------------------------------------------------------

export interface SubCategory {
  id: string;
  category_id: string;
  name: string;
  code: string;
  description: string;
  product_count: number;
}

export interface Category {
  id: string;
  name: string;
  code: string;
  description: string;
  product_count: number;
  created_at: string;
  sub_categories: SubCategory[];
}

export interface CategoryWrite {
  name: string;
  code?: string | null;
  description?: string;
}

// --- Brands, models, and variants ----------------------------------------------------------------

/** Variant (sub-model) attributes keyed by snake_case name, e.g. storage, ram, color, processor. */
export type VariantAttributes = Record<string, string>;

export const VARIANT_ATTRIBUTE_KEYS = ["storage", "ram", "color", "processor", "size", "connectivity"] as const;

export const variantAttributeLabels: Record<string, string> = {
  storage: "Storage",
  ram: "RAM",
  color: "Colour",
  processor: "Processor",
  size: "Size",
  connectivity: "Connectivity",
  graphics: "Graphics",
  capacity: "Capacity",
  length: "Length",
  fits: "Fits",
};

export function variantAttributeLabel(key: string): string {
  return variantAttributeLabels[key] ?? key.replace(/_/g, " ").replace(/^\w/, (letter) => letter.toUpperCase());
}

export interface Brand {
  id: string;
  name: string;
  code: string;
  description: string;
  sub_category_ids: string[];
  model_count: number;
  product_count: number;
  created_at: string;
}

export interface BrandWrite extends CategoryWrite {
  sub_category_ids?: string[];
}

export interface ProductModel extends FashionAttributes {
  id: string;
  brand_id: string;
  brand_name: string;
  category_id: string;
  category_name: string;
  sub_category_id: string;
  sub_category_name: string;
  name: string;
  code: string | null;
  release_year: number | null;
  description: string;
  variant_count: number;
  default_price_cents?: number | null;
  price_rules?: { key: string; value: string; price_cents: number }[];
  axis_swatches?: Record<string, Record<string, string>>;
}

export interface ProductModelWrite extends FashionAttributes {
  brand_id: string;
  sub_category_id: string;
  name: string;
  code?: string | null;
  release_year?: number | null;
  description?: string;
}

/** Attribute fields that are sent replace the model's value (null clears it) and are copied to its variants. */
export type ProductModelUpdate = Partial<
  Pick<ProductModelWrite, "name" | "code" | "release_year" | "description" | keyof FashionAttributes>
> & {
  default_price_cents?: number | null;
  price_rules?: { key: string; value: string; price_cents: number }[];
  axis_swatches?: Record<string, Record<string, string>>;
};

// --- Stock ---------------------------------------------------------------------------------------

export interface StockRow {
  product_id: string;
  sku: string;
  name: string;
  brand: string | null;
  model_number: string | null;
  is_serialized: boolean;
  category: string;
  category_id: string | null;
  sub_category: string | null;
  sub_category_id: string | null;
  brand_id?: string | null;
  product_model_id?: string | null;
  model_name?: string | null;
  /** null when the row is consolidated across all branches. */
  store_id: string | null;
  store_code: string | null;
  store_name: string | null;
  store_count: number;
  quantity_on_hand: number;
  quantity_reserved: number;
  quantity_available: number;
  min_reorder_level: number;
  max_stock_level: number | null;
  aisle_shelf_location: string | null;
  /** Cover thumbnail, when the product has a photo. */
  thumb_url?: string | null;
  status: StockStatus;
  /** Quantities of weighed products count grams. */
  sold_by_weight?: boolean;
  item_type?: ItemType;
  /** Menu availability: portions the current ingredient stock can still make. */
  max_portions?: number | null;
  limiting_ingredient?: string | null;
  availability_note?: string | null;
  menu_status?: MenuStatus | null;
}

export interface StockSummary {
  consolidated: boolean;
  store_id: string | null;
  rows: StockRow[];
  units_on_hand: number;
  low_count: number;
  out_count: number;
  view?: StockView;
}

export interface LevelUpdate {
  min_reorder_level?: number;
  max_stock_level?: number;
  clear_max?: boolean;
  aisle_shelf_location?: string | null;
}

export interface SerialInput {
  kind: SerialKind;
  value: string;
}

export const AdjustmentReason = {
  PhysicalCountAudit: "PHYSICAL_COUNT_AUDIT",
  DamagedOrExpired: "DAMAGED_OR_EXPIRED",
  StolenShrinkage: "STOLEN_SHRINKAGE",
  SupplierSampleIn: "SUPPLIER_SAMPLE_IN",
  IncorrectEntryCorrection: "INCORRECT_ENTRY_CORRECTION",
  InternalDemoUse: "INTERNAL_DEMO_USE",
  Other: "OTHER",
} as const;
export type AdjustmentReason = (typeof AdjustmentReason)[keyof typeof AdjustmentReason];

export const ADJUSTMENT_NOTE_MIN_LENGTH = 10;

export const adjustmentReasonLabels: Record<AdjustmentReason, string> = {
  PHYSICAL_COUNT_AUDIT: "Physical count / audit",
  DAMAGED_OR_EXPIRED: "Damaged or expired",
  STOLEN_SHRINKAGE: "Stolen / shrinkage",
  SUPPLIER_SAMPLE_IN: "Supplier sample received",
  INCORRECT_ENTRY_CORRECTION: "Incorrect entry correction",
  INTERNAL_DEMO_USE: "Internal demo use",
  OTHER: "Other",
};

/** Reasons that only make sense in one direction; the API rejects the opposite. */
export const REMOVE_ONLY_REASONS: readonly AdjustmentReason[] = ["DAMAGED_OR_EXPIRED", "STOLEN_SHRINKAGE"];
export const ADD_ONLY_REASONS: readonly AdjustmentReason[] = ["SUPPLIER_SAMPLE_IN"];

export type AdjustmentMode = "add" | "remove" | "set";

/** POST /api/v1/inventory/adjust. add/remove move `quantity` units; set reconciles on-hand to `quantity`. */
export interface ManualAdjustment {
  adjustment_id: string;
  product_id: string;
  store_id: string;
  mode: AdjustmentMode;
  quantity: number;
  reason_code: AdjustmentReason;
  note: string;
  new_serials?: SerialInput[];
  remove_serial_ids?: string[];
}

export interface ManualAdjustmentResult {
  adjustment_id: string;
  duplicate: boolean;
  quantity_change: number;
  row: StockRow;
  movements: StockMovement[];
}

export interface StoreSerial {
  id: string;
  kind: SerialKind;
  value: string;
  status: SerialStatus;
  updated_at: string;
}

export interface StockMovement {
  id: string;
  product_id: string;
  sku: string;
  product_name: string;
  store_id: string;
  store_code: string;
  serial_number_id: string | null;
  movement_type: MovementType;
  quantity: number;
  quantity_after: number;
  reference_type: string;
  reference_id: string | null;
  reason_code?: AdjustmentReason | null;
  user_name: string | null;
  note: string;
  created_at: string;
}

export interface BranchStock {
  store_id: string;
  store_code: string;
  store_name: string;
  is_warehouse: boolean;
  address: string | null;
  phone: string | null;
  quantity_on_hand: number;
  quantity_reserved: number;
  quantity_available: number;
  aisle_shelf_location: string | null;
}

export interface ProductBrief {
  id: string;
  sku: string;
  name: string;
  is_serialized: boolean;
}

export interface SerialLocation {
  serial_number_id: string;
  kind: SerialKind;
  last4: string;
  status: SerialStatus;
  store_id: string;
  store_code: string;
  store_name: string;
  is_warehouse: boolean;
  aisle_shelf_location: string | null;
}

export interface Availability {
  product: ProductBrief;
  branches: BranchStock[];
  serial: SerialLocation | null;
}

export interface TransferBrief {
  id: string;
  number: string;
  status: TransferStatus;
  source_store_code: string;
  destination_store_code: string;
  shipped_at: string | null;
  received_at: string | null;
}

export interface SerialTrace {
  product: ProductBrief;
  location: SerialLocation;
  history: StockMovement[];
  transfers: TransferBrief[];
}

// --- Purchasing ----------------------------------------------------------------------------------

export interface PurchaseOrderCreate {
  supplier_name: string;
  destination_store_id: string;
  expected_at?: string | null;
  notes?: string;
  lines: { product_id: string; quantity_ordered: number; unit_cost_cents: number }[];
}

export interface ReceiveRequest {
  note?: string;
  lines: {
    purchase_order_line_id: string;
    quantity: number;
    serials?: SerialInput[];
    aisle_shelf_location?: string | null;
  }[];
}

export interface PurchaseOrderLine {
  id: string;
  product_id: string;
  sku: string;
  name: string;
  is_serialized: boolean;
  quantity_ordered: number;
  quantity_received: number;
  unit_cost_cents: number;
}

export interface GoodsReceipt {
  id: string;
  number: string;
  store_id: string;
  received_by_name: string | null;
  note: string;
  created_at: string;
  lines: { purchase_order_line_id: string; product_id: string; quantity: number }[];
}

export interface PurchaseOrder {
  id: string;
  number: string;
  supplier_name: string;
  destination_store_id: string;
  destination_store_code: string;
  destination_store_name: string;
  status: PurchaseOrderStatus;
  notes: string;
  expected_at: string | null;
  ordered_at: string | null;
  received_at: string | null;
  created_at: string;
  created_by_name: string | null;
  total_cost_cents: number;
  lines: PurchaseOrderLine[];
  receipts: GoodsReceipt[];
}

// --- Transfers -----------------------------------------------------------------------------------

export interface TransferCreate {
  source_store_id: string;
  destination_store_id: string;
  note?: string;
  lines: { product_id: string; quantity: number }[];
}

export interface TransferShip {
  serial_lines: { transfer_line_id: string; serials: SerialInput[] }[];
}

export interface TransferLine {
  id: string;
  product_id: string;
  sku: string;
  name: string;
  is_serialized: boolean;
  quantity: number;
}

export interface StockTransfer {
  id: string;
  number: string;
  source_store_id: string;
  source_store_code: string;
  source_store_name: string;
  destination_store_id: string;
  destination_store_code: string;
  destination_store_name: string;
  status: TransferStatus;
  note: string;
  requested_by_name: string | null;
  shipped_by_name: string | null;
  received_by_name: string | null;
  created_at: string;
  shipped_at: string | null;
  received_at: string | null;
  lines: TransferLine[];
  serials: {
    serial_number_id: string;
    transfer_line_id: string;
    kind: SerialKind;
    last4: string;
    status: SerialStatus;
  }[];
}

// --- Catalog writes ------------------------------------------------------------------------------

export interface ProductCreate extends FashionAttributes {
  sku: string;
  barcode: string;
  name: string;
  model_number?: string | null;
  brand?: string | null;
  brand_id?: string | null;
  /** Optional when product_model_id is set: the model fixes category, sub-category, and brand. */
  category_id?: string | null;
  sub_category_id?: string | null;
  product_model_id?: string | null;
  variant_attributes?: VariantAttributes;
  /** Category-specific technical details. Keys follow the specification template. */
  specifications?: Record<string, string>;
  price_cents: number;
  is_serialized: boolean;
  tax_category?: TaxCategory;
  is_open_price?: boolean;
  /** Weighed goods: price_cents is per kilogram and opening_quantity counts grams. */
  sold_by_weight?: boolean;
  plu_code?: string | null;
  tare_grams?: number;
  /** Till asks before payment when set. Null means anyone can buy it. */
  minimum_age?: number | null;
  /** Recipes module: stocked for dishes only; registers do not sell it. */
  is_ingredient?: boolean;
  /** Prepared dishes are not stocked. Ingredients and packaged goods are. */
  item_type?: ItemType;
  /** Unit-of-measure codes it sells in; PIECE is always included. */
  sellable_units?: string[];
  opening_store_id?: string | null;
  opening_quantity?: number;
  min_reorder_level?: number;
}

export interface ProductUpdate extends FashionAttributes {
  name?: string;
  model_number?: string | null;
  brand?: string | null;
  brand_id?: string | null;
  category_id?: string | null;
  sub_category_id?: string;
  clear_sub_category?: boolean;
  /** null detaches the product from its model. */
  product_model_id?: string | null;
  variant_attributes?: VariantAttributes;
  specifications?: Record<string, string>;
  price_cents?: number;
  tax_category?: TaxCategory;
  is_open_price?: boolean;
  sold_by_weight?: boolean;
  /** null clears the PLU. */
  plu_code?: string | null;
  tare_grams?: number;
  /** null clears the age check. */
  minimum_age?: number | null;
  is_ingredient?: boolean;
  item_type?: ItemType;
  sellable_units?: string[];
  is_active?: boolean;
}

export function stockStatusLabel(status: StockStatus): string {
  return {
    ok: "In stock",
    low: "Low stock",
    out: "Out of stock",
    over: "Overstock",
    unavailable: "Ingredients Unavailable",
  }[status];
}

export function movementLabel(type: MovementType): string {
  return {
    PURCHASE_IN: "Purchase in",
    SALE_OUT: "Sale",
    RETURN_IN: "Return",
    TRANSFER_IN: "Transfer in",
    TRANSFER_OUT: "Transfer out",
    DAMAGE_SHRINKAGE: "Damage / shrinkage",
    AUDIT_ADJUSTMENT: "Audit adjustment",
    PURCHASE_REVERSAL: "Purchase reversal",
    RECIPE_OUT: "Used in recipes",
  }[type];
}
