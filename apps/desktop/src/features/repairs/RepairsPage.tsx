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
import { Printer, Wrench } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { PageFrame } from "../../components/shell/RegisterShell";
import { useShellPage } from "../../components/shell/ShellContext";
import { ui } from "../../components/shell/tokens";
import { ApiRejectedError, pushBatch } from "../../lib/api";
import { retailCall, RetailRequestError } from "../../lib/retailClient";
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
  const [openJobs, setOpenJobs] = useState<RepairTicket[]>([]);
  useShellPage(busy, setNotice);

  useEffect(() => {
    retailCall<RepairTicket[]>("GET", "/api/v1/repairs?limit=30")
      .then((rows) => setOpenJobs(rows.filter((row) => row.status !== "closed" && row.status !== "cancelled")))
      .catch(() => setOpenJobs([]));
  }, [ticket]);

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
    if (!name.trim() || !phone.trim() || !model.trim() || !issue.trim()) {
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
      await book({
        id,
        store_id: store.id,
        customer_name: name.trim(),
        customer_phone: phone.trim(),
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
      if (depositCents > 0) {
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

  const jobs = (
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
      <div>
        <h3 className="text-sm font-semibold">Open jobs</h3>
        <ul className="mt-2 space-y-1">
          {openJobs.map((job) => (
            <li key={job.id}>
              <button
                type="button"
                onClick={() => void openJob(job.id).catch((caught: unknown) => setError(String(caught)))}
                className="w-full rounded-lg px-2 py-1.5 text-left text-sm hover:bg-zinc-100 dark:hover:bg-zinc-800"
              >
                <span className="font-medium">{job.device_model}</span>
                <span className="block text-xs text-zinc-500">{job.customer_name}</span>
              </button>
            </li>
          ))}
          {openJobs.length === 0 ? <li className="text-sm text-zinc-500">No open repairs.</li> : null}
        </ul>
      </div>
    </div>
  );

  return (
    <PageFrame
      title="Repairs"
      sync={{ tone: "live", label: "Live", title: "Bookings are saved on the server." }}
      drawer={jobs}
    >
      <form onSubmit={(event) => void submit(event)} className="mx-auto max-w-3xl space-y-4 p-4">
          <div className="flex items-center gap-2">
            <Wrench size={18} aria-hidden="true" />
            <h2 className="text-lg font-semibold">Book a repair</h2>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block text-sm font-medium">
              Customer
              <input className={field} value={name} onChange={(event) => setName(event.target.value)} />
            </label>
            <label className="block text-sm font-medium">
              Phone
              <input className={field} value={phone} onChange={(event) => setPhone(event.target.value)} />
            </label>
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
              <select className={field} value={kind} onChange={(event) => setKind(event.target.value as SerialKind)}>
                <option value={SerialKind.Imei}>IMEI</option>
                <option value={SerialKind.Serial}>Serial</option>
              </select>
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
            <label className="block text-sm font-medium">
              Cash deposit
              <input className={field} inputMode="decimal" value={deposit} onChange={(event) => setDeposit(event.target.value)} placeholder="0.00" />
            </label>
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
          {error ? <p className="text-sm text-red-600">{error}</p> : null}
          {notice ? <p className="text-sm text-emerald-700">{notice}</p> : null}
          <button type="submit" disabled={busy} className={ui.primaryAction}>
          {busy ? "Booking…" : "Book repair"}
        </button>
      </form>
    </PageFrame>
  );
}
