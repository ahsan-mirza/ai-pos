import { SIGNUP_PASSWORD_MIN_LENGTH, type SignupState } from "@ai-pos/shared-types";
import { Eye, EyeOff } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ErrorNote, TextField } from "../../components/ui/Field";
import { ApiRequestError } from "../../lib/api";
import { signupApi, type SignupSession } from "./signupApi";

const RESEND_SECONDS = 30;
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

export function AccountStep({ onStarted }: { onStarted: (session: SignupSession) => void }) {
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("+971 ");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ready =
    email.includes("@") &&
    phone.replace(/\D/g, "").length >= 8 &&
    fullName.trim().length >= 2 &&
    password.length >= SIGNUP_PASSWORD_MIN_LENGTH;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const started = await signupApi.start({ email: email.trim(), phone, full_name: fullName.trim(), password });
      onStarted({
        id: started.id,
        token: started.token,
        sentTo: started.sent_to,
        channel: started.channel,
        devCode: started.dev_code,
      });
    } catch (caught) {
      setError(message(caught, "Could not start signup."));
    } finally {
      setBusy(false);
    }
  };

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
          onChange={(event) => setEmail(event.target.value)}
          required
        />
        <TextField
          label="Mobile number"
          type="tel"
          autoComplete="tel"
          value={phone}
          onChange={(event) => setPhone(event.target.value)}
          hint="We send a 6-digit code to confirm it."
          required
        />
        <TextField
          label="Your name"
          autoComplete="name"
          value={fullName}
          onChange={(event) => setFullName(event.target.value)}
          required
        />
        <div className="relative">
          <TextField
            label="Password"
            type={showPassword ? "text" : "password"}
            autoComplete="new-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            hint={`At least ${SIGNUP_PASSWORD_MIN_LENGTH} characters.`}
            className="pr-12"
            required
          />
          <button
            type="button"
            onClick={() => setShowPassword((value) => !value)}
            aria-label={showPassword ? "Hide password" : "Show password"}
            className="absolute right-2 top-[34px] flex h-9 w-9 items-center justify-center rounded-full text-charcoal/50 hover:bg-gray-100"
          >
            {showPassword ? <EyeOff size={16} aria-hidden="true" /> : <Eye size={16} aria-hidden="true" />}
          </button>
        </div>
      </div>
      <ErrorNote message={error} />
      <button type="submit" disabled={!ready || busy} className={`${submitClass} mt-6`}>
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
  const [wait, setWait] = useState(RESEND_SECONDS);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (wait <= 0) return;
    const timer = window.setTimeout(() => setWait((value) => value - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [wait]);

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
      onResent({ ...session, sentTo: sent.sent_to, channel: sent.channel, devCode: sent.dev_code });
      setWait(sent.resend_after_seconds);
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
          disabled={busy}
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
        disabled={code.length !== 6 || busy}
        onClick={() => void verify(code)}
        className={`${submitClass} mt-6`}
      >
        {busy ? "Checking…" : "Verify"}
      </button>
      <div className="mt-4 flex items-center justify-between text-sm">
        <button
          type="button"
          onClick={() => void resend()}
          disabled={wait > 0}
          className="font-medium text-accent disabled:text-charcoal/40"
        >
          {wait > 0 ? `Send a new code in ${wait}s` : "Send a new code"}
        </button>
        <button type="button" onClick={onRestart} className="text-charcoal/60 hover:text-charcoal">
          Use different details
        </button>
      </div>
    </div>
  );
}
