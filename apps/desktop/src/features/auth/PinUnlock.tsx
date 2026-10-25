import { BrandLogo } from "@ai-pos/ui";
import { Delete } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { version as packagedVersion } from "../../../package.json";
import { store } from "../checkout/catalog";
import { DemoCashiers, demoCashiersEnabled } from "./DemoCashiers";
import { unlock, type CashierSession } from "./session";

const MAX_PIN = 6;
const keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "clear", "0", "back"] as const;

export function PinUnlock({
  onUnlocked,
  onActivate,
}: {
  onUnlocked: (session: CashierSession) => void;
  onActivate?: () => void;
}) {
  const [username, setUsername] = useState("");
  const [pin, setPin] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [version, setVersion] = useState(packagedVersion);

  useEffect(() => {
    void import("@tauri-apps/api/app")
      .then(({ getVersion }) => getVersion())
      .then(setVersion)
      .catch(() => undefined);
  }, []);

  const press = useCallback((key: (typeof keys)[number]) => {
    setError(null);
    if (key === "clear") setPin("");
    else if (key === "back") setPin((value) => value.slice(0, -1));
    else setPin((value) => (value.length < MAX_PIN ? value + key : value));
  }, []);

  const submit = useCallback(async () => {
    if (busy || username.trim() === "" || pin.length < 4) return;
    setBusy(true);
    setError(null);
    try {
      onUnlocked(await unlock(username, pin));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      setPin("");
    } finally {
      setBusy(false);
    }
  }, [busy, onUnlocked, pin, username]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement) return;
      if (/^\d$/.test(event.key)) press(event.key as (typeof keys)[number]);
      else if (event.key === "Backspace") press("back");
      else if (event.key === "Escape") press("clear");
      else if (event.key === "Enter") void submit();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [press, submit]);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-charcoal p-6 font-sans text-white">
      <div className="grid w-full max-w-3xl gap-8 md:grid-cols-[1fr_340px]">
        <section className="flex flex-col justify-between">
          <BrandLogo tone="dark" className="h-10 w-auto" />
          <div className="mt-12">
            <p className="text-xs font-medium uppercase tracking-[0.18em] text-white/50">{store.name}</p>
            <h1 className="mt-2 text-4xl font-semibold leading-tight">Unlock register</h1>
            <p className="mt-3 max-w-sm text-sm text-white/60">
              Enter your username and POS PIN. Switching cashiers locks the current session.
            </p>
          </div>
          <label className="mt-10 block text-sm font-medium text-white/80" htmlFor="cashier">
            Username
            <input
              id="cashier"
              autoFocus
              autoComplete="off"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") void submit();
              }}
              className="mt-2 h-14 w-full rounded-2xl border border-white/10 bg-white/5 px-4 text-lg text-white outline-none focus:border-primary"
            />
          </label>
          {onActivate ? (
            <button
              type="button"
              onClick={onActivate}
              className="mt-4 h-12 w-full rounded-2xl border border-white/15 text-sm font-semibold text-white/80 transition hover:bg-white/10"
            >
              New activation
            </button>
          ) : null}
        </section>

        <section className="rounded-[28px] bg-white/5 p-6">
          <div className="flex justify-center gap-3" aria-label={`${pin.length} digits entered`}>
            {Array.from({ length: MAX_PIN }, (_, index) => (
              <span
                key={index}
                className={`h-3.5 w-3.5 rounded-full transition ${index < pin.length ? "bg-primary" : "bg-white/15"}`}
              />
            ))}
          </div>
          <p role="alert" className="mt-4 min-h-10 text-center text-sm text-red-400">
            {error}
          </p>
          <div className="mt-2 grid grid-cols-3 gap-3">
            {keys.map((key) => (
              <button
                key={key}
                type="button"
                onClick={() => press(key)}
                aria-label={key === "back" ? "Delete digit" : key === "clear" ? "Clear PIN" : key}
                className="flex h-16 items-center justify-center rounded-2xl bg-white/10 text-2xl font-semibold tabular-nums transition hover:bg-white/20 active:bg-primary"
              >
                {key === "back" ? <Delete size={22} aria-hidden="true" /> : key === "clear" ? <span className="text-sm">Clear</span> : key}
              </button>
            ))}
          </div>
          <button
            type="button"
            disabled={busy || username.trim() === "" || pin.length < 4}
            onClick={() => void submit()}
            className="mt-5 h-14 w-full rounded-2xl bg-primary text-base font-semibold disabled:opacity-40"
          >
            {busy ? "Checking…" : "Unlock"}
          </button>
        </section>
      </div>
      {demoCashiersEnabled ? (
        <DemoCashiers
          onPick={(pickedUsername, pickedPin) => {
            setUsername(pickedUsername);
            setPin(pickedPin);
            setError(null);
          }}
        />
      ) : null}
      <p className="pointer-events-none fixed bottom-4 right-5 text-xs tabular-nums text-white/40">v{version}</p>
    </div>
  );
}
