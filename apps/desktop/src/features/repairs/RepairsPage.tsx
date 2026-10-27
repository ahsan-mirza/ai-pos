import {
  RepairStatus,
  SerialKind,
  SyncEntityType,
  SyncOperation,
  formatMoney,
  isValidImei,
  type RepairDetail,
  type RepairTicket,
} from "@ai-pos/shared-types";
import { Select } from "@ai-pos/ui";
import { Printer, Wrench } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { DataTable, usePagination, type DataTableColumn } from "../../components/DataTable";
import { PageFrame } from "../../components/shell/RegisterShell";
import { useShellPage } from "../../components/shell/ShellContext";
import { ui } from "../../components/shell/tokens";
import { ApiRejectedError, pushBatch } from "../../lib/api";
import { retailCall, retailPage, RetailRequestError } from "../../lib/retailClient";
import { batchStatus, enqueueBatch, flushSync, inTauri } from "../../lib/tauri";
import type { CashierSession } from "../auth/session";
import { activeStore, useBusinessCurrency } from "../checkout/currency";
import { activeShiftId } from "../shifts/shift";

const CHECKS: { key: string; label: string }[] = [
  { key: "powers_on", label: "Powers on" },
  { key: "charges", label: "Charges" },
  { key: "screen_ok", label: "Screen intact" },
  { key: "buttons", label: "Buttons work" },
  { key: "liquid", label: "Liquid damage" },
  { key: "sim", label: "SIM / tray present" },
];

interface DeviceHit {
  product_id: string;
  name: string;
  sku: string;
  selling_price_cents: number;
  purchase_cost_cents: number | null;
  serial_status: string | null;
  available: boolean;
  warning: string | null;
  market_value: string;
}

function centsOf(value: string): number | null {
  const trimmed = value.trim();
  if (!/^\d+(\.\d{1,2})?$/.test(trimmed)) return null;
  return Math.round(Number(trimmed) * 100);
}

function fileBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const text = String(reader.result ?? "");
      resolve(text.slice(text.indexOf(",") + 1));
    };
    reader.onerror = () => reject(new Error("Could not read that photo."));
    reader.readAsDataURL(file);
  });
}

async function book(payload: Record<string, unknown>): Promise<void> {
  const event = {
    idempotency_key: crypto.randomUUID(),
    entity_type: SyncEntityType.RepairTicket,
    operation: SyncOperation.Upsert,
    payload,
    occurred_at: new Date().toISOString(),
  };
  if (inTauri()) {
    const batchId = crypto.randomUUID();
    await enqueueBatch(batchId, [event]);
    await flushSync();
    const status = await batchStatus(batchId);
    if (status?.status === "rejected") throw new Error(status.error ?? "The repair was rejected.");
    if (status?.status !== "synced") throw new Error("The repair is queued. It will book when the register is online.");
    return;
  }
  try {
    await pushBatch([event]);
  } catch (caught) {
    if (caught instanceof ApiRejectedError) throw new Error(caught.message);
    throw caught;
  }
}

function openPdf(filename: string, pdfBase64: string): void {
  const bytes = Uint8Array.from(atob(pdfBase64), (char) => char.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes], { type: "application/pdf" }));
  const frame = window.open(url, "_blank", "noopener");
  if (frame === null) {
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
  }
}

/** Book a device in, print the job card, take a deposit, and hand it back when there is nothing to invoice. */
export function RepairsPage({ session }: { session: CashierSession }) {
  const currency = useBusinessCurrency();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [ownership, setOwnership] = useState<"customer" | "internal">("customer");
  const [productId, setProductId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<DeviceHit[]>([]);
  const [selling, setSelling] = useState<number | null>(null);
  const [cost, setCost] = useState<number | null>(null);
  const [deviceNote, setDeviceNote] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [model, setModel] = useState("");
  const [kind, setKind] = useState<SerialKind>(SerialKind.Imei);
  const [identifier, setIdentifier] = useState("");
  const [issue, setIssue] = useState("");
  const [estimate, setEstimate] = useState("");
  const [passcode, setPasscode] = useState("");
  const [accessories, setAccessories] = useState("");
  const [deposit, setDeposit] = useState("");
  const [checks, setChecks] = useState<Record<string, boolean>>({});
  const [photo, setPhoto] = useState<File | null>(null);
  const [ticket, setTicket] = useState<RepairDetail | null>(null);
  const [bookingOpen, setBookingOpen] = useState(true);
  const [jobQuery, setJobQuery] = useState("");
  const [jobSearch, setJobSearch] = useState("");
  const [jobStatus, setJobStatus] = useState("active");
  const [jobs, setJobs] = useState<RepairTicket[]>([]);
  const [jobTotal, setJobTotal] = useState(0);
  const [jobError, setJobError] = useState<string | null>(null);
  const [loadingJobs, setLoadingJobs] = useState(true);
  const [reloadJobs, setReloadJobs] = useState(0);
  const [duplicates, setDuplicates] = useState<RepairTicket[]>([]);
  const [reviewing, setReviewing] = useState(false);
  const pager = usePagination({ resetKeys: [jobSearch, jobStatus] });
  useShellPage(busy, setNotice);

  useEffect(() => {
    const timer = window.setTimeout(() => setJobSearch(jobQuery.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [jobQuery]);

  useEffect(() => {
    setReviewing(false);
    setDuplicates([]);
  }, [name, phone, identifier]);

  useEffect(() => {
    if (ownership !== "internal" || query.trim().length < 2) {
      setHits([]);
      return;
    }
    const handle = window.setTimeout(() => {
      retailCall<DeviceHit[]>("GET", `/api/v1/repairs/devices?q=${encodeURIComponent(query.trim())}`)
        .then(setHits)
        .catch(() => setHits([]));
    }, 250);
    return () => window.clearTimeout(handle);
  }, [ownership, query]);

  useEffect(() => {
    const params = new URLSearchParams();
    if (jobSearch) params.set("q", jobSearch);
    if (jobStatus === "active") params.set("active", "true");
    else if (jobStatus) params.set("status", jobStatus);
    params.set("offset", String(pager.offset));
    params.set("limit", String(pager.pageSize));
    setLoadingJobs(true);
    retailPage<RepairTicket>(`/api/v1/repairs?${params.toString()}`)
      .then((page) => {
        setJobs(page.rows);
        setJobTotal(page.total);
        setJobError(null);
      })
      .catch((caught: unknown) => setJobError(caught instanceof Error ? caught.message : "Could not load repair jobs."))
      .finally(() => setLoadingJobs(false));
  }, [jobSearch, jobStatus, pager.offset, pager.pageSize, ticket, reloadJobs]);

  const field = "mt-1 h-11 w-full rounded-xl px-3 text-sm " + ui.input;

  async function openJob(id: string) {
    setError(null);
    setTicket(await retailCall<RepairDetail>("GET", `/api/v1/repairs/${id}/workshop`));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    const estimated = centsOf(estimate || "0");
    const depositCents = centsOf(deposit || "0");
    if (ownership === "internal") {
      if (!productId || !model.trim() || !issue.trim()) {
        setError("Select the shop device and describe the fault.");
        return;
      }
    } else if (!name.trim() || !phone.trim() || !model.trim() || !issue.trim()) {
      setError("Name, phone, device and the fault are required.");
      return;
    }
    if (kind === SerialKind.Imei && !isValidImei(identifier.trim())) {
      setError("Enter the 15-digit IMEI.");
      return;
    }
    if (!identifier.trim()) {
      setError("Enter the serial number.");
      return;
    }
    if (estimated === null || depositCents === null) {
      setError("Amounts use a number like 25.00.");
      return;
    }
    const id = crypto.randomUUID();
    const store = activeStore();
    setBusy(true);
    try {
      if (!reviewing) {
        const match = new URLSearchParams();
        match.set("phone", phone.trim());
        match.set("identifier", identifier.trim());
        match.set("customer_name", name.trim());
        const found = await retailCall<RepairTicket[]>("GET", `/api/v1/repairs/matches?${match.toString()}`);
        if (found.length > 0) {
          setDuplicates(found);
          setReviewing(true);
          setError(null);
          return;
        }
      }
      setDuplicates([]);
      setReviewing(false);
      await book({
        id,
        store_id: store.id,
        ownership,
        ...(productId ? { product_id: productId } : {}),
        customer_name: ownership === "internal" ? "Shop equipment" : name.trim(),
        customer_phone: ownership === "internal" ? "" : phone.trim(),
        device_model: model.trim(),
        identifier_kind: kind,
        identifier_value: identifier.trim(),
        issue: issue.trim(),
        status: RepairStatus.Intake,
        estimated_cost_cents: estimated,
        currency,
        ...(passcode.trim() ? { passcode: passcode.trim() } : {}),
        ...(accessories.trim() ? { accessories: accessories.trim() } : {}),
        intake_checklist: checks,
      });
      if (ownership === "customer" && depositCents > 0) {
        const shiftId = activeShiftId();
        await retailCall("POST", `/api/v1/repairs/${id}/deposits`, {
          amount_cents: depositCents,
          method: "cash",
          ...(shiftId ? { shift_id: shiftId } : {}),
        });
      }
      if (photo) {
        const data = await fileBase64(photo);
        await retailCall("POST", `/api/v1/repairs/${id}/attachments/json`, {
          content_type: photo.type || "image/jpeg",
          data_base64: data,
          file_name: photo.name || "intake.jpg",
          kind: "INTAKE",
        });
      }
      const detail = await retailCall<RepairDetail>("GET", `/api/v1/repairs/${id}/workshop`);
      setTicket(detail);
      setNotice(`Booked ${detail.reference || "the repair"}.`);
      setOwnership("customer");
      setProductId(null);
      setQuery("");
      setHits([]);
      setSelling(null);
      setCost(null);
      setDeviceNote(null);
      setName("");
      setPhone("");
      setModel("");
      setIdentifier("");
      setIssue("");
      setEstimate("");
      setPasscode("");
      setAccessories("");
      setDeposit("");
      setChecks({});
      setPhoto(null);
    } catch (caught) {
      const text =
        caught instanceof RetailRequestError || caught instanceof Error ? caught.message : "Could not book the repair.";
      setError(text);
    } finally {
      setBusy(false);
    }
  }

  async function printCard() {
    if (ticket === null) return;
    setBusy(true);
    setError(null);
    try {
      const file = await retailCall<{ filename: string; pdf_base64: string }>("GET", `/api/v1/repairs/${ticket.id}/job-card`);
      openPdf(file.filename, file.pdf_base64);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not print the job card.");
    } finally {
      setBusy(false);
    }
  }

  async function collect() {
    if (ticket === null) return;
    setBusy(true);
    setError(null);
    try {
      setTicket(await retailCall<RepairDetail>("POST", `/api/v1/repairs/${ticket.id}/pickup`, { note: `Collected by ${session.user.full_name}` }));
      setNotice("Marked collected.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not mark it collected.");
    } finally {
      setBusy(false);
    }
  }

  const jobColumns: DataTableColumn<RepairTicket>[] = [
    { id: "number", header: "Repair no.", cell: (row) => row.reference || row.id.slice(0, 8).toUpperCase() },
    {
      id: "owner",
      header: "Customer",
      cell: (row) => (row.ownership === "internal" ? "Business repair" : row.customer_name),
    },
    { id: "device", header: "Device", cell: (row) => row.device_model },
    { id: "serial", header: "Serial / IMEI", className: "hidden md:table-cell", headerClassName: "hidden md:table-cell", cell: (row) => row.identifier_value },
    { id: "fault", header: "Fault", className: "hidden lg:table-cell", headerClassName: "hidden lg:table-cell", cell: (row) => row.issue },
    { id: "status", header: "Status", cell: (row) => row.status.replaceAll("_", " ") },
    { id: "estimate", header: "Estimate", align: "right", cell: (row) => formatMoney(row.estimated_cost_cents, row.currency) },
    { id: "deposit", header: "Deposit", align: "right", cell: (row) => formatMoney(row.deposit_held_cents ?? 0, row.currency) },
  ];

  const sidePanel = (
    <div className={`flex h-full flex-col gap-4 overflow-y-auto p-4 ${ui.panel}`}>
      {ticket ? (
        <div className={`rounded-2xl border p-4 ${ui.border}`}>
          <p className="font-mono text-xs text-zinc-500">{ticket.reference}</p>
          <h3 className="text-lg font-semibold">{ticket.device_model}</h3>
          <p className="text-sm text-zinc-500">{ticket.customer_name}</p>
          <p className="mt-2 text-sm capitalize">{ticket.status.replaceAll("_", " ")}</p>
          {ticket.deposit_held_cents ? (
            <p className="mt-1 text-sm">Deposit held {formatMoney(ticket.deposit_held_cents, ticket.currency)}</p>
          ) : null}
          <div className="mt-3 flex flex-col gap-2">
            <button type="button" disabled={busy} onClick={() => void printCard()} className={`${ui.secondaryAction} h-11`}>
              <Printer size={16} aria-hidden="true" /> Job card
            </button>
            {ticket.status === "ready" && ticket.sale_id === null && ticket.total_cents === 0 ? (
              <button type="button" disabled={busy} onClick={() => void collect()} className={ui.primaryAction}>
                Mark collected
              </button>
            ) : null}
          </div>
        </div>
      ) : null}
      <p className="text-sm text-zinc-500">Choose a job in the list. Its intake, estimate, and collection actions stay here.</p>
    </div>
  );

  return (
    <PageFrame
      title="Repairs"
      sync={{ tone: "live", label: "Live", title: "Bookings are saved on the server." }}
      drawer={sidePanel}
    >
      <form id="book-repair" onSubmit={(event) => void submit(event)} className={`mx-auto max-w-3xl space-y-4 p-4 ${bookingOpen ? "" : "hidden"}`}>
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Wrench size={18} aria-hidden="true" />
              <h2 className="text-lg font-semibold">Book a repair</h2>
            </div>
            <button type="button" className="text-sm font-medium" onClick={() => setBookingOpen(false)}>
              Hide form
            </button>
          </div>
          <fieldset>
            <legend className={ui.label}>Whose device</legend>
            <div className="mt-2 grid grid-cols-2 gap-2">
              {(
                [
                  ["customer", "Customer repair"],
                  ["internal", "Shop equipment"],
                ] as const
              ).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => {
                    setOwnership(value);
                    setProductId(null);
                    setDeviceNote(null);
                  }}
                  className={`h-12 rounded-xl border text-sm font-medium ${
                    ownership === value ? "border-zinc-900 bg-zinc-900 text-white" : ui.border
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </fieldset>
          {ownership === "internal" ? (
            <div>
              <label className="block text-sm font-medium">
                Find the shop device
                <input
                  className={field}
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Name, SKU, barcode or serial"
                />
              </label>
              {hits.length > 0 ? (
                <ul className="mt-2 divide-y rounded-xl border">
                  {hits.map((hit) => (
                    <li key={hit.product_id}>
                      <button
                        type="button"
                        className="w-full px-3 py-2 text-left text-sm"
                        onClick={() => {
                          setProductId(hit.product_id);
                          setModel(hit.name);
                          setIdentifier(hit.serial_status ? query.trim() : hit.sku);
                          setKind(/^\d{15}$/.test(query.trim()) ? SerialKind.Imei : SerialKind.Serial);
                          setSelling(hit.selling_price_cents);
                          setCost(hit.purchase_cost_cents);
                          setDeviceNote(hit.warning ?? hit.market_value);
                          setHits([]);
                        }}
                      >
                        <span className="font-medium">{hit.name}</span>
                        <span className="block text-xs text-zinc-500">
                          {hit.sku}
                          {hit.purchase_cost_cents != null
                            ? ` · cost ${formatMoney(hit.purchase_cost_cents, currency)}`
                            : ""}
                          {` · selling ${formatMoney(hit.selling_price_cents, currency)}`}
                        </span>
                        {hit.warning ? <span className="block text-xs text-amber-700">{hit.warning}</span> : null}
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
              {productId ? (
                <p className="mt-2 text-sm">
                  Selected {model}.
                  {selling != null ? ` Selling price ${formatMoney(selling, currency)} is not the device value.` : ""}
                </p>
              ) : null}
              {deviceNote ? <p className="text-sm text-zinc-500">{deviceNote}</p> : null}
              {cost != null && centsOf(estimate || "0") != null && (centsOf(estimate || "0") ?? 0) > cost / 2 ? (
                <p className="text-sm text-amber-700">
                  The estimate is more than half the purchase cost. This is a warning only.
                </p>
              ) : null}
            </div>
          ) : null}
          <div className="grid gap-3 sm:grid-cols-2">
            {ownership === "customer" ? (
              <>
                <label className="block text-sm font-medium">
                  Customer
                  <input className={field} value={name} onChange={(event) => setName(event.target.value)} />
                </label>
                <label className="block text-sm font-medium">
                  Phone
                  <input className={field} value={phone} onChange={(event) => setPhone(event.target.value)} />
                </label>
              </>
            ) : null}
            <label className="block text-sm font-medium">
              Device
              <input className={field} value={model} onChange={(event) => setModel(event.target.value)} />
            </label>
            <label className="block text-sm font-medium">
              Estimate ({currency})
              <input className={field} inputMode="decimal" value={estimate} onChange={(event) => setEstimate(event.target.value)} placeholder="0.00" />
            </label>
            <label className="block text-sm font-medium">
              Identifier
              <Select
                className="mt-1"
                aria-label="Identifier kind"
                value={kind}
                onChange={(value) => setKind(value as SerialKind)}
                options={[
                  { value: SerialKind.Imei, label: "IMEI" },
                  { value: SerialKind.Serial, label: "Serial" },
                ]}
              />
            </label>
            <label className="block text-sm font-medium">
              {kind === SerialKind.Imei ? "IMEI" : "Serial"}
              <input className={field} value={identifier} onChange={(event) => setIdentifier(event.target.value)} />
            </label>
          </div>
          <label className="block text-sm font-medium">
            Fault
            <textarea className={`${field} h-20 py-2`} value={issue} onChange={(event) => setIssue(event.target.value)} />
          </label>
          <fieldset>
            <legend className={ui.label}>Intake check</legend>
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              {CHECKS.map((item) => (
                <label key={item.key} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={checks[item.key] === true}
                    onChange={(event) => setChecks({ ...checks, [item.key]: event.target.checked })}
                  />
                  {item.label}
                </label>
              ))}
            </div>
          </fieldset>
          <div className="grid gap-3 sm:grid-cols-3">
            <label className="block text-sm font-medium">
              Passcode
              <input className={field} value={passcode} onChange={(event) => setPasscode(event.target.value)} autoComplete="off" />
            </label>
            <label className="block text-sm font-medium">
              Accessories
              <input className={field} value={accessories} onChange={(event) => setAccessories(event.target.value)} />
            </label>
            {ownership === "customer" ? (
              <label className="block text-sm font-medium">
                Cash deposit
                <input className={field} inputMode="decimal" value={deposit} onChange={(event) => setDeposit(event.target.value)} placeholder="0.00" />
              </label>
            ) : (
              <p className="self-end text-sm text-zinc-500">Shop equipment is not invoiced to a customer.</p>
            )}
          </div>
          <label className="block text-sm font-medium">
            Photo
            <input
              type="file"
              accept="image/*,application/pdf"
              className="mt-1 block w-full text-sm"
              onChange={(event) => setPhoto(event.target.files?.[0] ?? null)}
            />
          </label>
          {duplicates.length > 0 ? (
            <div className="rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950">
              <p className="font-medium">An open repair already matches this customer or device. You can still book a repeat job.</p>
              <ul className="mt-2 space-y-1">
                {duplicates.map((job) => (
                  <li key={job.id}>
                    <button type="button" className="font-medium underline" onClick={() => void openJob(job.id)}>
                      {job.reference || job.id.slice(0, 8).toUpperCase()} · {job.device_model} · {job.ownership === "internal" ? "Business repair" : job.customer_name} · {job.status.replaceAll("_", " ")}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {error ? <p className="text-sm text-red-600">{error}</p> : null}
          {notice ? <p className="text-sm text-emerald-700">{notice}</p> : null}
          <button type="submit" disabled={busy} className={ui.primaryAction}>
          {busy ? "Booking…" : reviewing ? "Book this repeat repair" : "Book repair"}
        </button>
      </form>
      <section className="space-y-3 p-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Repair jobs</h2>
            <p className="text-sm text-zinc-500">{jobTotal} job{jobTotal === 1 ? "" : "s"}</p>
          </div>
          <button type="button" className={ui.secondaryAction} onClick={() => setBookingOpen(true)}>
            New repair
          </button>
        </div>
        <div className="flex flex-wrap gap-2">
          <input
            value={jobQuery}
            onChange={(event) => setJobQuery(event.target.value)}
            placeholder="Number, customer, phone, device, serial, IMEI"
            aria-label="Search repair jobs"
            className={"h-11 w-64 rounded-xl px-3 text-sm " + ui.input}
          />
          <Select
            aria-label="Repair status"
            value={jobStatus}
            onChange={setJobStatus}
            options={[
              { value: "active", label: "Active jobs" },
              { value: "", label: "All statuses" },
              { value: "intake", label: "Received" },
              { value: "diagnosing", label: "Awaiting diagnosis" },
              { value: "awaiting_approval", label: "Awaiting approval" },
              { value: "in_repair", label: "In progress" },
              { value: "waiting_parts", label: "Waiting for parts" },
              { value: "ready", label: "Ready for collection" },
              { value: "closed", label: "Collected" },
              { value: "cancelled", label: "Cancelled" },
            ]}
          />
        </div>
        <DataTable
          aria-label="Repair jobs"
          minWidth="720px"
          columns={jobColumns}
          data={jobs}
          getRowId={(row) => row.id}
          isLoading={loadingJobs}
          error={jobError}
          onRetry={() => setReloadJobs((value) => value + 1)}
          onRowClick={(row) => void openJob(row.id)}
          pagination={{
            mode: "server",
            currentPage: pager.page,
            pageSize: pager.pageSize,
            totalRecords: jobTotal,
            onPageChange: pager.setPage,
            onPageSizeChange: pager.setPageSize,
          }}
          emptyState={
            jobSearch || jobStatus
              ? { title: "No repairs match your filters", description: "Clear the search to see every job." }
              : { title: "No repair jobs yet", description: "Book the first repair above.", action: <button type="button" className={ui.secondaryAction} onClick={() => setBookingOpen(true)}>Book first repair</button> }
          }
        />
      </section>
    </PageFrame>
  );
}
