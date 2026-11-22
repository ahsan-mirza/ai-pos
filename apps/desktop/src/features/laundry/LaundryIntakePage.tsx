import { Permission, SyncEntityType, type SyncEvent } from "@ai-pos/shared-types";
import QRCode from "qrcode";
import { useEffect, useState, type ReactNode } from "react";
import { currentAccessToken, type CashierSession } from "../auth/session";
import { env, previewHeaders } from "../../config/env";
import { pushBatch } from "../../lib/api";
import { RetailRequestError, retailCall } from "../../lib/retailClient";
import { enqueueBatch, inTauri } from "../../lib/tauri";
import { noticeFromError, registerSignedIn, sessionHeadline, type FloorNotice } from "./diagnostics";
import { blankLine, intakeCounts, intakePayload, validateIntake, type DraftLine, type ServiceChoice } from "./intakeModel";
import {
  fieldClass,
  FieldLabel,
  LaundryCustomerSelector,
  LaundryEmptyState,
  LaundryErrorState,
  LaundryGarmentEditor,
  LaundryOrderCard,
  LaundryOrderSummary,
  LaundryPaymentSummary,
  LaundryPhotoUploader,
  PrimaryButton,
  SecondaryButton,
  SelectControl,
} from "./ui";

interface Named { id: string; name: string }
interface GarmentRow {
  id: string;
  service_id: string;
  description: string;
  quantity: number;
  condition: string;
  stage: string;
}
interface OrderDetail {
  id: string;
  code: string;
  customer_id: string;
  intake_store_id: string;
  operational_status: string;
  tax_cents: number;
  total_cents: number;
  amount_paid_cents: number;
  balance_due_cents: number;
  payment_status: string;
  promised_at: string | null;
  pricing_snapshot: { lines: { unit_price_cents: number; rate_bps: number; total_cents: number }[] };
  garments: GarmentRow[];
  tags: { id: string; code: string; status: string }[];
  photos: { id: string; mime: string; byte_size: number; created_at: string }[];
}
interface LocalPhoto { key: string; mime: string; name: string; dataUrl: string; base64: string }

const QUEUE_KEY = "axizpos.laundry.acceptance.queue";
type SyncState = "accepted" | "pending" | "failed" | "conflict" | "";

function readQueue(): SyncEvent[] {
  try {
    const raw = localStorage.getItem(QUEUE_KEY);
    return raw ? (JSON.parse(raw) as SyncEvent[]) : [];
  } catch {
    return [];
  }
}

function writeQueue(events: SyncEvent[]): void {
  localStorage.setItem(QUEUE_KEY, JSON.stringify(events));
}

function printHtml(title: string, body: string): void {
  const frame = document.createElement("iframe");
  frame.setAttribute("aria-hidden", "true");
  frame.style.cssText = "position:fixed;width:0;height:0;border:0";
  document.body.appendChild(frame);
  const page = frame.contentDocument;
  if (page === null) return;
  page.open();
  page.write(`<!doctype html><html><head><title>${title}</title><style>body{font-family:sans-serif;width:72mm;margin:0.5rem}h1{font-size:1rem}p,li{font-size:0.75rem}</style></head><body>${body}</body></html>`);
  page.close();
  frame.contentWindow?.focus();
  frame.contentWindow?.print();
  window.setTimeout(() => frame.remove(), 1000);
}

/** Register intake. Server totals are authoritative. Offline drafts stay local until sync accepts them. */
export function LaundryIntakePage({ session, onLookup, mode = "intake", action }: { session: CashierSession; onLookup?: () => void; mode?: "intake" | "lookup"; action?: ReactNode }) {
  const [customers, setCustomers] = useState<Named[]>([]);
  const [stores, setStores] = useState<Named[]>([]);
  const [services, setServices] = useState<ServiceChoice[]>([]);
  const [lines, setLines] = useState<DraftLine[]>([]);
  const [photos, setPhotos] = useState<LocalPhoto[]>([]);
  const [order, setOrder] = useState<OrderDetail | null>(null);
  const [savedPhotos, setSavedPhotos] = useState<{ id: string; url: string }[]>([]);
  const [tagPreview, setTagPreview] = useState<{ code: string; image: string } | null>(null);
  const [pending, setPending] = useState<SyncEvent[]>(() => readQueue());
  const [syncState, setSyncState] = useState<SyncState>(readQueue().length > 0 ? "pending" : "");
  const [notice, setNotice] = useState<FloorNotice | null>(null);
  const [lookup, setLookup] = useState("");
  const [customerId, setCustomerId] = useState("");
  const [customerQuery, setCustomerQuery] = useState("");
  const [orderType, setOrderType] = useState("WALK_IN");
  const [promised, setPromised] = useState("");
  const [instructions, setInstructions] = useState("");
  const [express, setExpress] = useState(false);
  const [deposit, setDeposit] = useState("");
  const [discount, setDiscount] = useState("");
  const [storeId, setStoreId] = useState(session.user.store_id ?? "");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [printAfter, setPrintAfter] = useState(false);
  const canCreate = session.user.permissions.includes(Permission.LaundryOrdersCreate);
  const canDiscount = session.user.permissions.includes(Permission.PosDiscount);
  const signedIn = registerSignedIn(session.mode);
  const canSubmit = !busy && (signedIn || session.mode === "offline");

  useEffect(() => {
    if (!registerSignedIn(session.mode)) return;
    void retailCall<Named[]>("GET", "/api/v1/customers/sync").then(setCustomers).catch((error: unknown) => setNotice(noticeFromError(error)));
    void retailCall<Named[]>("GET", "/api/v1/stores").then((rows) => {
      setStores(rows);
      setStoreId((current) => current || rows[0]?.id || "");
    }).catch(() => setStores([]));
    void retailCall<ServiceChoice[]>("GET", "/api/v1/laundry/services?active=true").then((rows) => {
      setServices(rows);
      setLines((current) => (current.length > 0 ? current : [blankLine(rows[0]?.id ?? "")]));
    }).catch((error: unknown) => setNotice(noticeFromError(error)));
  }, [session.mode, session.unlocked_at]);

  useEffect(() => {
    if (order === null) return;
    let cancelled = false;
    void Promise.all(
      order.photos.map(async (photo) => {
        const token = currentAccessToken();
        const response = await fetch(`${env.apiBaseUrl}/api/v1/laundry/orders/${order.id}/photos/${photo.id}`, {
          headers: { ...previewHeaders(), ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        });
        if (!response.ok) return null;
        const blob = await response.blob();
        return { id: photo.id, url: URL.createObjectURL(blob) };
      }),
    ).then((rows) => {
      if (!cancelled) setSavedPhotos(rows.filter((row): row is { id: string; url: string } => row !== null));
    });
    return () => {
      cancelled = true;
    };
  }, [order]);

  useEffect(() => {
    if (!printAfter || order === null) return;
    printHtml("Laundry intake receipt", `<h1>Laundry intake receipt</h1><p>This is not a tax invoice and not a payment receipt.</p><p>Order ${order.code}</p><p>Total ${(order.total_cents / 100).toFixed(2)} · tax ${(order.tax_cents / 100).toFixed(2)} · due ${(order.balance_due_cents / 100).toFixed(2)}</p>`);
    setPrintAfter(false);
  }, [printAfter, order]);

  if (mode === "intake" && !canCreate) return <p className="p-6 text-sm">This register user cannot take laundry orders.</p>;

  const nameOf = (rows: Named[], id: string) => rows.find((row) => row.id === id)?.name ?? id;
  const counts = intakeCounts(lines, services);

  async function remember(payload: Record<string, unknown>, clientId: string): Promise<void> {
    const queued: SyncEvent = {
      idempotency_key: clientId,
      entity_type: SyncEntityType.LaundryOrder,
      operation: "upsert",
      payload,
      occurred_at: new Date().toISOString(),
    };
    if (inTauri()) await enqueueBatch(clientId, [queued]);
    const next = [...readQueue().filter((row) => row.idempotency_key !== clientId), queued];
    writeQueue(next);
    setPending(next);
    setSyncState("pending");
    setOrder(null);
    setNotice({
      tone: "offline",
      title: "Kept on this register",
      detail: "This is a local pending order, not a server invoice. Express orders and deposits are not queued.",
      requestId: "",
      canRetry: true,
    });
  }

  async function flush(): Promise<void> {
    const queued = readQueue();
    if (queued.length === 0) {
      setSyncState("");
      setPending([]);
      return;
    }
    if (!registerSignedIn(session.mode)) {
      setSyncState("failed");
      setNotice(sessionHeadline(false));
      return;
    }
    try {
      const result = await pushBatch(queued);
      const accepted = new Set(result.results.filter((row) => row.status === "applied" || row.status === "duplicate").map((row) => row.idempotency_key));
      const left = queued.filter((row) => !accepted.has(row.idempotency_key));
      writeQueue(left);
      setPending(left);
      const first = queued.find((row) => accepted.has(row.idempotency_key));
      if (first) {
        const created = await retailCall<OrderDetail>("GET", `/api/v1/laundry/orders/${String(first.payload.id)}`);
        setOrder(created);
        setSyncState("accepted");
        setNotice(null);
      }
      if (left.length > 0) setSyncState("pending");
    } catch (caught) {
      setSyncState("failed");
      setNotice(noticeFromError(caught, "sync"));
    }
  }

  function submit(andPrint: boolean): void {
    const nextErrors = validateIntake({ customerId, lines, services, deposit, discount, canDiscount });
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0 || busy) return;
    if (!registerSignedIn(session.mode) && session.mode !== "offline") {
      setNotice(sessionHeadline(false));
      return;
    }
    const clientId = crypto.randomUUID();
    const payload = intakePayload({
      clientId,
      storeId,
      customerId,
      orderType,
      promised,
      instructions,
      express,
      lines,
      services,
      deposit,
      discount: canDiscount ? discount : "",
    });
    const depositCents = Number(deposit || 0);
    setBusy(true);
    setNotice(null);
    setPrintAfter(andPrint);
    void retailCall<OrderDetail>("POST", "/api/v1/laundry/orders", payload)
      .then(async (created) => {
        for (const photo of photos) {
          await retailCall("POST", `/api/v1/laundry/orders/${created.id}/photos`, { mime: photo.mime, content_base64: photo.base64 });
        }
        const fresh = photos.length > 0 ? await retailCall<OrderDetail>("GET", `/api/v1/laundry/orders/${created.id}`) : created;
        setPhotos([]);
        setOrder(fresh);
        setSyncState("accepted");
      })
      .catch(async (caught: unknown) => {
        const failed = caught instanceof RetailRequestError ? caught : null;
        if (failed?.status === 409) {
          setSyncState("conflict");
          setPrintAfter(false);
          setNotice({ tone: "sync", title: "Conflict requiring resolution", detail: failed.message, requestId: failed.requestId, canRetry: false });
          return;
        }
        if (failed?.offline && !express && depositCents === 0) {
          setPrintAfter(false);
          await remember(payload, clientId);
          return;
        }
        setPrintAfter(false);
        setSyncState(failed?.offline ? "failed" : "");
        setNotice(noticeFromError(caught, failed?.offline ? "sync" : "action"));
      })
      .finally(() => setBusy(false));
  }

  function resetForm(): void {
    setLines([blankLine(services[0]?.id ?? "")]);
    setPhotos([]);
    setCustomerId("");
    setInstructions("");
    setDeposit("");
    setDiscount("");
    setExpress(false);
    setErrors({});
    setOrder(null);
    setNotice(null);
  }

  const serviceBreakdown = services
    .map((service) => ({ name: service.name, count: lines.filter((line) => line.service_id === service.id).length }))
    .filter((row) => row.count > 0);

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-xl font-semibold text-zinc-900">{mode === "lookup" ? "Order lookup" : "New laundry order"}</h1>
        {action ? <div className="shrink-0">{action}</div> : null}
      </div>
      {syncState === "accepted" ? <p className="text-sm text-zinc-600">Last sync accepted.</p> : null}
      {syncState === "failed" ? <p className="text-sm text-zinc-600">Sync failed.</p> : null}
      {syncState === "conflict" ? <p className="text-sm text-zinc-600">Conflict requiring resolution.</p> : null}
      {notice ? <LaundryErrorState notice={notice} onRetry={notice.canRetry && pending.length > 0 ? () => void flush() : undefined} /> : null}
      {pending.length > 0 ? (
        <div>
          <ul aria-label="Pending sync">
            {pending.map((row) => <li key={row.idempotency_key}>Pending local {row.idempotency_key}</li>)}
          </ul>
          <div className="mt-2 flex flex-wrap gap-2">
            <SecondaryButton onClick={() => void flush()}>Synchronize</SecondaryButton>
            {inTauri() && onLookup ? <SecondaryButton onClick={onLookup}>View Sync Center</SecondaryButton> : null}
          </div>
        </div>
      ) : null}
      {mode === "lookup" ? null : <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="min-w-0 space-y-4">
          <section className="grid items-start gap-3 rounded-2xl bg-white p-4 ring-1 ring-zinc-200 md:grid-cols-2">
            <LaundryCustomerSelector
              customers={customers}
              value={customerId}
              query={customerQuery}
              onQuery={setCustomerQuery}
              onChange={setCustomerId}
              error={errors.customer}
              branch={session.user.store_id === null ? (
                <FieldLabel label="Branch">
                  <SelectControl value={storeId} onChange={(event) => setStoreId(event.target.value)}>
                    {stores.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
                  </SelectControl>
                </FieldLabel>
              ) : null}
            />
            <FieldLabel label="Order type">
              <SelectControl value={orderType} onChange={(event) => setOrderType(event.target.value)}>
                <option value="WALK_IN">Walk-in</option>
                <option value="DROP_OFF">Drop-off</option>
                <option value="PICKUP">Pickup</option>
              </SelectControl>
            </FieldLabel>
            <FieldLabel label="Promised completion">
              <input className={fieldClass} type="datetime-local" value={promised} onChange={(event) => setPromised(event.target.value)} />
            </FieldLabel>
            <FieldLabel label="Special instructions" className="md:col-span-2">
              <input className={fieldClass} value={instructions} onChange={(event) => setInstructions(event.target.value)} />
            </FieldLabel>
          </section>
          <section className="rounded-2xl bg-white p-4 ring-1 ring-zinc-200">
            <label className="flex min-h-11 w-fit items-center gap-3 text-sm font-medium">
              <input className="size-5" type="checkbox" checked={express} onChange={(event) => setExpress(event.target.checked)} />
              Express
            </label>
            <p className="mt-2 text-sm text-charcoal/70">The server adds the service express surcharge when it prices the order. This register does not calculate that surcharge.</p>
          </section>
          <div className="flex flex-wrap gap-2">
            <SecondaryButton onClick={() => setLines((rows) => [...rows, blankLine(services.find((row) => row.pricing_unit !== "KG")?.id ?? services[0]?.id ?? "")])}>Add garment</SecondaryButton>
            <SecondaryButton onClick={() => setLines((rows) => [...rows, blankLine(services.find((row) => row.pricing_unit === "KG")?.id ?? services[0]?.id ?? "")])}>Add weight bag</SecondaryButton>
          </div>
          <p className="text-sm text-charcoal/70">A garment type is the item received. The laundry service is the treatment. The same garment can use a different service on another line. Prices come from the laundry catalogue, and the server calculates tax.</p>
          {errors.lines ? <p className="text-sm text-red-700">{errors.lines}</p> : null}
          <ul aria-label="Garment lines" className="space-y-3">
            {lines.map((line) => (
              <li key={line.key}>
                <LaundryGarmentEditor
                  line={line}
                  services={services}
                  errors={errors}
                  onChange={(patch) => setLines((rows) => rows.map((row) => row.key === line.key ? { ...row, ...patch } : row))}
                  onRemove={lines.length > 1 ? () => setLines((rows) => rows.filter((row) => row.key !== line.key)) : undefined}
                />
              </li>
            ))}
          </ul>
          <LaundryPhotoUploader
            photos={photos}
            onAdd={(files) => {
              for (const file of Array.from(files)) {
                const reader = new FileReader();
                reader.onload = () => {
                  const dataUrl = String(reader.result);
                  setPhotos((rows) => [...rows, { key: crypto.randomUUID(), mime: file.type, name: file.name, dataUrl, base64: dataUrl.split(",")[1] ?? "" }]);
                };
                reader.readAsDataURL(file);
              }
            }}
            onRemove={(key) => setPhotos((rows) => rows.filter((row) => row.key !== key))}
          />
          <div className="grid items-start gap-3 rounded-2xl bg-white p-4 ring-1 ring-zinc-200 sm:grid-cols-2">
            <FieldLabel label="Deposit in cents" error={errors.deposit} hint="500 is 5.00. The server records the deposit. It is not queued while offline.">
              <input className={fieldClass} inputMode="numeric" value={deposit} onChange={(event) => setDeposit(event.target.value)} />
            </FieldLabel>
            {canDiscount ? (
              <FieldLabel label="Discount in cents" error={errors.discount}>
                <input className={fieldClass} inputMode="numeric" value={discount} onChange={(event) => setDiscount(event.target.value)} />
              </FieldLabel>
            ) : null}
          </div>
        </div>
        <aside className="min-w-0 space-y-3">
          <LaundryOrderSummary garments={counts.garments} bags={counts.bags} weight={counts.weight} services={serviceBreakdown} />
          {order ? (
            <>
              <p className="text-sm">Production {order.operational_status}. Payment is recorded separately and is not changed by the production stage.</p>
              <LaundryPaymentSummary total={order.total_cents} tax={order.tax_cents} paid={order.amount_paid_cents} due={order.balance_due_cents} status={order.payment_status} />
            </>
          ) : null}
        </aside>
        <div className="flex flex-wrap items-center gap-2 border-t border-zinc-200 pt-4 xl:col-span-2">
          <PrimaryButton disabled={!canSubmit} onClick={() => submit(false)}>{busy ? "Creating" : "Create Laundry Order"}</PrimaryButton>
          <SecondaryButton disabled={!canSubmit} onClick={() => submit(true)}>Create and print receipt</SecondaryButton>
          <SecondaryButton disabled={busy} onClick={resetForm}>Cancel</SecondaryButton>
          {signedIn || session.mode === "offline" ? null : <p className="w-full text-sm text-charcoal/70">Unlock the register to create the order. The entries on this form stay here.</p>}
        </div>
      </div>}
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          setNotice(null);
          if (!registerSignedIn(session.mode)) {
            setNotice(sessionHeadline(false));
            return;
          }
          void retailCall<OrderDetail[]>("GET", `/api/v1/laundry/orders?q=${encodeURIComponent(lookup)}`)
            .then((rows) => {
              const found = rows.find((row) => row.code === lookup.trim()) ?? rows[0];
              if (!found) {
                setNotice({ tone: "error", title: "No matching order", detail: "No order matched that code.", requestId: "", canRetry: false });
                return;
              }
              return retailCall<OrderDetail>("GET", `/api/v1/laundry/orders/${found.id}`).then((detail) => {
                setOrder(detail);
                setSyncState("accepted");
              });
            })
            .catch((caught: unknown) => setNotice(noticeFromError(caught)));
        }}
      >
        <FieldLabel label="Order lookup" className="min-w-0 flex-1">
          <input className={fieldClass} value={lookup} onChange={(event) => setLookup(event.target.value)} />
        </FieldLabel>
        <SecondaryButton type="submit">Find order</SecondaryButton>
      </form>
      {order ? (
        <div className="space-y-3">
          <LaundryOrderCard code={order.code} customer={nameOf(customers, order.customer_id)} status={order.operational_status} due={`${(order.balance_due_cents / 100).toFixed(2)}`} />
          <p className="text-sm">Branch {nameOf(stores, order.intake_store_id)} · payment {order.payment_status}</p>
          <p className="text-sm">Accepted unit {order.pricing_snapshot.lines[0]?.unit_price_cents ?? 0} cents · tax {order.pricing_snapshot.lines[0]?.rate_bps ?? 0} bps</p>
          <ul aria-label="Garments" className="space-y-1 text-sm">
            {order.garments.map((garment) => (
              <li key={garment.id}>{garment.description || "Garment"} · {nameOf(services, garment.service_id)} · qty {garment.quantity} · {garment.condition || "no condition noted"} · {garment.stage}</li>
            ))}
          </ul>
          <ul aria-label="Tag preview" className="text-sm">
            {order.tags.map((tag) => <li key={tag.code}>{tag.code} · {tag.status}</li>)}
          </ul>
          <ul aria-label="Saved photos" className="flex gap-2">
            {savedPhotos.map((photo) => <li key={photo.id}><img src={photo.url} alt="Intake evidence" width={120} /></li>)}
          </ul>
          <label className="text-xs font-semibold uppercase tracking-wide text-charcoal/55">
            Add evidence
            <input
              className="mt-1 block"
              type="file"
              accept="image/jpeg,image/png,image/webp"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (!file || order === null) return;
                const reader = new FileReader();
                reader.onload = () => {
                  const base64 = String(reader.result).split(",")[1] ?? "";
                  void retailCall("POST", `/api/v1/laundry/orders/${order.id}/photos`, { mime: file.type, content_base64: base64 })
                    .then(() => retailCall<OrderDetail>("GET", `/api/v1/laundry/orders/${order.id}`))
                    .then(setOrder)
                    .catch((caught: unknown) => setNotice(noticeFromError(caught)));
                };
                reader.readAsDataURL(file);
              }}
            />
          </label>
          <div className="flex flex-wrap gap-2">
            <SecondaryButton
              onClick={() => {
                const tag = order.tags.find((row) => row.status === "active") ?? order.tags[0];
                if (!tag) return;
                void retailCall("POST", `/api/v1/laundry/tags/${tag.id}/reprint`, { idempotency_key: crypto.randomUUID() }).then(async () => {
                  const image = await QRCode.toDataURL(tag.code, { margin: 1, width: 180 });
                  setTagPreview({ code: tag.code, image });
                  printHtml("Laundry tag", `<h1>Laundry</h1><p>Order ${order.code}</p><p>Tag ${tag.code}</p><p>Branch ${nameOf(stores, order.intake_store_id)}</p><img alt="Tag QR" src="${image}">`);
                });
              }}
            >
              Print tag
            </SecondaryButton>
            <SecondaryButton onClick={() => printHtml("Laundry intake receipt", `<h1>Laundry intake receipt</h1><p>This is not a tax invoice and not a payment receipt.</p><p>Order ${order.code}</p><p>Total ${(order.total_cents / 100).toFixed(2)} · tax ${(order.tax_cents / 100).toFixed(2)} · due ${(order.balance_due_cents / 100).toFixed(2)}</p>`)}>
              Print intake receipt
            </SecondaryButton>
            {order.amount_paid_cents > 0 ? (
              <SecondaryButton onClick={() => printHtml("Laundry payment receipt", `<h1>Laundry payment receipt</h1><p>This is a payment receipt, not a tax invoice.</p><p>Order ${order.code}</p><p>Paid ${(order.amount_paid_cents / 100).toFixed(2)} · due ${(order.balance_due_cents / 100).toFixed(2)}</p>`)}>
                Print payment receipt
              </SecondaryButton>
            ) : null}
          </div>
          {tagPreview ? <img aria-label="Tag image" alt={tagPreview.code} src={tagPreview.image} width={120} /> : null}
          <article aria-label="Intake receipt" className="rounded-2xl bg-white p-4 text-sm ring-1 ring-zinc-200">
            <h3 className="font-semibold">Laundry intake receipt</h3>
            <p>This is not a tax invoice and not a payment receipt.</p>
            <p>Order {order.code}</p>
            <p>Customer {nameOf(customers, order.customer_id)}</p>
            {order.promised_at ? <p>Promised {order.promised_at}</p> : null}
          </article>
        </div>
      ) : <LaundryEmptyState title="No accepted order on this screen" detail="Create an order or look one up. A queued local order is not a server invoice." />}
    </section>
  );
}
