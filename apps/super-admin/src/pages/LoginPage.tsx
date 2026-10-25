import { BrandLogo } from "@ai-pos/ui";
import { Eye, EyeOff, Lock, Mail, type LucideIcon } from "lucide-react";
import { useState, type FormEvent, type InputHTMLAttributes } from "react";
import { errorText } from "../lib/api";
import { useSession } from "../lib/session";

function LoginField({
  id,
  label,
  icon: Icon,
  type = "text",
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { id: string; label: string; icon: LucideIcon }) {
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
          className={`h-12 w-full rounded-2xl border border-line bg-surface pl-10 text-base transition focus:border-orange-500 focus:outline-none focus:ring-2 focus:ring-orange-500 ${
            isPassword ? "pr-12" : "pr-4"
          }`}
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
    </label>
  );
}

/** Operators sign in with the email and password created for the console. */
export function LoginPage() {
  const { signIn } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signIn(email.trim(), password);
    } catch (caught) {
      setError(errorText(caught, "Could not sign in."));
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-canvas p-4 font-sans text-charcoal">
      <div className="grid w-full max-w-5xl overflow-hidden rounded-[28px] border border-line bg-white md:grid-cols-2">
        <section className="flex flex-col justify-between bg-charcoal p-8 text-white">
          <BrandLogo tone="dark" className="h-9 w-auto" />
          <div className="mt-16">
            <h1 className="text-3xl font-semibold leading-tight">Console</h1>
            <p className="mt-3 max-w-xs text-sm text-white/60">
              For POS company staff. Every action here is audited.
            </p>
          </div>
          <div className="mt-10 inline-flex w-fit rounded-full bg-white/10 px-3 py-1 text-xs text-white/70">
            Email and password for console operators
          </div>
        </section>
        <form className="flex flex-col justify-center gap-4 p-8" onSubmit={(event) => void submit(event)}>
          <div>
            <h2 className="text-2xl font-semibold">Sign in</h2>
            <p className="text-sm text-charcoal/60">Use the email and password created for this console.</p>
          </div>
          <LoginField
            id="email"
            label="Email"
            icon={Mail}
            type="email"
            autoComplete="username"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
          <LoginField
            id="password"
            label="Password"
            icon={Lock}
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
          {error ? (
            <p role="alert" className="rounded-2xl bg-danger/10 px-4 py-3 text-sm text-danger">
              {error}
            </p>
          ) : null}
          <button
            type="submit"
            disabled={busy || email.trim() === "" || password.length === 0}
            className="h-12 rounded-2xl bg-accent font-semibold text-white disabled:opacity-40"
          >
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
