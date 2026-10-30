import type { Gender } from "./catalogue.js";
import type { SerialKind, SerialStatus, UnitType } from "./enums.js";
import type { ItemType } from "./inventory.js";
import type { PriceListEntry, ProductPrice } from "./pricing.js";
import type { TaxCategory } from "./tax.js";
import type { UnitOption } from "./units.js";

/** Wholesale pricing and tax carried by catalog rows. price_cents remains the RETAIL price. */
export interface ProductPricing {
  min_order_quantity?: number;
  sellable_units?: UnitType[];
  /** The packs in sellable_units with their names and factors (built-in and the business's own). */
  unit_options?: UnitOption[];
  prices?: ProductPrice[];
  tax_category?: TaxCategory;
  is_open_price?: boolean;
  /** Fixed-price services such as warranty plans; sold without stock. */
  is_service?: boolean;
  /** "api" once the register got the row from the server; only other rows are synced back as upserts. */
  origin?: "api" | "seed";
  /** Weighed goods: quantities count grams and price_cents is the price per kilogram. */
  sold_by_weight?: boolean;
  /** Price-look-up code a scale prints into its EAN-13 labels. */
  plu_code?: string | null;
  tare_grams?: number;
  /** Soonest batch expiry at this branch (YYYY-MM-DD), when the expiry-first stock module is on. */
  nearest_expiry?: string | null;
  /** Till asks for an age check when this is set. Null means unrestricted. */
  minimum_age?: number | null;
  /** Recipes module: a dish drawn from its ingredients (it carries no stock of its own). */
  has_recipe?: boolean;
  /** Recipes module: kept in stock for dishes only; registers do not sell it. */
  is_ingredient?: boolean;
  /** MADE_TO_ORDER dishes are prepared from ingredients and are not a shelf quantity. */
  item_type?: ItemType;
  is_stock_tracked?: boolean;
  /** Business-wide and this branch's price-list entries; customer and group lists come per customer. */
  price_lists?: PriceListEntry[];
  /** Cover photo (the variant's own, its model's photo for this colour, or the model's primary photo). */
  image_url?: string | null;
  thumb_url?: string | null;
  season?: string | null;
  collection?: string | null;
  gender?: Gender | null;
  material?: string | null;
  fit?: string | null;
  care?: string | null;
  /** Price before the active markdown; the register strikes it through. */
  compare_at_cents?: number | null;
  /** false when the variant is retired. Missing means active. */
  is_active?: boolean;
  /** default and rule follow the model. override is a price set on this variant. */
  price_source?: "default" | "rule" | "override";
  /** Hex colour for an attribute value on this variant, from the model's swatch map. */
  variant_swatches?: Record<string, string>;
  /** Technical details for this category (processor, capacity, fabric). Portal-managed. */
  specifications?: Record<string, string>;
}

/**
 * Global catalog row. stock_quantity / quantity_reserved are for `store_id`, or consolidated across all
 * branches when store_id is null.
 */
export interface Product extends ProductPricing {
  id: string;
  store_id: string | null;
  sku: string;
  barcode: string;
  name: string;
  model_number?: string | null;
  brand?: string | null;
  category: string;
  category_id?: string | null;
  sub_category?: string | null;
  sub_category_id?: string | null;
  brand_id?: string | null;
  /** Set when this product is a sub-model (sellable variant) of a catalog model. */
  product_model_id?: string | null;
  model_name?: string | null;
  variant_attributes?: Record<string, string>;
  price_cents: number;
  currency: string;
  is_serialized: boolean;
  stock_quantity: number;
  quantity_reserved?: number;
  created_at: string;
  updated_at: string;
}

/**
 * Catalog row as registers hold it. Pass it through productSyncPayload() before sending it as a sync
 * upsert, where store_id + stock_quantity set opening stock only when the product is first created.
 */
export interface ProductUpsert extends ProductPricing {
  id: string;
  store_id: string;
  sku: string;
  barcode: string;
  name: string;
  model_number?: string | null;
  brand?: string | null;
  category: string;
  category_id?: string | null;
  sub_category?: string | null;
  sub_category_id?: string | null;
  price_cents: number;
  currency: string;
  is_serialized: boolean;
  stock_quantity: number;
  /** Parent model of a size / colour variant, for the register's variant picker. Portal-managed. */
  product_model_id?: string | null;
  model_name?: string | null;
  variant_attributes?: Record<string, string>;
}

type PortalManaged =
  | keyof ProductPricing
  | "product_model_id"
  | "model_name"
  | "variant_attributes"
  | "is_active"
  | "price_source"
  | "variant_swatches";

/** The fields the sync API accepts for a product upsert; pricing tiers and models are managed in the portal. */
export function productSyncPayload(product: ProductUpsert): Omit<ProductUpsert, PortalManaged> {
  const {
    min_order_quantity: _moq,
    sellable_units: _units,
    unit_options: _unitOptions,
    prices: _prices,
    tax_category: _tax,
    is_open_price: _open,
    is_service: _service,
    origin: _origin,
    sold_by_weight: _weighed,
    plu_code: _plu,
    tare_grams: _tare,
    nearest_expiry: _expiry,
    has_recipe: _recipe,
    is_ingredient: _ingredient,
    item_type: _itemType,
    is_stock_tracked: _tracked,
    price_lists: _lists,
    image_url: _image,
    thumb_url: _thumb,
    season: _season,
    collection: _collection,
    gender: _gender,
    material: _material,
    fit: _fit,
    care: _care,
    compare_at_cents: _was,
    specifications: _specs,
    product_model_id: _model,
    model_name: _modelName,
    variant_attributes: _variant,
    is_active: _active,
    price_source: _source,
    variant_swatches: _swatches,
    ...rest
  } = product;
  return rest;
}

export type ProductMatch = "identifier" | "exact" | "text";

/** Response row of GET /api/v1/products/search. */
export interface ProductSearchHit<P extends ProductUpsert | Product = Product> {
  product: P;
  match: ProductMatch;
  serial_kind?: SerialKind | null;
  serial_status?: SerialStatus | null;
}
