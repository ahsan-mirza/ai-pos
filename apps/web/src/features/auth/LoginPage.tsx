import { PASSWORD_MIN_LENGTH } from "@ai-pos/shared-types";
import { BrandLogo } from "@ai-pos/ui";
import { Eye, EyeOff, Lock, Mail, ShieldCheck, Store, User, type LucideIcon } from "lucide-react";
import { useState, type FormEvent, type InputHTMLAttributes } from "react";
import { env, saveStoreCode } from "../../config/env";
import { ApiRequestError, apiPublicPost } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { DemoAccounts, demoAccountsEnabled } from "./DemoAccounts";

const STORE_CODE = /^[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?$/;

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
    <label className="text-sm font-medium" htmlFor={id}>
      {label}
      <span className="relative mt-1 block">
        <Icon className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-gray-400" aria-hidden="true" />
        <input
          id={id}
          type={isPassword && showPassword ? "text" : type}
          {...props}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-error` : undefined}
          className={`h-12 w-full rounded-2xl border bg-surface pl-10 text-base transition focus:outline-none focus:ring-2 ${
            error ? "border-danger focus:border-danger focus:ring-danger" : "border-line focus:border-orange-500 focus:ring-orange-500"
          } ${isPassword ? "pr-12" : "pr-4"}`}
        />
        {isPassword ? (
          <button
            type="button"
            tabIndex={-1}
            aria-label={showPassword ? "Hide password" : "Show password"}
            aria-pressed={showPassword}
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => setShowPassword((value) => !value)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
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

type Step = "sign-in" | "email" | "code" | "password";

const RESET_STEPS: { id: Exclude<Step, "sign-in">; label: string }[] = [
  { id: "email", label: "Email" },
  { id: "code", label: "Code" },
  { id: "password", label: "Password" },
];

export function LoginPage() {
  const { login } = useAuth();
  const [step, setStep] = useState<Step>("sign-in");
  const [storeCode, setStoreCode] = useState(() => (env.needsStoreCode ? (env.tenantDomain ?? "") : ""));
  const [identity, setIdentity] = useState("");
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [confirm, setConfirm] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<{ store?: string; identity?: string; password?: string; email?: string; confirm?: string }>({});
  const [busy, setBusy] = useState(false);
  const store = storeCode.trim().toLowerCase();
  const storeReady = !env.needsStoreCode || STORE_CODE.test(store);

  const rememberStore = () => {
    if (env.needsStoreCode) saveStoreCode(store);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const next: { store?: string; identity?: string; password?: string } = {};
    if (!storeReady) next.store = "Enter the store code.";
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
    if (!storeReady) return;
    setBusy(true);
    setError(null);
    try {
      rememberStore();
      const result = await apiPublicPost<{ message: string }>("/api/v1/auth/forgot-password", { email: email.trim() });
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
      rememberStore();
      await apiPublicPost("/api/v1/auth/verify-reset-code", { email: email.trim(), code: code.trim() });
      setPassword("");
      setConfirm("");
      setNotice(null);
      setStep("password");
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
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-canvas p-4 font-sans text-charcoal">
      <div className="grid w-full max-w-5xl overflow-hidden rounded-[28px] border border-line bg-white md:grid-cols-2">
        <section className="flex flex-col justify-between bg-charcoal p-8 text-white">
          <BrandLogo tone="dark" className="h-9 w-auto" />
          <div className="mt-16">
            <h1 className="text-3xl font-semibold leading-tight">Admin portal</h1>
            <p className="mt-3 max-w-xs text-sm text-white/60">
              Manage stores, inventory, repairs, staff, and role permissions.
            </p>
          </div>
          <div className="mt-10 inline-flex w-fit rounded-full bg-white/10 px-3 py-1 text-xs text-white/70">
            Password sign-in for portal users
          </div>
        </section>
        {step === "sign-in" ? (
          <form className="flex flex-col justify-center gap-4 p-8" onSubmit={(event) => void submit(event)}>
            <div>
              <h2 className="text-2xl font-semibold">Sign in</h2>
              <p className="text-sm text-charcoal/60">
                {env.needsStoreCode
                  ? "Enter the store code, then your email or username and password."
                  : "Use your email or username and password."}
              </p>
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
                onChange={(event) => setStoreCode(event.target.value.toLowerCase())}
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
            {notice ? <p className="rounded-2xl bg-emerald-500/10 px-4 py-3 text-sm text-emerald-800">{notice}</p> : null}
            {error ? (
              <p role="alert" className="rounded-2xl bg-danger/10 px-4 py-3 text-sm text-danger">
                {error}
              </p>
            ) : null}
            <button
              type="submit"
              disabled={busy}
              className="h-12 rounded-2xl bg-accent font-semibold text-white disabled:opacity-40"
            >
              {busy ? "Signing in…" : "Sign in"}
            </button>
            <button
              type="button"
              className="text-center text-sm font-semibold text-accent hover:underline"
              onClick={() => {
                setError(null);
                setNotice(null);
                setStep("email");
              }}
            >
              Forgot password?
            </button>
            {env.onTenantHost ? null : (
              <p className="text-center text-sm text-charcoal/60">
                New to AI POS?{" "}
                <a href="/signup" className="font-semibold text-accent hover:underline">
                  Create your store
                </a>
              </p>
            )}
          </form>
        ) : (
          <form
            className="flex flex-col justify-center gap-4 p-8"
            onSubmit={(event) => {
              event.preventDefault();
              void (step === "email" ? requestCode() : step === "code" ? verifyCode() : reset());
            }}
          >
            <div>
              <ol className="mb-3 flex gap-3 text-xs font-semibold" aria-label="Reset steps">
                {RESET_STEPS.map((item, index) => {
                  const active = item.id === step;
                  const done = RESET_STEPS.findIndex((entry) => entry.id === step) > index;
                  return (
                    <li key={item.id} className={active ? "text-accent" : done ? "text-charcoal" : "text-charcoal/40"} aria-current={active ? "step" : undefined}>
                      {index + 1}. {item.label}
                    </li>
                  );
                })}
              </ol>
              <h2 className="text-2xl font-semibold">
                {step === "email" ? "Reset password" : step === "code" ? "Enter the code" : "Choose a new password"}
              </h2>
              <p className="text-sm text-charcoal/60">
                {step === "email"
                  ? "We email a 6-digit code to the address on your portal account."
                  : step === "code"
                    ? `Enter the 6-digit code sent to ${email.trim()}.`
                    : `At least ${PASSWORD_MIN_LENGTH} characters.`}
              </p>
            </div>
            {step === "email" && env.needsStoreCode ? (
              <LoginField
                id="reset-store-code"
                label="Store code"
                icon={Store}
                autoComplete="off"
                spellCheck={false}
                value={storeCode}
                onChange={(event) => setStoreCode(event.target.value.toLowerCase())}
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
            {notice && step === "code" ? <p className="rounded-2xl bg-emerald-500/10 px-4 py-3 text-sm text-emerald-800">{notice}</p> : null}
            {error ? (
              <p role="alert" className="rounded-2xl bg-danger/10 px-4 py-3 text-sm text-danger">
                {error}
              </p>
            ) : null}
            <button
              type="submit"
              disabled={
                busy ||
                !storeReady ||
                (step === "email" && email.trim() === "") ||
                (step === "code" && code.length !== 6) ||
                (step === "password" && (password.length < PASSWORD_MIN_LENGTH || confirm.length < PASSWORD_MIN_LENGTH))
              }
              className="h-12 rounded-2xl bg-accent font-semibold text-white disabled:opacity-40"
            >
              {busy ? "Please wait…" : step === "email" ? "Email me a code" : step === "code" ? "Continue" : "Update password"}
            </button>
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
            <button
              type="button"
              className="text-center text-sm font-semibold text-charcoal/60 hover:underline"
              onClick={() => {
                setError(null);
                setNotice(null);
                setStep(step === "password" ? "code" : step === "code" ? "email" : "sign-in");
              }}
            >
              {step === "password" ? "Back to code" : step === "code" ? "Use a different email" : "Back to sign in"}
            </button>
          </form>
        )}
      </div>
      {demoAccountsEnabled ? (
        <DemoAccounts
          onPick={(pickedUsername, pickedPassword) => {
            setIdentity(pickedUsername);
            setPassword(pickedPassword);
            setError(null);
          }}
        />
      ) : null}
    </div>
  );
}
