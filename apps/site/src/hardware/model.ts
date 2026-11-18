import { money } from "../catalog";

export interface HardwareImage {
  url: string;
  thumb_url: string;
  alt: string;
  is_primary: boolean;
}

export interface HardwareCategory {
  slug: string;
  name: string;
  description: string;
  image_url: string | null;
  image_alt: string;
}

export interface HardwareProduct {
  slug: string;
  name: string;
  sku: string;
  brand: string;
  model_number: string;
  short_description: string;
  full_description: string;
  display_price_fils: number | null;
  currency: string;
  warranty_months: number;
  stock_status: string;
  compatibility: string;
  is_featured: boolean;
  category_slug: string;
  category_name: string;
  specifications: { label: string; value: string }[];
  images: HardwareImage[];
}

export interface HardwarePackageCard {
  slug: string;
  name: string;
  short_description: string;
  display_price_fils: number | null;
  currency: string;
  package_type: string;
  is_featured: boolean;
  thumb_url: string | null;
}

export interface HardwarePlan {
  code: string;
  name: string;
  monthly_fils: number;
  included_registers: number;
}

export interface HardwareComponent {
  slug: string;
  name: string;
  quantity: number;
  is_optional: boolean;
  display_price_fils: number | null;
  thumb_url: string | null;
}

export interface HardwarePackage extends HardwarePackageCard {
  full_description: string;
  images: HardwareImage[];
  plan: HardwarePlan | null;
  items: HardwareComponent[];
  component_value_fils: number | null;
  savings_fils: number | null;
}

export type HardwareView =
  | { kind: "catalog" }
  | { kind: "product"; slug: string }
  | { kind: "package"; slug: string };

const STOCK: Record<string, string> = {
  in_stock: "In stock",
  limited: "Limited stock",
  out_of_stock: "Out of stock",
  on_request: "Available on request",
};

const AVAILABILITY: Record<string, string> = {
  in_stock: "https://schema.org/InStock",
  limited: "https://schema.org/LimitedAvailability",
  out_of_stock: "https://schema.org/OutOfStock",
  on_request: "https://schema.org/PreOrder",
};

export const BUSINESS_TYPES = [
  ["restaurant", "Restaurant"],
  ["cafe", "Café"],
  ["supermarket", "Supermarket & grocery"],
  ["electronics", "Electronics"],
  ["fashion", "Fashion & retail"],
  ["wholesale", "Wholesale"],
  ["other", "Other"],
] as const;

const SEGMENTS = [
  { id: "dining", title: "Restaurant & Café", words: ["restaurant", "cafe", "café"] },
  { id: "grocery", title: "Supermarket & Grocery", words: ["supermarket", "grocery"] },
  { id: "trade", title: "Electronics & Wholesale", words: ["electronics", "wholesale"] },
  { id: "fashion", title: "Fashion & Retail", words: ["fashion", "retail"] },
] as const;

export function stockLabel(status: string): string {
  return STOCK[status] ?? "Available on request";
}

export function publicPrice(fils: number | null, currency: string): string | null {
  if (fils == null) return null;
  return money(fils, currency || "AED");
}

export function hardwareView(pathname: string): HardwareView {
  const path = pathname.replace(/\/+$/, "") || "/";
  const product = path.match(/^\/hardware\/products\/([a-z0-9]+(?:-[a-z0-9]+)*)$/);
  if (product?.[1]) return { kind: "product", slug: product[1] };
  const bundle = path.match(/^\/hardware\/packages\/([a-z0-9]+(?:-[a-z0-9]+)*)$/);
  if (bundle?.[1]) return { kind: "package", slug: bundle[1] };
  return { kind: "catalog" };
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function fils(value: unknown): number | null {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : null;
}

function image(value: unknown): HardwareImage | null {
  if (value === null || typeof value !== "object") return null;
  const row = value as Record<string, unknown>;
  const url = text(row.url);
  if (!url.startsWith("https://") && !url.startsWith("http://") && !url.startsWith("/")) return null;
  return {
    url,
    thumb_url: text(row.thumb_url) || url,
    alt: text(row.alt),
    is_primary: row.is_primary === true,
  };
}

export function readProduct(value: unknown): HardwareProduct | null {
  if (value === null || typeof value !== "object") return null;
  const row = value as Record<string, unknown>;
  const slug = text(row.slug);
  const name = text(row.name);
  if (!slug || !name) return null;
  const specifications = Array.isArray(row.specifications)
    ? row.specifications.flatMap((item) => {
        if (item === null || typeof item !== "object") return [];
        const spec = item as Record<string, unknown>;
        const label = text(spec.label);
        const specValue = text(spec.value);
        return label && specValue ? [{ label, value: specValue }] : [];
      })
    : [];
  return {
    slug,
    name,
    sku: text(row.sku),
    brand: text(row.brand),
    model_number: text(row.model_number),
    short_description: text(row.short_description),
    full_description: text(row.full_description),
    display_price_fils: fils(row.display_price_fils),
    currency: text(row.currency) || "AED",
    warranty_months: typeof row.warranty_months === "number" ? row.warranty_months : 0,
    stock_status: text(row.stock_status) || "on_request",
    compatibility: text(row.compatibility),
    is_featured: row.is_featured === true,
    category_slug: text(row.category_slug),
    category_name: text(row.category_name),
    specifications,
    images: Array.isArray(row.images) ? row.images.flatMap((item) => {
      const parsed = image(item);
      return parsed ? [parsed] : [];
    }) : [],
  };
}

export function readCategory(value: unknown): HardwareCategory | null {
  if (value === null || typeof value !== "object") return null;
  const row = value as Record<string, unknown>;
  const slug = text(row.slug);
  const name = text(row.name);
  if (!slug || !name) return null;
  const imageUrl = text(row.image_url);
  return {
    slug,
    name,
    description: text(row.description),
    image_url: imageUrl || null,
    image_alt: text(row.image_alt) || name,
  };
}

export function readPackageCard(value: unknown): HardwarePackageCard | null {
  if (value === null || typeof value !== "object") return null;
  const row = value as Record<string, unknown>;
  const slug = text(row.slug);
  const name = text(row.name);
  if (!slug || !name) return null;
  return {
    slug,
    name,
    short_description: text(row.short_description),
    display_price_fils: fils(row.display_price_fils),
    currency: text(row.currency) || "AED",
    package_type: text(row.package_type),
    is_featured: row.is_featured === true,
    thumb_url: text(row.thumb_url) || null,
  };
}

export function readPackage(value: unknown): HardwarePackage | null {
  const card = readPackageCard(value);
  if (!card || value === null || typeof value !== "object") return null;
  const row = value as Record<string, unknown>;
  const planRow = row.plan;
  let plan: HardwarePlan | null = null;
  if (planRow !== null && typeof planRow === "object") {
    const planRecord = planRow as Record<string, unknown>;
    const monthly = fils(planRecord.monthly_fils);
    if (text(planRecord.name) && monthly != null) {
      plan = {
        code: text(planRecord.code),
        name: text(planRecord.name),
        monthly_fils: monthly,
        included_registers: typeof planRecord.included_registers === "number" ? planRecord.included_registers : 0,
      };
    }
  }
  const items = Array.isArray(row.items)
    ? row.items.flatMap((item) => {
        if (item === null || typeof item !== "object") return [];
        const component = item as Record<string, unknown>;
        const name = text(component.name);
        if (!name) return [];
        return [
          {
            slug: text(component.slug),
            name,
            quantity: typeof component.quantity === "number" ? component.quantity : 1,
            is_optional: component.is_optional === true,
            display_price_fils: fils(component.display_price_fils),
            thumb_url: text(component.thumb_url) || null,
          },
        ];
      })
    : [];
  return {
    ...card,
    full_description: text(row.full_description),
    images: Array.isArray(row.images) ? row.images.flatMap((item) => {
      const parsed = image(item);
      return parsed ? [parsed] : [];
    }) : [],
    plan,
    items,
    component_value_fils: fils(row.component_value_fils),
    savings_fils: fils(row.savings_fils),
  };
}

export function readList<T>(value: unknown, read: (item: unknown) => T | null): T[] {
  return Array.isArray(value) ? value.flatMap((item) => {
    const parsed = read(item);
    return parsed ? [parsed] : [];
  }) : [];
}

/** A segment is shown only when a published product's category or compatibility names it. */
export function segmentProducts(products: HardwareProduct[]): { title: string; products: HardwareProduct[] }[] {
  return SEGMENTS.flatMap((segment) => {
    const matched = products.filter((product) => {
      const haystack = `${product.category_name} ${product.category_slug} ${product.compatibility}`.toLowerCase();
      return segment.words.some((word) => haystack.includes(word));
    });
    return matched.length ? [{ title: segment.title, products: matched.slice(0, 3) }] : [];
  });
}

export interface EnquiryDraft {
  customer_name: string;
  business_name: string;
  email: string;
  phone: string;
  country: string;
  business_type: string;
  product_slug: string;
  package_slug: string;
  quantity: string;
  message: string;
}

export function enquiryErrors(draft: EnquiryDraft): Record<string, string> {
  const errors: Record<string, string> = {};
  if (draft.customer_name.trim().length < 2) errors.customer_name = "Enter your name.";
  if (draft.business_name.trim().length < 2) errors.business_name = "Enter the business name.";
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(draft.email.trim().toLowerCase())) errors.email = "Enter a valid email address.";
  if (!/^\+[1-9][0-9]{6,14}$/.test(draft.phone.trim())) errors.phone = "Enter a phone number with the country code, such as +971500000000.";
  if (!BUSINESS_TYPES.some(([id]) => id === draft.business_type)) errors.business_type = "Choose a business type.";
  const quantity = Number(draft.quantity);
  if (!Number.isInteger(quantity) || quantity < 1 || quantity > 999) errors.quantity = "Enter a quantity from 1 to 999.";
  if (draft.message.trim().length < 10) errors.message = "Tell us what you need, in at least a few words.";
  return errors;
}

export function productJsonLd(product: HardwareProduct, url: string): Record<string, unknown> | null {
  if (product.display_price_fils == null) return null;
  const photo = product.images.find((item) => item.is_primary) ?? product.images[0];
  return {
    "@context": "https://schema.org",
    "@type": "Product",
    name: product.name,
    sku: product.sku,
    description: product.short_description || product.full_description,
    image: photo?.url,
    brand: product.brand ? { "@type": "Brand", name: product.brand } : undefined,
    offers: {
      "@type": "Offer",
      url,
      priceCurrency: product.currency || "AED",
      price: (product.display_price_fils / 100).toFixed(2),
      availability: AVAILABILITY[product.stock_status] ?? AVAILABILITY.on_request,
    },
  };
}
