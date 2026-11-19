import type { SeoPage } from "../seo-types.ts";

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

export function articleText(page: SeoPage): string {
  const chunks = [page.lead, ...page.points];
  for (const section of page.sections) {
    chunks.push(section.heading, ...section.paragraphs);
    for (const sub of section.subsections ?? []) chunks.push(sub.heading, ...sub.paragraphs);
    if (section.table) chunks.push(section.table.caption, ...section.table.headers, ...section.table.rows.flat());
  }
  for (const faq of page.faqs ?? []) chunks.push(faq.question, faq.answer);
  return chunks.join(" ");
}

export function wordCount(page: SeoPage): number {
  return articleText(page).split(/\s+/).filter(Boolean).length;
}

/** About 200 words a minute, rounded, and never zero for a published guide. */
export function readingMinutes(page: SeoPage): number {
  return Math.max(1, Math.round(wordCount(page) / 200));
}

export function formatPublished(iso: string, locale: "en" | "ar"): string {
  const [year, month, day] = iso.split("-").map(Number);
  if (!year || !month || !day || month < 1 || month > 12) return iso;
  if (locale === "ar") return iso;
  return `${day} ${MONTHS[month - 1]} ${year}`;
}

export function categoryOf(page: SeoPage): string {
  if (page.category) return page.category;
  const path = page.path;
  const ar = page.locale === "ar";
  if (path.includes("cafe") || path.includes("restaurant")) return ar ? "مطعم" : "Restaurant";
  if (path.includes("supermarket") || path.includes("grocery")) return ar ? "بقالة" : "Grocery";
  if (path.includes("electronics") || path.includes("imei")) return ar ? "جملة" : "Wholesale";
  if (path.includes("offline") || path.includes("branch")) return ar ? "تشغيل" : "Operations";
  return ar ? "اختيار" : "Buying";
}
