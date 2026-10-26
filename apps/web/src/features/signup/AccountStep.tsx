import { signupPasswordReady, signupPasswordRules, type SignupState } from "@ai-pos/shared-types";
import { Check } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ErrorNote, TextField } from "../../components/ui/Field";
import { PhoneField, emailError, phoneError, requiredError } from "@ai-pos/ui";
import { ApiRequestError } from "../../lib/api";
import { sessionFromStarted, signupApi, type SignupSession } from "./signupApi";

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
  email: "email",
};

function message(error: unknown, fallback: string): string {
  return error instanceof ApiRequestError ? error.message : fallback;
}

const submitClass =
  "mt-2 h-12 w-full rounded-2xl bg-accent font-semibold text-white transition-colors hover:bg-accent-hover disabled:opacity-40";

export function AccountStep({
  onStarted,
  onResumed,
}: {
  onStarted: (session: SignupSession) => void;
  onResumed: (session: SignupSession, state: SignupState) => void;
}) {
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [existing, setExisting] = useState(false);
  const [emailProblem, setEmailProblem] = useState<string | undefined>();
  const [phoneProblem, setPhoneProblem] = useState<string | undefined>();
  const [nameProblem, setNameProblem] = useState<string | undefined>();
  const [passwordProblem, setPasswordProblem] = useState<string | undefined>();

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const nextEmail = emailError(email, true);
    const nextPhone = phoneError(phone, true);
    const nextName = fullName.trim().length < 2 ? "Enter your name." : requiredError(fullName, "your name");
    const nextPassword = signupPasswordReady(password) ? undefined : "Choose a password that meets every requirement.";
    setEmailProblem(nextEmail);
    setPhoneProblem(nextPhone);
    setNameProblem(nextName);
    setPasswordProblem(nextPassword);
    if (nextEmail || nextPhone || nextName || nextPassword) return;
    setBusy(true);
    setError(null);
    try {
      const started = await signupApi.start({ email: email.trim(), phone, full_name: fullName.trim(), password });
      onStarted(sessionFromStarted(started));
    } catch (caught) {
      if (caught instanceof ApiRequestError && caught.code === "signup_exists") {
        setExisting(true);
        setError(null);
      } else {
        setError(message(caught, "Could not start signup."));
      }
    } finally {
      setBusy(false);
    }
  };

  const resume = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const started = await signupApi.resume({ email: email.trim(), password });
      const session = sessionFromStarted(started);
      onResumed(session, await signupApi.status(session));
    } catch (caught) {
      setError(message(caught, "Could not open your signup."));
    } finally {
      setBusy(false);
    }
  };

  if (existing) {
    return (
      <form className="mx-auto max-w-md" onSubmit={(event) => void resume(event)}>
        <h2 className="text-2xl font-semibold">You already have a signup</h2>
        <p className="mt-1 text-sm text-charcoal/60">
          Log in with the email and password you used. We will open the step you still need to finish.
        </p>
        <div className="mt-6 space-y-4">
          <TextField
            label="Email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
          <TextField
            label="Password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        </div>
        <ErrorNote message={error} />
        <button type="submit" disabled={!email.includes("@") || password.length === 0 || busy} className={`${submitClass} mt-6`}>
          {busy ? "Opening your signup…" : "Log in and continue"}
        </button>
        <button
          type="button"
          onClick={() => {
            setExisting(false);
            setError(null);
          }}
          className="mt-4 text-sm text-charcoal/60 hover:text-charcoal"
        >
          Use different details
        </button>
      </form>
    );
  }

  return (
    <form className="mx-auto max-w-md" onSubmit={(event) => void submit(event)}>
      <h2 className="text-2xl font-semibold">Create your account</h2>
      <p className="mt-1 text-sm text-charcoal/60">You will be the owner of the store, with full access.</p>
      <div className="mt-6 space-y-4">
        <TextField
          label="Email"
          type="email"
          autoComplete="email"
          value={email}
          error={emailProblem}
          onChange={(event) => setEmail(event.target.value)}
          required
        />
        <PhoneField
          label="Mobile number"
          value={phone}
          error={phoneProblem}
          onChange={setPhone}
          hint="Saved on your account. The code is sent by email."
          required
        />
        <fieldset>
          <legend className="text-sm font-medium">Send the code by</legend>
          <div className="mt-2 grid gap-2 sm:grid-cols-2">
            <label className="flex cursor-pointer gap-3 rounded-2xl border-2 border-accent bg-white p-4">
              <input type="radio" name="otp-channel" value="email" defaultChecked className="mt-1 accent-accent" />
              <span>
                <span className="block text-sm font-semibold">Email</span>
                <span className="block text-xs text-charcoal/60">A 6-digit code to your inbox.</span>
              </span>
            </label>
            <label className="flex cursor-not-allowed gap-3 rounded-2xl border-2 border-transparent bg-surface p-4 opacity-50">
              <input type="radio" name="otp-channel" value="sms" disabled className="mt-1 accent-accent" />
              <span>
                <span className="block text-sm font-semibold">Mobile number</span>
                <span className="block text-xs text-charcoal/60">Not available yet.</span>
              </span>
            </label>
          </div>
        </fieldset>
        <TextField
          label="Your name"
          autoComplete="name"
          value={fullName}
          error={nameProblem}
          onChange={(event) => setFullName(event.target.value)}
          required
        />
        <div>
          <TextField
            label="Password"
            type="password"
            autoComplete="new-password"
            value={password}
            error={passwordProblem}
            onChange={(event) => setPassword(event.target.value)}
            aria-describedby="signup-password-rules"
            required
          />
          <ul id="signup-password-rules" className="mt-2 space-y-1" aria-live="polite">
            {signupPasswordRules(password).map((rule) => (
              <li
                key={rule.id}
                className={`flex items-center gap-2 text-xs ${rule.met ? "text-emerald-700" : "text-charcoal/50"}`}
              >
                <Check size={14} className={rule.met ? "text-emerald-600" : "text-charcoal/30"} aria-hidden="true" />
                <span>
                  {rule.label}
                  <span className="sr-only">{rule.met ? ", met" : ", still needed"}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>
      <ErrorNote message={error} />
      <button type="submit" disabled={busy} className={`${submitClass} mt-6`}>
        {busy ? "Sending code…" : "Continue"}
      </button>
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
      setError(message(caught, "Could not check the code."));
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
      setError(message(caught, "Could not send a new code."));
    }
  };

  return (
    <div className="mx-auto max-w-md">
      <h2 className="text-2xl font-semibold">Enter the code</h2>
      <p className="mt-1 text-sm text-charcoal/60">
        We sent a 6-digit code by {CHANNEL_LABELS[session.channel]} to <strong>{session.sentTo}</strong>.
      </p>
      <p className={`mt-3 text-sm font-medium ${expired ? "text-accent" : "text-charcoal/70"}`} aria-live="polite">
        {expired ? "This code has expired." : `Code expires in ${formatClock(remaining)}.`}
      </p>
      {session.devCode ? (
        <p className="mt-4 rounded-2xl bg-surface px-4 py-3 text-sm text-charcoal/70">
          Development: the code is <strong className="font-mono tracking-widest">{session.devCode}</strong>.
        </p>
      ) : null}
      <label className="mt-6 block text-sm font-medium" htmlFor="signup-code">
        Code
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
        disabled={code.length !== 6 || busy || expired}
        onClick={() => void verify(code)}
        className={`${submitClass} mt-6`}
      >
        {busy ? "Checking…" : "Verify"}
      </button>
      <div className="mt-4 flex items-center justify-between text-sm">
        <button
          type="button"
          onClick={() => void resend()}
          disabled={!expired || busy}
          className="font-medium text-accent disabled:text-charcoal/40"
        >
          Send a new code
        </button>
        <button type="button" onClick={onRestart} className="text-charcoal/60 hover:text-charcoal">
          Use different details
        </button>
      </div>
    </div>
  );
}
