/** Fashion catalogue: product photos and attributes. Mirrors apps/api/app/schemas/catalogue.py. */

export type Gender = "women" | "men" | "kids" | "unisex";

export const GENDER_LABELS: Record<Gender, string> = {
  women: "Women",
  men: "Men",
  kids: "Kids",
  unisex: "Unisex",
};

/** Set on a model (copied to its variants) or on a standalone product. */
export interface FashionAttributes {
  /** Upper-cased season code, e.g. SS26. */
  season?: string | null;
  collection?: string | null;
  gender?: Gender | null;
  material?: string | null;
  fit?: string | null;
  care?: string | null;
}

/** GET /api/v1/catalog/attributes: values in use, for filters and form pickers. */
export interface CatalogAttributes {
  seasons: string[];
  collections: string[];
  genders: Gender[];
  materials: string[];
  fits: string[];
}

export interface ProductImage {
  id: string;
  product_id: string | null;
  product_model_id: string | null;
  /** A model photo for one colour: attribute_key "color", attribute_value "Black". */
  attribute_key: string | null;
  attribute_value: string | null;
  url: string;
  thumb_url: string;
  width: number;
  height: number;
  position: number;
  is_primary: boolean;
  created_at: string;
}

export interface ProductImageUpdate {
  is_primary?: boolean;
  position?: number;
  attribute_key?: string | null;
  attribute_value?: string | null;
}
