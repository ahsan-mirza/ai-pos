/** Category-driven technical details. The same product table stores every shape in `specifications`. */

export interface SpecField {
  key: string;
  label: string;
  placeholder: string;
  options: readonly string[];
}

export interface SpecSchema {
  id:
    | "COMPUTERS_LAPTOPS"
    | "MOBILES_PHONES"
    | "HOME_APPLIANCES_FRIDGE"
    | "TV_AUDIO"
    | "FASHION_CLOTHING"
    | "FASHION_DRESS"
    | "FASHION_FOOTWEAR"
    | "FASHION_BAG"
    | "RESTAURANT_BURGER"
    | "RESTAURANT_PIZZA"
    | "RESTAURANT_SANDWICH"
    | "RESTAURANT_DRINK"
    | "RESTAURANT_DESSERT"
    | "RESTAURANT_MAIN"
    | "CAFE_DRINK"
    | "CAFE_BAKERY"
    | "GROCERY_ITEM"
    | "OTHER";
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

const FASHION_COLORS = ["Black", "White", "Navy", "Grey", "Beige", "Cream", "Red", "Pink", "Burgundy", "Green", "Brown", "Gold"] as const;
const FASHION_SIZES = ["XS", "S", "M", "L", "XL", "XXL", "32", "34", "36", "38", "40", "42"] as const;
const FABRICS = ["Cotton", "Silk", "Polyester", "Wool", "Linen", "Denim", "Chiffon", "Satin", "Velvet", "Crepe"] as const;

const FASHION: SpecSchema = {
  id: "FASHION_CLOTHING",
  title: "Fashion & apparel",
  variantKeys: ["size", "color"],
  fields: [
    { key: "size", label: "Size", placeholder: "M", options: FASHION_SIZES },
    { key: "color", label: "Color", placeholder: "Navy", options: FASHION_COLORS },
    { key: "fabric", label: "Fabric / material", placeholder: "Cotton", options: FABRICS },
    { key: "gender_fit", label: "Gender / fit", placeholder: "Regular", options: ["Men", "Women", "Unisex", "Kids", "Slim", "Regular", "Relaxed"] },
  ],
};

const DRESS: SpecSchema = {
  id: "FASHION_DRESS",
  title: "Dresses",
  variantKeys: ["size", "color"],
  fields: [
    { key: "size", label: "Size", placeholder: "M", options: FASHION_SIZES },
    { key: "color", label: "Color", placeholder: "Beige", options: FASHION_COLORS },
    { key: "fabric", label: "Fabric", placeholder: "Chiffon", options: FABRICS },
    { key: "length", label: "Length", placeholder: "Midi", options: ["Mini", "Knee", "Midi", "Maxi", "Floor"] },
    { key: "sleeve", label: "Sleeve", placeholder: "Sleeveless", options: ["Sleeveless", "Short", "Three-quarter", "Long"] },
    { key: "neckline", label: "Neckline", placeholder: "V-neck", options: ["Round", "V-neck", "Square", "Sweetheart", "Boat", "High neck", "Off shoulder"] },
    { key: "gender_fit", label: "Gender / fit", placeholder: "Women", options: ["Women", "Girls", "Unisex", "Slim", "Regular", "Relaxed"] },
  ],
};

const FOOTWEAR: SpecSchema = {
  id: "FASHION_FOOTWEAR",
  title: "Footwear",
  variantKeys: ["size", "color"],
  fields: [
    { key: "size", label: "Size", placeholder: "40", options: ["36", "37", "38", "39", "40", "41", "42", "43", "44", "45", "UK 5", "UK 6", "UK 7", "UK 8", "UK 9", "UK 10"] },
    { key: "color", label: "Color", placeholder: "Black", options: FASHION_COLORS },
    { key: "material", label: "Material", placeholder: "Leather", options: ["Leather", "Suede", "Canvas", "Mesh", "Synthetic", "Rubber"] },
    { key: "width", label: "Width", placeholder: "Regular", options: ["Narrow", "Regular", "Wide"] },
  ],
};

const BAG: SpecSchema = {
  id: "FASHION_BAG",
  title: "Bags",
  variantKeys: ["color"],
  fields: [
    { key: "size", label: "Size", placeholder: "Medium", options: ["Mini", "Small", "Medium", "Large"] },
    { key: "color", label: "Color", placeholder: "Black", options: FASHION_COLORS },
    { key: "material", label: "Material", placeholder: "Leather", options: ["Leather", "Canvas", "Nylon", "Straw", "Suede", "Fabric"] },
  ],
};

const BURGER: SpecSchema = {
  id: "RESTAURANT_BURGER",
  title: "Burgers",
  variantKeys: [],
  fields: [
    { key: "patty_type", label: "Patty type", placeholder: "Beef", options: ["Beef", "Chicken", "Fish", "Veggie"] },
    { key: "patty_quantity", label: "Patty quantity", placeholder: "Single", options: ["Single", "Double", "Triple"] },
    { key: "bun_type", label: "Bun type", placeholder: "Brioche", options: ["Brioche", "Sesame", "Whole wheat", "Gluten-free"] },
    { key: "cheese_type", label: "Cheese type", placeholder: "Cheddar", options: ["Cheddar", "American", "Swiss", "None"] },
    { key: "spice_level", label: "Spice level", placeholder: "Mild", options: ["Mild", "Medium", "Hot"] },
    { key: "serving_size", label: "Serving size", placeholder: "Regular", options: ["Regular", "Large"] },
    { key: "dietary", label: "Dietary classification", placeholder: "Regular", options: ["Regular", "Vegetarian", "Vegan"] },
    { key: "allergens", label: "Allergens", placeholder: "Gluten", options: ["None", "Gluten", "Dairy", "Eggs", "Nuts"] },
  ],
};

const PIZZA: SpecSchema = {
  id: "RESTAURANT_PIZZA",
  title: "Pizza",
  variantKeys: [],
  fields: [
    { key: "pizza_size", label: "Size", placeholder: "Medium", options: ["Personal", "Small", "Medium", "Large"] },
    { key: "crust", label: "Crust", placeholder: "Thin", options: ["Thin", "Classic", "Thick", "Stuffed"] },
    { key: "spice_level", label: "Spice level", placeholder: "Mild", options: ["Mild", "Medium", "Hot"] },
    { key: "dietary", label: "Dietary classification", placeholder: "Regular", options: ["Regular", "Vegetarian", "Vegan"] },
    { key: "allergens", label: "Allergens", placeholder: "Gluten", options: ["None", "Gluten", "Dairy"] },
  ],
};

const SANDWICH: SpecSchema = {
  id: "RESTAURANT_SANDWICH",
  title: "Sandwiches",
  variantKeys: [],
  fields: [
    { key: "bread", label: "Bread", placeholder: "White", options: ["White", "Whole wheat", "Wrap", "Gluten-free"] },
    { key: "filling", label: "Filling", placeholder: "Chicken", options: ["Chicken", "Beef", "Veggie", "Cheese"] },
    { key: "spice_level", label: "Spice level", placeholder: "Mild", options: ["Mild", "Medium", "Hot"] },
    { key: "allergens", label: "Allergens", placeholder: "Gluten", options: ["None", "Gluten", "Dairy", "Eggs"] },
  ],
};

const FOOD_DRINK: SpecSchema = {
  id: "RESTAURANT_DRINK",
  title: "Beverages",
  variantKeys: [],
  fields: [
    { key: "beverage_size", label: "Size", placeholder: "Regular", options: ["Small", "Regular", "Large"] },
    { key: "temperature", label: "Temperature", placeholder: "Cold", options: ["Hot", "Cold"] },
  ],
};

const DESSERT: SpecSchema = {
  id: "RESTAURANT_DESSERT",
  title: "Desserts",
  variantKeys: [],
  fields: [
    { key: "serving_size", label: "Serving size", placeholder: "Regular", options: ["Regular", "Sharing"] },
    { key: "dietary", label: "Dietary classification", placeholder: "Regular", options: ["Regular", "Vegetarian", "Vegan"] },
    { key: "allergens", label: "Allergens", placeholder: "Dairy", options: ["None", "Dairy", "Eggs", "Nuts", "Gluten"] },
  ],
};

const MAIN: SpecSchema = {
  id: "RESTAURANT_MAIN",
  title: "Main courses",
  variantKeys: [],
  fields: [
    { key: "serving_size", label: "Serving size", placeholder: "Regular", options: ["Regular", "Large"] },
    { key: "spice_level", label: "Spice level", placeholder: "Mild", options: ["Mild", "Medium", "Hot"] },
    { key: "dietary", label: "Dietary classification", placeholder: "Regular", options: ["Regular", "Vegetarian", "Vegan"] },
    { key: "allergens", label: "Allergens", placeholder: "None", options: ["None", "Gluten", "Dairy", "Nuts", "Shellfish"] },
  ],
};

const CAFE_DRINK: SpecSchema = {
  id: "CAFE_DRINK",
  title: "Café drinks",
  variantKeys: [],
  fields: [
    { key: "beverage_size", label: "Beverage size", placeholder: "Medium", options: ["Small", "Medium", "Large"] },
    { key: "temperature", label: "Temperature", placeholder: "Hot", options: ["Hot", "Iced"] },
    { key: "milk_type", label: "Milk type", placeholder: "Whole", options: ["Whole", "Skim", "Oat", "Almond", "Soy", "None"] },
    { key: "sugar_level", label: "Sugar level", placeholder: "Regular", options: ["None", "Less", "Regular", "Extra"] },
    { key: "flavor", label: "Flavor", placeholder: "Plain", options: ["Plain", "Vanilla", "Caramel", "Hazelnut"] },
    { key: "caffeine", label: "Caffeine", placeholder: "Regular", options: ["Regular", "Decaf"] },
  ],
};

const CAFE_BAKERY: SpecSchema = {
  id: "CAFE_BAKERY",
  title: "Bakery",
  variantKeys: [],
  fields: [
    { key: "dietary", label: "Dietary classification", placeholder: "Regular", options: ["Regular", "Vegetarian", "Vegan"] },
    { key: "allergens", label: "Allergens", placeholder: "Gluten", options: ["None", "Gluten", "Dairy", "Eggs", "Nuts"] },
  ],
};

const GROCERY: SpecSchema = {
  id: "GROCERY_ITEM",
  title: "Grocery",
  variantKeys: [],
  fields: [
    { key: "net_weight", label: "Net weight or volume", placeholder: "500g", options: ["250g", "500g", "1kg", "250ml", "500ml", "1L"] },
    { key: "storage_temperature", label: "Storage temperature", placeholder: "Chilled", options: ["Ambient", "Chilled", "Frozen"] },
    { key: "packaging", label: "Packaging type", placeholder: "Carton", options: ["Bottle", "Carton", "Bag", "Tray", "Can"] },
    { key: "grade", label: "Product grade", placeholder: "Standard", options: ["Standard", "Premium", "A", "B"] },
    { key: "origin", label: "Origin", placeholder: "Local", options: ["Local", "Imported"] },
  ],
};

const OTHER: SpecSchema = {
  id: "OTHER",
  title: "Custom specifications",
  variantKeys: [],
  fields: [],
};

const SCHEMAS = [
  LAPTOP,
  MOBILE,
  FRIDGE,
  TV,
  FASHION,
  DRESS,
  FOOTWEAR,
  BAG,
  BURGER,
  PIZZA,
  SANDWICH,
  FOOD_DRINK,
  DESSERT,
  MAIN,
  CAFE_DRINK,
  CAFE_BAKERY,
  GROCERY,
] as const;

function text(value: string): string {
  return value.toLowerCase();
}

function mentions(value: string, words: readonly string[]): boolean {
  return words.some((word) => value.includes(word));
}

export interface SpecSchemaHint {
  /** Product or model name, so "Evening dress" picks dress fields even under a broad category. */
  productName?: string;
  /** Business profile. Templates are chosen only from this profile. */
  profile?: string;
}

function hasTerm(value: string, terms: readonly string[]): boolean {
  return terms.some((term) => new RegExp(`(^|[^a-z])${term}(?:es|s)?([^a-z]|$)`).test(value));
}

const DRESS_TERMS = ["dress", "gown", "abaya", "jalabiya", "kaftan", "jilbab"];
const FOOTWEAR_TERMS = ["shoe", "footwear", "sneaker", "sandal", "heel", "boot", "loafer", "slipper"];
const BAG_TERMS = ["bag", "handbag", "clutch", "tote", "purse", "wallet"];
const CLOTHING_TERMS = [
  "apparel",
  "fashion",
  "clothing",
  "garment",
  "shirt",
  "top",
  "tee",
  "jean",
  "trouser",
  "pant",
  "skirt",
  "blouse",
  "hijab",
  "scarf",
  "jacket",
  "coat",
  "sweater",
  "hoodie",
  "short",
];

function matchElectronics(both: string, category: string, sub: string, productName: string): SpecSchema | null {
  if (mentions(both, ["refrigerator", "fridge", "freezer"])) return FRIDGE;
  if (/(^|[^a-z])tv([^a-z]|$)|television|soundbar/.test(both)) return TV;
  if (mentions(both, ["phone", "mobile", "smartphone", "tablet", "ipad", "handset"])) return MOBILE;
  const computer =
    mentions(category, ["laptop", "desktop", "notebook", "macbook"]) ||
    mentions(sub, ["laptop", "desktop", "notebook", "macbook"]) ||
    mentions(productName, ["laptop", "notebook", "macbook"]);
  const computerCategory = mentions(category, ["computer"]) && (sub === "" || mentions(sub, ["laptop", "desktop", "notebook"]));
  if (computer || computerCategory) return LAPTOP;
  return null;
}

function matchFashion(both: string): SpecSchema | null {
  const dress = hasTerm(both, DRESS_TERMS);
  const footwear = hasTerm(both, FOOTWEAR_TERMS);
  const clothing = hasTerm(both, CLOTHING_TERMS);
  // "Dress shoes" are shoes; "boot cut jeans" stay apparel. A plain dress stays a dress.
  if (dress && !hasTerm(both, ["shoe", "boot", "sandal", "sneaker"])) return DRESS;
  if (footwear && !hasTerm(both, ["jean", "trouser", "pant"])) return FOOTWEAR;
  if (hasTerm(both, BAG_TERMS)) return BAG;
  if (clothing || dress) return FASHION;
  return null;
}

function matchRestaurant(both: string): SpecSchema | null {
  if (mentions(both, ["burger"])) return BURGER;
  if (mentions(both, ["pizza"])) return PIZZA;
  if (mentions(both, ["sandwich", "wrap"])) return SANDWICH;
  if (mentions(both, ["dessert", "cake", "sweet"])) return DESSERT;
  if (mentions(both, ["drink", "beverage", "juice", "soda", "coffee", "tea"])) return FOOD_DRINK;
  if (mentions(both, ["main", "appetizer", "starter", "grill", "course"])) return MAIN;
  return null;
}

function matchCafe(both: string): SpecSchema | null {
  if (mentions(both, ["coffee", "tea", "latte", "espresso", "chai", "juice", "drink"])) return CAFE_DRINK;
  if (mentions(both, ["bakery", "muffin", "croissant", "pastry", "cookie", "dessert", "cake"])) return CAFE_BAKERY;
  return null;
}

function matchGrocery(both: string): SpecSchema | null {
  if (
    mentions(both, [
      "dairy",
      "milk",
      "fruit",
      "vegetable",
      "produce",
      "bakery",
      "frozen",
      "beverage",
      "household",
      "grocery",
      "meat",
      "pantry",
    ])
  ) {
    return GROCERY;
  }
  return null;
}

/**
 * Specification template for this business type and category.
 * An unmatched name, or a business type with no template, is an empty custom list.
 * One business type never receives another type's fields.
 */
export function specSchemaFor(categoryName: string, subCategoryName = "", hint?: SpecSchemaHint): SpecSchema {
  const profile = hint?.profile ?? "";
  const category = text(categoryName);
  const sub = text(subCategoryName);
  const productName = text(hint?.productName ?? "");
  const both = `${category} ${sub} ${productName}`.trim();
  if (both === "" || profile === "") return OTHER;
  if (profile === "electronics_wholesale") return matchElectronics(both, category, sub, productName) ?? OTHER;
  if (profile === "retail_fashion") return matchFashion(both) ?? OTHER;
  if (profile === "grocery") return matchGrocery(both) ?? OTHER;
  if (profile === "restaurant" || profile === "quick_service") return matchRestaurant(both) ?? OTHER;
  if (profile === "cafe") return matchCafe(both) ?? OTHER;
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
    case "FASHION_DRESS":
    case "FASHION_FOOTWEAR":
    case "FASHION_BAG":
      return join([
        brand,
        model,
        value(specs, "color"),
        value(specs, "fabric") || value(specs, "material"),
        value(specs, "length"),
        value(specs, "size"),
      ]);
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
