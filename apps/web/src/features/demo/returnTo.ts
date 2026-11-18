/** Where Exit Demo and a finished demo session send the visitor. The address never carries a token. */

export function marketingExploreUrl(): string {
  const configured = import.meta.env.VITE_MARKETING_URL;
  if (typeof configured === "string" && configured.trim() !== "") {
    const base = configured.trim().replace(/\/$/, "");
    return base.endsWith("/explore") ? base : `${base}/explore`;
  }
  if (typeof window !== "undefined") {
    const host = window.location.hostname.toLowerCase();
    if (host === "axizpos.com" || host === "www.axizpos.com") return `${window.location.origin}/explore`;
    if (host === "localhost" || host === "127.0.0.1") return `${window.location.protocol}//${host}:5175/explore`;
  }
  return "https://axizpos.com/explore";
}

export function exploreReturnUrl(notice?: "ended"): string {
  const url = new URL(marketingExploreUrl());
  url.search = "";
  url.hash = "";
  if (notice === "ended") url.searchParams.set("notice", "ended");
  return url.toString();
}

let pendingDemoExit: string | null = null;

/** Remembered until the signed-out screen is reached, so the login redirect cannot replace it. */
export function rememberDemoExit(url: string): void {
  pendingDemoExit = url;
}

export function consumeDemoExit(): string | null {
  const url = pendingDemoExit;
  pendingDemoExit = null;
  return url;
}
