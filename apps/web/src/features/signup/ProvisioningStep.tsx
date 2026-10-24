import type { ProvisionStep, SignupState } from "@ai-pos/shared-types";
import { Check, Circle, Loader2, X } from "lucide-react";
import { useEffect, useState } from "react";
import { ErrorNote } from "../../components/ui/Field";
import { saveStoreCode } from "../../config/env";
import { ApiRequestError } from "../../lib/api";
import { signupApi, type SignupSession } from "./signupApi";

const POLL_MS = 1000;

function StepIcon({ state }: { state: ProvisionStep["state"] }) {
  if (state === "done") {
    return (
      <span className="flex h-7 w-7 items-center justify-center rounded-full bg-emerald-600 text-white">
        <Check size={14} aria-hidden="true" />
      </span>
    );
  }
  if (state === "running") {
    return (
      <span className="flex h-7 w-7 items-center justify-center rounded-full bg-accent/10 text-accent">
        <Loader2 size={15} className="animate-spin" aria-hidden="true" />
      </span>
    );
  }
  if (state === "failed") {
    return (
      <span className="flex h-7 w-7 items-center justify-center rounded-full bg-accent text-white">
        <X size={14} aria-hidden="true" />
      </span>
    );
  }
  return (
    <span className="flex h-7 w-7 items-center justify-center rounded-full text-charcoal/25">
      <Circle size={16} aria-hidden="true" />
    </span>
  );
}

/** Polls the job and renders its real steps; when the store is ready, hands the owner over signed in. */
export function ProvisioningStep({
  session,
  initial,
  onFinished,
}: {
  session: SignupSession;
  initial: SignupState;
  onFinished: () => void;
}) {
  const [state, setState] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);

  const active = state.status === "PROVISIONING";

  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => {
      signupApi
        .status(session)
        .then(setState)
        .catch(() => undefined);
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [active, session]);

  useEffect(() => {
    if (state.status !== "READY" || state.slug === null) return;
    onFinished();
    if (state.handoff_token === null) return;
    const slug = state.slug;
    const token = state.handoff_token;
    const timer = window.setTimeout(() => {
      saveStoreCode(slug);
      const welcome = new URL("/welcome", window.location.origin);
      welcome.searchParams.set("handoff", token);
      window.location.assign(welcome.toString());
    }, 900);
    return () => window.clearTimeout(timer);
  }, [state.status, state.handoff_token, state.slug, onFinished]);

  const retry = async () => {
    setRetrying(true);
    setError(null);
    try {
      setState(await signupApi.retry(session));
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Could not retry.");
    } finally {
      setRetrying(false);
    }
  };

  const done = state.steps.filter((step) => step.state === "done").length;
  const percent = state.steps.length ? Math.round((done / state.steps.length) * 100) : 0;

  return (
    <div className="mx-auto max-w-md">
      <h2 className="text-2xl font-semibold">
        {state.status === "READY"
          ? "Your store is ready"
          : state.status === "FAILED"
            ? "Setup stopped"
            : `Setting up ${state.store_name ?? "your store"}`}
      </h2>
      <p className="mt-1 text-sm text-charcoal/60">
        {state.status === "READY"
          ? "Opening your dashboard…"
          : state.status === "FAILED"
            ? "Nothing is lost. Try again; finished steps are skipped."
            : "This takes under a minute."}
      </p>
      <div className="mt-6 h-1.5 overflow-hidden rounded-full bg-surface" aria-hidden="true">
        <div className="h-full rounded-full bg-accent transition-all duration-500" style={{ width: `${percent}%` }} />
      </div>
      <ol className="mt-6 space-y-3" aria-live="polite">
        {state.steps.map((step) => (
          <li key={step.key} className="flex items-center gap-3 text-sm">
            <StepIcon state={step.state} />
            <span
              className={
                step.state === "pending" ? "text-charcoal/40" : step.state === "failed" ? "text-accent" : "text-charcoal"
              }
            >
              {step.label}
            </span>
          </li>
        ))}
      </ol>
      {state.status === "FAILED" ? (
        <>
          <ErrorNote message={state.error ?? "Setup failed."} />
          <ErrorNote message={error} />
          <button
            type="button"
            onClick={() => void retry()}
            disabled={retrying}
            className="mt-6 h-12 w-full rounded-2xl bg-accent font-semibold text-white disabled:opacity-40"
          >
            {retrying ? "Retrying…" : "Try again"}
          </button>
        </>
      ) : null}
      {state.status === "READY" && state.slug ? (
        <div className="mt-8 rounded-2xl bg-surface p-4 text-sm">
          <p>
            Your dashboard is on <strong>{window.location.host}</strong>. Sign in there with store code{" "}
            <strong>{state.slug}</strong> as <strong>{state.owner_username}</strong> and the password you chose.
          </p>
          {state.handoff_token === null ? (
            <a
              href={window.location.origin}
              className="mt-4 inline-flex h-11 items-center rounded-2xl bg-accent px-6 font-semibold text-white"
            >
              Open my dashboard
            </a>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
