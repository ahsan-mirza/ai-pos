import type { SignupState } from "@ai-pos/shared-types";
import { Check } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { env } from "../../config/env";
import { ApiRequestError } from "../../lib/api";
import { AccountStep, VerifyStep } from "./AccountStep";
import { BusinessStep, WaitlistStep } from "./BusinessStep";
import { ProvisioningStep } from "./ProvisioningStep";
import { StoreStep } from "./StoreStep";
import { readSignupSession, saveSignupSession, signupApi, type SignupSession } from "./signupApi";

type Step = "loading" | "account" | "verify" | "business" | "waitlist" | "store" | "provisioning";

const PROGRESS: { key: string; label: string; steps: Step[] }[] = [
  { key: "account", label: "Your account", steps: ["account", "verify"] },
  { key: "business", label: "Business type", steps: ["business", "waitlist"] },
  { key: "store", label: "Your store", steps: ["store"] },
  { key: "setup", label: "Setting up", steps: ["provisioning"] },
];

function stepFor(state: SignupState): Step {
  switch (state.status) {
    case "PENDING_OTP":
      return "verify";
    case "WAITLIST":
      return "waitlist";
    case "VERIFIED":
      return state.sub_type ? "store" : "business";
    default:
      return "provisioning";
  }
}

/** Public signup on the bare domain: account and code, business type, store, then live provisioning. */
export function SignupApp() {
  const [session, setSession] = useState<SignupSession | null>(() => readSignupSession());
  const [state, setState] = useState<SignupState | null>(null);
  const [step, setStep] = useState<Step>(session ? "loading" : "account");

  const restart = useCallback(() => {
    saveSignupSession(null);
    setSession(null);
    setState(null);
    setStep("account");
  }, []);

  useEffect(() => {
    if (session === null || step !== "loading") return;
    signupApi
      .status(session)
      .then((current) => {
        setState(current);
        setStep(stepFor(current));
      })
      .catch((error: unknown) => {
        if (error instanceof ApiRequestError && error.status === 404) restart();
        else setStep("account");
      });
  }, [session, step, restart]);

  const forget = useCallback(() => saveSignupSession(null), []);

  const advance = (next: SignupState) => {
    setState(next);
    setStep(stepFor(next));
  };

  const activeIndex = PROGRESS.findIndex((item) => item.steps.includes(step));

  return (
    <div className="flex min-h-screen items-center justify-center bg-canvas p-4 font-sans text-charcoal">
      <div className="grid w-full max-w-5xl overflow-hidden rounded-[28px] border border-line bg-white md:grid-cols-[300px_1fr]">
        <aside className="flex flex-col justify-between bg-charcoal p-8 text-white">
          <div>
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-accent text-sm font-bold">ai</div>
            <p className="mt-10 text-xs font-medium uppercase tracking-[0.16em] text-white/50">AI POS</p>
            <h1 className="mt-2 text-2xl font-semibold leading-tight">Open your store</h1>
            <p className="mt-2 text-sm text-white/60">About two minutes. Practise with sample items before you go live.</p>
          </div>
          <ol className="mt-10 space-y-4" aria-label="Signup progress">
            {PROGRESS.map((item, index) => {
              const done = activeIndex > index;
              const active = activeIndex === index;
              return (
                <li key={item.key} className="flex items-center gap-3 text-sm" aria-current={active ? "step" : undefined}>
                  <span
                    className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
                      done ? "bg-accent text-white" : active ? "bg-white text-charcoal" : "bg-white/10 text-white/50"
                    }`}
                  >
                    {done ? <Check size={14} aria-hidden="true" /> : index + 1}
                  </span>
                  <span className={active ? "font-semibold text-white" : done ? "text-white/80" : "text-white/50"}>
                    {item.label}
                  </span>
                </li>
              );
            })}
          </ol>
          <p className="mt-10 text-xs text-white/50">
            Already have a store?{" "}
            <span className="text-white/70">Open its address, for example yourstore.{env.tenantBaseDomain()}.</span>
          </p>
        </aside>
        <main className="min-h-[560px] p-6 sm:p-10">
          {step === "loading" ? <p className="text-sm text-charcoal/60">Loading…</p> : null}
          {step === "account" ? (
            <AccountStep
              onStarted={(next) => {
                saveSignupSession(next);
                setSession(next);
                setStep("verify");
              }}
            />
          ) : null}
          {step === "verify" && session ? (
            <VerifyStep
              session={session}
              onResent={(next) => {
                saveSignupSession(next);
                setSession(next);
              }}
              onVerified={advance}
              onRestart={restart}
            />
          ) : null}
          {step === "business" && session ? <BusinessStep session={session} onChosen={advance} /> : null}
          {step === "waitlist" && session && state ? (
            <WaitlistStep state={state} onBack={() => setStep("business")} />
          ) : null}
          {step === "store" && session ? (
            <StoreStep session={session} onBack={() => setStep("business")} onSubmitted={advance} />
          ) : null}
          {step === "provisioning" && session && state ? (
            <ProvisioningStep session={session} initial={state} onFinished={forget} />
          ) : null}
        </main>
      </div>
    </div>
  );
}
