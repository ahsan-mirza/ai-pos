import { useState, type FormEvent } from "react";
import { env, saveStoreCode } from "../../config/env";
import { ApiRequestError } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { DemoAccounts, demoAccountsEnabled } from "./DemoAccounts";

const STORE_CODE = /^[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?$/;

export function LoginPage() {
  const { login } = useAuth();
  const [storeCode, setStoreCode] = useState(() => (env.needsStoreCode ? (env.tenantDomain ?? "") : ""));
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const store = storeCode.trim().toLowerCase();
  const storeReady = !env.needsStoreCode || STORE_CODE.test(store);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!storeReady) return;
    setBusy(true);
    setError(null);
    try {
      if (env.needsStoreCode) saveStoreCode(store);
      await login(username.trim(), password);
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Sign-in failed.");
      setPassword("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-canvas p-4 font-sans text-charcoal">
      <div className="grid w-full max-w-5xl overflow-hidden rounded-[28px] border border-line bg-white md:grid-cols-2">
        <section className="flex flex-col justify-between bg-charcoal p-8 text-white">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-accent text-sm font-bold">ai</div>
          <div className="mt-16">
            <p className="text-xs font-medium uppercase tracking-[0.16em] text-white/50">AI POS</p>
            <h1 className="mt-2 text-3xl font-semibold leading-tight">Admin portal</h1>
            <p className="mt-3 max-w-xs text-sm text-white/60">
              Manage stores, inventory, repairs, staff, and role permissions.
            </p>
          </div>
          <div className="mt-10 inline-flex w-fit rounded-full bg-white/10 px-3 py-1 text-xs text-white/70">
            Password sign-in for portal users
          </div>
        </section>
        <form className="flex flex-col justify-center gap-4 p-8" onSubmit={(event) => void submit(event)}>
          <div>
            <h2 className="text-2xl font-semibold">Sign in</h2>
            <p className="text-sm text-charcoal/60">
              {env.needsStoreCode ? "Enter the store code, then your portal username and password." : "Use your portal username and password."}
            </p>
          </div>
          {env.needsStoreCode ? (
            <label className="text-sm font-medium" htmlFor="store-code">
              Store code
              <input
                id="store-code"
                autoComplete="off"
                spellCheck={false}
                value={storeCode}
                onChange={(event) => setStoreCode(event.target.value.toLowerCase())}
                placeholder="client1"
                className="mt-1 h-12 w-full rounded-2xl border border-line bg-surface px-4 text-base"
                required
              />
            </label>
          ) : null}
          <label className="text-sm font-medium" htmlFor="username">
            Username
            <input
              id="username"
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              className="mt-1 h-12 w-full rounded-2xl border border-line bg-surface px-4 text-base"
              required
            />
          </label>
          <label className="text-sm font-medium" htmlFor="password">
            Password
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="mt-1 h-12 w-full rounded-2xl border border-line bg-surface px-4 text-base"
              required
            />
          </label>
          {error ? (
            <p role="alert" className="rounded-2xl bg-accent/10 px-4 py-3 text-sm text-accent">
              {error}
            </p>
          ) : null}
          <button
            type="submit"
            disabled={busy || !storeReady || username.trim() === "" || password === ""}
            className="h-12 rounded-2xl bg-accent font-semibold text-white disabled:opacity-40"
          >
            {busy ? "Signing in…" : "Sign in"}
          </button>
          {env.onTenantHost || env.needsStoreCode ? null : (
            <p className="text-center text-sm text-charcoal/60">
              New to AI POS?{" "}
              <a href="/signup" className="font-semibold text-accent hover:underline">
                Create your store
              </a>
            </p>
          )}
        </form>
      </div>
      {demoAccountsEnabled ? (
        <DemoAccounts
          onPick={(pickedUsername, pickedPassword) => {
            setUsername(pickedUsername);
            setPassword(pickedPassword);
            setError(null);
          }}
        />
      ) : null}
    </div>
  );
}
