import { readFileSync } from "node:fs";
import { join } from "node:path";
import {
  DEMO_BUSINESSES,
  DemoOpenError,
  claimDemoClick,
  demoExchangeBody,
  demoMarkerFrom,
  exchangeDemo,
  friendlyDemoError,
  planDemoOpen,
  portalDemoEntry,
  visibleDemo,
} from "@ai-pos/shared-types";
import { describe, expect, it, vi } from "vitest";
import { signedOutLocation } from "./entry";
import { exploreReturnUrl } from "../features/demo/returnTo";

function token(demo: boolean): string {
  const payload = btoa(JSON.stringify(demo ? { demo: true, tid: "server-chosen" } : { sub: "customer" }));
  return `header.${payload}.signature`;
}

const issued = {
  access_token: token(true),
  token_type: "bearer",
  scope: "portal",
  expires_in: 900,
  demo: true,
  business_code: "restaurant",
  business_name: "Harbor & Rye",
  user: { id: "explorer" },
};

describe("demo entry", () => {
  it("renders the four public business codes and no tenant id", () => {
    expect(DEMO_BUSINESSES.map((business) => business.code)).toEqual(["restaurant", "supermarket", "electronics", "fashion"]);
    for (const business of DEMO_BUSINESSES) {
      expect(demoExchangeBody(business.code)).toEqual({ business_code: business.code });
      expect(Object.keys(demoExchangeBody(business.code))).toEqual(["business_code"]);
    }
  });

  it("ignores a second click while one demo is opening", () => {
    expect(claimDemoClick(null, "restaurant")).toBe("restaurant");
    expect(claimDemoClick("restaurant", "fashion")).toBeNull();
  });

  it("sends the selected code and keeps the token out of the address", async () => {
    const fetchImpl = vi.fn(async (_url: string, init?: RequestInit) => {
      expect(JSON.parse(String(init?.body))).toEqual({ business_code: "electronics" });
      expect(String(init?.body)).not.toContain("tenant_id");
      return new Response(JSON.stringify({ ...issued, business_code: "electronics", business_name: "Axis Electronics" }), { status: 200 });
    });
    const result = await exchangeDemo("http://127.0.0.1:8000", "electronics", fetchImpl as unknown as typeof fetch);
    expect(result.business_name).toBe("Axis Electronics");
    const entry = portalDemoEntry("http://127.0.0.1:5173/login", "electronics");
    expect(entry).toBe("http://127.0.0.1:5173/demo/electronics");
    expect(entry).not.toContain("access_token");
    expect(entry).not.toContain(result.access_token);
  });

  it("describes a closed demo, a rate limit, a network failure, and a server error", async () => {
    expect(friendlyDemoError(404, "Restaurant")).toBe("Restaurant demo is temporarily unavailable. Please try again shortly.");
    expect(friendlyDemoError(429, "Restaurant")).toBe("Too many attempts. Please wait a moment before trying again.");
    expect(friendlyDemoError(0, "Restaurant")).toBe("Unable to connect. Please check your internet connection.");
    expect(friendlyDemoError(500, "Restaurant")).toBe("The demo could not be opened. Please try again shortly.");
    const limited = vi.fn(async () => new Response("{}", { status: 429 }));
    await expect(exchangeDemo("http://127.0.0.1:8000", "restaurant", limited as unknown as typeof fetch)).rejects.toMatchObject({ status: 429 });
    const offline = vi.fn(async () => {
      throw new Error("network");
    });
    await expect(exchangeDemo("http://127.0.0.1:8000", "restaurant", offline as unknown as typeof fetch)).rejects.toBeInstanceOf(DemoOpenError);
  });

  it("opens the portal exchange on another origin and stores a same-origin session without a query", () => {
    const remote = planDemoOpen("http://127.0.0.1:5175", "http://127.0.0.1:5173/login", "fashion");
    expect(remote).toEqual({ kind: "navigate", href: "http://127.0.0.1:5173/demo/fashion" });
    const local = planDemoOpen("http://127.0.0.1:5173", "http://127.0.0.1:5173/login", "fashion");
    expect(local.kind).toBe("exchange");
    if (local.kind === "exchange") {
      expect(local.href).toBe("http://127.0.0.1:5173/");
      expect(local.body).toEqual({ business_code: "fashion" });
      expect(local.href).not.toContain("access_token");
    }
    const production = planDemoOpen("https://axizpos.com", "https://axizpos.com/login", "restaurant");
    expect(production).toMatchObject({ kind: "exchange", href: "https://axizpos.com/dashboard" });
  });

  it("shows the banner for the session business and hides it for a normal sign-in", () => {
    const demo = visibleDemo({ token: token(true), demo: { businessCode: "restaurant", businessName: "Harbor & Rye" } });
    expect(demo?.businessName).toBe("Harbor & Rye");
    expect(visibleDemo({ token: token(false), demo: { businessCode: "restaurant", businessName: "Harbor & Rye" } })).toBeNull();
    expect(visibleDemo({ token: token(false) })).toBeNull();
  });

  it("keeps the demo name across a refresh and drops it for a normal login or a different business", () => {
    const restaurant = { businessCode: "restaurant" as const, businessName: "Harbor & Rye" };
    const refreshed = demoMarkerFrom({ access_token: token(true) }, restaurant);
    expect(refreshed).toEqual(restaurant);
    const switched = demoMarkerFrom(
      { access_token: token(true), demo: true, business_code: "fashion", business_name: "Linen & Co" },
      restaurant,
    );
    expect(switched).toEqual({ businessCode: "fashion", businessName: "Linen & Co" });
    expect(demoMarkerFrom({ access_token: token(false) }, restaurant)).toBeNull();
  });

  it("sends an ended demo back to the explore page without a token", () => {
    expect(exploreReturnUrl("ended")).toMatch(/\/explore\?notice=ended$/);
    expect(exploreReturnUrl()).not.toContain("access_token");
    expect(signedOutLocation("/inventory/stock", "", "127.0.0.1")).toBe("/login?next=%2Finventory%2Fstock");
    expect(signedOutLocation("/demo/supermarket", "", "127.0.0.1")).toBeNull();
  });

  it("does not ship credentials, a tenant id, or a reset control", () => {
    const files = [
      join(process.cwd(), "src", "features", "demo", "DemoEntry.tsx"),
      join(process.cwd(), "src", "features", "demo", "DemoBanner.tsx"),
      join(process.cwd(), "../site/src/pages/ExplorePage.tsx"),
      join(process.cwd(), "../../packages/shared-types/src/demoAccess.ts"),
    ];
    const source = files.map((file) => readFileSync(file, "utf8")).join("\n");
    expect(source).not.toContain("password");
    expect(source).not.toContain("tenant_id");
    expect(source).not.toContain("reset-demo");
    expect(source).not.toContain("set-demo-access");
    expect(source).toContain("grid-cols-1");
    expect(source).toContain("md:grid-cols-2");
    expect(source).toContain("Explore Business Pro");
    expect(source).toContain("Download POS Register");
  });
});
