export interface CatalogImage {
  id: string;
  url: string;
  thumb_url: string;
  alt: string;
  position: number;
  is_primary: boolean;
}

export interface CatalogCategory {
  id: string;
  name: string;
  slug: string;
  description: string;
  image_url: string | null;
  thumb_url: string | null;
  image_alt: string;
  display_order: number;
  is_active: boolean;
}

export interface CatalogProduct {
  id: string;
  category_id: string;
  category_name: string;
  name: string;
  slug: string;
  sku: string;
  short_description: string;
  full_description: string;
  brand: string;
  model_number: string;
  manufacturer: string;
  specifications: { label: string; value: string }[];
  purchase_price_fils: number | null;
  display_price_fils: number | null;
  currency: string;
  warranty_months: number;
  stock_status: string;
  compatibility: string;
  display_order: number;
  is_featured: boolean;
  is_published: boolean;
  is_active: boolean;
  archived: boolean;
  images: CatalogImage[];
  updated_at: string;
}

export interface CatalogPlan {
  id: string;
  code: string;
  name: string;
  monthly_fils: number;
  included_registers: number;
  active: boolean;
}

export interface PackageItem {
  id: string;
  product_id: string;
  product_name: string;
  sku: string;
  quantity: number;
  is_optional: boolean;
  display_order: number;
  display_price_fils: number | null;
  is_published: boolean;
  archived: boolean;
  thumb_url: string | null;
}

export interface CatalogPackage {
  id: string;
  name: string;
  slug: string;
  short_description: string;
  full_description: string;
  display_price_fils: number | null;
  currency: string;
  billing_plan_id: string | null;
  plan: CatalogPlan | null;
  package_type: string;
  display_order: number;
  is_featured: boolean;
  is_published: boolean;
  is_active: boolean;
  items: PackageItem[];
  images: CatalogImage[];
  component_value_fils: number | null;
  savings_fils: number | null;
  updated_at: string;
}

export interface EnquiryNote {
  id: string;
  body: string;
  operator_name: string;
  created_at: string;
}

export interface CatalogEnquiry {
  id: string;
  enquiry_reference: string;
  customer_name: string;
  business_name: string;
  email: string;
  phone: string;
  country: string;
  business_type: string;
  enquiry_type: string;
  product_label: string;
  package_label: string;
  quantity: number;
  message: string;
  status: string;
  source: string;
  notes: EnquiryNote[];
  created_at: string;
}

export interface CatalogOverview {
  categories: number;
  products: number;
  published_products: number;
  draft_products: number;
  archived_products: number;
  packages: number;
  published_packages: number;
  new_enquiries: number;
  converted_enquiries: number;
}

export const STOCK = [
  ["in_stock", "In stock"],
  ["limited", "Limited stock"],
  ["out_of_stock", "Out of stock"],
  ["on_request", "Available on request"],
] as const;

export const PACKAGE_TYPES = [
  ["hardware_only", "Hardware only"],
  ["hardware_software", "Hardware + software"],
  ["all_in_one", "All-in-one POS package"],
  ["custom", "Custom package"],
] as const;

export const ENQUIRY_STATUSES = ["new", "contacted", "quoted", "converted", "closed"] as const;

export function stockLabel(value: string): string {
  return STOCK.find(([id]) => id === value)?.[1] ?? value;
}
