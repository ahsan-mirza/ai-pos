import {
  NEXT_TICKET_STATUS,
  mergeBoard,
  modifierSummary,
  ticketAge,
  type KitchenBoard,
  type KitchenStation,
  type KitchenTicket,
  type TicketAge,
} from "@ai-pos/shared-types";
import { ChefHat, LogOut, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import { ApiRequestError, apiPublicPost, apiTerminal } from "../../lib/api";
import { listenForStation } from "./live";

const STORAGE_KEY = "kds.device";
/** Safety net when a frame is missed. Live tickets arrive on the station socket. */
const POLL_MS = 15000;

interface KdsDevice {
  token: string;
  store_id: string;
  store_name: string;
  register_name: string;
}

interface Activation {
  device_token: string;
  store_id: string;
  store_name: string;
  register_name: string;
}

function loadDevice(): KdsDevice | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as KdsDevice) : null;
  } catch {
    return null;
  }
}

function stationFromPath(): string | null {
  const match = /^\/kds\/([0-9a-f-]{36})/i.exec(window.location.pathname);
  return match ? match[1]! : null;
}

function errorText(caught: unknown, fallback: string): string {
  return caught instanceof Error && caught.message ? caught.message : fallback;
}

/** Kitchen display: a full-screen board for one station, signed in once with a register activation key. */
export function KdsApp() {
  const [device, setDevice] = useState<KdsDevice | null>(loadDevice);
  const [stationId, setStationId] = useState<string | null>(stationFromPath);

  const choose = useCallback((id: string | null) => {
    window.history.pushState(null, "", id ? `/kds/${id}` : "/kds");
    setStationId(id);
  }, []);

  const forget = useCallback(() => {
    window.localStorage.removeItem(STORAGE_KEY);
    setDevice(null);
  }, []);

  if (device === null) {
    return (
      <Activate
        onActivated={(next) => {
          window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
          setDevice(next);
        }}
      />
    );
  }
  if (stationId === null) return <StationPicker device={device} onChoose={choose} onForget={forget} />;
  return <Board device={device} stationId={stationId} onLeave={() => choose(null)} onForget={forget} />;
}

function Shell({ children }: { children: ReactNode }) {
  return <div className="min-h-screen bg-zinc-950 text-zinc-100">{children}</div>;
}

function Activate({ onActivated }: { onActivated: (device: KdsDevice) => void }) {
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await apiPublicPost<Activation>("/api/v1/terminals/activate", {
        activation_key: key.trim(),
        machine_name: "Kitchen display",
      });
      onActivated({
        token: result.device_token,
        store_id: result.store_id,
        store_name: result.store_name,
        register_name: result.register_name,
      });
    } catch (caught) {
      setError(errorText(caught, "Could not activate this screen."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Shell>
      <form onSubmit={(event) => void submit(event)} className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-4 p-6">
        <ChefHat size={40} className="text-amber-400" aria-hidden="true" />
        <h1 className="text-3xl font-semibold">Kitchen display</h1>
        <p className="text-sm text-zinc-400">
          In the portal, open Registers, add a register for this screen and issue an activation key. Enter it here once;
          the screen stays signed in.
        </p>
        <label className="text-sm font-medium" htmlFor="kds-key">
          Activation key
        </label>
        <input
          id="kds-key"
          value={key}
          onChange={(event) => setKey(event.target.value)}
          autoComplete="off"
          className="h-14 rounded-xl border border-zinc-700 bg-zinc-900 px-4 text-xl tracking-widest outline-none focus:border-amber-400"
          placeholder="ABCD-EFGH-JKLM"
        />
        {error ? <p className="rounded-lg bg-red-500/15 px-3 py-2 text-sm text-red-300">{error}</p> : null}
        <button
          type="submit"
          disabled={busy || key.trim().length < 8}
          className="h-14 rounded-xl bg-amber-400 text-lg font-semibold text-zinc-950 disabled:opacity-50"
        >
          {busy ? "Activating…" : "Activate"}
        </button>
      </form>
    </Shell>
  );
}

function StationPicker({
  device,
  onChoose,
  onForget,
}: {
  device: KdsDevice;
  onChoose: (id: string) => void;
  onForget: () => void;
}) {
  const [stations, setStations] = useState<KitchenStation[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiTerminal<KitchenStation[]>("GET", `/api/v1/kds/stations?store_id=${device.store_id}`, device.token)
      .then((rows) => setStations(rows.filter((station) => station.is_active)))
      .catch((caught: unknown) => {
        if (caught instanceof ApiRequestError && caught.status === 401) onForget();
        setError(errorText(caught, "Could not load the kitchen stations."));
      });
  }, [device, onForget]);

  return (
    <Shell>
      <div className="mx-auto max-w-3xl p-8">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-semibold">Pick a station</h1>
            <p className="mt-1 text-sm text-zinc-400">{device.store_name}</p>
          </div>
          <button type="button" onClick={onForget} className="flex items-center gap-2 text-sm text-zinc-400 hover:text-zinc-100">
            <LogOut size={16} aria-hidden="true" /> Sign out screen
          </button>
        </div>
        {error ? <p className="mt-6 rounded-lg bg-red-500/15 px-3 py-2 text-sm text-red-300">{error}</p> : null}
        {stations !== null && stations.length === 0 ? (
          <p className="mt-6 text-zinc-400">No stations yet. Add them in the portal under Inventory, Kitchen stations.</p>
        ) : null}
        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          {(stations ?? []).map((station) => (
            <button
              key={station.id}
              type="button"
              onClick={() => onChoose(station.id)}
              className="rounded-2xl border border-zinc-800 bg-zinc-900 p-6 text-left text-2xl font-semibold hover:border-amber-400"
            >
              {station.name}
              {station.is_default ? <span className="ml-2 text-sm font-normal text-zinc-400">default</span> : null}
            </button>
          ))}
        </div>
      </div>
    </Shell>
  );
}

const AGE_STYLE: Record<TicketAge, string> = {
  fresh: "border-zinc-700",
  warn: "border-amber-400",
  late: "border-red-500",
};
const AGE_HEADER: Record<TicketAge, string> = {
  fresh: "bg-zinc-800",
  warn: "bg-amber-400 text-zinc-950",
  late: "bg-red-600 text-white",
};
const ACTION_LABEL: Record<string, string> = { NEW: "Start", PREPARING: "Ready", READY: "Bump" };

function elapsed(from: string, now: number): string {
  const seconds = Math.max(0, Math.floor((now - Date.parse(from)) / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function chime() {
  try {
    const context = new AudioContext();
    const tone = context.createOscillator();
    const gain = context.createGain();
    tone.frequency.value = 880;
    gain.gain.value = 0.08;
    tone.connect(gain).connect(context.destination);
    tone.start();
    tone.stop(context.currentTime + 0.25);
  } catch {
    // Audio is optional (some browsers block it until the screen is tapped).
  }
}

function Board({
  device,
  stationId,
  onLeave,
  onForget,
}: {
  device: KdsDevice;
  stationId: string;
  onLeave: () => void;
  onForget: () => void;
}) {
  const [tickets, setTickets] = useState<KitchenTicket[]>([]);
  const [meta, setMeta] = useState<Pick<KitchenBoard, "station" | "warn_minutes" | "late_minutes"> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState(0);
  const [now, setNow] = useState(() => Date.now());
  const since = useRef<string | null>(null);
  const known = useRef(new Set<string>());
  const snapshots = useRef(new Map<string, KitchenTicket>());
  const sendStatus = useRef<(ticketId: string, status: KitchenTicket["status"]) => boolean>(() => false);

  const poll = useCallback(async () => {
    const query = since.current ? `?since=${encodeURIComponent(since.current)}` : "";
    try {
      const board = await apiTerminal<KitchenBoard>("GET", `/api/v1/kds/stations/${stationId}/tickets${query}`, device.token);
      since.current = board.server_time;
      setMeta({ station: board.station, warn_minutes: board.warn_minutes, late_minutes: board.late_minutes });
      const fresh = board.tickets.filter((ticket) => !known.current.has(ticket.id));
      for (const ticket of board.tickets) known.current.add(ticket.id);
      if (query && fresh.some((ticket) => ticket.status === "NEW")) chime();
      setTickets((current) => mergeBoard(current, board.tickets));
      setError(null);
    } catch (caught) {
      if (caught instanceof ApiRequestError && caught.status === 401) onForget();
      setError(errorText(caught, "Connection lost; retrying."));
    }
  }, [device.token, onForget, stationId]);

  useEffect(() => {
    since.current = null;
    known.current = new Set();
    setTickets([]);
    void poll();
    const timer = window.setInterval(() => void poll(), POLL_MS);
    const clock = window.setInterval(() => setNow(Date.now()), 1000);
    const stationSocket = listenForStation(
      stationId,
      device.token,
      (event) => {
        if (event.type === "kitchen:status-rejected") {
          const previous = event.ticket_id ? snapshots.current.get(event.ticket_id) : undefined;
          if (event.ticket_id) snapshots.current.delete(event.ticket_id);
          if (previous) setTickets((current) => mergeBoard(current, [previous]));
          setError(event.message ?? "Could not update the ticket.");
          void poll();
          return;
        }
        const ticket = event.ticket;
        if (!ticket || ticket.station_id !== stationId) return;
        if (event.type === "kitchen:new-order" && ticket.status === "NEW" && !known.current.has(ticket.id)) chime();
        known.current.add(ticket.id);
        snapshots.current.delete(ticket.id);
        setTickets((current) => mergeBoard(current, [ticket]));
      },
      () => {
        since.current = null;
        void poll();
      },
    );
    sendStatus.current = stationSocket.sendStatus;
    return () => {
      stationSocket.stop();
      window.clearInterval(timer);
      window.clearInterval(clock);
    };
  }, [device.token, poll, stationId]);

  const live = useMemo(() => tickets.filter((ticket) => ticket.status !== "BUMPED"), [tickets]);
  const bumped = useMemo(
    () => tickets.filter((ticket) => ticket.status === "BUMPED").sort((a, b) => (b.bumped_at ?? "").localeCompare(a.bumped_at ?? "")),
    [tickets],
  );

  const replace = useCallback((ticket: KitchenTicket) => {
    setTickets((current) => mergeBoard(current, [ticket]));
  }, []);

  const advance = useCallback(
    async (ticket: KitchenTicket) => {
      const next = NEXT_TICKET_STATUS[ticket.status];
      if (next === null) return;
      snapshots.current.set(ticket.id, ticket);
      replace({ ...ticket, status: next });
      if (sendStatus.current(ticket.id, next)) return;
      try {
        const saved = await apiTerminal<KitchenTicket>("POST", `/api/v1/kds/tickets/${ticket.id}/status`, device.token, { status: next });
        snapshots.current.delete(ticket.id);
        replace(saved);
      } catch (caught) {
        const previous = snapshots.current.get(ticket.id);
        if (previous) replace(previous);
        snapshots.current.delete(ticket.id);
        setError(errorText(caught, "Could not update the ticket."));
        void poll();
      }
    },
    [device.token, poll, replace],
  );

  const recall = useCallback(
    async (ticket: KitchenTicket) => {
      try {
        replace(await apiTerminal<KitchenTicket>("POST", `/api/v1/kds/tickets/${ticket.id}/recall`, device.token));
      } catch (caught) {
        setError(errorText(caught, "Could not recall the ticket."));
      }
    },
    [device.token, replace],
  );

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.target instanceof HTMLInputElement) return;
      const digit = Number(event.key);
      if (Number.isInteger(digit) && digit >= 1 && digit <= 9) {
        const ticket = live[digit - 1];
        if (ticket) {
          setSelected(digit - 1);
          void advance(ticket);
        }
      } else if (event.key === "ArrowRight") {
        setSelected((index) => Math.min(index + 1, Math.max(live.length - 1, 0)));
      } else if (event.key === "ArrowLeft") {
        setSelected((index) => Math.max(index - 1, 0));
      } else if (event.key === "Enter" || event.key === " ") {
        const ticket = live[selected];
        if (ticket) {
          event.preventDefault();
          void advance(ticket);
        }
      } else if (event.key.toLowerCase() === "r" && bumped[0]) {
        void recall(bumped[0]);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [advance, bumped, live, recall, selected]);

  const warn = meta?.warn_minutes ?? 8;
  const late = meta?.late_minutes ?? 15;

  return (
    <Shell>
      <header className="flex items-center gap-4 border-b border-zinc-800 px-5 py-3">
        <ChefHat size={22} className="text-amber-400" aria-hidden="true" />
        <h1 className="text-xl font-semibold">{meta?.station.name ?? "Kitchen"}</h1>
        <span className="text-sm text-zinc-400">
          {live.length} open · {device.store_name}
        </span>
        {error ? <span className="rounded-full bg-red-500/20 px-3 py-1 text-xs text-red-300">{error}</span> : null}
        <div className="ml-auto flex items-center gap-2">
          {bumped[0] ? (
            <button
              type="button"
              onClick={() => void recall(bumped[0]!)}
              className="flex h-9 items-center gap-1.5 rounded-lg border border-zinc-700 px-3 text-sm hover:border-amber-400"
              title="Bring back the last bumped ticket (R)"
            >
              <RotateCcw size={14} aria-hidden="true" /> Recall #{bumped[0].number}
            </button>
          ) : null}
          <button type="button" onClick={onLeave} className="h-9 rounded-lg border border-zinc-700 px-3 text-sm hover:border-zinc-400">
            Stations
          </button>
        </div>
      </header>
      {live.length === 0 ? (
        <p className="p-10 text-center text-lg text-zinc-500">No open tickets. New orders appear here as they are sent.</p>
      ) : (
        <div className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
          {live.map((ticket, index) => {
            const age = ticketAge(ticket.fired_at, now, warn, late);
            return (
              <article
                key={ticket.id}
                className={`flex flex-col overflow-hidden rounded-2xl border-2 bg-zinc-900 ${AGE_STYLE[age]} ${
                  index === selected ? "ring-2 ring-sky-400" : ""
                }`}
              >
                <div className={`flex items-baseline justify-between px-4 py-2 ${AGE_HEADER[age]}`}>
                  <span className="text-lg font-bold">
                    {index < 9 ? <span className="mr-2 text-xs opacity-70">{index + 1}</span> : null}#{ticket.number} {ticket.label}
                  </span>
                  <span className="font-mono text-lg tabular-nums">{elapsed(ticket.fired_at, now)}</span>
                </div>
                <ul className="flex-1 space-y-2 px-4 py-3">
                  {ticket.items.map((item) => (
                    <li key={item.id} className={item.voided_at ? "text-zinc-500 line-through" : ""}>
                      <div className="flex gap-2 text-lg">
                        <span className="font-bold">{item.quantity}×</span>
                        <span>{item.product_name}</span>
                        {item.seat ? <span className="ml-auto text-xs text-zinc-400">seat {item.seat}</span> : null}
                      </div>
                      {item.combo_name ? <p className="ml-7 text-xs text-zinc-400">for {item.combo_name}</p> : null}
                      {item.modifiers.length > 0 ? (
                        <p className="ml-7 font-bold text-amber-300">{modifierSummary(item.modifiers)}</p>
                      ) : null}
                      {item.note ? <p className="ml-7 italic text-zinc-300">“{item.note}”</p> : null}
                    </li>
                  ))}
                </ul>
                <div className="flex items-center gap-2 border-t border-zinc-800 px-4 py-2 text-xs text-zinc-400">
                  <span>{ticket.service_type.replace("_", " ").toLowerCase()}</span>
                  <span className="ml-auto uppercase tracking-wide">{ticket.status.toLowerCase()}</span>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setSelected(index);
                    void advance(ticket);
                  }}
                  className={`h-14 text-lg font-semibold ${
                    ticket.status === "READY" ? "bg-emerald-500 text-zinc-950" : "bg-zinc-800 hover:bg-zinc-700"
                  }`}
                >
                  {ACTION_LABEL[ticket.status]}
                </button>
              </article>
            );
          })}
        </div>
      )}
    </Shell>
  );
}
