import { SIGNUP_EMBED_MESSAGE, SIGNUP_EMBED_PARAM } from "@ai-pos/shared-types";
import { useEffect, useId, useRef, useState } from "react";
import { signupUrl } from "../env";

function embedSrc(): string {
  const url = new URL(signupUrl);
  url.searchParams.set(SIGNUP_EMBED_PARAM, "1");
  return url.toString();
}

/** The real signup wizard, framed so Step 1 and every later step stay the portal implementation. */
export function SignupEmbed() {
  const src = embedSrc();
  const origin = new URL(src).origin;
  const [height, setHeight] = useState(720);
  const [phase, setPhase] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      if (event.origin !== origin) return;
      const data = event.data as { type?: string; height?: number } | null;
      if (!data || data.type !== SIGNUP_EMBED_MESSAGE) return;
      if (typeof data.height !== "number" || data.height < 240 || data.height > 4000) return;
      setHeight(Math.ceil(data.height));
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [origin]);

  return (
    <div>
      {phase === "loading" ? <p className="mb-3 text-sm text-slate-600">Loading the signup form…</p> : null}
      {phase === "error" ? (
        <p className="mb-3 text-sm text-slate-700">
          The signup form didn’t load.{" "}
          <a className="font-semibold text-orange-600" href={signupUrl}>
            Continue on the signup page
          </a>
          .
        </p>
      ) : (
        <iframe
          title="Create your AxizPOS account"
          src={src}
          style={{ height }}
          className="block w-full bg-white"
          scrolling="no"
          onLoad={() => setPhase("ready")}
          onError={() => setPhase("error")}
        />
      )}
    </div>
  );
}

/** Opens the real signup wizard. Unmounting removes the iframe and its application. */
export function SignupDialog({ onClose }: { onClose: () => void }) {
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);
  const arabic = document.documentElement.lang === "ar";

  useEffect(() => {
    closeRef.current?.focus();
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 grid place-items-end overflow-y-auto bg-slate-950/50 p-4 sm:place-items-center" onClick={onClose} role="presentation">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={(event) => event.stopPropagation()}
        className="relative max-h-[calc(100dvh-2rem)] w-full max-w-3xl overflow-y-auto rounded-3xl border border-slate-100 bg-white p-6 text-slate-900 shadow-2xl sm:p-8"
      >
        <button
          ref={closeRef}
          type="button"
          onClick={onClose}
          className="absolute right-4 top-4 inline-flex h-9 w-9 items-center justify-center rounded-full text-sm font-semibold text-slate-500 hover:bg-slate-100 hover:text-slate-900"
        >
          <span className="sr-only">Close</span>
          <span aria-hidden="true">×</span>
        </button>
        <h2 id={titleId} className="pr-10 text-2xl font-bold tracking-tight text-slate-900">
          {arabic ? "ابدأ مع AxizPOS" : "Get Started with AxizPOS"}
        </h2>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          {arabic ? "أنشئ الحساب وجهّز المتجر من الخطوات نفسها." : "Create your AxizPOS account and set up your business in a few simple steps."}
        </p>
        <div className="mt-6">
          <SignupEmbed />
        </div>
        <p className="mt-4 text-sm text-slate-600">
          <a className="font-semibold text-orange-600" href={signupUrl}>
            {arabic ? "افتح صفحة التسجيل" : "Open the signup page"}
          </a>
        </p>
      </div>
    </div>
  );
}
