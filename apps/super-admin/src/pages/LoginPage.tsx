import { ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { ErrorNote, Field, PrimaryButton } from "../components/ui";
import { errorText } from "../lib/api";
import { useSession } from "../lib/session";

/** Operators sign in with their email, password and the 6-digit code from their authenticator app. */
export function LoginPage() {
  const { signIn } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signIn(email.trim(), password, code.trim());
    } catch (caught) {
      setError(errorText(caught, "Could not sign in."));
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-charcoal p-6">
      <form onSubmit={(event) => void submit(event)} className="w-full max-w-sm rounded-3xl bg-white p-8 shadow-2xl">
        <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-accent text-white">
          <ShieldCheck size={24} aria-hidden="true" />
        </span>
        <h1 className="mt-5 text-2xl font-semibold text-charcoal">QIOS Console</h1>
        <p className="mt-1 text-sm text-charcoal/60">For POS company staff. Every action here is audited.</p>
        <div className="mt-6 space-y-4">
          <Field label="Email" type="email" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} required />
          <Field label="Password" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required />
          <Field
            label="Authenticator code"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            value={code}
            onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))}
            required
          />
        </div>
        <ErrorNote message={error} />
        <PrimaryButton type="submit" disabled={busy || code.length !== 6} className="mt-6 h-11 w-full">
          {busy ? "Signing in…" : "Sign in"}
        </PrimaryButton>
      </form>
    </main>
  );
}
