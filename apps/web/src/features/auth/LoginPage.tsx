import { PASSWORD_MIN_LENGTH, normalizeStoreCode, storeCodeError } from "@ai-pos/shared-types";
import { BrandLogo } from "@ai-pos/ui";
import { PwaChrome } from "../../pwa/PwaChrome";
import { Eye, EyeOff, Lock, Mail, ShieldCheck, Store, User, type LucideIcon } from "lucide-react";
import { useState, type FormEvent, type InputHTMLAttributes, type ReactNode } from "react";
import { env, saveStoreCode } from "../../config/env";
import { ApiRequestError, apiPublicPost } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { DemoAccounts, demoAccountsEnabled } from "./DemoAccounts";

const primaryButtonClass =
  "flex h-12 w-full items-center justify-center rounded-2xl bg-accent text-sm font-semibold text-white transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-40";

const secondaryButtonClass =
  "flex min-h-12 w-full items-center justify-center rounded-2xl border border-line bg-card px-3 py-2 text-center text-sm font-semibold leading-tight text-charcoal transition-colors hover:border-accent hover:text-accent disabled:opacity-40 dark:border-white/15 dark:bg-white/5 dark:text-white dark:hover:border-accent";

const noticeClass = "rounded-2xl bg-emerald-500/10 px-4 py-3 text-sm text-emerald-800 dark:text-emerald-200";
const alertClass = "rounded-2xl bg-danger/10 px-4 py-3 text-sm text-danger";

function LoginField({
  id,
  label,
  icon: Icon,
  type = "text",
  error,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { id: string; label: string; icon: LucideIcon; error?: string }) {
  const [showPassword, setShowPassword] = useState(false);
  const isPassword = type === "password";
  return (
    <label className="text-sm font-medium text-charcoal dark:text-white" htmlFor={id}>
      {label}
      <span className="relative mt-1.5 block">
        <Icon className="pointer-events-none absolute left-3.5 top-1/2 h-5 w-5 -translate-y-1/2 text-charcoal/40 dark:text-white/40" aria-hidden="true" />
        <input
          id={id}
          type={isPassword && showPassword ? "text" : type}
          {...props}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-error` : undefined}
          className={`h-12 w-full rounded-2xl border bg-surface pl-11 text-base text-charcoal transition placeholder:text-charcoal/40 focus:bg-card focus:outline-none focus:ring-2 dark:bg-[#2D2A32] dark:text-white dark:placeholder:text-white/35 dark:focus:bg-[#2D2A32] ${
            error
              ? "border-danger focus:border-danger focus:ring-danger/40"
              : "border-line focus:border-accent focus:ring-accent/35 dark:border-white/10"
          } ${isPassword ? "pr-12" : "pr-4"}`}
        />
        {isPassword ? (
          <button
            type="button"
            aria-label={showPassword ? "Hide password" : "Show password"}
            aria-pressed={showPassword}
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => setShowPassword((value) => !value)}
            className="absolute right-1 top-1/2 flex h-11 w-11 -translate-y-1/2 items-center justify-center rounded-xl text-charcoal/45 hover:text-charcoal dark:text-white/50 dark:hover:text-white"
          >
            {showPassword ? <EyeOff className="h-5 w-5" aria-hidden="true" /> : <Eye className="h-5 w-5" aria-hidden="true" />}
          </button>
        ) : null}
      </span>
      {error ? (
        <span id={`${id}-error`} role="alert" className="mt-1.5 block text-xs font-medium text-danger">
          {error}
        </span>
      ) : null}
    </label>
  );
}

function AuthFrame({ children, footer }: { children: ReactNode; footer?: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col items-center bg-canvas px-4 py-6 font-sans text-charcoal sm:px-6 sm:py-10 dark:bg-[#121215] dark:text-white">
      <div className="my-auto flex w-full max-w-md flex-col gap-4 md:max-w-lg">
        <PwaChrome />
        <section className="rounded-card border border-line bg-card px-5 py-6 shadow-[0_16px_40px_-28px_rgb(34_32_38/0.55)] sm:px-8 sm:py-8 dark:border-white/10 dark:bg-[#1c1b1f] dark:shadow-none">
          <header className="text-center">
            <BrandLogo className="mx-auto h-8" />
            <p className="mt-3 text-sm text-charcoal/60 dark:text-white/60">Manage your business. Smarter.</p>
          </header>
          {children}
        </section>
      </div>
      {footer ? <div className="mt-4 w-full max-w-5xl">{footer}</div> : null}
    </div>
  );
}

type Step = "sign-in" | "email" | "code" | "password" | "stores";
type Recovery = "password" | "store";

interface RecoveredStore {
  code: string;
  name: string;
  branch: string | null;
}

const PASSWORD_STEPS: { id: Exclude<Step, "sign-in" | "stores">; label: string }[] = [
  { id: "email", label: "Email" },
  { id: "code", label: "Code" },
  { id: "password", label: "Password" },
];

const STORE_STEPS: { id: "email" | "code" | "stores"; label: string }[] = [
  { id: "email", label: "Email" },
  { id: "code", label: "Code" },
  { id: "stores", label: "Store codes" },
];

export function LoginPage() {
  const { login } = useAuth();
  const [step, setStep] = useState<Step>("sign-in");
  const [recovery, setRecovery] = useState<Recovery>("password");
  const [stores, setStores] = useState<RecoveredStore[]>([]);
  const [storeCode, setStoreCode] = useState(() =>
    normalizeStoreCode(env.needsStoreCode ? (env.tenantDomain ?? "") : ""),
  );
  const [identity, setIdentity] = useState("");
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [confirm, setConfirm] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<{ store?: string; identity?: string; password?: string; email?: string; confirm?: string }>({});
  const [busy, setBusy] = useState(false);
  const store = normalizeStoreCode(storeCode);
  const storeProblem = env.needsStoreCode ? storeCodeError(store) : undefined;
  const storeReady = storeProblem === undefined;

  const rememberStore = () => {
    if (env.needsStoreCode) saveStoreCode(store);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const next: { store?: string; identity?: string; password?: string } = {};
    if (storeProblem) next.store = storeProblem;
    if (identity.trim() === "") next.identity = "Enter your email or username.";
    if (password === "") next.password = "Enter your password.";
    setFieldError(next);
    if (Object.keys(next).length > 0) return;
    setBusy(true);
    setError(null);
    try {
      rememberStore();
      await login(identity.trim(), password);
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Sign-in failed.");
      setPassword("");
    } finally {
      setBusy(false);
    }
  };

  const requestCode = async () => {
    if (recovery === "password" && !storeReady) {
      setFieldError({ store: "Enter the store code." });
      return;
    }
    if (!email.trim().includes("@")) {
      setFieldError({ email: "Enter the email on the account." });
      return;
    }
    setFieldError({});
    setBusy(true);
    setError(null);
    try {
      if (recovery === "password") rememberStore();
      const path = recovery === "store" ? "/api/v1/auth/recover-store-code" : "/api/v1/auth/forgot-password";
      const result = await apiPublicPost<{ message: string }>(path, { email: email.trim() });
      setNotice(result.message);
      setCode("");
      setStep("code");
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Could not send the code.");
    } finally {
      setBusy(false);
    }
  };

  const verifyCode = async () => {
    setBusy(true);
    setError(null);
    try {
      if (recovery === "password") rememberStore();
      if (recovery === "store") {
        const result = await apiPublicPost<{ message: string; stores: RecoveredStore[] }>(
          "/api/v1/auth/recover-store-code/verify",
          { email: email.trim(), code: code.trim() },
        );
        setStores(result.stores);
        setNotice(result.message);
        const only = result.stores[0];
        if (result.stores.length === 1 && only) setStoreCode(only.code);
        setStep("stores");
      } else {
        await apiPublicPost("/api/v1/auth/verify-reset-code", { email: email.trim(), code: code.trim() });
        setPassword("");
        setConfirm("");
        setNotice(null);
        setStep("password");
      }
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "That code is wrong or has expired.");
    } finally {
      setBusy(false);
    }
  };

  const reset = async () => {
    if (password !== confirm) {
      setFieldError({ confirm: "The two passwords do not match." });
      setError(null);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      rememberStore();
      await apiPublicPost("/api/v1/auth/reset-password", { email: email.trim(), code: code.trim(), password });
      setPassword("");
      setConfirm("");
      setCode("");
      setNotice("Password updated. Sign in with the new password.");
      setStep("sign-in");
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Could not reset the password.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthFrame
      footer={
        demoAccountsEnabled ? (
          <DemoAccounts
            onPick={(pickedUsername, pickedPassword) => {
              setIdentity(pickedUsername);
              setPassword(pickedPassword);
              setError(null);
            }}
          />
        ) : null
      }
    >
      {step === "sign-in" ? (
        <form className="mt-6 flex flex-col gap-4" onSubmit={(event) => void submit(event)}>
          <div>
            <h1 className="text-xl font-semibold text-charcoal dark:text-white">Welcome back</h1>
            <p className="mt-1 text-sm text-charcoal/60 dark:text-white/60">Sign in to your AxizPOS store.</p>
          </div>
          {env.needsStoreCode ? (
            <LoginField
              id="store-code"
              label="Store code"
              icon={Store}
              autoComplete="off"
              spellCheck={false}
              value={storeCode}
              error={fieldError.store}
              onChange={(event) => setStoreCode(normalizeStoreCode(event.target.value))}
              placeholder="client1"
              required
            />
          ) : null}
          <LoginField
            id="identity"
            label="Email or username"
            icon={User}
            autoComplete="username"
            spellCheck={false}
            value={identity}
            error={fieldError.identity}
            onChange={(event) => setIdentity(event.target.value)}
            placeholder="email or username"
            required
          />
          <LoginField
            id="password"
            label="Password"
            icon={Lock}
            type="password"
            autoComplete="current-password"
            value={password}
            error={fieldError.password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
          {notice ? <p className={noticeClass}>{notice}</p> : null}
          {error ? (
            <p role="alert" className={alertClass}>
              {error}
            </p>
          ) : null}
          <button type="submit" disabled={busy} className={primaryButtonClass}>
            {busy ? "Signing in…" : "Sign In"}
          </button>
          <div className="grid grid-cols-1 gap-2 min-[420px]:grid-cols-2">
            <button
              type="button"
              className={secondaryButtonClass}
              onClick={() => {
                setError(null);
                setNotice(null);
                setFieldError({});
                setRecovery("store");
                setStep("email");
              }}
            >
              Forgot Store Code?
            </button>
            <button
              type="button"
              className={secondaryButtonClass}
              onClick={() => {
                setError(null);
                setNotice(null);
                setFieldError({});
                setRecovery("password");
                setStep("email");
              }}
            >
              Forgot Password?
            </button>
          </div>
          {env.onTenantHost ? null : (
            <div className="border-t border-line pt-4 dark:border-white/10">
              <p className="text-center text-sm text-charcoal/70 dark:text-white/60">New to AxizPOS?</p>
              <a href="/signup" className={`${secondaryButtonClass} mt-3`}>
                Create Your Store
              </a>
            </div>
          )}
        </form>
      ) : (
        <form
          className="mt-6 flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            void (step === "email" ? requestCode() : step === "code" ? verifyCode() : step === "password" ? reset() : undefined);
          }}
        >
          <div>
            <ol className="mb-3 flex flex-wrap gap-x-3 gap-y-1 text-xs font-semibold" aria-label="Recovery steps">
              {(recovery === "store" ? STORE_STEPS : PASSWORD_STEPS).map((item, index) => {
                const active = item.id === step;
                const steps = recovery === "store" ? STORE_STEPS : PASSWORD_STEPS;
                const done = steps.findIndex((entry) => entry.id === step) > index;
                return (
                  <li
                    key={item.id}
                    className={active ? "text-accent" : done ? "text-charcoal dark:text-white" : "text-charcoal/40 dark:text-white/40"}
                    aria-current={active ? "step" : undefined}
                  >
                    {index + 1}. {item.label}
                  </li>
                );
              })}
            </ol>
            <h1 className="text-xl font-semibold text-charcoal dark:text-white">
              {step === "email"
                ? recovery === "store"
                  ? "Find your store code"
                  : "Reset password"
                : step === "code"
                  ? "Enter the code"
                  : step === "stores"
                    ? "Your store codes"
                    : "Choose a new password"}
            </h1>
            <p className="mt-1 text-sm text-charcoal/60 dark:text-white/60">
              {step === "email"
                ? recovery === "store"
                  ? "We email a 6-digit code. Store codes are shown only after that code is accepted."
                  : "We email a 6-digit code to the address on your portal account."
                : step === "code"
                  ? `Enter the 6-digit code sent to ${email.trim()}.`
                  : step === "stores"
                    ? "Use a store code with your email and password. This does not sign you in."
                    : `At least ${PASSWORD_MIN_LENGTH} characters.`}
            </p>
          </div>
          {step === "email" && recovery === "password" && env.needsStoreCode ? (
            <LoginField
              id="reset-store-code"
              label="Store code"
              icon={Store}
              autoComplete="off"
              spellCheck={false}
              value={storeCode}
              onChange={(event) => setStoreCode(normalizeStoreCode(event.target.value))}
              placeholder="client1"
              required
            />
          ) : null}
          {step === "email" ? (
            <LoginField
              id="reset-email"
              label="Email"
              icon={Mail}
              type="email"
              autoComplete="email"
              value={email}
              error={fieldError.email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          ) : null}
          {step === "code" ? (
            <LoginField
              id="reset-code"
              label="Code"
              icon={ShieldCheck}
              inputMode="numeric"
              autoComplete="one-time-code"
              value={code}
              onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
              placeholder="000000"
              maxLength={6}
              required
            />
          ) : null}
          {step === "stores" ? (
            stores.length > 0 ? (
              <ul className="space-y-2" aria-label="Store codes">
                {stores.map((item) => (
                  <li key={`${item.code}-${item.branch ?? ""}`} className="rounded-2xl border border-line px-4 py-3 dark:border-white/10">
                    <p className="font-mono text-base font-semibold">{item.code}</p>
                    <p className="text-sm text-charcoal/70 dark:text-white/70">
                      {item.name}
                      {item.branch ? ` · ${item.branch}` : ""}
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-charcoal/70 dark:text-white/70">No store code is linked to this email.</p>
            )
          ) : null}
          {step === "password" ? (
            <>
              <LoginField
                id="reset-password"
                label="New password"
                icon={Lock}
                type="password"
                autoComplete="new-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                minLength={PASSWORD_MIN_LENGTH}
                required
              />
              <LoginField
                id="reset-confirm"
                label="Confirm password"
                icon={Lock}
                type="password"
                autoComplete="new-password"
                value={confirm}
                error={fieldError.confirm}
                onChange={(event) => setConfirm(event.target.value)}
                minLength={PASSWORD_MIN_LENGTH}
                required
              />
            </>
          ) : null}
          {notice && (step === "code" || step === "stores") ? <p className={noticeClass}>{notice}</p> : null}
          {error ? (
            <p role="alert" className={alertClass}>
              {error}
            </p>
          ) : null}
          {step === "stores" ? (
            <button
              type="button"
              className={primaryButtonClass}
              onClick={() => {
                setNotice(null);
                setError(null);
                setStep("sign-in");
              }}
            >
              Back to sign in
            </button>
          ) : (
            <button
              type="submit"
              disabled={
                busy ||
                (recovery === "password" && !storeReady) ||
                (step === "email" && email.trim() === "") ||
                (step === "code" && code.length !== 6) ||
                (step === "password" && (password.length < PASSWORD_MIN_LENGTH || confirm.length < PASSWORD_MIN_LENGTH))
              }
              className={primaryButtonClass}
            >
              {busy ? "Please wait…" : step === "email" ? "Email me a code" : step === "code" ? "Continue" : "Update password"}
            </button>
          )}
          {step === "code" ? (
            <button
              type="button"
              disabled={busy}
              className="text-center text-sm font-semibold text-accent hover:underline disabled:opacity-40"
              onClick={() => void requestCode()}
            >
              Resend code
            </button>
          ) : null}
          {step === "stores" ? null : (
            <button
              type="button"
              className="text-center text-sm font-semibold text-charcoal/60 hover:underline dark:text-white/60"
              onClick={() => {
                setError(null);
                setStep(step === "password" ? "code" : step === "code" ? "email" : "sign-in");
                if (step === "email") setNotice(null);
              }}
            >
              {step === "password" ? "Back to code" : step === "code" ? "Use a different email" : "Back to sign in"}
            </button>
          )}
        </form>
      )}
    </AuthFrame>
  );
}
