import { isDemoBusinessCode, portalDemoEntry, type DemoBusinessCode } from "@ai-pos/shared-types";
import type { SeoPage } from "./seo-types";

/**
 * Public Business Pro demo for each Solutions page.
 * A null entry is a page that does not match one of the four demos.
 * Retail, wholesale, and the UAE page are solutions without one matching business.
 * Hardware is the product catalogue, not a business demo.
 * Arabic pages resolve through `translationOf`.
 *
 * Food-service pages share the restaurant demo (counter, kitchen, modifiers, delivery).
 * Grocery is the supermarket demo. Fashion and electronics map to their own demos.
 */
export const SOLUTION_DEMO = {
  "restaurant-pos": "restaurant",
  "cafe-pos": "restaurant",
  "quick-service-pos": "restaurant",
  "grocery-pos": "supermarket",
  "electronics-pos": "electronics",
  "fashion-pos": "fashion",
  "retail-pos": null,
  "wholesale-pos": null,
  "pos-software-uae": null,
  hardware: null,
} as const satisfies Record<string, DemoBusinessCode | null>;

export type SolutionPageId = keyof typeof SOLUTION_DEMO;

export const EXPLORE_DEMO_LABEL = "Explore Live Demo";
export const EXPLORE_DEMO_LABEL_AR = "استكشف العرض المباشر";

/** Shared demo, not the visitor's own store. */
export const EXPLORE_DEMO_NOTE = "See how AxizPOS works for your business. Explore our interactive business demo.";
export const EXPLORE_DEMO_NOTE_AR = "شاهد كيف يعمل AxizPOS لنشاطك. استكشف العرض التوضيحي التفاعلي.";

export function solutionDemoCode(page: Pick<SeoPage, "id" | "translationOf">): DemoBusinessCode | null {
  const id = page.translationOf ?? page.id;
  if (!Object.prototype.hasOwnProperty.call(SOLUTION_DEMO, id)) return null;
  const code = SOLUTION_DEMO[id as SolutionPageId];
  if (code === null) return null;
  return isDemoBusinessCode(code) ? code : null;
}

/** Portal `/demo/{code}` with an empty query and no credentials. Invalid codes do not produce a URL. */
export function solutionDemoHref(portalLoginUrl: string, code: string): string | null {
  if (!isDemoBusinessCode(code)) return null;
  const href = portalDemoEntry(portalLoginUrl, code);
  const url = new URL(href);
  if (url.username !== "" || url.password !== "" || url.search !== "" || url.hash !== "") return null;
  if (url.pathname.replace(/\/+$/, "") !== `/demo/${code}`) return null;
  return url.toString();
}
