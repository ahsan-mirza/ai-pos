import { useEffect, useState } from "react";
import { ApiRequestError } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { portalHomePath, portalSignInPath } from "../../lib/portal-home";

/** Opened from signup on the new store's address; asks the checklist to start open. */
export const CHECKLIST_OPEN_KEY = "ai-pos.checklist-open";

// The token is single use, so a remount (React strict mode) must not redeem it twice.
const redeemed = new Map<string, Promise<void>>();

export function isWelcomeHandoff(): boolean {
  return window.location.pathname === "/welcome" && new URLSearchParams(window.location.search).has("handoff");
}

export function WelcomeHandoff({ onDone }: { onDone: () => void }) {
  const { handoff } = useAuth();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get("handoff") ?? "";
    let pending = redeemed.get(token);
    if (pending === undefined) {
      pending = handoff(token);
      redeemed.set(token, pending);
    }
    pending
      .then(() => {
        sessionStorage.setItem(CHECKLIST_OPEN_KEY, "1");
        window.history.replaceState(null, "", portalHomePath());
        onDone();
      })
      .catch((caught: unknown) => {
        setError(caught instanceof ApiRequestError ? caught.message : "Could not sign you in.");
      });
  }, [handoff, onDone]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-canvas p-4 text-charcoal">
      <div className="w-full max-w-sm rounded-[28px] border border-line bg-white p-8 text-center">
        {error === null ? (
          <>
            <h1 className="text-xl font-semibold">Welcome to your store</h1>
            <p className="mt-2 text-sm text-charcoal/60">Signing you in…</p>
          </>
        ) : (
          <>
            <h1 className="text-xl font-semibold">Sign in to continue</h1>
            <p className="mt-2 text-sm text-charcoal/60">{error}</p>
            <a
              href={portalSignInPath()}
              className="mt-6 inline-flex h-11 items-center rounded-2xl bg-accent px-6 font-semibold text-white"
            >
              Go to sign-in
            </a>
          </>
        )}
      </div>
    </div>
  );
}
