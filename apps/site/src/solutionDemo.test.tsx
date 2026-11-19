import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { EMPTY_CATALOG } from "./catalog";
import { ExploreDemoButton } from "./components/ExploreDemoButton";
import { GET_STARTED_LABEL, GET_STARTED_NOTE } from "./components/GetStartedLink";
import { portalUrl, signupUrl } from "./env";
import { IndustryPage } from "./pages/IndustryPage";
import { SEO_PAGES, pageByPath } from "./seo";
import {
  EXPLORE_DEMO_LABEL,
  EXPLORE_DEMO_LABEL_AR,
  EXPLORE_DEMO_NOTE,
  SOLUTION_DEMO,
  solutionDemoCode,
  solutionDemoHref,
  type SolutionPageId,
} from "./solutionDemo";

const here = dirname(fileURLToPath(import.meta.url));

function pageHtml(path: string): string {
  const page = pageByPath(path);
  if (page === undefined) throw new Error(`missing ${path}`);
  return renderToStaticMarkup(<IndustryPage page={page} catalog={EMPTY_CATALOG} />);
}

function demoHref(html: string): string | null {
  const match = html.match(/href="(https?:\/\/[^"]+\/demo\/[a-z]+)"/);
  return match?.[1] ?? null;
}

const MAPPED: Record<string, "restaurant" | "supermarket" | "electronics" | "fashion"> = {
  "/restaurant-pos": "restaurant",
  "/cafe-pos": "restaurant",
  "/quick-service-pos": "restaurant",
  "/grocery-pos": "supermarket",
  "/electronics-pos": "electronics",
  "/fashion-pos": "fashion",
};

const UNMAPPED = ["/retail-pos", "/wholesale-pos", "/pos-software-uae", "/hardware"];

describe("solution demo mapping", () => {
  it("classifies every English solutions page and no other industry page", () => {
    const industry = SEO_PAGES.filter((page) => page.kind === "industry" && page.locale !== "ar" && page.id !== "explore").map(
      (page) => page.id,
    );
    expect(industry.sort()).toEqual(Object.keys(SOLUTION_DEMO).sort());
  });

  it("maps café to restaurant, grocery to supermarket, and the other demos to themselves", () => {
    expect(solutionDemoCode(pageByPath("/cafe-pos")!)).toBe("restaurant");
    expect(solutionDemoCode(pageByPath("/grocery-pos")!)).toBe("supermarket");
    expect(solutionDemoCode(pageByPath("/electronics-pos")!)).toBe("electronics");
    expect(solutionDemoCode(pageByPath("/fashion-pos")!)).toBe("fashion");
    expect(solutionDemoCode(pageByPath("/restaurant-pos")!)).toBe("restaurant");
    expect(solutionDemoCode(pageByPath("/quick-service-pos")!)).toBe("restaurant");
  });

  it("leaves retail, wholesale, and the UAE page without a demo", () => {
    for (const path of UNMAPPED) expect(solutionDemoCode(pageByPath(path)!)).toBeNull();
  });

  it("uses the same code for each Arabic translation", () => {
    for (const page of SEO_PAGES.filter((item) => item.locale === "ar" && item.kind === "industry")) {
      expect(page.translationOf).toBeTruthy();
      if (!Object.prototype.hasOwnProperty.call(SOLUTION_DEMO, page.translationOf)) continue;
      const code = SOLUTION_DEMO[page.translationOf as SolutionPageId];
      expect(solutionDemoCode(page)).toBe(code);
    }
  });

  it("does not assign a demo to features, guides, explore, or pages that were not created", () => {
    for (const page of SEO_PAGES.filter((item) => item.kind !== "industry")) {
      expect(solutionDemoCode(page)).toBeNull();
    }
    expect(solutionDemoCode(pageByPath("/explore")!)).toBeNull();
    for (const path of ["/bakery-pos", "/cloud-kitchen-pos", "/convenience-store-pos", "/clothing-pos", "/boutique-pos", "/mobile-pos", "/supermarket-pos"]) {
      expect(pageByPath(path)).toBeUndefined();
    }
  });
});

describe("portal destination", () => {
  it("opens /demo/{code} on the portal origin with an empty query and no credentials", () => {
    const portals = ["http://127.0.0.1:5173/login", "http://localhost:5173/login", "https://axizpos.com/login"];
    for (const login of portals) {
      for (const code of ["restaurant", "supermarket", "electronics", "fashion", "pharmacy"] as const) {
        const href = solutionDemoHref(login, code);
        expect(href).toBe(`${new URL(login).origin}/demo/${code}`);
        const url = new URL(href!);
        expect(url.search).toBe("");
        expect(url.hash).toBe("");
        expect(url.username).toBe("");
        expect(url.password).toBe("");
        expect(href).not.toMatch(/access_token|refresh_token|password|tenant_id|authorization/i);
      }
    }
  });

  it("drops a query that was attached to the portal login address", () => {
    const href = solutionDemoHref("https://axizpos.com/login?access_token=secret&tenant_id=1", "supermarket");
    expect(href).toBe("https://axizpos.com/demo/supermarket");
    expect(new URL(href!).search).toBe("");
  });

  it("rejects a code that is not one of the public demos", () => {
    expect(solutionDemoHref(portalUrl, "wholesale")).toBeNull();
    expect(solutionDemoHref(portalUrl, "restaurant?access_token=secret")).toBeNull();
    expect(solutionDemoHref(portalUrl, "")).toBeNull();
    expect(renderToStaticMarkup(<ExploreDemoButton businessCode={"wholesale" as "restaurant"} />)).toBe("");
  });
});

describe("solutions page call to action", () => {
  it("renders Explore Live Demo on every mapped page and keeps Get Started and See pricing", () => {
    for (const [path, code] of Object.entries(MAPPED)) {
      const html = pageHtml(path);
      const href = demoHref(html);
      expect(href).toBe(solutionDemoHref(portalUrl, code));
      expect(new URL(href!).search).toBe("");
      expect(html).toContain(EXPLORE_DEMO_LABEL);
      expect(html).toContain(EXPLORE_DEMO_NOTE);
      expect(html).toContain(GET_STARTED_LABEL);
      expect(html).toContain(GET_STARTED_NOTE);
      expect(html).toContain(`href="${signupUrl}"`);
      expect(html).toContain('href="/#pricing"');
      expect(html).toContain("See pricing");
      expect(html).toContain("bg-primary");
      expect(html).toContain("flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center");
      expect(html).toContain("w-full");
      expect(html).toContain("sm:w-auto");
      expect(html.match(/data-explore-demo="/g)).toHaveLength(1);
    }
  });

  it("renders the Arabic label on the Arabic solutions pages", () => {
    for (const [path, code] of Object.entries(MAPPED)) {
      const html = pageHtml(`/ar${path}`);
      expect(demoHref(html)).toBe(solutionDemoHref(portalUrl, code));
      expect(html).toContain(EXPLORE_DEMO_LABEL_AR);
      expect(html).toContain('href="/#pricing"');
      expect(html).toContain("الأسعار");
      expect(html).toContain(`href="${signupUrl}"`);
    }
  });

  it("does not add a demo button on solutions that have no matching demo", () => {
    const paths = UNMAPPED.flatMap((path) => (pageByPath(`/ar${path}`) ? [path, `/ar${path}`] : [path]));
    for (const path of paths) {
      const html = pageHtml(path);
      expect(demoHref(html)).toBeNull();
      expect(html).not.toContain(EXPLORE_DEMO_LABEL);
      expect(html).not.toContain(EXPLORE_DEMO_LABEL_AR);
      expect(html).not.toContain("/demo/");
      expect(html).toContain(`href="${signupUrl}"`);
      expect(html).toContain('href="/#pricing"');
    }
  });

  it("keeps the café example on the restaurant demo", () => {
    const html = pageHtml("/cafe-pos");
    expect(html).toContain("Café POS system for the counter, modifiers, and tabs in the UAE");
    expect(demoHref(html)).toBe(solutionDemoHref(portalUrl, "restaurant"));
    expect(html).toContain("interactive business demo");
    expect(html).not.toMatch(/production environment/i);
  });

  it("styles the button with the brand orange and wraps it on a narrow screen", () => {
    const html = renderToStaticMarkup(<ExploreDemoButton businessCode="electronics" className="extra-class" />);
    expect(html).toContain("bg-primary");
    expect(html).toContain("text-white");
    expect(html).toContain("w-full");
    expect(html).toContain("sm:w-auto");
    expect(html).toContain("extra-class");
    expect(html).toContain(EXPLORE_DEMO_LABEL);
    const outline = renderToStaticMarkup(<ExploreDemoButton businessCode="fashion" variant="outline" label="Preview" />);
    expect(outline).toContain("border-primary");
    expect(outline).toContain("text-primary");
    expect(outline).toContain(">Preview<");
    expect(outline).not.toContain("bg-primary ");
  });
});

describe("demo availability stays on the portal route", () => {
  it("does not exchange a session, enroll a store, or download an installer", () => {
    const source = ["components/ExploreDemoButton.tsx", "solutionDemo.ts", "pages/IndustryPage.tsx"]
      .map((file) => readFileSync(join(here, file), "utf8"))
      .join("\n");
    expect(source).not.toContain("exchangeDemo");
    expect(source).not.toContain("enrollment");
    expect(source).not.toContain("installer");
    expect(source).not.toContain("access_token");
    expect(source).not.toContain("preventDefault");
    expect(source).toContain("solutionDemoHref");
    expect(source).toContain("portalUrl");
    expect(source).not.toContain("friendlyDemoError");
  });
});
