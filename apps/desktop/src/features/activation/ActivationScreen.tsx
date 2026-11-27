import { businessCodeLabel, businessCodePhrase, isStoreCode, normalizeStoreCode } from "@ai-pos/shared-types";
import { BrandLogo, useLocale } from "@ai-pos/ui";
import { CheckCircle2, KeyRound, Loader2, ShieldCheck, Store } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useRegisterLayout } from "../../components/RegisterLayout";
import { useCapabilities } from "../../lib/capabilities";
import {
  activateTerminal,
  archivePendingForMigration,
  enrollDemoFile,
  exportPendingRecords,
  flushSync,
  inTauri,
  preflightActivation,
  type ActivationDecision,
  type TerminalStatus,
} from "../../lib/tauri";
import { activationNotice, hideServerAddress, retryLabel, retrySeconds, SERVER_UNREACHABLE } from "./messages";

/** Store host for this build: a public IP until DNS exists, otherwise a domain suffix. */
const BASE_DOMAIN = (import.meta.env.VITE_TENANT_BASE_DOMAIN?.trim() || "axizpos.com").replace(/^\./, "").toLowerCase();
const DIRECT_IP = /^\d{1,3}(?:\.\d{1,3}){3}$/.test(BASE_DOMAIN) || BASE_DOMAIN.includes(":");

/** "ab12cd34ef56" -> "AB12-CD34-EF56" while typing. */
function formatKey(raw: string): string {
  const compact = raw.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 12);
  return compact.match(/.{1,4}/g)?.join("-") ?? "";
}

function subdomainOf(raw: string): string {
  return normalizeStoreCode(raw)
    .replace(/^[a-z]+:\/\//, "")
    .split(/[/:]/)[0]!
    .replace(new RegExp(`\\.${BASE_DOMAIN.replaceAll(".", "\\.")}$`), "");
}

const input =
  "h-12 w-full rounded-xl border border-zinc-200 bg-white px-4 text-base text-zinc-900 placeholder:text-zinc-400 focus:border-orange-500 focus:outline-none focus:ring-4 focus:ring-orange-500/15 dark:border-zinc-800 dark:bg-zinc-900/60 dark:text-zinc-100 dark:placeholder:text-zinc-500";

type StageState = "waiting" | "active" | "done" | "failed";

const STAGE_LABELS = [
  "Store identified",
  "Register assigned",
  "Entitlement signing verified",
  "Activation credential validated",
  "Device activated",
  "Initial synchronization started",
  "Synchronization completed or requires attention",
] as const;

function safeActivationMessage(text: string): string {
  if (/traceback|exception|sqlalchemy|psycopg|internal server error/i.test(text)) {
    return "Activation could not be completed. Contact your administrator.";
  }
  return text;
}

function activationFailure(text: string): { code: string; message: string } {
  const match = /^\[([a-z0-9_]+)\]\s+([\s\S]+)$/.exec(text);
  if (!match) {
    if (text.includes("محفوظ")) return { code: "network", message: activationNotice("network") };
    const hidden = hideServerAddress(text);
    if (hidden) return { code: "network", message: hidden };
    return { code: "activation_failed", message: safeActivationMessage(text) };
  }
  const code = match[1] ?? "activation_failed";
  const raw = match[2] ?? "";
  if (code === "network") {
    return { code, message: raw.includes("محفوظ") ? activationNotice("network") : SERVER_UNREACHABLE };
  }
  if (code === "pending_same_store") return { code, message: hideServerAddress(raw) ?? safeActivationMessage(raw) };
  const notice = activationNotice(code);
  const shown = notice || safeActivationMessage(raw);
  return { code, message: hideServerAddress(shown) ?? shown };
}

function stageIndex(code: string): number {
  if (code === "network" || code === "tenant_not_found" || code === "tenant_invalid") return 0;
  if (code === "plan_limit" || code === "device_binding" || code === "conflict") return 1;
  if (code === "entitlement_unconfigured" || code === "entitlement_key_mismatch") return 2;
  if (code === "activation_invalid") return 3;
  if (code === "pending_offline") return 5;
  return 4;
}

function ActivationStages({ states }: { states: StageState[] }) {
  return (
    <ol className="space-y-2 text-sm">
      {STAGE_LABELS.map((label, index) => {
        const state = states[index] ?? "waiting";
        const mark = state === "done" ? "Done" : state === "failed" ? "Failed" : state === "active" ? "In progress" : "Waiting";
        return (
          <li key={label} className="flex items-center justify-between gap-3">
            <span>{label}</span>
            <span className={state === "failed" ? "font-semibold text-red-600 dark:text-red-300" : "text-zinc-500 dark:text-zinc-400"}>{mark}</span>
          </li>
        );
      })}
    </ol>
  );
}

/** First run: binds this register to a store code with a one-time key from the admin portal. */
export function ActivationScreen({ onCancel }: { onCancel?: () => void }) {
  const { theme } = useRegisterLayout();
  const { t } = useLocale();
  const { profile } = useCapabilities();
  const codeLabel = t(businessCodeLabel(profile));
  const [subdomain, setSubdomain] = useState("");
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryUntil, setRetryUntil] = useState<number | null>(null);
  const [done, setDone] = useState<TerminalStatus | null>(null);
  const [stages, setStages] = useState<StageState[]>(STAGE_LABELS.map(() => "waiting"));
  const [migration, setMigration] = useState<ActivationDecision | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const storeCode = useRef<HTMLInputElement>(null);
  const slug = subdomainOf(subdomain);
  const keyReady = key.replace(/-/g, "").length === 12;
  const storeReady = isStoreCode(slug);

  useEffect(() => {
    if (done === null || inTauri()) return;
    const timer = window.setTimeout(() => window.location.reload(), 1200);
    return () => window.clearTimeout(timer);
  }, [done]);

  useEffect(() => {
    if (retryUntil === null) return;
    const tick = () => {
      const left = Math.ceil((retryUntil - Date.now()) / 1000);
      if (left <= 0) {
        setRetryUntil(null);
        setError("You can try again.");
        return;
      }
      setError(retryLabel(left));
    };
    tick();
    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
  }, [retryUntil]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!keyReady || busy) return;
    if (!storeReady) {
      setError(t(businessCodePhrase(profile, "enterExample")));
      storeCode.current?.focus();
      return;
    }
    setBusy(true);
    setError(null);
    setRetryUntil(null);
    setNotice(null);
    setStages(STAGE_LABELS.map((_, index) => (index === 0 ? "done" : index < 5 ? "active" : "waiting")));
    try {
      const decision = await preflightActivation(slug, key);
      if (decision.code === "pending_different_store") {
        setMigration(decision);
        setStages(STAGE_LABELS.map((_, index) => (index === 0 ? "done" : index === 1 ? "failed" : "waiting")));
        setBusy(false);
        return;
      }
      if (decision.blocked) {
        throw new Error(`[${decision.code}] ${decision.message}`);
      }
      if (decision.code === "pending_same_store") setNotice(decision.message);
      setDone(await activateTerminal(slug, key));
      setStages(STAGE_LABELS.map((_, index) => (index < 6 ? "done" : "active")));
    } catch (caught) {
      const parsed = activationFailure(caught instanceof Error ? caught.message : String(caught));
      const failed = stageIndex(parsed.code);
      setStages(STAGE_LABELS.map((_, index) => (index < failed ? "done" : index === failed ? "failed" : "waiting")));
      const wait = retrySeconds(parsed.message);
      if (wait === null) {
        setRetryUntil(null);
        setError(parsed.message);
      } else {
        setError(retryLabel(wait));
        setRetryUntil(Date.now() + wait * 1000);
      }
    } finally {
      setBusy(false);
    }
  };

  const openConnection = async () => {
    if (!inTauri() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const dialog = await import("@tauri-apps/plugin-dialog");
      const selected = await dialog.open({
        multiple: false,
        directory: false,
        title: "Open the AxizPOS connection file",
        filters: [{ name: "AxizPOS connection", extensions: ["posdemo"] }],
      });
      if (typeof selected !== "string" || selected === "") return;
      setDone(await enrollDemoFile(selected));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      data-theme={theme}
      className="flex min-h-screen w-screen items-center justify-center bg-slate-50 p-6 font-sans text-zinc-900 antialiased dark:bg-zinc-950 dark:text-zinc-100"
    >
      <div className="grid w-full max-w-4xl overflow-hidden rounded-3xl border border-zinc-200 bg-white shadow-2xl md:grid-cols-[1fr_1.1fr] dark:border-zinc-800 dark:bg-zinc-900">
        <aside className="flex flex-col justify-between gap-10 bg-zinc-950 p-8 text-white">
          <div>
            <BrandLogo tone="dark" className="h-9 w-auto" />
            <p className="mt-8 text-xs font-semibold uppercase tracking-[0.18em] text-white/50">Register</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight">Activate this register</h1>
            <p className="mt-3 text-sm leading-relaxed text-white/60">
              Connect the till to your store once. Sales keep working offline afterwards and sync when the
              connection returns.
            </p>
          </div>
          <ol className="space-y-4 text-sm text-white/70">
            {[
              {
                icon: Store,
                text: DIRECT_IP
                  ? t(businessCodePhrase(profile, "portalHost"), { host: BASE_DOMAIN })
                  : t(businessCodePhrase(profile, "portal")),
              },
              { icon: KeyRound, text: "Registers › choose this till › Generate activation key." },
              { icon: ShieldCheck, text: t(businessCodePhrase(profile, "enterKey")) },
            ].map(({ icon: Icon, text }) => (
              <li key={text} className="flex gap-3">
                <Icon size={18} aria-hidden="true" className="mt-0.5 shrink-0 text-orange-400" />
                {text}
              </li>
            ))}
          </ol>
        </aside>

        <div className="p-8">
          {done ? (
            <div className="flex h-full flex-col justify-center" role="status">
              <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                <CheckCircle2 size={24} aria-hidden="true" />
              </span>
              <h2 className="mt-5 text-2xl font-semibold">Register activated</h2>
              <dl className="mt-5 divide-y divide-zinc-200 rounded-2xl border border-zinc-200 text-sm dark:divide-zinc-800 dark:border-zinc-800">
                {[
                  ["Business", done.tenant_name],
                  [codeLabel, done.tenant_slug],
                  ["Branch", `${done.store_code} · ${done.store_name}`],
                  ["Register", `${done.register_code} · ${done.register_name}`],
                ].map(([label, value]) => (
                  <div key={label} className="flex justify-between gap-4 px-4 py-3">
                    <dt className="text-zinc-500 dark:text-zinc-400">{label}</dt>
                    <dd className="text-right font-semibold">{value}</dd>
                  </div>
                ))}
              </dl>
              <div className="mt-5">
                <ActivationStages states={stages} />
              </div>
              <p className="mt-4 flex items-center gap-2 text-sm text-zinc-500 dark:text-zinc-400">
                <Loader2 size={16} aria-hidden="true" className="animate-spin" />
                Device activated. Initial synchronization starts when this register restarts and downloads this store&apos;s catalogue.
              </p>
            </div>
          ) : (
            <form onSubmit={(event) => void submit(event)} className="space-y-5">
              <div>
                <h2 className="text-xl font-semibold">Store connection</h2>
                <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                  {onCancel
                    ? "A new key connects this app to that register. Other tills at the same store stay connected."
                    : t(businessCodePhrase(profile, "ask"))}
                </p>
              </div>
              <label className="block">
                <span className="mb-1.5 block text-sm font-semibold">{codeLabel}</span>
                <input
                  ref={storeCode}
                  autoFocus
                  autoComplete="off"
                  spellCheck={false}
                  value={subdomain}
                  onChange={(event) => {
                    setError(null);
                    setSubdomain(normalizeStoreCode(event.target.value));
                  }}
                  placeholder={t(businessCodePhrase(profile, "placeholder"))}
                  className={input}
                />
                {slug ? (
                  <span className="mt-1.5 block text-xs text-zinc-500 dark:text-zinc-400">
                    {t(businessCodePhrase(profile, "connects"))} <span className="font-mono">{slug}</span>
                  </span>
                ) : keyReady ? (
                  <span className="mt-1.5 block text-xs text-zinc-500 dark:text-zinc-400">
                    {t(businessCodePhrase(profile, "typeExample"))}
                  </span>
                ) : null}
              </label>
              <label className="block">
                <span className="mb-1.5 block text-sm font-semibold">Activation key</span>
                <input
                  autoComplete="off"
                  spellCheck={false}
                  value={key}
                  onChange={(event) => setKey(formatKey(event.target.value))}
                  placeholder="ABCD-EFGH-JKLM"
                  className={`${input} font-mono tracking-[0.2em]`}
                />
              </label>
              <ActivationStages
                states={stages.map((state, index) => (index === 0 && storeReady && state === "waiting" ? "done" : state))}
              />
              {notice ? <p className="rounded-xl bg-zinc-100 px-4 py-3 text-sm text-zinc-700 dark:bg-zinc-800 dark:text-zinc-200">{notice}</p> : null}
              {migration ? (
                <div className="space-y-3 rounded-xl border border-zinc-200 p-4 dark:border-zinc-700">
                  <p className="text-sm font-semibold">This device contains transactions belonging to another store.</p>
                  <p className="text-sm text-zinc-600 dark:text-zinc-300">{migration.message}</p>
                  <ul className="text-sm text-zinc-600 dark:text-zinc-300">
                    <li>{migration.pending_sales} sales</li>
                    <li>{migration.pending_returns} returns</li>
                    <li>{migration.pending_cash_movements} cash movements</li>
                  </ul>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400">
                    Exporting keeps a copy for review. It does not sync, settle, or remove the original store&apos;s records.
                  </p>
                  <div className="grid gap-2">
                    <button
                      type="button"
                      disabled={busy || !inTauri()}
                      onClick={() => {
                        setBusy(true);
                        setError(null);
                        void flushSync()
                          .then(() => preflightActivation(slug, key))
                          .then((decision) => {
                            if (decision.code === "pending_different_store") setMigration(decision);
                            else setMigration(null);
                          })
                          .catch((caught) => setError(caught instanceof Error ? caught.message : String(caught)))
                          .finally(() => setBusy(false));
                      }}
                      className="h-11 rounded-xl bg-zinc-950 text-sm font-semibold text-white disabled:opacity-60"
                    >
                      Sync to original store
                    </button>
                    <button
                      type="button"
                      disabled={busy || !inTauri()}
                      onClick={() => {
                        setBusy(true);
                        setError(null);
                        void exportPendingRecords()
                          .then((paths) => setNotice(`Exported for review. The pending queue was not cleared. ${paths.join(" ")}`))
                          .catch((caught) => setError(caught instanceof Error ? caught.message : String(caught)))
                          .finally(() => setBusy(false));
                      }}
                      className="h-11 rounded-xl border border-zinc-300 text-sm font-semibold disabled:opacity-60"
                    >
                      Export pending data
                    </button>
                    <button
                      type="button"
                      disabled={busy || !inTauri()}
                      onClick={() => {
                        setBusy(true);
                        setError(null);
                        void archivePendingForMigration(slug)
                          .then(() => activateTerminal(slug, key))
                          .then((status) => {
                            setMigration(null);
                            setDone(status);
                          })
                          .catch((caught) => setError(caught instanceof Error ? caught.message : String(caught)))
                          .finally(() => setBusy(false));
                      }}
                      className="h-11 rounded-xl border border-red-300 text-sm font-semibold text-red-700 disabled:opacity-60"
                    >
                      Archive locally and change store
                    </button>
                    <button type="button" onClick={() => setMigration(null)} className="h-11 text-sm font-semibold text-zinc-500">
                      Cancel migration
                    </button>
                  </div>
                </div>
              ) : null}
              {error ? (
                <p role="alert" className="rounded-xl bg-red-500/10 px-4 py-3 text-sm text-red-700 ring-1 ring-red-500/20 dark:text-red-300">
                  {error}
                </p>
              ) : null}
              <button
                type="submit"
                disabled={!keyReady || busy || retryUntil !== null}
                className="flex h-14 w-full items-center justify-center gap-2 rounded-xl bg-orange-500 text-base font-bold text-white shadow-lg shadow-orange-500/25 transition-colors hover:bg-orange-600 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-orange-500/30 disabled:cursor-not-allowed disabled:bg-zinc-200 disabled:text-zinc-500 disabled:shadow-none dark:disabled:bg-zinc-800"
              >
                {busy ? <Loader2 size={18} aria-hidden="true" className="animate-spin" /> : <KeyRound size={18} aria-hidden="true" />}
                {busy ? "Activating…" : "Activate register"}
              </button>
              {inTauri() && !onCancel ? (
                <div className="rounded-2xl border border-dashed border-orange-200 p-4 dark:border-orange-500/30">
                  <p className="text-sm font-semibold">Demo connection file</p>
                  <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                    Install the register first, then download the connection file from the demo page and open it here. The file is used once and removed.
                  </p>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void openConnection()}
                    className="mt-3 flex h-12 w-full items-center justify-center rounded-xl border border-orange-500 text-sm font-semibold text-orange-600 disabled:opacity-60 dark:text-orange-300"
                  >
                    Open connection file
                  </button>
                </div>
              ) : null}
              {onCancel ? (
                <button
                  type="button"
                  onClick={onCancel}
                  className="h-12 w-full rounded-xl text-sm font-semibold text-zinc-500 transition hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
                >
                  Back to unlock
                </button>
              ) : null}
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
