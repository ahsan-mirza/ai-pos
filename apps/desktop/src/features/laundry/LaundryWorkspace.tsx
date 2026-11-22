import { Permission } from "@ai-pos/shared-types";
import { useEffect, useMemo, useState } from "react";
import { PageFrame } from "../../components/shell/RegisterShell";
import { inventoryContentClass, inventoryWorkspaceClass } from "../inventory/layout";
import { PinUnlock } from "../auth/PinUnlock";
import type { CashierSession } from "../auth/session";
import { SyncCenterModal } from "../sync/SyncCenterModal";
import { dashboardPhase, laundryCall, noticeFromError, registerSignedIn, sessionHeadline, type FloorNotice } from "./diagnostics";
import { filterReady, nextActionCopy, packingProgress, priorityWork, productionColumns, recentGarments, reworkRate, stageDistribution, type FloorGarment, type ReadyFilter } from "./floorModel";
import { LaundryActiveOrders, LaundryCataloguePage, LaundryCustomersPage } from "./LaundryReferencePages";
import { isSettingsHash } from "../../components/shell/settingsEntry";
import { defaultStation, openingStation, primaryTabs, secondaryTabs, sectionOf, workspaceDestinations, type LaundrySection } from "./laundryNav";
import { laundryLocation, laundryStationFromLocation } from "./laundryRoute";
import { nextScrollTop, scrollingBox } from "./shellScroll";
import { LaundryIntakePage } from "./LaundryIntakePage";
import { OFFLINE_PRODUCTION, visibleStations } from "./productionAccess";
import {
  LaundryEmptyState,
  LaundryErrorState,
  LaundryExceptionPanel,
  LaundryGarmentCard,
  LaundryMetricCard,
  LaundryProductionBoard,
  LaundryScanInput,
  LaundrySectionBars,
  SelectControl,
  LaundryStatusBadge,
  LaundryTimeline,
  PrimaryButton,
  SecondaryButton,
  money,
} from "./ui";

interface GarmentCard extends FloorGarment {
  store_id: string;
  customer_phone: string;
  brand: string;
  size: string;
  version: number;
  sorting_category: string;
  station: string;
  batch_id: string | null;
  tax_cents: number;
}
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
  garments: GarmentCard[];
}
interface ScanResult { result: string; message: string; allowed_targets: string[]; garment: GarmentCard | null }
interface History {
  garment: GarmentCard;
  stages: string[];
  next_stage: string;
  allowed_targets: string[];
  events: { from_stage: string; to_stage: string; reason: string; created_at: string }[];
  inspections: { id: string; result: string; reason: string; created_at: string }[];
  incidents: { id: string; kind: string; status: string; description: string }[];
  photo_ids: string[];
  open_rework: { id: string; reason: string; required_stage: string; status: string } | null;
}
interface Shift { transitions: number; inspections: number; packed: number; incidents: number }
interface Workflow { id: string; code: string; stages: string[] }
interface Category { id: string; code: string; name: string }
interface Machine { id: string; code: string; name: string; machine_type: string; status: string; capacity: number | null; capacity_unit: string }
interface Batch { id: string; code: string; workflow_code: string; status: string; item_count: number; load_weight: number | null; store_id: string; version: number }
interface Incident { id: string; order_id: string; garment_id: string | null; kind: string; status: string; blocks_ready: boolean; description: string; resolution: string; stage: string }
const CHECKLIST = ["cleaning", "stain", "finishing", "ironing", "fabric", "buttons", "zippers", "tag", "order", "instructions"] as const;
const INCIDENT_KINDS = ["MISSING", "DAMAGED", "WRONG_TAG", "WRONG_CUSTOMER", "PROCESSING_DAMAGE", "STAIN_REMAINS", "WRONG_SERVICE", "COUNT_DISCREPANCY", "MACHINE_FAILURE"];

function cardOf(raw: Partial<GarmentCard> & Pick<GarmentCard, "id" | "order_id" | "order_code">): GarmentCard {
  return {
    store_id: "",
    customer_name: "",
    customer_phone: "",
    description: "",
    stage: "",
    workflow_code: "",
    service_name: "",
    colour: "",
    fabric: "",
    brand: "",
    size: "",
    condition: "",
    instructions: "",
    tag_code: "",
    version: 1,
    hold: false,
    qc_result: "",
    rework_count: 0,
    sorting_category: "",
    station: "",
    location: "",
    batch_id: null,
    promised_at: null,
    stage_entered_at: null,
    total_cents: 0,
    tax_cents: 0,
    amount_paid_cents: 0,
    balance_due_cents: 0,
    operational_status: "",
    ...raw,
  };
}

export function LaundryWorkspace({ session, onUnlocked }: { session: CashierSession; onUnlocked?: (session: CashierSession) => void }) {
  const permissionKey = session.user.permissions.join("\n");
  const stations = useMemo(() => visibleStations(session.user.permissions), [permissionKey]);
  const allowed = useMemo(() => workspaceDestinations(session.user.permissions).map((station) => station.id), [permissionKey]);
  const [panel, setPanel] = useState(() => openingStation(typeof window === "undefined" ? "" : window.location.hash, allowed));
  const [board, setBoard] = useState<Board | null>(null);
  const [shift, setShift] = useState<Shift | null>(null);
  const [code, setCode] = useState("");
  const [scan, setScan] = useState<ScanResult | null>(null);
  const [history, setHistory] = useState<History | null>(null);
  const [notice, setNotice] = useState<FloorNotice | null>(null);
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState("");
  const [loadWeight, setLoadWeight] = useState("");
  const [cycleCode, setCycleCode] = useState("");
  const [category, setCategory] = useState("");
  const [categories, setCategories] = useState<Category[]>([]);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [workflowCode, setWorkflowCode] = useState("");
  const [machines, setMachines] = useState<Machine[]>([]);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [machineId, setMachineId] = useState("");
  const [batchId, setBatchId] = useState("");
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [incidentKind, setIncidentKind] = useState("DAMAGED");
  const [readyFilter, setReadyFilter] = useState<ReadyFilter>("ready");
  const [boardWorkflow, setBoardWorkflow] = useState("");
  const [checks, setChecks] = useState<Record<string, boolean>>({});
  const [requiredStage, setRequiredStage] = useState("");
  const [packedIds, setPackedIds] = useState<string[]>([]);
  const [orderGarments, setOrderGarments] = useState<number>(0);
  const [bagCode, setBagCode] = useState("");
  const [syncOpen, setSyncOpen] = useState(false);
  const [unlocking, setUnlocking] = useState(false);
  const [authLost, setAuthLost] = useState(false);
  const [machinesLoaded, setMachinesLoaded] = useState(false);
  const [incidentsLoaded, setIncidentsLoaded] = useState(false);
  const offlineRegister = session.mode === "offline";
  const signedIn = registerSignedIn(session.mode) && !authLost;

  function fail(error: unknown): FloorNotice {
    console.error("laundry request failed", error);
    const next = noticeFromError(error);
    if (next.kind === "unauthenticated") setAuthLost(true);
    setNotice(next);
    return next;
  }

  async function loadBoard(): Promise<void> {
    if (!registerSignedIn(session.mode) || authLost) return;
    try {
      const next = await laundryCall<Board>("GET", "/api/v1/laundry/production/board");
      setBoard({ ...next, garments: (next.garments ?? []).map((item) => cardOf(item)) });
      setNotice((current) => (current?.tone === "session" || current?.kind === "unauthenticated" || current?.tone === "offline" ? null : current));
    } catch (error) {
      setBoard(null);
      fail(error);
    }
  }

  useEffect(() => {
    const sync = () => {
      if (isSettingsHash(window.location.hash)) return;
      const next = openingStation(window.location.hash, allowed);
      if (allowed.includes(next)) setPanel(next);
    };
    window.addEventListener("hashchange", sync);
    window.addEventListener("popstate", sync);
    return () => {
      window.removeEventListener("hashchange", sync);
      window.removeEventListener("popstate", sync);
    };
  }, [allowed]);

  useEffect(() => {
    if (allowed.length === 0 || isSettingsHash(window.location.hash)) return;
    const next = openingStation(window.location.hash, allowed);
    if (!allowed.includes(next)) return;
    if (next !== panel) {
      setPanel(next);
      return;
    }
    const current = laundryStationFromLocation(window.location.hash);
    if (current === next) return;
    const base = `${window.location.pathname}${window.location.search}`;
    window.history.replaceState({ posView: "laundry", station: next }, "", `${base}${laundryLocation(next)}`);
  }, [allowed, panel]);

  useEffect(() => {
    if (!signedIn || ["intake", "active", "services", "categories", "garment-types", "pricing", "customers"].includes(panel)) return;
    let cancelled = false;
    void laundryCall<Board>("GET", "/api/v1/laundry/production/board")
      .then((next) => {
        if (cancelled) return;
        setBoard({ ...next, garments: (next.garments ?? []).map((item) => cardOf(item)) });
        setNotice((current) => (current?.tone === "session" || current?.kind === "unauthenticated" || current?.tone === "offline" ? null : current));
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setBoard(null);
        fail(error);
      });
    return () => {
      cancelled = true;
    };
  }, [panel, signedIn]);

  useEffect(() => {
    if (signedIn) return;
    setBoard(null);
  }, [signedIn]);

  useEffect(() => {
    if (!signedIn) return;
    void laundryCall<Category[]>("GET", "/api/v1/laundry/production/categories").then((rows) => {
      setCategories(rows);
      setCategory(rows[0]?.code ?? "");
    }).catch(() => setCategories([]));
    void laundryCall<Workflow[]>("GET", "/api/v1/laundry/production/workflows").then(setWorkflows).catch(() => setWorkflows([]));
  }, [signedIn]);

  useEffect(() => {
    if (!signedIn || panel !== "machines") return;
    setMachinesLoaded(false);
    void laundryCall<Machine[]>("GET", "/api/v1/laundry/production/machines").then((rows) => {
      setMachines(rows);
      setMachinesLoaded(true);
    }).catch((error: unknown) => fail(error));
    void laundryCall<Batch[]>("GET", "/api/v1/laundry/production/batches").then(setBatches).catch((error: unknown) => fail(error));
  }, [panel, signedIn]);

  useEffect(() => {
    if (!signedIn || panel !== "incidents") return;
    setIncidentsLoaded(false);
    void laundryCall<Incident[]>("GET", "/api/v1/laundry/production/incidents").then((rows) => {
      setIncidents(rows);
      setIncidentsLoaded(true);
    }).catch((error: unknown) => fail(error));
  }, [panel, signedIn]);

  useEffect(() => {
    if (!signedIn || panel !== "shift") return;
    void laundryCall<Shift>("GET", "/api/v1/laundry/production/shift").then(setShift).catch((error: unknown) => fail(error));
  }, [panel, signedIn]);

  if (stations.length === 0) {
    return (
      <PageFrame title="Laundry" sync={{ tone: "live", label: "Live", title: "This sign-in cannot open the laundry floor." }} drawer={null}>
        <p className="p-4 text-sm text-zinc-600">This register user cannot open the laundry floor.</p>
      </PageFrame>
    );
  }

  const garment = scan?.garment ?? null;
  const now = Date.now();
  const garments = board?.garments ?? [];
  const priority = priorityWork(garments, now);
  const activeWorkflow = workflows.find((item) => item.code === (boardWorkflow || garment?.workflow_code)) ?? workflows[0];
  const columns = productionColumns(
    garments.filter((item) => !activeWorkflow || item.workflow_code === activeWorkflow.code || item.workflow_code === ""),
    activeWorkflow?.stages ?? [],
  );
  const progress = packingProgress(orderGarments, packedIds.length);
  const canResolve = session.user.permissions.includes(Permission.LaundryIncidentsResolve);
  const canBatch = session.user.permissions.includes(Permission.LaundryBatchesManage);

  async function openHistory(id: string): Promise<void> {
    const next = await laundryCall<History>("GET", `/api/v1/laundry/production/garments/${id}`);
    setHistory({ ...next, garment: cardOf(next.garment), open_rework: next.open_rework ?? null });
    setScan({ result: "valid", message: "Garment loaded.", allowed_targets: next.allowed_targets, garment: cardOf(next.garment) });
    if (next.open_rework?.required_stage) setRequiredStage(next.open_rework.required_stage);
  }

  async function lookup(): Promise<void> {
    setBusy(true);
    try {
      const found = await laundryCall<ScanResult>("POST", "/api/v1/laundry/production/scan", { code });
      setScan(found.garment ? { ...found, garment: cardOf(found.garment) } : found);
      setNotice(found.result === "valid" || found.result === "already_scanned" ? null : {
        tone: "error",
        title: found.result.replaceAll("_", " "),
        detail: found.message,
        requestId: "",
        canRetry: false,
      });
      if (found.garment) await openHistory(found.garment.id);
    } catch (error) {
      setScan(null);
      setHistory(null);
      fail(error);
    } finally {
      setBusy(false);
    }
  }

  async function move(target: string): Promise<void> {
    if (!garment || busy) return;
    setBusy(true);
    try {
      const card = cardOf(await laundryCall<GarmentCard>("POST", `/api/v1/laundry/production/garments/${garment.id}/transition`, {
        target,
        version: garment.version,
        idempotency_key: crypto.randomUUID(),
        sorting_category: target === "SORTING" ? category : "",
        workflow_code: garment.stage === "RECEIVED" || garment.stage === "TAGGED" ? workflowCode : "",
        reason,
      }));
      setScan({ result: "valid", message: `${card.tag_code} is now ${card.stage}.`, allowed_targets: [], garment: card });
      setNotice(null);
      await openHistory(card.id);
      await loadBoard();
    } catch (error) {
      fail(error);
    } finally {
      setBusy(false);
    }
  }

  async function inspect(result: string): Promise<void> {
    if (!garment || busy) return;
    if (result !== "PASS" && reason.trim().length < 3) {
      setNotice({ tone: "error", title: "A reason is required", detail: "Enter why this garment failed, needs rework, or needs a manager.", requestId: "", canRetry: false });
      return;
    }
    setBusy(true);
    try {
      await laundryCall("POST", "/api/v1/laundry/production/inspections", {
        garment_id: garment.id,
        version: garment.version,
        result,
        checklist: Object.fromEntries(CHECKLIST.map((item) => [item, Boolean(checks[item])])),
        reason: reason || "Inspection recorded",
        required_stage: result === "PASS" ? "" : requiredStage,
        idempotency_key: crypto.randomUUID(),
      });
      setNotice(null);
      await openHistory(garment.id);
      await loadBoard();
    } catch (error) {
      fail(error);
    } finally {
      setBusy(false);
    }
  }

  async function packScan(): Promise<void> {
    if (!garment || busy) return;
    if (packedIds.includes(garment.id)) {
      setNotice({ tone: "error", title: "Already scanned in this packing session", detail: "Scan the next garment for this order.", requestId: "", canRetry: false });
      return;
    }
    setBusy(true);
    try {
      await laundryCall("POST", "/api/v1/laundry/production/packing/scans", {
        order_id: garment.order_id,
        garment_id: garment.id,
        bag_code: bagCode,
        version: garment.version,
        idempotency_key: crypto.randomUUID(),
      });
      const order = await laundryCall<{ garments: { id: string }[] }>("GET", `/api/v1/laundry/orders/${garment.order_id}`);
      setOrderGarments(order.garments.length);
      setPackedIds((current) => current.includes(garment.id) ? current : [...current, garment.id]);
      setNotice(null);
    } catch (error) {
      fail(error);
    } finally {
      setBusy(false);
    }
  }

  async function completePack(): Promise<void> {
    if (!garment || busy || !progress.complete) return;
    setBusy(true);
    try {
      const card = cardOf(await laundryCall<GarmentCard>("POST", `/api/v1/laundry/production/orders/${garment.order_id}/packing/complete`, { idempotency_key: crypto.randomUUID() }));
      setScan({ result: "valid", message: `${card.order_code} is ${card.operational_status}.`, allowed_targets: [], garment: card });
      setNotice(null);
      await loadBoard();
    } catch (error) {
      fail(error);
    } finally {
      setBusy(false);
    }
  }

  async function reportIncident(): Promise<void> {
    if (!garment || busy) return;
    if (reason.trim().length < 3) {
      setNotice({ tone: "error", title: "Describe the incident", detail: "Enter what happened. Opening an incident does not create a refund.", requestId: "", canRetry: false });
      return;
    }
    setBusy(true);
    try {
      await laundryCall("POST", "/api/v1/laundry/production/incidents", {
        order_id: garment.order_id,
        garment_id: garment.id,
        kind: incidentKind,
        description: reason,
        blocks_ready: true,
      });
      setNotice(null);
      await openHistory(garment.id);
      if (panel === "incidents") setIncidents(await laundryCall<Incident[]>("GET", "/api/v1/laundry/production/incidents"));
    } catch (error) {
      fail(error);
    } finally {
      setBusy(false);
    }
  }

  async function resolveIncident(id: string, status: string): Promise<void> {
    if (reason.trim().length < 3) {
      setNotice({ tone: "error", title: "Add a resolution note", detail: "Resolution does not post a refund or a credit note.", requestId: "", canRetry: false });
      return;
    }
    setBusy(true);
    try {
      await laundryCall("POST", `/api/v1/laundry/production/incidents/${id}/resolve`, { status, resolution: reason });
      setIncidents(await laundryCall<Incident[]>("GET", "/api/v1/laundry/production/incidents"));
      setNotice(null);
    } catch (error) {
      fail(error);
    } finally {
      setBusy(false);
    }
  }

  async function assignBatch(): Promise<void> {
    if (!garment || !batchId || busy) return;
    const batch = batches.find((item) => item.id === batchId);
    if (!batch) return;
    setBusy(true);
    try {
      await laundryCall("POST", `/api/v1/laundry/production/batches/${batch.id}/items`, { garment_id: garment.id, version: batch.version });
      setNotice(null);
      await loadBoard();
    } catch (error) {
      fail(error);
    } finally {
      setBusy(false);
    }
  }

  async function startCycle(): Promise<void> {
    const weight = Number(loadWeight);
    const machine = machines.find((item) => item.id === machineId);
    if (!machine || machine.status !== "AVAILABLE") {
      setNotice({ tone: "error", title: "Choose an available machine", detail: "A machine in maintenance or out of service cannot take a new cycle.", requestId: "", canRetry: false });
      return;
    }
    if (machine.capacity !== null && (!Number.isInteger(weight) || weight < 1)) {
      setNotice({ tone: "error", title: "Enter the measured load", detail: `This machine capacity is ${machine.capacity} ${machine.capacity_unit}. The register does not guess a weight.`, requestId: "", canRetry: false });
      return;
    }
    if (cycleCode.trim() === "") {
      setNotice({ tone: "error", title: "Enter the cycle code", detail: "Use the cycle configured for this machine.", requestId: "", canRetry: false });
      return;
    }
    setBusy(true);
    try {
      let chosen = batchId;
      if (!chosen && garment) {
        const created = await laundryCall<Batch>("POST", "/api/v1/laundry/production/batches", {
          store_id: garment.store_id,
          workflow_code: garment.workflow_code,
          idempotency_key: crypto.randomUUID(),
        });
        await laundryCall("POST", `/api/v1/laundry/production/batches/${created.id}/items`, { garment_id: garment.id, version: created.version });
        chosen = created.id;
      }
      if (!chosen) {
        setNotice({ tone: "error", title: "Choose a batch", detail: "Select an open batch or scan a garment to start one.", requestId: "", canRetry: false });
        return;
      }
      await laundryCall("POST", `/api/v1/laundry/production/machines/${machine.id}/cycles`, {
        batch_id: chosen,
        cycle_code: cycleCode.trim(),
        load_weight: Number.isInteger(weight) ? weight : null,
        idempotency_key: crypto.randomUUID(),
      });
      setNotice(null);
      setMachines(await laundryCall<Machine[]>("GET", "/api/v1/laundry/production/machines"));
    } catch (error) {
      fail(error);
    } finally {
      setBusy(false);
    }
  }

  async function closeRework(): Promise<void> {
    if (!history?.open_rework || busy) return;
    setBusy(true);
    try {
      await laundryCall("POST", `/api/v1/laundry/production/rework/${history.open_rework.id}/complete`, { note: reason || "Rework finished" });
      await openHistory(history.garment.id);
      setNotice(null);
    } catch (error) {
      fail(error);
    } finally {
      setBusy(false);
    }
  }

  const phase = dashboardPhase({
    signedIn,
    offlineSession: offlineRegister,
    loaded: board !== null,
    garmentCount: garments.length,
    notice,
  });
  const showBoard = phase === "ready" || phase === "empty";
  const laundrySync =
    offlineRegister || notice?.kind === "offline"
      ? { tone: "offline" as const, label: "Offline", title: OFFLINE_PRODUCTION }
      : { tone: "live" as const, label: "Live", title: "Laundry uses the signed-in register session." };
  const banner: FloorNotice | null = offlineRegister
    ? {
        tone: "offline",
        kind: "offline",
        title: "The register is offline",
        detail: OFFLINE_PRODUCTION,
        requestId: "",
        canRetry: false,
      }
    : !signedIn
      ? notice?.kind === "unauthenticated"
        ? notice
        : sessionHeadline(false)
      : notice && notice.kind !== "ok" && notice.tone !== "ok"
        ? notice
        : null;

  function openStation(id: string): void {
    if (!allowed.includes(id) || id === panel) return;
    const base = `${window.location.pathname}${window.location.search}`;
    window.history.pushState({ posView: "laundry", station: id }, "", `${base}${laundryLocation(id)}`);
    setPanel(id);
  }

  const metrics: { id: string; label: string; value: number }[] = board
    ? [
        { id: "lookup", label: "Received Today", value: board.received_today },
        { id: "sorting", label: "Awaiting Sorting", value: board.awaiting_sorting },
        { id: "production", label: "In Processing", value: board.processing },
        { id: "machines", label: "Active Batches", value: board.active_batches },
        { id: "machines", label: "Machine Cycles", value: board.active_cycles },
        { id: "quality", label: "Quality Check", value: board.qc_pending },
        { id: "rework", label: "Rework", value: board.rework_pending },
        { id: "packing", label: "Packing", value: board.packing_pending },
        { id: "ready", label: "Ready Orders", value: board.ready_orders },
        { id: "dashboard", label: "Overdue", value: board.overdue },
        { id: "incidents", label: "Incidents", value: board.open_incidents },
      ]
    : [];

  const referencePanel = ["intake", "dashboard", "active", "services", "categories", "garment-types", "pricing", "customers", "shift", "settings"].includes(panel);
  const scanForm = referencePanel ? null : (
    <LaundryScanInput value={code} busy={busy} onChange={setCode} onSubmit={() => void lookup()} />
  );

  const detail = garment && !referencePanel ? (
    <article className="space-y-3 rounded-2xl bg-white p-4 ring-1 ring-zinc-200">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-2xl font-semibold">{garment.tag_code || garment.order_code}</h2>
        <LaundryStatusBadge value={garment.hold ? "HOLD" : garment.stage} />
      </div>
      <p>{garment.order_code} · {garment.customer_name}{garment.customer_phone ? ` · ${garment.customer_phone}` : ""}</p>
      <p>{garment.description || garment.service_name} · {garment.service_name}</p>
      <p className="text-sm text-charcoal/70">{[garment.colour, garment.fabric, garment.brand, garment.size, garment.condition].filter(Boolean).join(" · ")}</p>
      <p className="text-sm">{garment.instructions || "No special care recorded"}</p>
      <p className="text-sm">Location {garment.location || "not set"} · batch {garment.batch_id ?? "none"} · QC {garment.qc_result || "none"}</p>
      <p className="text-sm">Total {money(garment.total_cents)} · tax {money(garment.tax_cents)} · paid {money(garment.amount_paid_cents)} · due {money(garment.balance_due_cents)}</p>
      {scan?.result === "already_scanned" ? <LaundryExceptionPanel title="Already scanned at this stage" detail={scan.message} /> : null}
      {scan && scan.result !== "valid" && scan.result !== "already_scanned" ? <LaundryExceptionPanel title={scan.result} detail={scan.message} /> : null}
      <p className="text-sm font-medium">{nextActionCopy(garment.stage, scan?.allowed_targets ?? [], scan?.message ?? "")}</p>
      <label className="block text-xs font-semibold uppercase tracking-wide text-charcoal/55">
        Reason
        <input className="mt-1 min-h-12 w-full rounded-xl border border-zinc-200 px-3" value={reason} onChange={(event) => setReason(event.target.value)} />
      </label>
      <div className="flex flex-wrap gap-2">
        {(panel === "sorting" ? scan?.allowed_targets.filter((item) => item === "SORTING") : scan?.allowed_targets)?.map((target) => (
          <PrimaryButton key={target} disabled={busy} onClick={() => void move(target)}>Move to {target.replaceAll("_", " ")}</PrimaryButton>
        ))}
      </div>
      {panel === "sorting" ? (
        <div className="grid gap-2 sm:grid-cols-2">
          <label className="text-xs font-semibold uppercase tracking-wide text-charcoal/55">Sorting category
            <SelectControl className="mt-1" value={category} onChange={(event) => setCategory(event.target.value)}>
              {categories.map((item) => <option key={item.id} value={item.code}>{item.name}</option>)}
            </SelectControl>
          </label>
          <label className="text-xs font-semibold uppercase tracking-wide text-charcoal/55">Workflow
            <SelectControl className="mt-1" value={workflowCode} onChange={(event) => setWorkflowCode(event.target.value)}>
              <option value="">Keep the service workflow</option>
              {workflows.map((item) => <option key={item.id} value={item.code}>{item.code}</option>)}
            </SelectControl>
          </label>
          {canBatch ? (
            <label className="text-xs font-semibold uppercase tracking-wide text-charcoal/55">Open batch
              <SelectControl className="mt-1" value={batchId} onChange={(event) => setBatchId(event.target.value)}>
                <option value="">Select a batch</option>
                {batches.filter((item) => item.status === "OPEN").map((item) => <option key={item.id} value={item.id}>{item.code} · {item.workflow_code}</option>)}
              </SelectControl>
            </label>
          ) : null}
          <div className="flex flex-wrap items-end gap-2">
            {canBatch ? <SecondaryButton disabled={busy || !batchId} onClick={() => void assignBatch()}>Assign batch</SecondaryButton> : null}
            <SecondaryButton disabled={busy} onClick={() => void reportIncident()}>Record exception</SecondaryButton>
          </div>
        </div>
      ) : null}
      {panel === "quality" ? (
        <div className="space-y-2">
          <div className="grid gap-2 sm:grid-cols-2">
            {CHECKLIST.map((item) => (
              <label key={item} className="flex min-h-11 items-center gap-2 text-sm">
                <input type="checkbox" checked={Boolean(checks[item])} onChange={(event) => setChecks((current) => ({ ...current, [item]: event.target.checked }))} />
                {item}
              </label>
            ))}
          </div>
          <label className="text-xs font-semibold uppercase tracking-wide text-charcoal/55">Return stage
            <SelectControl className="mt-1" value={requiredStage} onChange={(event) => setRequiredStage(event.target.value)}>
              <option value="">Select a stage</option>
              {(history?.stages ?? []).filter((item) => item !== "READY_FOR_COLLECTION").map((item) => <option key={item} value={item}>{item}</option>)}
            </SelectControl>
          </label>
          <div className="flex flex-wrap gap-2">
            <PrimaryButton disabled={busy} onClick={() => void inspect("PASS")}>Pass</PrimaryButton>
            <SecondaryButton disabled={busy} onClick={() => void inspect("FAIL")}>Fail</SecondaryButton>
            <SecondaryButton disabled={busy} onClick={() => void inspect("REWORK_REQUIRED")}>Rework</SecondaryButton>
            <SecondaryButton disabled={busy} onClick={() => void inspect("MANAGER_REVIEW")}>Manager review</SecondaryButton>
          </div>
        </div>
      ) : null}
      {panel === "rework" && history?.open_rework ? (
        <LaundryExceptionPanel title={`Rework ${history.open_rework.status}`} detail={`${history.open_rework.reason} Return to ${history.open_rework.required_stage}. Count ${garment.rework_count}.`}>
          <SecondaryButton disabled={busy || garment.stage !== "QUALITY_CHECK"} onClick={() => void closeRework()}>Complete rework</SecondaryButton>
        </LaundryExceptionPanel>
      ) : null}
      {panel === "packing" ? (
        <div className="space-y-2">
          <p className="text-lg font-semibold">Expected: {progress.expected} | Scanned: {progress.scanned} | Remaining: {progress.remaining}</p>
          <label className="text-xs font-semibold uppercase tracking-wide text-charcoal/55">Bag code
            <input className="mt-1 min-h-12 w-full rounded-xl border px-3" value={bagCode} onChange={(event) => setBagCode(event.target.value)} />
          </label>
          <div className="flex flex-wrap gap-2">
            <PrimaryButton disabled={busy} onClick={() => void packScan()}>Scan into order</PrimaryButton>
            <SecondaryButton disabled={busy || !progress.complete} onClick={() => void completePack()}>Complete packing</SecondaryButton>
          </div>
          {!progress.complete ? <p className="text-sm text-charcoal/60">Complete packing stays off until every garment on this order has been scanned here and the server still has to accept QC and holds.</p> : null}
        </div>
      ) : null}
      {panel === "incidents" ? (
        <div className="flex flex-wrap items-end gap-2">
          <label className="text-xs font-semibold uppercase tracking-wide text-charcoal/55">Type
            <SelectControl full={false} className="mt-1" value={incidentKind} onChange={(event) => setIncidentKind(event.target.value)}>
              {INCIDENT_KINDS.map((item) => <option key={item} value={item}>{item}</option>)}
            </SelectControl>
          </label>
          <SecondaryButton disabled={busy} onClick={() => void reportIncident()}>Report incident</SecondaryButton>
        </div>
      ) : null}
      {panel === "machines" ? (
        <div className="grid gap-2 sm:grid-cols-2">
          <label className="text-xs font-semibold uppercase tracking-wide text-charcoal/55">Machine
            <SelectControl className="mt-1" value={machineId} onChange={(event) => setMachineId(event.target.value)}>
              <option value="">Select a machine</option>
              {machines.map((item) => <option key={item.id} value={item.id} disabled={item.status !== "AVAILABLE"}>{item.name} · {item.status}</option>)}
            </SelectControl>
          </label>
          <label className="text-xs font-semibold uppercase tracking-wide text-charcoal/55">Measured load
            <input aria-label="Measured load grams" className="mt-1 min-h-12 w-full rounded-xl border px-3" value={loadWeight} onChange={(event) => setLoadWeight(event.target.value)} />
          </label>
          <label className="text-xs font-semibold uppercase tracking-wide text-charcoal/55">Cycle code
            <input className="mt-1 min-h-12 w-full rounded-xl border px-3" value={cycleCode} onChange={(event) => setCycleCode(event.target.value)} />
          </label>
          <PrimaryButton disabled={busy} onClick={() => void startCycle()}>Start cycle</PrimaryButton>
        </div>
      ) : null}
      <LaundryTimeline events={(history?.events ?? []).map((event) => ({ label: `${event.from_stage} → ${event.to_stage}`, detail: event.reason || event.created_at }))} />
      {(history?.inspections.length ?? 0) > 0 ? (
        <ul className="text-sm">
          {history?.inspections.map((item) => <li key={item.id}>{item.result} · {item.reason}</li>)}
        </ul>
      ) : null}
    </article>
  ) : null;

  const newOrder = sectionOf(panel) === "orders" && panel !== "intake" && allowed.includes("intake")
    ? <PrimaryButton onClick={() => openStation("intake")}>New Order</PrimaryButton>
    : null;

  return (
    <PageFrame
      title={sectionOf(panel) === "orders" ? "Orders" : "Laundry"}
      sync={laundrySync}
      drawer={null}
    >
      <div className={inventoryWorkspaceClass}>
        <LaundrySectionBars
          primary={primaryTabs()}
          secondary={["orders", "production", "services"].includes(sectionOf(panel)) ? secondaryTabs(sectionOf(panel), stations) : []}
          activePrimary={sectionOf(panel)}
          activeSecondary={panel === "dashboard" ? "active" : panel}
          onPrimary={(id) => openStation(defaultStation(id as LaundrySection, stations))}
          onSecondary={openStation}
        />
        <div
          data-laundry-scroll
          tabIndex={0}
          className={`${inventoryContentClass} outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary`}
          onKeyDown={(event) => {
            const target = event.target;
            if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement) return;
            const box = scrollingBox(event.currentTarget);
            const next = nextScrollTop(box, event.key);
            if (next === null) return;
            box.scrollTop = next;
            event.preventDefault();
          }}
        >
      {banner ? (
        <LaundryErrorState
          notice={banner}
          onRetry={banner.canRetry ? () => void loadBoard() : undefined}
          onUnlock={!signedIn && !offlineRegister ? () => setUnlocking(true) : undefined}
        />
      ) : null}
      {panel === "intake" ? <LaundryIntakePage session={session} onLookup={() => setSyncOpen(true)} /> : null}
      {panel === "active" ? <LaundryActiveOrders signedIn={signedIn} action={newOrder} /> : null}
      {panel === "services" || panel === "categories" || panel === "garment-types" || panel === "pricing" ? (
        <LaundryCataloguePage station={panel} signedIn={signedIn} />
      ) : null}
      {panel === "customers" ? <LaundryCustomersPage signedIn={signedIn} /> : null}
      {panel === "dashboard" ? (
        <div className="space-y-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h1 className="text-xl font-semibold text-zinc-900">Laundry</h1>
              <p className="text-sm text-zinc-500">Branch work for this register. Counts appear after the board loads for the signed-in user.</p>
            </div>
            {newOrder ? <div className="shrink-0">{newOrder}</div> : null}
          </div>
          {phase === "loading" ? <p className="text-sm">Loading the production board.</p> : null}
          {showBoard ? (
            <>
              <div className="grid grid-cols-[repeat(auto-fill,minmax(11.5rem,11.5rem))] gap-3">
                {metrics.map((item) => (
                  <LaundryMetricCard key={item.label} label={item.label} value={item.value} onOpen={() => openStation(item.id)} />
                ))}
              </div>
              <div className="grid gap-4 xl:grid-cols-3">
                <section className="space-y-2 xl:col-span-2">
                  <h2 className="font-semibold">Priority work</h2>
                  {priority.overdue.length + priority.dueSoon.length + priority.waiting.length + priority.qcFailures.length + priority.held.length === 0 ? (
                    <LaundryEmptyState title={phase === "empty" ? "No garments on the board" : "No priority exceptions"} detail={phase === "empty" ? "The board loaded and there is nothing waiting." : "Overdue orders, long waits, QC failures, and holds appear here."} />
                  ) : (
                    <div className="grid gap-2 sm:grid-cols-2">
                      {[...priority.overdue, ...priority.qcFailures, ...priority.held, ...priority.dueSoon, ...priority.waiting].slice(0, 8).map((item) => (
                        <LaundryGarmentCard key={item.id} garment={item} onOpen={() => { setCode(item.tag_code); openStation("scan"); void openHistory(item.id); }} />
                      ))}
                    </div>
                  )}
                  <h2 className="pt-2 font-semibold">Production overview</h2>
                  <ul className="flex flex-wrap gap-2 text-sm">
                    {stageDistribution(garments).map((item) => <li key={item.stage} className="rounded-full bg-white px-3 py-1 ring-1 ring-zinc-200">{item.stage} · {item.count}</li>)}
                  </ul>
                  <p className="text-sm">{reworkRate(garments) === null ? "Rework percentage needs garments on the board." : `Rework on ${reworkRate(garments)}% of garments on this board.`}</p>
                </section>
                <section className="space-y-3">
                  <h2 className="font-semibold">Recent activity</h2>
                  {recentGarments(garments).length === 0 ? <p className="text-sm text-zinc-500">No recent garments on this board.</p> : recentGarments(garments).map((item) => <LaundryGarmentCard key={item.id} garment={item} />)}
                  <h2 className="font-semibold">Quick actions</h2>
                  <div className="flex flex-wrap gap-2">
                    {stations.filter((item) => ["intake", "scan", "sorting", "packing", "lookup"].includes(item.id)).map((item) => (
                      <SecondaryButton key={item.id} onClick={() => openStation(item.id)}>{item.label}</SecondaryButton>
                    ))}
                    {canBatch ? <SecondaryButton onClick={() => openStation("machines")}>Create production batch</SecondaryButton> : null}
                  </div>
                </section>
              </div>
            </>
          ) : null}
        </div>
      ) : null}
      {panel === "lookup" ? <LaundryIntakePage session={session} mode="lookup" action={newOrder} /> : null}
      {panel === "scan" ? (
        <div className="grid items-start gap-4 xl:grid-cols-2">
          <div className="space-y-3">{scanForm}</div>
          {detail ?? <LaundryEmptyState title="No garment selected" detail="Scan a tag or type one and press Enter. The garment stays at its current stage until an authorized action." />}
        </div>
      ) : null}
      {panel === "production" ? (
        <div className="space-y-3">
          <label className="text-xs font-semibold uppercase tracking-wide text-charcoal/55">Workflow
            <SelectControl full={false} className="mt-1" value={activeWorkflow?.code ?? ""} onChange={(event) => setBoardWorkflow(event.target.value)}>
              {workflows.map((item) => <option key={item.id} value={item.code}>{item.code}</option>)}
            </SelectControl>
          </label>
          <LaundryProductionBoard columns={columns} onOpen={(id) => void openHistory(id)} />
        </div>
      ) : null}
      {panel === "sorting" && board ? (
        <div className="grid gap-2 sm:grid-cols-2">
          {garments.filter((item) => item.stage === "TAGGED" || item.stage === "RECEIVED" || item.stage === "SORTING").map((item) => (
            <LaundryGarmentCard key={item.id} garment={item} selected={item.id === garment?.id} onOpen={() => void openHistory(item.id)} />
          ))}
        </div>
      ) : null}
      {panel === "machines" && machinesLoaded ? (
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {machines.map((item) => (
            <article key={item.id} className="rounded-2xl bg-white p-4 ring-1 ring-zinc-200">
              <div className="flex items-center justify-between"><h3 className="font-semibold">{item.name}</h3><LaundryStatusBadge value={item.status} /></div>
              <p className="text-sm">{item.machine_type} · {item.code}</p>
              <p className="text-sm">Capacity {item.capacity ?? "not set"} {item.capacity_unit}</p>
            </article>
          ))}
          {machines.length === 0 ? <LaundryEmptyState title="No machines registered" detail="Business Pro registers machines. This station starts cycles on machines that are already available." /> : null}
        </div>
      ) : null}
      {panel === "machines" && signedIn && !machinesLoaded && !notice ? <p className="text-sm">Loading machines.</p> : null}
      {panel === "scan" ? null : detail}
      {panel === "ready" && board ? (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap gap-2" aria-label="Ready order filters">
              {(["ready", "unpaid", "paid", "hold", "overdue"] as ReadyFilter[]).map((item) => (
                <button key={item} type="button" className={`min-h-11 rounded-full px-4 text-sm font-semibold ${readyFilter === item ? "bg-zinc-900 text-white" : "bg-white ring-1 ring-zinc-200"}`} onClick={() => setReadyFilter(item)}>{item}</button>
              ))}
            </div>
            {newOrder ? <div className="shrink-0">{newOrder}</div> : null}
          </div>
          <ul className="space-y-2">
            {filterReady(garments, readyFilter, now).map((item) => (
              <li key={item.id} className="rounded-2xl bg-white p-3 ring-1 ring-zinc-200">
                <p className="font-semibold">{item.order_code} · {item.customer_name}</p>
                <p className="text-sm">Total {money(item.total_cents)} · paid {money(item.amount_paid_cents)} · due {money(item.balance_due_cents)} · {item.hold ? "On hold" : item.operational_status}</p>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {panel === "incidents" ? (
        <ul className="space-y-2">
          {incidents.map((item) => (
            <li key={item.id} className="rounded-2xl bg-white p-3 ring-1 ring-zinc-200">
              <p className="font-semibold">{item.kind} · {item.status}</p>
              <p className="text-sm">{item.description}</p>
              <p className="text-sm">{item.blocks_ready ? "Holding ready" : "Not holding"} · {item.stage}</p>
              {canResolve && item.status === "OPEN" ? (
                <div className="mt-2 flex flex-wrap gap-2">
                  <SecondaryButton disabled={busy} onClick={() => void resolveIncident(item.id, "INVESTIGATING")}>Open investigation</SecondaryButton>
                  <SecondaryButton disabled={busy} onClick={() => void resolveIncident(item.id, "RESOLVED")}>Resolve</SecondaryButton>
                  <SecondaryButton disabled={busy} onClick={() => void resolveIncident(item.id, "CLOSED")}>Close</SecondaryButton>
                </div>
              ) : null}
            </li>
          ))}
          {incidents.length === 0 && incidentsLoaded ? <LaundryEmptyState title="No incidents" detail="Scan a garment and report one. A report does not create a refund." /> : null}
        </ul>
      ) : null}
      {panel === "shift" && shift ? (
        <div className="space-y-3">
          <p className="text-sm text-zinc-500">Shift summary is the register report. Financial and production reports that are not on this register stay in Business Pro.</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <article className="rounded-2xl bg-white p-4 ring-1 ring-zinc-200">
            <h2 className="font-semibold">Your activity today</h2>
            <p>Moves {shift.transitions}</p>
            <p>Inspections {shift.inspections}</p>
            <p>Packed {shift.packed}</p>
            <p>Incidents {shift.incidents}</p>
          </article>
          <article className="rounded-2xl bg-white p-4 ring-1 ring-zinc-200">
            <h2 className="font-semibold">Branch board</h2>
            {board ? (
              <>
                <p>Received {board.received_today}</p>
                <p>Ready {board.ready_orders}</p>
                <p>Rework {board.rework_pending}</p>
              </>
            ) : (
              <p>Branch counts stay hidden until the board loads.</p>
            )}
            <p>The personal counts are the signed-in operator. The branch counts are the whole board.</p>
          </article>
        </div>
        </div>
      ) : null}
      {panel === "settings" ? (
        <article className="rounded-2xl bg-white p-4 ring-1 ring-zinc-200">
          <h2 className="font-semibold">Laundry settings</h2>
          <p className="mt-2 text-sm text-zinc-600">Services, workflows, stations, machines, quality, and tags open from the Settings gear. They stay read-only on this register.</p>
          <button
            type="button"
            className="mt-4 box-border inline-flex h-12 items-center justify-center rounded-xl bg-primary px-4 text-sm font-semibold text-white transition-colors hover:bg-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
            onClick={() => {
              const base = `${window.location.pathname}${window.location.search}`;
              window.history.pushState({ posView: "settings", section: "laundry-workflows" }, "", `${base}#/settings/laundry-workflows`);
              window.dispatchEvent(new HashChangeEvent("hashchange"));
            }}
          >
            Open laundry settings
          </button>
        </article>
      ) : null}
      </div>
      </div>
      {syncOpen ? <SyncCenterModal session={session} onClose={() => setSyncOpen(false)} /> : null}
      {unlocking ? (
        <div className="fixed inset-0 z-50 overflow-auto bg-slate-50">
          <div className="flex justify-end p-3">
            <button type="button" className="min-h-11 rounded-full border border-zinc-300 bg-white px-4 text-sm font-semibold" onClick={() => setUnlocking(false)}>
              Back to laundry
            </button>
          </div>
          <PinUnlock
            onUnlocked={(next) => {
              setAuthLost(false);
              setNotice(null);
              setUnlocking(false);
              onUnlocked?.(next);
            }}
          />
        </div>
      ) : null}
    </PageFrame>
  );
}
