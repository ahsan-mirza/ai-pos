import {
  DemoOpenError,
  demoBusiness,
  demoCodeFromPath,
  exchangeDemo,
  friendlyDemoError,
  type DemoBusinessCode,
  type TokenResponse,
} from "@ai-pos/shared-types";
import { useEffect, useState } from "react";
import { env } from "../../config/env";
import { useAuth } from "../../lib/auth";
import { portalHomePath } from "../../lib/portal-home";
import { exploreReturnUrl } from "./returnTo";

const inflight = new Map<DemoBusinessCode, Promise<TokenResponse>>();

function exchangeOnce(code: DemoBusinessCode): Promise<TokenResponse> {
  const existing = inflight.get(code);
  if (existing) return existing;
  const pending = exchangeDemo(env.apiBaseUrl, code, fetch).finally(() => inflight.delete(code));
  inflight.set(code, pending);
  return pending;
}

function rememberEntry(code: string): void {
  const target = window as Window & { dataLayer?: unknown[] };
  target.dataLayer = target.dataLayer ?? [];
  target.dataLayer.push({ event: "demo_entered", business_code: code });
}

/** Opens one shared demo inside this portal. The address carries the public business code and nothing else. */
export function DemoEntry() {
  const { status, demo, enterDemo } = useAuth();
  const code = demoCodeFromPath(window.location.pathname);
  const business = code === null ? null : demoBusiness(code);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (status === "checking" || code === null || business === null) return;
    if (status === "signed-in" && demo?.businessCode === code) {
      window.location.replace(portalHomePath());
      return;
    }
    let cancelled = false;
    exchangeOnce(code)
      .then((result) => {
        if (cancelled) return;
        enterDemo(result);
        rememberEntry(code);
        window.location.replace(portalHomePath());
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        const statusCode = error instanceof DemoOpenError ? error.status : 500;
        setMessage(friendlyDemoError(statusCode, business.short));
      });
    return () => {
      cancelled = true;
    };
  }, [status, code, business, demo, enterDemo]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-canvas px-6 py-16 text-center text-charcoal">
      <div className="max-w-md">
        <p className="text-sm font-semibold text-accent">{message === null ? "Opening demo" : "Demo unavailable"}</p>
        <h1 className="mt-2 text-2xl font-semibold">
          {business === null ? "Choose a demo from the AxizPOS website" : `AxizPOS ${business.title}`}
        </h1>
        <p className="mt-3 text-sm text-charcoal/70" role={message === null ? undefined : "alert"}>
          {message ??
            (business === null
              ? "This address is not one of the four shared demos."
              : "This is a shared demonstration. Other visitors can see the same sales, tables, and stock, and the data is reset from time to time.")}
        </p>
        <a className="mt-6 inline-flex rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-white" href={exploreReturnUrl()}>
          Back to Explore AxizPOS
        </a>
      </div>
    </main>
  );
}
