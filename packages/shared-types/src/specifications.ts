/** Category-driven technical details. The same product table stores every shape in `specifications`. */

export interface SpecField {
  key: string;
  label: string;
  placeholder: string;
  options: readonly string[];
}

export interface SpecSchema {
  id: "COMPUTERS_LAPTOPS" | "MOBILES_PHONES" | "HOME_APPLIANCES_FRIDGE" | "TV_AUDIO" | "FASHION_CLOTHING" | "OTHER";
  title: string;
  fields: readonly SpecField[];
  /** Values that also distinguish a sellable variant (size, storage, colour). */
  variantKeys: readonly string[];
}

const LAPTOP: SpecSchema = {
  id: "COMPUTERS_LAPTOPS",
  title: "Computers & laptops",
  variantKeys: ["ram", "storage"],
  fields: [
    { key: "processor", label: "Processor", placeholder: "Apple M3", options: ["Apple M3", "Apple M4", "Intel Core i5", "Intel Core i7", "i7-13700H", "AMD Ryzen 7", "Snapdragon X Elite"] },
    { key: "ram", label: "RAM", placeholder: "16GB DDR5", options: ["8GB", "16GB", "16GB DDR5", "32GB", "32GB DDR5", "64GB"] },
    { key: "storage", label: "Storage", placeholder: "512GB NVMe SSD", options: ["256GB SSD", "512GB SSD", "512GB NVMe SSD", "1TB NVMe SSD", "2TB NVMe SSD"] },
    { key: "graphics", label: "Graphics / GPU", placeholder: "RTX 4060", options: ["Integrated", "RTX 4050", "RTX 4060", "RTX 4070", "Apple GPU"] },
    { key: "screen_size", label: "Screen size", placeholder: '15.6"', options: ['13"', '14"', '15.6"', '16"', '17"'] },
    { key: "os", label: "OS", placeholder: "Windows 11", options: ["Windows 11", "macOS", "ChromeOS", "Linux"] },
  ],
};

const MOBILE: SpecSchema = {
  id: "MOBILES_PHONES",
  title: "Mobiles & smartphones",
  variantKeys: ["storage", "ram", "color"],
  fields: [
    { key: "storage", label: "Storage", placeholder: "256GB", options: ["128GB", "256GB", "512GB", "1TB"] },
    { key: "ram", label: "RAM", placeholder: "8GB", options: ["4GB", "6GB", "8GB", "12GB", "16GB"] },
    { key: "color", label: "Color / finish", placeholder: "Natural Titanium", options: ["Natural Titanium", "Black", "White", "Blue", "Green", "Desert Titanium"] },
    { key: "network", label: "Network / SIM", placeholder: "Dual SIM / eSIM", options: ["Single SIM", "Dual SIM", "eSIM", "Dual SIM / eSIM", "5G"] },
    { key: "battery", label: "Battery capacity", placeholder: "5000mAh", options: ["4000mAh", "4500mAh", "5000mAh", "6000mAh"] },
  ],
};

const FRIDGE: SpecSchema = {
  id: "HOME_APPLIANCES_FRIDGE",
  title: "Refrigerators",
  variantKeys: ["capacity_litres", "door_style"],
  fields: [
    { key: "capacity_litres", label: "Capacity (litres)", placeholder: "450L", options: ["200L", "300L", "350L", "450L", "600L"] },
    { key: "defrost_type", label: "Defrost type", placeholder: "Frost Free", options: ["Frost Free", "Direct Cool", "Manual"] },
    { key: "energy_rating", label: "Energy rating", placeholder: "5 Star", options: ["3 Star", "4 Star", "5 Star"] },
    { key: "compressor", label: "Compressor type", placeholder: "Inverter", options: ["Inverter", "Digital Inverter", "Reciprocating"] },
    { key: "door_style", label: "Door style", placeholder: "Double Door", options: ["Single Door", "Double Door", "Side-by-Side", "French Door"] },
  ],
};

const TV: SpecSchema = {
  id: "TV_AUDIO",
  title: "Television & audio",
  variantKeys: ["screen_size"],
  fields: [
    { key: "screen_size", label: "Screen size", placeholder: '65"', options: ['32"', '43"', '50"', '55"', '65"', '75"'] },
    { key: "display_tech", label: "Display tech", placeholder: "OLED", options: ["LED", "QLED", "OLED", "Mini LED"] },
    { key: "resolution", label: "Resolution", placeholder: "4K UHD", options: ["HD", "Full HD", "4K UHD", "8K"] },
    { key: "refresh_rate", label: "Refresh rate", placeholder: "120Hz", options: ["60Hz", "120Hz", "144Hz"] },
  ],
};

const FASHION: SpecSchema = {
  id: "FASHION_CLOTHING",
  title: "Fashion & apparel",
  variantKeys: ["size", "color"],
  fields: [
    { key: "size", label: "Size", placeholder: "M", options: ["XS", "S", "M", "L", "XL", "XXL", "32", "34", "36", "38", "40", "42"] },
    { key: "color", label: "Color", placeholder: "Navy", options: ["Black", "White", "Navy", "Grey", "Beige", "Red"] },
    { key: "fabric", label: "Fabric / material", placeholder: "Cotton", options: ["Cotton", "Silk", "Polyester", "Wool", "Linen", "Denim"] },
    { key: "gender_fit", label: "Gender / fit", placeholder: "Regular", options: ["Men", "Women", "Unisex", "Kids", "Slim", "Regular", "Relaxed"] },
  ],
};

const OTHER: SpecSchema = {
  id: "OTHER",
  title: "Custom specifications",
  variantKeys: [],
  fields: [],
};

const SCHEMAS = [LAPTOP, MOBILE, FRIDGE, TV, FASHION] as const;

function text(value: string): string {
  return value.toLowerCase();
}

function mentions(value: string, words: readonly string[]): boolean {
  return words.some((word) => value.includes(word));
}

/** Pick the specification template from the catalog names the merchant just chose. */
export function specSchemaFor(categoryName: string, subCategoryName = ""): SpecSchema {
  const category = text(categoryName);
  const sub = text(subCategoryName);
  const both = `${category} ${sub}`.trim();
  if (both === "") return OTHER;
  if (mentions(both, ["refrigerator", "fridge", "freezer"])) return FRIDGE;
  if (/(^|[^a-z])tv([^a-z]|$)|television|soundbar/.test(both)) return TV;
  if (mentions(both, ["apparel", "fashion", "clothing", "garment", "footwear", "shoe"])) return FASHION;
  if (mentions(both, ["phone", "mobile", "smartphone", "tablet", "ipad", "handset"])) return MOBILE;
  const computer = mentions(sub, ["laptop", "desktop", "notebook", "macbook"]);
  const computerCategory = mentions(category, ["computer"]) && (sub === "" || mentions(sub, ["laptop", "desktop", "notebook"]));
  if (computer || computerCategory) return LAPTOP;
  return OTHER;
}

/** Every key a built-in template can write, so a category change can drop stale variant keys. */
export function allSpecKeys(): ReadonlySet<string> {
  return new Set(SCHEMAS.flatMap((schema) => schema.fields.map((field) => field.key)));
}

export function specKey(label: string): string {
  const key = label
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 24);
  return /^[a-z][a-z0-9_]{0,23}$/.test(key) ? key : "";
}

function join(parts: string[]): string {
  return parts.map((part) => part.trim()).filter(Boolean).join(" ");
}

function value(specs: Record<string, string>, key: string): string {
  return (specs[key] ?? "").trim();
}

/** Brand, model, and the specs that identify this kind of product. */
export function titleFromSpecs(input: {
  brand: string;
  model: string;
  schema: SpecSchema;
  specs: Record<string, string>;
}): string {
  const brand = input.brand.trim();
  const model = input.model.trim();
  const specs = input.specs;
  switch (input.schema.id) {
    case "COMPUTERS_LAPTOPS":
      return join([brand, model, value(specs, "processor"), value(specs, "ram"), value(specs, "storage")]);
    case "MOBILES_PHONES":
      return join([brand, model, value(specs, "storage"), value(specs, "ram"), value(specs, "color")]);
    case "HOME_APPLIANCES_FRIDGE": {
      const title = join([brand, value(specs, "capacity_litres"), value(specs, "door_style"), model]);
      return title === "" || /refrigerator/i.test(title) ? title : `${title} Refrigerator`;
    }
    case "TV_AUDIO":
      return join([brand, value(specs, "screen_size"), value(specs, "display_tech"), model || "Television"]);
    case "FASHION_CLOTHING":
      return join([brand, model, value(specs, "color"), value(specs, "fabric"), value(specs, "size")]);
    default:
      return join([brand, model, ...Object.values(specs)]);
  }
}

/** Short line for a till tile, e.g. "16GB DDR5 · 512GB NVMe SSD". */
export function specSummary(specs: Record<string, string> | undefined, limit = 3): string {
  return Object.values(specs ?? {})
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, limit)
    .join(" · ");
}
