import { CheckCircle2, KeyRound, Loader2, ShieldCheck, Store } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { useRegisterLayout } from "../../components/RegisterLayout";
import { activateTerminal, inTauri, type TerminalStatus } from "../../lib/tauri";

/** Store host for this build: a public IP until DNS exists, otherwise a domain suffix. */
const BASE_DOMAIN = (import.meta.env.VITE_TENANT_BASE_DOMAIN?.trim() || "qios.ae").replace(/^\./, "").toLowerCase();
const DIRECT_IP = /^\d{1,3}(?:\.\d{1,3}){3}$/.test(BASE_DOMAIN) || BASE_DOMAIN.includes(":");

/** "ab12cd34ef56" -> "AB12-CD34-EF56" while typing. */
function formatKey(raw: string): string {
  const compact = raw.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 12);
  return compact.match(/.{1,4}/g)?.join("-") ?? "";
}

function subdomainOf(raw: string): string {
  return raw
    .trim()
    .toLowerCase()
    .replace(/^[a-z]+:\/\//, "")
    .split(/[/:]/)[0]!
    .replace(new RegExp(`\\.${BASE_DOMAIN.replaceAll(".", "\\.")}$`), "");
}

const input =
  "h-12 w-full rounded-xl border border-zinc-200 bg-white px-4 text-base text-zinc-900 placeholder:text-zinc-400 focus:border-orange-500 focus:outline-none focus:ring-4 focus:ring-orange-500/15 dark:border-zinc-800 dark:bg-zinc-900/60 dark:text-zinc-100 dark:placeholder:text-zinc-500";

/** First run: binds this register to a store subdomain with a one-time key from the admin portal. */
export function ActivationScreen({ onCancel }: { onCancel?: () => void }) {
  const { theme } = useRegisterLayout();
  const [subdomain, setSubdomain] = useState("");
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<TerminalStatus | null>(null);
  const slug = subdomainOf(subdomain);
  const ready = /^[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?$/.test(slug) && key.replace(/-/g, "").length === 12;

  useEffect(() => {
    if (done === null || inTauri()) return;
    const timer = window.setTimeout(() => window.location.reload(), 1200);
    return () => window.clearTimeout(timer);
  }, [done]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!ready || busy) return;
    setBusy(true);
    setError(null);
    try {
      setDone(await activateTerminal(slug, key));
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
            <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-orange-500 text-sm font-bold">ai</span>
            <p className="mt-8 text-xs font-semibold uppercase tracking-[0.18em] text-white/50">AI POS register</p>
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
                  ? `Open the admin portal at http://${BASE_DOMAIN} and sign in with the store code.`
                  : `Open your admin portal at yourstore.${BASE_DOMAIN}.`,
              },
              { icon: KeyRound, text: "Registers › choose this till › Generate activation key." },
              {
                icon: ShieldCheck,
                text: DIRECT_IP
                  ? "Enter the store code and key here. The key works once, for 24 hours."
                  : "Enter the subdomain and key here. The key works once, for 24 hours.",
              },
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
                  ["Subdomain", done.tenant_domain],
                  ["Branch", `${done.store_code} · ${done.store_name}`],
                  ["Register", `${done.register_code} · ${done.register_name}`],
                ].map(([label, value]) => (
                  <div key={label} className="flex justify-between gap-4 px-4 py-3">
                    <dt className="text-zinc-500 dark:text-zinc-400">{label}</dt>
                    <dd className="text-right font-semibold">{value}</dd>
                  </div>
                ))}
              </dl>
              <p className="mt-5 flex items-center gap-2 text-sm text-zinc-500 dark:text-zinc-400">
                <Loader2 size={16} aria-hidden="true" className="animate-spin" />
                Restarting with this store's data…
              </p>
            </div>
          ) : (
            <form onSubmit={(event) => void submit(event)} className="space-y-5">
              <div>
                <h2 className="text-xl font-semibold">Store connection</h2>
                <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                  {DIRECT_IP ? "Ask your manager for the store code and key." : "Ask your manager for the subdomain and key."}
                </p>
              </div>
              <label className="block">
                <span className="mb-1.5 block text-sm font-semibold">{DIRECT_IP ? "Store code" : "Store subdomain"}</span>
                <span className="flex overflow-hidden rounded-xl border border-zinc-200 focus-within:border-orange-500 focus-within:ring-4 focus-within:ring-orange-500/15 dark:border-zinc-800">
                  <input
                    autoFocus
                    autoComplete="off"
                    spellCheck={false}
                    value={subdomain}
                    onChange={(event) => setSubdomain(event.target.value)}
                    placeholder="client1"
                    className="h-12 min-w-0 flex-1 bg-white px-4 text-base text-zinc-900 placeholder:text-zinc-400 focus:outline-none dark:bg-zinc-900/60 dark:text-zinc-100 dark:placeholder:text-zinc-500"
                  />
                  {DIRECT_IP ? null : (
                    <span className="flex items-center border-l border-zinc-200 bg-zinc-50 px-4 text-sm font-medium text-zinc-500 dark:border-zinc-800 dark:bg-zinc-800/60 dark:text-zinc-400">
                      .{BASE_DOMAIN}
                    </span>
                  )}
                </span>
                {DIRECT_IP ? (
                  <span className="mt-1.5 block text-xs text-zinc-500 dark:text-zinc-400">
                    Connects to <span className="font-mono">http://{BASE_DOMAIN}</span>
                  </span>
                ) : slug ? (
                  <span className="mt-1.5 block text-xs text-zinc-500 dark:text-zinc-400">
                    Connects to <span className="font-mono">{slug}.{BASE_DOMAIN}</span>
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
              {error ? (
                <p role="alert" className="rounded-xl bg-red-500/10 px-4 py-3 text-sm text-red-700 ring-1 ring-red-500/20 dark:text-red-300">
                  {error}
                </p>
              ) : null}
              <button
                type="submit"
                disabled={!ready || busy}
                className="flex h-14 w-full items-center justify-center gap-2 rounded-xl bg-orange-500 text-base font-bold text-white shadow-lg shadow-orange-500/25 transition-colors hover:bg-orange-600 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-orange-500/30 disabled:cursor-not-allowed disabled:bg-zinc-200 disabled:text-zinc-500 disabled:shadow-none dark:disabled:bg-zinc-800"
              >
                {busy ? <Loader2 size={18} aria-hidden="true" className="animate-spin" /> : <KeyRound size={18} aria-hidden="true" />}
                {busy ? "Activating…" : "Activate register"}
              </button>
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
