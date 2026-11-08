import { currencyForCountry, signupPasswordConfirmation, signupPasswordReady, signupPasswordRules, signupPasswordsAccepted, type SignupState } from "@ai-pos/shared-types";
import { CountryField, availabilityBlocksSubmit, emailError, phoneError, requiredError, useLocale } from "@ai-pos/ui";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Check } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ErrorNote, TextField } from "../../components/ui/Field";
import { ApiRequestError } from "../../lib/api";
import { portalSignInPath } from "../../lib/portal-home";
import { EmailAvailabilityField, PhoneAvailabilityField, useEmailAvailability, usePhoneAvailability } from "./availabilityFields";
import { sessionFromStarted, signupApi, type SignupSession } from "./signupApi";
import { WizardFooter } from "./WizardFooter";

function secondsLeft(expiresAt: number | undefined): number {
  if (!expiresAt) return 0;
  return Math.max(0, Math.ceil((expiresAt - Date.now()) / 1000));
}

function formatClock(total: number): string {
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}
const CHANNEL_LABELS: Record<SignupSession["channel"], string> = {
  log: "the server log",
  whatsapp: "WhatsApp",
  sms: "SMS",
  email: "Email",
};

function message(error: unknown, fallback: string): string {
  return error instanceof ApiRequestError ? error.message : fallback;
}

const submitClass =
  "mt-2 h-12 w-full rounded-2xl bg-accent font-semibold text-white transition-colors hover:bg-accent-hover disabled:opacity-40";

export function AccountStep({
  country,
  onCountryChange,
  onStarted,
  onResumed,
  embedded = false,
}: {
  country: string;
  onCountryChange: (iso: string) => void;
  onStarted: (session: SignupSession) => void;
  onResumed: (session: SignupSession, state: SignupState) => void;
  /** Fits the landing-page card. Fields, validation, and the start API stay the same. */
  embedded?: boolean;
}) {
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const submitting = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const [existing, setExisting] = useState(false);
  const [nameProblem, setNameProblem] = useState<string | undefined>();
  const [passwordProblem, setPasswordProblem] = useState<string | undefined>();
  const { t } = useLocale();
  const reduced = useReducedMotion() === true;
  const emailCheck = useEmailAvailability(email);
  const phoneCheck = usePhoneAvailability(phone);
  const emailValid = emailError(email, true) === undefined;
  const phoneValid = phoneError(phone, true) === undefined;
  const nameValid = fullName.trim().length >= 2 && requiredError(fullName, "your name") === undefined;
  const passwordValid = signupPasswordReady(password);
  const confirmState = signupPasswordConfirmation(password, confirm);
  const canContinue =
    !busy &&
    nameValid &&
    signupPasswordsAccepted(password, confirm) &&
    !availabilityBlocksSubmit(emailCheck.status, emailValid) &&
    !availabilityBlocksSubmit(phoneCheck.status, phoneValid);

  const clearPasswords = () => {
    setPassword("");
    setConfirm("");
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (submitting.current) return;
    const nextName = fullName.trim().length < 2 ? "Enter your name." : requiredError(fullName, "your name");
    const nextPassword = passwordValid ? undefined : "Choose a password that meets every requirement.";
    setNameProblem(nextName);
    setPasswordProblem(nextPassword);
    if (!canContinue || nextName || nextPassword || confirmState !== "match") return;
    const chosen = password;
    submitting.current = true;
    setBusy(true);
    setError(null);
    try {
      const started = await signupApi.start({ email: email.trim(), phone, full_name: fullName.trim(), password: chosen });
      clearPasswords();
      onStarted(sessionFromStarted(started));
    } catch (caught) {
      if (caught instanceof ApiRequestError && caught.code === "signup_exists") {
        clearPasswords();
        setExisting(true);
        setError(null);
      } else {
        setError(t(message(caught, "Could not start signup.")));
      }
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  };

  const resume = async (event: FormEvent) => {
    event.preventDefault();
    if (submitting.current) return;
    const chosen = password;
    submitting.current = true;
    setBusy(true);
    setError(null);
    try {
      const started = await signupApi.resume({ email: email.trim(), password: chosen });
      const session = sessionFromStarted(started);
      const current = await signupApi.status(session);
      clearPasswords();
      onResumed(session, current);
    } catch (caught) {
      setError(t(message(caught, "Could not open your signup.")));
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  };

  if (existing) {
    return (
      <form className={embedded ? "mx-auto max-w-md" : "flex min-h-0 w-full flex-auto flex-col overflow-hidden"} onSubmit={(event) => void resume(event)}>
        <h2 className="text-2xl font-semibold">{t("You already have a signup")}</h2>
        <p className="mt-1 text-sm text-charcoal/60">
          {t("Log in with the email and password you used. We will open the step you still need to finish.")}
        </p>
        <div className="mt-6 space-y-4">
          <TextField
            label={t("Email")}
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
          <TextField
            label={t("Password")}
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        </div>
        <ErrorNote message={error} />
        {embedded ? (
          <>
            <button type="submit" disabled={!email.includes("@") || password.length === 0 || busy} className={`${submitClass} mt-6`}>
              {busy ? t("Opening your signup…") : t("Log in and continue")}
            </button>
            <button
              type="button"
              onClick={() => {
                setExisting(false);
                setError(null);
              }}
              className="mt-4 text-sm text-charcoal/60 hover:text-charcoal"
            >
              {t("Use different details")}
            </button>
          </>
        ) : (
          <WizardFooter
            type="submit"
            continueLabel={t("Log in and continue")}
            busyLabel={t("Opening your signup…")}
            busy={busy}
            disabled={!email.includes("@") || password.length === 0}
            onBack={() => {
              setExisting(false);
              setError(null);
            }}
            backLabel={t("Use different details")}
          />
        )}
      </form>
    );
  }

  return (
    <form
      className={embedded ? "w-full" : "flex min-h-0 w-full flex-auto flex-col overflow-hidden"}
      onSubmit={(event) => void submit(event)}
    >
      <div className={embedded ? undefined : "signup-fields min-h-0 flex-auto overflow-y-auto overscroll-contain"}>
      <h2 className={embedded ? "text-2xl font-semibold" : "text-xl font-semibold"}>{t("Create your account")}</h2>
      <p className="mt-0.5 text-sm text-charcoal/60">{t("You will be the owner of the store, with full access.")}</p>
      <div className={embedded ? "mt-6 space-y-4" : "signup-fields mt-3 space-y-2"}>
        <EmailAvailabilityField
          value={email}
          onChange={setEmail}
          status={emailCheck.status}
          onRetry={emailCheck.retry}
        />
        <div className={embedded ? "grid grid-cols-1 items-start gap-4 sm:grid-cols-2" : "signup-pair"}>
          <CountryField label={t("Country")} value={country} onChange={onCountryChange} detail={currencyForCountry} required />
          <PhoneAvailabilityField
            value={phone}
            onChange={setPhone}
            country={country}
            onCountryChange={onCountryChange}
            status={phoneCheck.status}
            onRetry={phoneCheck.retry}
          />
        </div>
        <fieldset>
          <legend className="text-sm font-medium">{t("Send the code by")}</legend>
          <div className="signup-channel-grid signup-pair mt-1.5">
            <label className={`flex cursor-pointer gap-3 rounded-2xl border-2 border-accent bg-white ${embedded ? "p-4" : "px-2.5 py-2"}`}>
              <input type="radio" name="otp-channel" value="email" defaultChecked className="mt-1 accent-accent" />
              <span>
                <span className="block text-sm font-semibold">{t("Email")}</span>
                <span className="block text-xs text-charcoal/60">{t("A 6-digit code to your inbox.")}</span>
              </span>
            </label>
            <label className={`signup-sms-option flex cursor-not-allowed gap-3 rounded-2xl border-2 border-transparent bg-surface opacity-50 ${embedded ? "p-4" : "p-2.5"}`}>
              <input type="radio" name="otp-channel" value="sms" disabled className="mt-1 accent-accent" />
              <span>
                <span className="block text-sm font-semibold">{t("Mobile number")}</span>
                <span className="block text-xs text-charcoal/60">{t("Not available yet.")}</span>
              </span>
            </label>
          </div>
        </fieldset>
        <div className={embedded ? "grid grid-cols-1 items-start gap-4 sm:grid-cols-2" : "signup-pair"}>
          <TextField
            label={t("Your name")}
            autoComplete="name"
            value={fullName}
            error={nameProblem ? t(nameProblem) : undefined}
            onChange={(event) => setFullName(event.target.value)}
            required
          />
          <div className="flex flex-col gap-2">
            <TextField
              id="signup-password"
              label={t("Password")}
              name="password"
              type="password"
              autoComplete="new-password"
              value={password}
              error={passwordProblem ? t(passwordProblem) : undefined}
              onChange={(event) => {
                setPassword(event.target.value);
                if (passwordProblem && signupPasswordReady(event.target.value)) setPasswordProblem(undefined);
              }}
              aria-describedby="signup-password-rules"
              required
            />
            <TextField
              id="signup-confirm-password"
              label={t("Confirm password")}
              name="confirm-password"
              type="password"
              autoComplete="new-password"
              toggleLabel="confirm password"
              value={confirm}
              error={confirmState === "mismatch" ? t("Passwords do not match.") : undefined}
              onChange={(event) => setConfirm(event.target.value)}
              required
            />
            <AnimatePresence initial={false}>
              {confirmState === "match" ? (
                <motion.p
                  role="status"
                  className="flex items-center gap-1.5 text-xs font-medium text-emerald-700"
                  initial={reduced ? false : { opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={reduced ? undefined : { opacity: 0, y: -4 }}
                  transition={{ duration: reduced ? 0 : 0.18 }}
                >
                  <Check size={14} className="text-emerald-600" aria-hidden="true" />
                  {t("Passwords match.")}
                </motion.p>
              ) : null}
            </AnimatePresence>
            <ul id="signup-password-rules" className="flex flex-col gap-1" aria-live="polite">
              {signupPasswordRules(password).map((rule) => (
                <li
                  key={rule.id}
                  className={`flex items-center gap-2 text-xs ${rule.met ? "text-emerald-700" : "text-charcoal/50"}`}
                >
                  {rule.met ? (
                    <Check size={14} className="text-emerald-600" aria-hidden="true" />
                  ) : (
                    <span className="h-3.5 w-3.5 rounded-full border border-charcoal/25" aria-hidden="true" />
                  )}
                  <span>
                    {t(rule.label)}
                    <span className="sr-only">{t(rule.met ? ", met" : ", still needed")}</span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
        {embedded ? null : (
          <p className="text-sm text-charcoal/60 min-[900px]:hidden">
            {t("Already have an account?")}{" "}
            <a href={portalSignInPath()} className="font-semibold text-accent hover:underline">
              {t("Log in")}
            </a>
          </p>
        )}
      </div>
      <ErrorNote message={error} />
      {embedded ? (
        <>
          <button type="submit" disabled={!canContinue} className={`${submitClass} mt-6`}>
            {busy ? t("Sending code…") : t("Continue")}
          </button>
          <p className="mt-4 text-center text-sm text-charcoal/60">
            {t("Already have an account?")}{" "}
            <a href={portalSignInPath()} target="_top" className="font-semibold text-accent hover:underline">
              {t("Log in")}
            </a>
          </p>
        </>
      ) : null}
      </div>
      {embedded ? null : (
        <WizardFooter type="submit" continueLabel={t("Continue")} busyLabel={t("Sending code…")} busy={busy} disabled={!canContinue} />
      )}
    </form>
  );
}

export function VerifyStep({
  session,
  onResent,
  onVerified,
  onRestart,
}: {
  session: SignupSession;
  onResent: (session: SignupSession) => void;
  onVerified: (state: SignupState) => void;
  onRestart: () => void;
}) {
  const { t } = useLocale();
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [remaining, setRemaining] = useState(() => secondsLeft(session.expiresAt));
  const input = useRef<HTMLInputElement>(null);
  const expired = remaining <= 0;

  useEffect(() => {
    setCode("");
    setError(null);
    setRemaining(secondsLeft(session.expiresAt));
  }, [session.id, session.expiresAt]);

  useEffect(() => {
    if (remaining <= 0) return;
    const timer = window.setTimeout(() => setRemaining((value) => Math.max(0, value - 1)), 1000);
    return () => window.clearTimeout(timer);
  }, [remaining]);

  const verify = async (value: string) => {
    setBusy(true);
    setError(null);
    try {
      onVerified(await signupApi.verify(session, value));
    } catch (caught) {
      setError(t(message(caught, "Could not check the code.")));
      setCode("");
      input.current?.focus();
    } finally {
      setBusy(false);
    }
  };

  const resend = async () => {
    setError(null);
    try {
      const sent = await signupApi.resend(session);
      onResent(sessionFromStarted(sent));
      setCode("");
    } catch (caught) {
      setError(t(message(caught, "Could not send a new code.")));
    }
  };

  return (
    <div className="flex min-h-0 flex-auto flex-col overflow-hidden">
      <div className="min-h-0 flex-auto overflow-y-auto overscroll-contain">
      <h2 className="text-xl font-semibold">{t("Enter the code")}</h2>
      <p className="mt-1 text-sm text-charcoal/60">
        {t("We sent a 6-digit code by {channel} to {destination}.", {
          channel: t(CHANNEL_LABELS[session.channel]),
          destination: session.sentTo,
        })}
      </p>
      <p className={`mt-3 text-sm font-medium ${expired ? "text-accent" : "text-charcoal/70"}`} aria-live="polite">
        {expired ? t("This code has expired.") : t("Code expires in {time}.", { time: formatClock(remaining) })}
      </p>
      {session.devCode ? (
        <p className="mt-4 rounded-2xl bg-surface px-4 py-3 text-sm text-charcoal/70">
          {t("Development: the code is {code}.", { code: session.devCode })}
        </p>
      ) : null}
      <label className="mt-6 block text-sm font-medium" htmlFor="signup-code">
        {t("Code")}
        <input
          id="signup-code"
          ref={input}
          autoFocus
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={6}
          value={code}
          disabled={busy || expired}
          onChange={(event) => {
            const digits = event.target.value.replace(/\D/g, "").slice(0, 6);
            setCode(digits);
            if (digits.length === 6) void verify(digits);
          }}
          className="mt-1.5 h-14 w-full rounded-2xl border border-line bg-surface px-4 text-center font-mono text-2xl tracking-[0.5em] focus:border-accent focus:bg-white focus:outline-none"
        />
      </label>
      <ErrorNote message={error} />
      <button
        type="button"
        onClick={() => void resend()}
        disabled={!expired || busy}
        className="mt-3 text-sm font-medium text-accent disabled:text-charcoal/40"
      >
        {t("Send a new code")}
      </button>
      </div>
      <WizardFooter
        continueLabel="Verify"
        busyLabel="Checking…"
        busy={busy}
        disabled={code.length !== 6 || expired}
        onContinue={() => void verify(code)}
        onBack={onRestart}
        backLabel="Use different details"
      />
    </div>
  );
}
