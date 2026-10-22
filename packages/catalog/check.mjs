import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const seed = JSON.parse(readFileSync(join(here, "seed.json"), "utf8"));
const demo = JSON.parse(readFileSync(join(here, "demo-users.json"), "utf8"));

const roleNames = new Set(demo.roles.map((role) => role.name));
const usernames = new Set();
for (const user of demo.users) {
  if (usernames.has(user.username)) throw new Error(`Duplicate demo username ${user.username}`);
  usernames.add(user.username);
  if (!roleNames.has(user.role)) throw new Error(`Demo user ${user.username} uses unknown role ${user.role}`);
  if (user.has_portal_access && (typeof user.password !== "string" || user.password.length < 10)) {
    throw new Error(`Demo user ${user.username} needs a password of at least 10 characters for portal access.`);
  }
  if (user.has_pos_access && !/^\d{4,6}$/.test(user.pin ?? "")) {
    throw new Error(`Demo user ${user.username} needs a 4-6 digit PIN for POS access.`);
  }
  if (user.store_id !== null && user.store_id !== seed.store.id) {
    throw new Error(`Demo user ${user.username} references an unknown store.`);
  }
}

if (!seed.store?.id || !Array.isArray(seed.products) || seed.products.length === 0) {
  throw new Error("Catalog seed is missing a store or products.");
}

const taxonomy = new Map();
for (const category of seed.categories ?? []) {
  const key = category.name.toLowerCase();
  if (taxonomy.has(key)) throw new Error(`Duplicate category ${category.name}`);
  const subs = new Set();
  for (const sub of category.sub_categories) {
    if (subs.has(sub.toLowerCase())) throw new Error(`Duplicate sub-category ${category.name} › ${sub}`);
    subs.add(sub.toLowerCase());
  }
  for (const name of [category.name, ...category.sub_categories]) {
    if (name.length > 80) throw new Error(`Category name "${name}" is longer than 80 characters.`);
  }
  taxonomy.set(key, subs);
}
for (const product of seed.products) {
  const subs = taxonomy.get(product.category.toLowerCase());
  if (subs === undefined) throw new Error(`Product ${product.sku} uses category ${product.category}, which is not seeded.`);
  if (product.sub_category && !subs.has(product.sub_category.toLowerCase())) {
    throw new Error(`Product ${product.sku} uses sub-category ${product.sub_category}, which is not seeded.`);
  }
}

const seedSkus = new Set(seed.products.map((product) => product.sku));
const treeSkus = new Set();
const treeBarcodes = new Set();
const isEan13 = (code) => {
  if (!/^\d{13}$/.test(code)) return false;
  const digits = [...code].map(Number);
  const sum = digits.slice(0, 12).reduce((total, digit, index) => total + digit * (index % 2 ? 3 : 1), 0);
  return (10 - (sum % 10)) % 10 === digits[12];
};
const brandNames = new Set();
for (const brand of seed.catalog_tree ?? []) {
  if (brandNames.has(brand.brand.toLowerCase())) throw new Error(`Duplicate brand ${brand.brand}`);
  brandNames.add(brand.brand.toLowerCase());
  const modelKeys = new Set();
  for (const model of brand.models) {
    const subs = taxonomy.get(model.category.toLowerCase());
    if (subs === undefined || !subs.has(model.sub_category.toLowerCase())) {
      throw new Error(`${brand.brand} ${model.name} points at ${model.category} › ${model.sub_category}, which is not seeded.`);
    }
    const key = `${model.sub_category}|${model.name}`.toLowerCase();
    if (modelKeys.has(key)) throw new Error(`Duplicate model ${brand.brand} ${model.name}`);
    modelKeys.add(key);
    if (model.variants.length === 0) throw new Error(`${brand.brand} ${model.name} has no variants.`);
    for (const variant of model.variants) {
      if (treeSkus.has(variant.sku)) throw new Error(`Duplicate variant SKU ${variant.sku}`);
      treeSkus.add(variant.sku);
      if (Object.keys(variant.attributes).length > 8) throw new Error(`${variant.sku} has more than 8 attributes.`);
      if (seedSkus.has(variant.sku)) continue;
      if (!isEan13(variant.barcode ?? "")) throw new Error(`${variant.sku} needs a valid EAN-13 barcode.`);
      if (treeBarcodes.has(variant.barcode)) throw new Error(`Duplicate barcode ${variant.barcode}`);
      treeBarcodes.add(variant.barcode);
      if (variant.stock && model.serialized) throw new Error(`${variant.sku} is serialized; receive its IMEIs instead of seeding stock.`);
    }
  }
}

const barcodes = new Set();
for (const product of seed.products) {
  if (barcodes.has(product.barcode)) {
    throw new Error(`Duplicate barcode ${product.barcode}`);
  }
  barcodes.add(product.barcode);
  if (product.store_id !== seed.store.id) {
    throw new Error(`Product ${product.sku} does not belong to the seed store.`);
  }
}
