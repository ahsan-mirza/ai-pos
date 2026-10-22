import { LogIn, LogOut, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { clockIn, clockOut, clockStatus, onDuty, type LocalTimeEntry } from "../../lib/tauri";
import type { CashierSession } from "../auth/session";

function since(iso: string): string {
  const minutes = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60_000));
  return `${Math.floor(minutes / 60)}h ${String(minutes % 60).padStart(2, "0")}m`;
}

const clockTime = (iso: string) => new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });

/** Clock in or out as the person who unlocked the register. Works offline; the entry syncs later. */
export function ClockModal({ session, onClose }: { session: CashierSession; onClose: () => void }) {
  const [entry, setEntry] = useState<LocalTimeEntry | null>(null);
  const [team, setTeam] = useState<LocalTimeEntry[]>([]);
  const [breakMinutes, setBreakMinutes] = useState("0");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [mine, others] = await Promise.all([clockStatus(), onDuty()]);
    setEntry(mine);
    setTeam(others);
  }, []);

  useEffect(() => {
    void refresh().catch((caught: unknown) => setError(caught instanceof Error ? caught.message : String(caught)));
  }, [refresh]);

  async function act() {
    setBusy(true);
    setError(null);
    try {
      if (entry) {
        const done = await clockOut({ at: new Date().toISOString(), break_minutes: Math.min(600, Math.max(0, Number(breakMinutes) || 0)) });
        setMessage(`Clocked out at ${clockTime(done.clock_out_at ?? new Date().toISOString())}. See you next shift.`);
      } else {
        const started = await clockIn({ id: crypto.randomUUID(), at: new Date().toISOString() });
        setMessage(`Clocked in at ${clockTime(started.clock_in_at)}.`);
      }
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="clock-title">
      <div className="modal-card max-w-md">
        <div className="mb-5 flex items-start justify-between gap-3">
          <div>
            <h2 id="clock-title" className="text-xl font-semibold">
              Time clock
            </h2>
            <p className="text-sm text-zinc-500 dark:text-zinc-400">{session.user.full_name}</p>
          </div>
          <button type="button" onClick={onClose} className="modal-close" aria-label="Close">
            <X size={18} aria-hidden="true" />
          </button>
        </div>

        <div className="rounded-2xl bg-zinc-100 p-5 text-center dark:bg-white/5">
          {entry ? (
            <>
              <p className="text-sm text-zinc-500 dark:text-zinc-400">On the clock since {clockTime(entry.clock_in_at)}</p>
              <p className="mt-1 text-4xl font-semibold tabular-nums">{since(entry.clock_in_at)}</p>
            </>
          ) : (
            <p className="py-3 text-sm text-zinc-600 dark:text-zinc-300">You are not clocked in.</p>
          )}
        </div>

        {entry ? (
          <label className="mt-4 block text-xs font-medium text-zinc-600 dark:text-white/60">
            Unpaid break taken (minutes)
            <input
              inputMode="numeric"
              value={breakMinutes}
              onChange={(event) => setBreakMinutes(event.target.value.replace(/\D/g, "").slice(0, 3))}
              className="modal-input mt-1.5 tabular-nums"
            />
          </label>
        ) : null}

        {message ? <p className="mt-4 rounded-xl bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-300">{message}</p> : null}
        {error ? (
          <p role="alert" className="mt-4 rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-700 dark:text-red-300">
            {error}
          </p>
        ) : null}

        <button type="button" disabled={busy} onClick={() => void act()} className="modal-save mt-5 w-full gap-2">
          {entry ? <LogOut size={16} aria-hidden="true" /> : <LogIn size={16} aria-hidden="true" />}
          {entry ? "Clock out" : "Clock in"}
        </button>

        {team.length ? (
          <div className="mt-6">
            <p className="text-xs font-semibold uppercase tracking-wider text-zinc-500">On duty at this register</p>
            <ul className="mt-2 space-y-1.5">
              {team.map((row) => (
                <li key={row.id} className="flex justify-between text-sm">
                  <span>{row.user_name}</span>
                  <span className="tabular-nums text-zinc-500">
                    since {clockTime(row.clock_in_at)} · {since(row.clock_in_at)}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </div>
  );
}
