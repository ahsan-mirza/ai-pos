import { BrandLogo } from "@ai-pos/ui";
import { Delete } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { version as packagedVersion } from "../../../package.json";
import { useRegisterLayout } from "../../components/RegisterLayout";
import { terminal } from "../../config/terminal";
import { store } from "../checkout/catalog";
import { loadCashiers, type CashierCard } from "./cashiers";
import { DemoCashiers, demoCashiersEnabled } from "./DemoCashiers";
import { unlock, unlockSelected, type CashierSession } from "./session";

const MAX_PIN = 6;
const keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "clear", "0", "back"] as const;

export function PinUnlock({
  onUnlocked,
  onActivate,
}: {
  onUnlocked: (session: CashierSession) => void;
  onActivate?: () => void;
}) {
  const { theme } = useRegisterLayout();
  const dark = theme === "dark";
  const activated = terminal();
  const business = activated?.tenant_name || store.name;
  const branch = activated?.store_name && activated.store_name !== business ? activated.store_name : null;
  const [cashiers, setCashiers] = useState<CashierCard[]>([]);
  const [directoryError, setDirectoryError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [manual, setManual] = useState(false);
  const [username, setUsername] = useState("");
  const [pin, setPin] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [version, setVersion] = useState(packagedVersion);
  const selected = cashiers.find((card) => card.id === selectedId) ?? null;

  useEffect(() => {
    void import("@tauri-apps/api/app")
      .then(({ getVersion }) => getVersion())
      .then(setVersion)
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    let cancelled = false;
    void loadCashiers()
      .then((cards) => {
        if (!cancelled) setCashiers(cards);
      })
      .catch((caught: unknown) => {
        if (!cancelled) setDirectoryError(caught instanceof Error ? caught.message : String(caught));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const press = useCallback((key: (typeof keys)[number]) => {
    setError(null);
    if (key === "clear") setPin("");
    else if (key === "back") setPin((value) => value.slice(0, -1));
    else setPin((value) => (value.length < MAX_PIN ? value + key : value));
  }, []);

  const ready = manual ? username.trim() !== "" : selected !== null;

  const submit = useCallback(async () => {
    if (busy || !ready || pin.length < 4) return;
    setBusy(true);
    setError(null);
    try {
      const session = manual || selected === null ? await unlock(username, pin) : await unlockSelected(selected.id, pin);
      onUnlocked(session);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      setPin("");
    } finally {
      setBusy(false);
    }
  }, [busy, manual, onUnlocked, pin, ready, selected, username]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return;
      if (/^\d$/.test(event.key)) press(event.key as (typeof keys)[number]);
      else if (event.key === "Backspace") press("back");
      else if (event.key === "Escape") press("clear");
      else if (event.key === "Enter") void submit();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [press, submit]);

  const panel = dark ? "border-white/10 bg-white/5 text-white" : "border-zinc-200 bg-white text-zinc-900";
  const muted = dark ? "text-white/60" : "text-zinc-500";
  const keyClass = `flex h-14 items-center justify-center rounded-2xl text-xl font-semibold tabular-nums transition active:bg-primary sm:h-16 sm:text-2xl ${
    dark ? "bg-white/10 hover:bg-white/20" : "bg-zinc-100 hover:bg-zinc-200"
  }`;

  return (
    <div
      data-theme={theme}
      className={`flex min-h-screen flex-col items-center justify-center p-4 font-sans sm:p-6 ${dark ? "bg-charcoal text-white" : "bg-slate-50 text-zinc-900"}`}
    >
      <div className="grid w-full max-w-5xl items-start gap-8 lg:grid-cols-[minmax(0,1fr)_340px]">
        <section className="min-w-0">
          <BrandLogo tone={dark ? "dark" : "light"} className="h-10 w-auto" />
          <p className={`mt-8 text-xs font-medium uppercase tracking-[0.18em] ${muted}`}>
            {business}
            {branch ? ` · ${branch}` : ""} · POS register
          </p>
          <h1 className="mt-2 text-3xl font-semibold leading-tight sm:text-4xl">Unlock register</h1>
          <p className={`mt-3 max-w-md text-sm ${muted}`}>Select your cashier and enter your POS PIN to continue.</p>

          {manual ? (
            <label className={`mt-8 block text-sm font-medium ${dark ? "text-white/80" : "text-zinc-700"}`} htmlFor="cashier">
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
                className={`mt-2 h-14 w-full rounded-2xl border px-4 text-lg outline-none focus:border-primary ${panel}`}
              />
            </label>
          ) : (
            <div className="mt-8">
              <p className={`text-sm font-medium ${dark ? "text-white/80" : "text-zinc-700"}`}>Cashiers</p>
              {directoryError ? <p className="mt-2 text-sm text-red-500">{directoryError}</p> : null}
              {cashiers.length === 0 ? (
                <p className={`mt-3 text-sm ${muted}`}>No cashier profiles are on this register yet.</p>
              ) : (
                <ul className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
                  {cashiers.map((card) => {
                    const active = card.id === selectedId;
                    return (
                      <li key={card.id}>
                        <button
                          type="button"
                          aria-pressed={active}
                          onClick={() => {
                            setSelectedId(card.id);
                            setError(null);
                            setPin("");
                          }}
                          className={`flex min-h-16 w-full items-center gap-3 rounded-2xl border px-3 py-3 text-left transition ${
                            active ? "border-primary ring-2 ring-primary" : panel
                          }`}
                        >
                          {card.avatar_url ? (
                            <img src={card.avatar_url} alt="" className="h-11 w-11 rounded-full object-cover" />
                          ) : (
                            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-primary/15 text-sm font-semibold text-primary">
                              {card.initials}
                            </span>
                          )}
                          <span className="min-w-0">
                            <span className="block truncate font-medium">{card.display_name}</span>
                            {card.role_label ? <span className={`block truncate text-xs ${muted}`}>{card.role_label}</span> : null}
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          )}

          <button
            type="button"
            onClick={() => {
              setManual((value) => !value);
              setSelectedId(null);
              setUsername("");
              setPin("");
              setError(null);
            }}
            className={`mt-4 text-sm font-semibold text-primary`}
          >
            {manual ? "Choose a cashier" : "Use username instead"}
          </button>
          {onActivate ? (
            <button
              type="button"
              onClick={onActivate}
              className={`mt-4 h-12 w-full rounded-2xl border text-sm font-semibold transition ${
                dark ? "border-white/15 text-white/80 hover:bg-white/10" : "border-zinc-200 bg-white text-zinc-700 hover:bg-zinc-100"
              }`}
            >
              New activation
            </button>
          ) : null}
        </section>

        <section className={`rounded-[28px] border p-5 sm:p-6 ${panel}`}>
          <p className="min-h-6 text-center text-sm font-medium">{manual ? "Username login" : (selected?.display_name ?? "Select a cashier")}</p>
          <div className="mt-4 flex justify-center gap-3" aria-label={`${pin.length} digits entered`}>
            {Array.from({ length: MAX_PIN }, (_, index) => (
              <span
                key={index}
                className={`h-3.5 w-3.5 rounded-full transition ${index < pin.length ? "bg-primary" : dark ? "bg-white/15" : "bg-zinc-200"}`}
              />
            ))}
          </div>
          <p role="alert" className="mt-4 min-h-10 text-center text-sm text-red-500">
            {error}
          </p>
          <div className="mt-2 grid grid-cols-3 gap-2 sm:gap-3">
            {keys.map((key) => (
              <button
                key={key}
                type="button"
                onClick={() => press(key)}
                aria-label={key === "back" ? "Delete digit" : key === "clear" ? "Clear PIN" : key}
                className={keyClass}
              >
                {key === "back" ? <Delete size={22} aria-hidden="true" /> : key === "clear" ? <span className="text-sm">Clear</span> : key}
              </button>
            ))}
          </div>
          <button
            type="button"
            disabled={busy || !ready || pin.length < 4}
            onClick={() => void submit()}
            className="mt-5 h-14 w-full rounded-2xl bg-primary text-base font-semibold text-white disabled:opacity-40"
          >
            {busy ? "Checking…" : "Unlock"}
          </button>
        </section>
      </div>
      {demoCashiersEnabled ? (
        <DemoCashiers
          onPick={(pickedUsername, pickedPin) => {
            setManual(true);
            setUsername(pickedUsername);
            setPin(pickedPin);
            setError(null);
          }}
        />
      ) : null}
      <p className={`pointer-events-none fixed bottom-4 right-5 text-xs tabular-nums ${dark ? "text-white/40" : "text-zinc-400"}`}>v{version}</p>
    </div>
  );
}
