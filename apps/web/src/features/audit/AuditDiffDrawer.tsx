import { diffAuditValues, type AuditLogDetail, type AuditLogRow, type FieldChange } from "@ai-pos/shared-types";
import { Braces, ChevronDown, Copy, ShieldAlert, X } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { useAuditEntry } from "./api";
import { ActionBadge, Avatar, DeviceLabel, formatStamp } from "./AuditParts";

const changeStyles: Record<FieldChange, { pill: string; label: string; row: string }> = {
  modified: { pill: "bg-accent/10 text-accent", label: "Modified", row: "border-l-accent" },
  added: { pill: "bg-accent text-white", label: "Added", row: "border-l-accent" },
  removed: { pill: "bg-charcoal text-white", label: "Removed", row: "border-l-charcoal" },
  unchanged: { pill: "bg-surface text-charcoal/50", label: "Same", row: "border-l-transparent" },
};

function Value({ value, tone }: { value: unknown; tone: "before" | "after" | "plain" }) {
  if (value === undefined) return <span className="text-charcoal/30">—</span>;
  if (value === null) return <span className="italic text-charcoal/40">null</span>;
  const text = typeof value === "object" ? JSON.stringify(value, null, 2) : String(value);
  const color =
    tone === "before" ? "text-charcoal/50 line-through decoration-charcoal/30" : tone === "after" ? "text-accent" : "";
  const isBlock = typeof value === "object" || text.length > 48;
  return isBlock ? (
    <pre className={`whitespace-pre-wrap break-all font-mono text-[12px] leading-relaxed ${color}`}>{text}</pre>
  ) : (
    <span className={`break-all font-mono text-[12.5px] font-medium tabular-nums ${color}`}>{text}</span>
  );
}

function DiffTable({ entry }: { entry: AuditLogDetail }) {
  const [showSame, setShowSame] = useState(false);
  const rows = useMemo(() => diffAuditValues(entry.old_values, entry.new_values), [entry]);
  const changed = rows.filter((row) => row.change !== "unchanged");
  const same = rows.length - changed.length;
  const visible = showSame ? rows : changed;
  const counts = (["modified", "added", "removed"] as const).map((kind) => ({
    kind,
    count: changed.filter((row) => row.change === kind).length,
  }));

  if (rows.length === 0) {
    return (
      <p className="rounded-2xl border border-dashed border-line p-5 text-sm text-charcoal/60">
        This entry has no field snapshot. See the event details below.
      </p>
    );
  }

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {counts
          .filter((item) => item.count > 0)
          .map((item) => (
            <span
              key={item.kind}
              className={`rounded-full px-2.5 py-1 text-[11px] font-semibold tabular-nums ${changeStyles[item.kind].pill}`}
            >
              {item.count} {changeStyles[item.kind].label.toLowerCase()}
            </span>
          ))}
        {same > 0 ? (
          <button
            type="button"
            onClick={() => setShowSame((value) => !value)}
            className="ml-auto inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold text-charcoal/60 transition hover:bg-surface hover:text-charcoal"
            aria-expanded={showSame}
          >
            {showSame ? "Hide" : "Show"} {same} unchanged
            <ChevronDown size={13} className={`transition ${showSame ? "rotate-180" : ""}`} aria-hidden="true" />
          </button>
        ) : null}
      </div>
      <div className="overflow-hidden rounded-2xl border border-line">
        <div className="grid grid-cols-[minmax(0,0.9fr)_minmax(0,1fr)_minmax(0,1fr)] bg-charcoal px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wider text-white/70">
          <span>Field</span>
          <span>Before</span>
          <span>After</span>
        </div>
        <ul className="divide-y divide-line">
          {visible.map((row) => (
            <li
              key={row.field}
              className={`grid grid-cols-[minmax(0,0.9fr)_minmax(0,1fr)_minmax(0,1fr)] gap-3 border-l-[3px] px-4 py-3 ${
                changeStyles[row.change].row
              } ${row.change === "unchanged" ? "bg-surface/40" : "bg-white"}`}
            >
              <span className="min-w-0">
                <span className="block break-all font-mono text-[12px] font-semibold text-charcoal">{row.field}</span>
                <span
                  className={`mt-1 inline-block rounded-full px-2 py-0.5 text-[10px] font-semibold ${changeStyles[row.change].pill}`}
                >
                  {changeStyles[row.change].label}
                </span>
              </span>
              <span className="min-w-0">
                <Value value={row.before} tone={row.change === "unchanged" ? "plain" : "before"} />
              </span>
              <span className="min-w-0">
                <Value
                  value={row.after}
                  tone={row.change === "unchanged" ? "plain" : row.change === "removed" ? "plain" : "after"}
                />
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function JsonPanel({ title, value, accent = false }: { title: string; value: unknown; accent?: boolean }) {
  const text = value === null || value === undefined ? "null" : JSON.stringify(value, null, 2);
  return (
    <div className="min-w-0">
      <div className="mb-1.5 flex items-center justify-between">
        <span className={`text-[11px] font-semibold uppercase tracking-wider ${accent ? "text-accent" : "text-charcoal/50"}`}>
          {title}
        </span>
        <button
          type="button"
          onClick={() => void navigator.clipboard?.writeText(text)}
          className="grid h-7 w-7 place-items-center rounded-full text-charcoal/50 transition hover:bg-surface hover:text-charcoal"
          aria-label={`Copy ${title} JSON`}
          title="Copy JSON"
        >
          <Copy size={13} aria-hidden="true" />
        </button>
      </div>
      <pre
        className={`max-h-72 overflow-auto rounded-2xl p-3 font-mono text-[11.5px] leading-relaxed ${
          accent ? "bg-charcoal text-white" : "bg-surface text-charcoal"
        }`}
      >
        {text}
      </pre>
    </div>
  );
}

function Meta({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0 rounded-2xl bg-surface px-4 py-3">
      <p className="text-[11px] font-medium uppercase tracking-wide text-charcoal/50">{label}</p>
      <div className="mt-1 truncate text-sm font-semibold">{children}</div>
    </div>
  );
}

export function AuditDiffDrawer({
  row,
  closing,
  onClose,
}: {
  row: AuditLogRow;
  closing: boolean;
  onClose: () => void;
}) {
  const loaded = useAuditEntry(row.id);
  const entry = loaded.state === "ready" && loaded.data.id === row.id ? loaded.data : null;
  const [raw, setRaw] = useState(false);
  const panelRef = useRef<HTMLElement>(null);
  const titleId = useId();
  const stamp = formatStamp(row.occurred_at);
  const lag = entry ? (new Date(entry.created_at).getTime() - new Date(entry.occurred_at).getTime()) / 60_000 : 0;

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    panelRef.current?.focus({ preventScroll: true });
  }, [row.id]);

  useEffect(() => {
    const overlay = window.matchMedia("(max-width: 1023px)");
    const apply = () => {
      document.body.style.overflow = overlay.matches ? "hidden" : "";
    };
    apply();
    overlay.addEventListener("change", apply);
    return () => {
      overlay.removeEventListener("change", apply);
      document.body.style.overflow = "";
    };
  }, []);

  return (
    <>
      <div
        className={`drawer-backdrop fixed inset-0 z-40 bg-charcoal/40 backdrop-blur-[8px] lg:hidden ${closing ? "opacity-0" : ""}`}
        onClick={onClose}
        aria-hidden="true"
      />
      <aside
        ref={panelRef}
        tabIndex={-1}
        role="dialog"
        aria-labelledby={titleId}
        data-state={closing ? "closing" : "open"}
        className="drawer-panel fixed inset-y-0 right-0 z-40 flex w-full flex-col overflow-hidden bg-white shadow-2xl outline-none sm:max-w-xl md:max-w-2xl split-drawer-h lg:sticky lg:top-8 lg:z-auto lg:w-auto lg:min-w-0 lg:max-w-none lg:basis-[46%] lg:self-start lg:rounded-card lg:border lg:border-line lg:shadow-none"
      >
        <header className="sticky top-0 z-20 flex-none border-b border-line bg-white px-5 pb-4 pt-5 sm:px-6">
          <div className="flex items-start justify-between gap-3">
            <div className="flex min-w-0 flex-wrap items-center gap-1.5">
              <ActionBadge type={row.action_type} />
              <span className="rounded-full bg-surface px-2.5 py-1 font-mono text-[11px] font-semibold text-charcoal/70">
                {row.action}
              </span>
              {row.sensitive ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-charcoal px-2.5 py-1 text-[11px] font-semibold text-white">
                  <ShieldAlert size={12} aria-hidden="true" /> Sensitive
                </span>
              ) : null}
            </div>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close panel"
              title="Close panel (Esc)"
              className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-charcoal text-white transition hover:bg-accent"
            >
              <X size={17} aria-hidden="true" />
            </button>
          </div>
          <h3 id={titleId} className="mt-3 text-2xl font-bold leading-tight tracking-tight">
            {row.target_entity}
            {row.target_entity_id ? (
              <span className="ml-2 align-middle font-mono text-sm font-semibold text-charcoal/40">
                #{row.target_entity_id.slice(0, 8)}
              </span>
            ) : null}
          </h3>
          <p className="mt-1 text-sm tabular-nums text-charcoal/60">
            {stamp.day} · {stamp.time}
          </p>
        </header>

        <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-5 py-5 sm:px-6">
          <div className="flex items-center gap-3 rounded-2xl bg-charcoal p-4 text-white">
            <Avatar name={row.user_name} />
            <div className="min-w-0 flex-1">
              <p className="truncate font-semibold">{row.user_name ?? "System"}</p>
              <p className="truncate text-xs text-white/60">
                {row.user_role ?? "No role"}
                {row.store_code ? ` · ${row.store_code}` : " · Business-wide"}
              </p>
            </div>
            {row.approver_name ? (
              <div className="min-w-0 text-right">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-white/50">Approved by</p>
                <p className="truncate text-sm font-semibold text-accent">{row.approver_name}</p>
              </div>
            ) : null}
          </div>

          {row.reason_notes ? (
            <div className="rounded-2xl border border-accent/30 bg-accent/5 px-4 py-3">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-accent">Reason / notes</p>
              <p className="mt-1 text-sm text-charcoal">{row.reason_notes}</p>
            </div>
          ) : row.sensitive ? (
            <p className="rounded-2xl border border-dashed border-warning/40 px-4 py-3 text-sm text-warning">
              No reason was recorded for this sensitive action.
            </p>
          ) : null}

          <div className="grid grid-cols-2 gap-3">
            <Meta label="Device">
              <DeviceLabel device={row.client_device} />
            </Meta>
            <Meta label="IP address">
              <span className="font-mono text-[13px]">{row.ip_address ?? "—"}</span>
            </Meta>
            <Meta label="Branch">{row.store_name ?? "Business-wide"}</Meta>
            <Meta label="Recorded">
              <span className="tabular-nums">
                {entry && lag >= 1 ? `Synced ${Math.round(lag).toLocaleString()} min later` : "Immediately"}
              </span>
            </Meta>
          </div>

          <section>
            <div className="mb-3 flex items-end justify-between gap-3">
              <div>
                <h4 className="text-lg font-semibold">Changes</h4>
                <p className="text-sm text-charcoal/60">
                  <span className="font-semibold text-accent">Orange</span> is the new value,{" "}
                  <span className="font-semibold text-charcoal">charcoal</span> what was removed.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setRaw((value) => !value)}
                aria-pressed={raw}
                className={`inline-flex h-9 shrink-0 items-center gap-1.5 rounded-full border px-3.5 text-xs font-semibold transition ${
                  raw ? "border-charcoal bg-charcoal text-white" : "border-line bg-white hover:border-charcoal"
                }`}
              >
                <Braces size={14} aria-hidden="true" /> Raw JSON
              </button>
            </div>
            {loaded.state === "error" ? (
              <p className="rounded-2xl bg-danger/10 px-4 py-3 text-sm text-danger" role="alert">
                {loaded.message}
              </p>
            ) : entry === null ? (
              <div className="space-y-2" aria-busy="true">
                {[0, 1, 2].map((index) => (
                  <div key={index} className="h-14 animate-pulse rounded-2xl bg-surface" />
                ))}
              </div>
            ) : raw ? (
              <div className="grid gap-3 xl:grid-cols-2">
                <JsonPanel title="Before" value={entry.old_values} />
                <JsonPanel title="After" value={entry.new_values} accent />
              </div>
            ) : (
              <DiffTable entry={entry} />
            )}
          </section>

          {entry && Object.keys(entry.details).length > 0 ? (
            <section>
              <h4 className="mb-2 text-lg font-semibold">Event details</h4>
              <JsonPanel title="Details" value={entry.details} />
            </section>
          ) : null}

          {entry ? (
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 border-t border-line pt-4 text-xs text-charcoal/50">
              <dt>Entry ID</dt>
              <dd className="break-all font-mono">{entry.id}</dd>
              {entry.target_entity_id ? (
                <>
                  <dt>Target ID</dt>
                  <dd className="break-all font-mono">{entry.target_entity_id}</dd>
                </>
              ) : null}
              {entry.request_path ? (
                <>
                  <dt>Request</dt>
                  <dd className="break-all font-mono">{entry.request_path}</dd>
                </>
              ) : null}
              {entry.client_event_id ? (
                <>
                  <dt>Register event</dt>
                  <dd className="break-all font-mono">{entry.client_event_id}</dd>
                </>
              ) : null}
            </dl>
          ) : null}
        </div>
      </aside>
    </>
  );
}
