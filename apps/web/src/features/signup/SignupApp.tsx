import { SIGNUP_EMBED_MESSAGE, isSignupEmbedSearch, type SignupState } from "@ai-pos/shared-types";
import { BrandLogo, useLocale } from "@ai-pos/ui";
import { motion, useReducedMotion } from "framer-motion";
import { Check } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useState, type ReactNode } from "react";
import { env } from "../../config/env";
import { ApiRequestError } from "../../lib/api";
import { portalSignInPath } from "../../lib/portal-home";
import { AccountStep, VerifyStep } from "./AccountStep";
import { BusinessStep, WaitlistStep } from "./BusinessStep";
import { ProvisioningStep } from "./ProvisioningStep";
import { StoreStep } from "./StoreStep";
import { readSignupSession, saveSignupSession, signupApi, type SignupSession } from "./signupApi";

type Step = "loading" | "account" | "verify" | "business" | "waitlist" | "store" | "provisioning";

function trackSignup(name: "signup_step_1_complete" | "signup_complete") {
  const target = window as Window & { dataLayer?: unknown[] };
  target.dataLayer = target.dataLayer ?? [];
  target.dataLayer.push({ event: name });
}

const PROGRESS: { key: string; label: string; steps: Step[] }[] = [
  { key: "account", label: "Your account", steps: ["account", "verify"] },
  { key: "business", label: "Business type", steps: ["business", "waitlist"] },
  { key: "store", label: "Your store", steps: ["store"] },
  { key: "setup", label: "Setting up", steps: ["provisioning"] },
];

function WizardPane({ active, children }: { active: boolean; children: ReactNode }) {
  const reduced = useReducedMotion() === true;
  return (
    <motion.div
      className={active ? "flex min-h-0 flex-auto flex-col overflow-hidden" : "hidden"}
      initial={false}
      animate={{ opacity: active ? 1 : 0, y: active ? 0 : 8 }}
      transition={{ duration: reduced ? 0 : 0.22, ease: [0.4, 0, 0.2, 1] }}
    >
      {children}
    </motion.div>
  );
}

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
  const embed = isSignupEmbedSearch(window.location.search);
  const { t } = useLocale();
  const [session, setSession] = useState<SignupSession | null>(() => readSignupSession());
  const [country, setCountry] = useState("AE");
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

  const forget = useCallback(() => {
    trackSignup("signup_complete");
    saveSignupSession(null);
  }, []);

  const advance = (next: SignupState) => {
    setState(next);
    setStep(stepFor(next));
  };

  const activeIndex = PROGRESS.findIndex((item) => item.steps.includes(step));

  useLayoutEffect(() => {
    if (embed) return undefined;
    document.documentElement.classList.add("signup-open");
    return () => document.documentElement.classList.remove("signup-open");
  }, [embed]);

  useLayoutEffect(() => {
    if (!embed) return undefined;
    document.documentElement.classList.add("signup-embed");
    const post = () => {
      const height = Math.ceil(document.documentElement.scrollHeight);
      window.parent.postMessage({ type: SIGNUP_EMBED_MESSAGE, height }, "*");
    };
    post();
    const observer = new ResizeObserver(post);
    observer.observe(document.body);
    return () => {
      observer.disconnect();
      document.documentElement.classList.remove("signup-embed");
    };
  }, [embed, step]);

  const wizard = (
    <>
      {step === "loading" ? <p className="text-sm text-charcoal/60">{t("Loading…")}</p> : null}
      <WizardPane active={step === "account"}>
        <AccountStep
          embedded={embed}
          country={country}
          onCountryChange={setCountry}
          onStarted={(next) => {
            trackSignup("signup_step_1_complete");
            saveSignupSession(next);
            setSession(next);
            setStep("verify");
          }}
          onResumed={(next, current) => {
            saveSignupSession(next);
            setSession(next);
            setState(current);
            setStep(stepFor(current));
          }}
        />
      </WizardPane>
      {session ? (
        <WizardPane active={step === "verify"}>
          <VerifyStep
            session={session}
            onResent={(next) => {
              saveSignupSession(next);
              setSession(next);
            }}
            onVerified={advance}
            onRestart={restart}
          />
        </WizardPane>
      ) : null}
      {session ? (
        <WizardPane active={step === "business"}>
          <BusinessStep
            session={session}
            initialProfile={state?.profile ?? null}
            initialSubType={state?.sub_type ?? null}
            onChosen={advance}
          />
        </WizardPane>
      ) : null}
      {step === "waitlist" && session && state ? (
        <WizardPane active>
          <WaitlistStep state={state} onBack={() => setStep("business")} />
        </WizardPane>
      ) : null}
      {session ? (
        <WizardPane active={step === "store"}>
          <StoreStep
            session={session}
            profile={state?.profile ?? null}
            subType={state?.sub_type ?? null}
            country={country}
            onBack={() => setStep("business")}
            onSubmitted={advance}
          />
        </WizardPane>
      ) : null}
      {step === "provisioning" && session && state ? (
        <WizardPane active>
          <ProvisioningStep session={session} initial={state} onFinished={forget} />
        </WizardPane>
      ) : null}
    </>
  );

  if (embed) {
    return (
      <div className="bg-white p-1 font-sans text-charcoal">
        <ol className="mb-6 flex flex-wrap gap-x-4 gap-y-2" aria-label={t("Signup progress")}>
          {PROGRESS.map((item, index) => {
            const done = activeIndex > index;
            const active = activeIndex === index;
            return (
              <li key={item.key} className="flex items-center gap-2 text-sm" aria-current={active ? "step" : undefined}>
                <span
                  className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold ${
                    done ? "bg-accent text-white" : active ? "bg-charcoal text-white" : "bg-surface text-charcoal/50"
                  }`}
                >
                  {done ? <Check size={12} aria-hidden="true" /> : index + 1}
                </span>
                <span className={active ? "font-semibold text-charcoal" : "text-charcoal/60"}>{t(item.label)}</span>
              </li>
            );
          })}
        </ol>
        {wizard}
      </div>
    );
  }

  return (
    <div className="signup-screen flex items-center justify-center bg-canvas font-sans text-charcoal">
      <div className="signup-modal flex flex-col rounded-3xl border border-line bg-white md:flex-row">
        <aside className="signup-side hidden shrink-0 flex-col justify-between bg-charcoal px-5 py-5 text-white min-[900px]:flex">
          <div>
            <BrandLogo tone="dark" className="h-8 w-auto" />
            <h1 className="mt-5 text-xl font-semibold leading-tight">{t("Open your store")}</h1>
            <p className="signup-intro mt-2 text-sm leading-5 text-white/60">
              {t("About two minutes. Practise with sample items before you go live. New stores start on the Standard trial.")}
            </p>
          </div>
          <ol className="mt-6 space-y-3" aria-label={t("Signup progress")}>
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
                    {t(item.label)}
                  </span>
                </li>
              );
            })}
          </ol>
          <p className="mt-6 text-xs text-white/50">
            {t("Already have an account?")}{" "}
            <a href={portalSignInPath()} className="font-semibold text-white hover:underline">
              {t("Log in")}
            </a>
            {env.storesShareThisHost ? null : (
              <span className="signup-host mt-1 block text-white/70">
                {t("Or open your store, for example yourstore.{domain}.", { domain: env.tenantBaseDomain() })}
              </span>
            )}
          </p>
        </aside>
        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          <ol
            className="flex gap-3 overflow-x-auto border-b border-line px-4 py-3 pt-[max(0.75rem,env(safe-area-inset-top))] min-[900px]:hidden"
            aria-label={t("Signup progress")}
          >
            {PROGRESS.map((item, index) => {
              const done = activeIndex > index;
              const active = activeIndex === index;
              return (
                <li key={item.key} className="flex shrink-0 items-center gap-2 text-xs" aria-current={active ? "step" : undefined}>
                  <span
                    className={`flex h-6 w-6 items-center justify-center rounded-full text-[11px] font-semibold ${
                      done ? "bg-accent text-white" : active ? "bg-charcoal text-white" : "bg-surface text-charcoal/50"
                    }`}
                  >
                    {done ? <Check size={12} aria-hidden="true" /> : index + 1}
                  </span>
                  <span className={active ? "font-semibold text-charcoal" : "text-charcoal/60"}>{t(item.label)}</span>
                </li>
              );
            })}
          </ol>
          <main className="signup-main flex min-h-0 flex-auto flex-col overflow-hidden px-4 py-3 sm:px-5 sm:py-4">{wizard}</main>
        </div>
      </div>
    </div>
  );
}
