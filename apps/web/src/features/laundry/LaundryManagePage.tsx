import { useEffect, useState } from "react";
import { ApiRequestError, apiGet, apiPatch, apiPost, apiPut } from "../../lib/api";

type Section = "production" | "workflows" | "batches" | "machines" | "quality" | "incidents" | "reports";

interface Board {
  received_today: number;
  awaiting_sorting: number;
  processing: number;
  active_batches: number;
  active_cycles: number;
  qc_pending: number;
  rework_pending: number;
  packing_pending: number;
  ready_orders: number;
  overdue: number;
  open_incidents: number;
}
interface Workflow { id: string; code: string; name: string; stages: string[]; is_active: boolean }
interface Machine { id: string; code: string; name: string; machine_type: string; status: string; store_id: string; version: number; capacity: number | null }
interface Batch { id: string; code: string; workflow_code: string; status: string; item_count: number; load_weight: number | null }
interface Incident { id: string; kind: string; status: string; description: string; blocks_ready: boolean }

export function LaundryManagePage({ section }: { section: Section }) {
  const [board, setBoard] = useState<Board | null>(null);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [machines, setMachines] = useState<Machine[]>([]);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [message, setMessage] = useState("");
  const [stages, setStages] = useState("RECEIVED\nTAGGED\nSORTING\nQUALITY_CHECK\nPACKING\nREADY_FOR_COLLECTION");
  const [machineName, setMachineName] = useState("");
  const [storeId, setStoreId] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load(): Promise<void> {
      try {
        if (section === "production" || section === "reports" || section === "quality") {
          const next = await apiGet<Board>("/api/v1/laundry/production/board");
          if (!cancelled) setBoard(next);
        }
        if (section === "workflows") {
          const next = await apiGet<Workflow[]>("/api/v1/laundry/production/workflows");
          if (!cancelled) setWorkflows(next);
        }
        if (section === "machines") {
          const next = await apiGet<Machine[]>("/api/v1/laundry/production/machines");
          if (!cancelled) setMachines(next);
        }
        if (section === "batches") {
          const next = await apiGet<Batch[]>("/api/v1/laundry/production/batches");
          if (!cancelled) setBatches(next);
        }
        if (section === "incidents") {
          const next = await apiGet<Incident[]>("/api/v1/laundry/production/incidents");
          if (!cancelled) setIncidents(next);
        }
        if (!cancelled) setMessage("");
      } catch (error) {
        if (!cancelled) setMessage(error instanceof ApiRequestError ? error.message : "The laundry desk could not be loaded.");
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [section]);

  async function saveWorkflow(code: string): Promise<void> {
    const saved = await apiPut<Workflow>(`/api/v1/laundry/production/workflows/${code}`, {
      name: code.replaceAll("_", " "),
      stages: stages.split(/\s+/).filter(Boolean),
      is_active: true,
    });
    setWorkflows((current) => [...current.filter((item) => item.code !== saved.code), saved]);
  }

  async function addMachine(): Promise<void> {
    const created = await apiPost<Machine>("/api/v1/laundry/production/machines", {
      code: machineName.trim().toUpperCase().replaceAll(" ", "-"),
      name: machineName,
      machine_type: "OTHER",
      store_id: storeId,
      capacity: null,
    });
    setMachines((current) => [...current, created]);
  }

  async function takeDown(machine: Machine): Promise<void> {
    const updated = await apiPatch<Machine>(`/api/v1/laundry/production/machines/${machine.id}`, {
      status: "MAINTENANCE",
      maintenance_note: "Taken down from the management desk",
      version: machine.version,
    });
    setMachines((current) => current.map((item) => (item.id === updated.id ? updated : item)));
  }

  const counts = board
    ? [
        ["Received today", board.received_today],
        ["Awaiting sort", board.awaiting_sorting],
        ["Processing", board.processing],
        ["Active batches", board.active_batches],
        ["Active cycles", board.active_cycles],
        ["QC pending", board.qc_pending],
        ["Rework", board.rework_pending],
        ["Packing", board.packing_pending],
        ["Ready", board.ready_orders],
        ["Overdue", board.overdue],
        ["Incidents", board.open_incidents],
      ]
    : [];

  const titles: Record<Section, string> = {
    production: "Production oversight",
    workflows: "Workflow templates",
    batches: "Batch supervision",
    machines: "Machine registry",
    quality: "Quality review",
    incidents: "Incident investigation",
    reports: "Production report",
  };

  return (
    <section className="space-y-4">
      <header>
        <p className="text-xs font-semibold uppercase tracking-wide text-charcoal/50">Laundry management</p>
        <h1 className="text-2xl font-semibold text-charcoal">{titles[section]}</h1>
        <p className="text-sm text-charcoal/70">Business Pro configures and supervises. Routine scanning, sorting, cycles, inspection, and packing stay on the register.</p>
      </header>
      {message ? <p role="alert" className="rounded-card border border-line bg-white p-3 text-sm">{message}</p> : null}
      {counts.length > 0 ? (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {counts.map(([label, value]) => (
            <article key={label} className="rounded-card border border-line bg-white p-4">
              <p className="text-sm text-charcoal/60">{label}</p>
              <p className="text-3xl font-semibold">{value}</p>
            </article>
          ))}
        </div>
      ) : null}
      {section === "quality" ? <p className="text-sm text-charcoal/70">Inspections are recorded on the register. This page shows how many garments are waiting for quality check.</p> : null}
      {section === "reports" ? <p className="text-sm text-charcoal/70">These counts come from the same production board the register uses.</p> : null}
      {section === "workflows" ? (
        <form
          className="space-y-2"
          onSubmit={(event) => {
            event.preventDefault();
            void saveWorkflow("CUSTOM").catch((error: unknown) => setMessage(error instanceof Error ? error.message : "Save failed"));
          }}
        >
          <ul className="space-y-2">
            {workflows.map((item) => (
              <li key={item.id} className="rounded-card border border-line bg-white p-3 text-sm">{item.code}: {item.stages.join(" → ")}</li>
            ))}
          </ul>
          <textarea aria-label="Workflow stages" className="min-h-32 w-full rounded-card border border-line p-3" value={stages} onChange={(event) => setStages(event.target.value)} />
          <button type="submit" className="rounded-card bg-ink px-4 py-2 text-white">Save custom workflow</button>
        </form>
      ) : null}
      {section === "machines" ? (
        <div className="space-y-3">
          <ul className="space-y-2">
            {machines.map((item) => (
              <li key={item.id} className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-line bg-white p-3">
                <span>{item.code} · {item.name} · {item.machine_type} · {item.status}{item.capacity === null ? "" : ` · capacity ${item.capacity}`}</span>
                <button type="button" className="min-h-11 text-sm underline" onClick={() => void takeDown(item)}>Mark maintenance</button>
              </li>
            ))}
          </ul>
          {machines.length === 0 ? <p className="text-sm text-charcoal/60">No machines are registered for this tenant.</p> : null}
          <form
            className="flex gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              void addMachine().catch((error: unknown) => setMessage(error instanceof Error ? error.message : "Save failed"));
            }}
          >
            <input aria-label="Machine name" className="rounded-card border border-line px-3 py-2" value={machineName} onChange={(event) => setMachineName(event.target.value)} />
            <input aria-label="Branch id" className="rounded-card border border-line px-3 py-2" value={storeId} onChange={(event) => setStoreId(event.target.value)} placeholder="Branch id" />
            <button type="submit" className="rounded-card bg-ink px-4 py-2 text-white">Register machine</button>
          </form>
        </div>
      ) : null}
      {section === "batches" ? (
        <>
          <ul className="space-y-2">
            {batches.map((item) => (
              <li key={item.id} className="rounded-card border border-line bg-white p-3 text-sm">{item.code} · {item.workflow_code} · {item.status} · {item.item_count} items · load {item.load_weight ?? "not measured"}</li>
            ))}
          </ul>
          {batches.length === 0 ? <p className="text-sm text-charcoal/60">No batches yet. The register creates batches during production.</p> : null}
        </>
      ) : null}
      {section === "incidents" ? (
        <>
          <ul className="space-y-2">
            {incidents.map((item) => (
              <li key={item.id} className="rounded-card border border-line bg-white p-3 text-sm">{item.kind} · {item.status} · {item.blocks_ready ? "holding ready" : "not holding"} · {item.description}</li>
            ))}
          </ul>
          {incidents.length === 0 ? <p className="text-sm text-charcoal/60">No incidents are open. Compensation still uses the existing finance permissions.</p> : null}
        </>
      ) : null}
    </section>
  );
}
