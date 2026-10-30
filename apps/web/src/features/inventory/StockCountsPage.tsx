import {
  formatMoney,
  Permission,
  STOCK_COUNT_STATUS_LABELS,
  type StockCount,
  type StockCountEntry,
  type StockCountLine,
  type StockCountStatus,
  type StockCountSummary,
} from "@ai-pos/shared-types";
import { ArrowLeft, ClipboardCheck, ClipboardList, Plus, ScanLine } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ErrorNote, FilterSelect, GhostButton, PrimaryButton, SearchField, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { Toast } from "../../components/ui/Toast";
import { Toggle } from "../../components/ui/Toggle";
import { apiGet, apiPost, apiPut } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useCurrency } from "../../lib/currency";
import { errorMessage } from "../users/api";
import { modelsApi } from "./api";
import { formatDate, storeOptions, useCategories, useStores } from "./shared";

const COUNTS = "/api/v1/inventory/counts";

function StatusChip({ status }: { status: StockCountStatus }) {
  const tone =
    status === "SUBMITTED"
      ? "bg-accent text-white"
      : status === "OPEN"
        ? "bg-charcoal text-white"
        : status === "POSTED"
          ? "bg-surface text-charcoal ring-1 ring-line"
          : "bg-white text-charcoal/50 ring-1 ring-line";
  return <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${tone}`}>{STOCK_COUNT_STATUS_LABELS[status]}</span>;
}

function signed(value: number): string {
  return value > 0 ? `+${value}` : String(value);
}

export function StockCountsPage() {
  const { user, can } = useAuth();
  const { stores } = useStores();
  const { currency } = useCurrency();
  const [storeId, setStoreId] = useState(user?.store_id ?? "");
  const [counts, setCounts] = useState<StockCountSummary[]>([]);
  const [openId, setOpenId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);
  const canReview = can(Permission.InventoryAdjustStock);

  const load = useCallback(async () => {
    try {
      setCounts(await apiGet<StockCountSummary[]>(`${COUNTS}${storeId ? `?store_id=${storeId}` : ""}`));
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "Could not load stock counts."));
    }
  }, [storeId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (openId) {
    return (
      <CountSheet
        countId={openId}
        currency={currency}
        onBack={() => {
          setOpenId(null);
          void load();
        }}
        onToast={setToast}
        toast={toast}
        dismissToast={dismissToast}
      />
    );
  }

  const active = counts.filter((count) => count.status === "OPEN" || count.status === "SUBMITTED");
  const posted = counts.filter((count) => count.status === "POSTED");
  const shrinkCents = posted.reduce((sum, count) => sum + Math.min(0, count.variance_value_cents ?? 0), 0);

  return (
    <section className="space-y-4">
      <div className="grid gap-4 md:grid-cols-3">
        <article className="rounded-card bg-charcoal p-6 text-white">
          <p className="text-sm text-white/60">Counts in progress</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{active.length}</p>
          <p className="mt-2 text-xs text-white/50">{active.filter((count) => count.status === "SUBMITTED").length} waiting for review</p>
        </article>
        <article className="rounded-card bg-accent p-6 text-white">
          <p className="text-sm text-white/80">Shrinkage posted</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{formatMoney(Math.abs(shrinkCents), currency)}</p>
          <p className="mt-2 text-xs text-white/80">At cost, across the counts listed</p>
        </article>
        <article className="rounded-card border border-line bg-white p-6">
          <p className="text-sm text-charcoal/60">Counts posted</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{posted.length}</p>
          <p className="mt-2 text-xs text-charcoal/50">Variances booked to the stock ledger</p>
        </article>
      </div>

      <div className="rounded-card border border-line bg-white p-6">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold">Stock counts</h2>
            <p className="text-sm text-charcoal/60">
              Staff count shelves without seeing system quantities; a manager reviews the differences and posts them.
            </p>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            {user?.store_id ? null : (
              <FilterSelect
                label="Branch"
                value={storeId}
                options={[{ value: "", label: "All branches" }, ...storeOptions(stores)]}
                onChange={setStoreId}
                className="w-56"
              />
            )}
            {canReview ? (
              <PrimaryButton onClick={() => setStarting(true)}>
                <Plus size={16} aria-hidden="true" className="-ml-1 mr-1.5" /> Start a count
              </PrimaryButton>
            ) : null}
          </div>
        </div>
        <ErrorNote message={error} />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[820px] text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-charcoal/50">
              <tr>
                <th className="pb-3 font-medium">Count</th>
                <th className="pb-3 font-medium">Scope</th>
                <th className="pb-3 font-medium">Started</th>
                <th className="pb-3 text-right font-medium">Counted</th>
                <th className="pb-3 text-right font-medium">Net variance</th>
                <th className="pb-3 text-right font-medium">Value</th>
                <th className="pb-3 pl-6 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {counts.map((count) => (
                <tr
                  key={count.id}
                  onClick={() => setOpenId(count.id)}
                  className="cursor-pointer border-t border-line align-top transition-colors hover:bg-surface/60"
                >
                  <td className="py-3">
                    <button type="button" className="font-mono text-xs font-semibold hover:text-accent">
                      {count.number}
                    </button>
                    <span className="block text-xs text-charcoal/50">{count.blind ? "Blind count" : "Open count"}</span>
                  </td>
                  <td className="py-3">
                    <span className="block">{count.store_name}</span>
                    <span className="block text-xs text-charcoal/50">{count.category_name ?? "Every product"}</span>
                  </td>
                  <td className="py-3 tabular-nums">
                    {formatDate(count.created_at)}
                    <span className="block text-xs text-charcoal/50">{count.created_by_name ?? ""}</span>
                  </td>
                  <td className="py-3 text-right tabular-nums">
                    {count.lines_counted} / {count.lines_total}
                  </td>
                  <td
                    className={`py-3 text-right font-semibold tabular-nums ${
                      (count.net_variance ?? 0) < 0 ? "text-accent" : ""
                    }`}
                  >
                    {count.net_variance === null ? "Hidden" : signed(count.net_variance)}
                  </td>
                  <td className="py-3 text-right tabular-nums">
                    {count.variance_value_cents === null ? "—" : formatMoney(count.variance_value_cents, currency)}
                  </td>
                  <td className="py-3 pl-6">
                    <StatusChip status={count.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {counts.length === 0 ? (
            <p className="py-8 text-sm text-charcoal/60">No stock counts yet. Start one to check a branch's shelves.</p>
          ) : null}
        </div>
      </div>
      {starting ? (
        <StartCountModal
          stores={stores}
          defaultStoreId={storeId || user?.store_id || stores.find((store) => !store.is_warehouse)?.id || ""}
          lockStore={Boolean(user?.store_id)}
          onClose={() => setStarting(false)}
          onStarted={(count) => {
            setStarting(false);
            setToast(`Count ${count.number} started with ${count.lines_total} products.`);
            setOpenId(count.id);
          }}
        />
      ) : null}
      {toast ? <Toast message={toast} onDismiss={dismissToast} /> : null}
    </section>
  );
}

function StartCountModal({
  stores,
  defaultStoreId,
  lockStore,
  onClose,
  onStarted,
}: {
  stores: ReturnType<typeof useStores>["stores"];
  defaultStoreId: string;
  lockStore: boolean;
  onClose: () => void;
  onStarted: (count: StockCount) => void;
}) {
  const { categories } = useCategories();
  const [storeId, setStoreId] = useState(defaultStoreId);
  const [categoryId, setCategoryId] = useState("");
  const [modelId, setModelId] = useState("");
  const [models, setModels] = useState<{ id: string; name: string }[]>([]);
  const [blind, setBlind] = useState(true);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    modelsApi.list().then(setModels).catch(() => setModels([]));
  }, []);

  const start = async () => {
    if (!storeId) return setError("Choose the branch to count.");
    setBusy(true);
    setError(null);
    try {
      onStarted(
        await apiPost<StockCount>(COUNTS, {
          store_id: storeId,
          category_id: categoryId || null,
          product_model_id: modelId || null,
          blind,
          note: note.trim(),
        }),
      );
    } catch (caught) {
      setError(errorMessage(caught, "Could not start the count."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title="Start a stock count"
      subtitle="Every product the branch stocks is listed; counters can add anything else they find."
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy} onClick={() => void start()}>
            {busy ? "Starting…" : "Start count"}
          </PrimaryButton>
        </>
      }
    >
      <div className="space-y-4">
        {lockStore ? null : (
          <FilterSelect label="Branch" value={storeId} options={storeOptions(stores)} onChange={setStoreId} />
        )}
        <FilterSelect
          label="Scope"
          value={categoryId}
          options={[{ value: "", label: "Every product (full count)" }, ...categories.map((category) => ({ value: category.id, label: category.name }))]}
          onChange={setCategoryId}
        />
        <FilterSelect
          label="Model"
          value={modelId}
          options={[{ value: "", label: "Any model" }, ...models.map((model) => ({ value: model.id, label: model.name }))]}
          onChange={setModelId}
        />
        <Toggle
          checked={blind}
          onChange={setBlind}
          label="Blind count"
          description="Counters don't see what the system expects, so they count what is really there."
        />
        <TextField label="Note (optional)" value={note} maxLength={255} onChange={(event) => setNote(event.target.value)} />
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}

function CountSheet({
  countId,
  currency,
  onBack,
  onToast,
  toast,
  dismissToast,
}: {
  countId: string;
  currency: string;
  onBack: () => void;
  onToast: (message: string) => void;
  toast: string | null;
  dismissToast: () => void;
}) {
  const [count, setCount] = useState<StockCount | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [scanning, setScanning] = useState<StockCountLine | null>(null);
  const [confirming, setConfirming] = useState<"post" | "cancel" | null>(null);
  const [filter, setFilter] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setCount(await apiGet<StockCount>(`${COUNTS}/${countId}`));
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "Could not load the count."));
    }
  }, [countId]);

  useEffect(() => {
    void load();
  }, [load]);

  const editable = count?.status === "OPEN";
  const dirty = Object.keys(drafts).length;
  const showExpected = count !== null && count.lines.some((line) => line.expected_qty !== null);

  const visibleLines = useMemo(() => {
    const term = filter.trim().toLowerCase();
    if (!count || !term) return count?.lines ?? [];
    return count.lines.filter((line) => `${line.name} ${line.sku} ${line.barcode}`.toLowerCase().includes(term));
  }, [count, filter]);

  const save = async (entries: StockCountEntry[]) => {
    setBusy(true);
    try {
      setCount(await apiPut<StockCount>(`${COUNTS}/${countId}/lines`, { entries }));
      setError(null);
      return true;
    } catch (caught) {
      setError(errorMessage(caught, "Could not save the counts."));
      return false;
    } finally {
      setBusy(false);
    }
  };

  const saveDrafts = async () => {
    const entries: StockCountEntry[] = [];
    for (const [productId, raw] of Object.entries(drafts)) {
      const quantity = Number(raw);
      if (raw.trim() === "" || !Number.isInteger(quantity) || quantity < 0) {
        setError("Counts must be whole numbers of 0 or more.");
        return;
      }
      entries.push({ product_id: productId, counted_qty: quantity });
    }
    if (entries.length && (await save(entries))) {
      setDrafts({});
      onToast(`${entries.length} count${entries.length === 1 ? "" : "s"} saved.`);
    }
  };

  const act = async (action: "submit" | "post" | "reopen" | "cancel") => {
    setBusy(true);
    try {
      const next = await apiPost<StockCount>(`${COUNTS}/${countId}/${action}`, {});
      setCount(next);
      setConfirming(null);
      setError(null);
      onToast(
        action === "post"
          ? `Count ${next.number} posted; the stock ledger now matches the shelves.`
          : `Count ${next.number}: ${STOCK_COUNT_STATUS_LABELS[next.status].toLowerCase()}.`,
      );
    } catch (caught) {
      setError(errorMessage(caught, "Could not update the count."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="space-y-4">
      <button type="button" onClick={onBack} className="inline-flex items-center gap-1.5 text-sm font-medium text-charcoal/60 hover:text-accent">
        <ArrowLeft size={15} aria-hidden="true" /> All counts
      </button>
      {count ? (
        <div className="grid gap-4 md:grid-cols-3">
          <article className="rounded-card bg-charcoal p-6 text-white">
            <p className="text-sm text-white/60">Counted</p>
            <p className="mt-4 text-4xl font-semibold tabular-nums">
              {count.lines_counted}
              <span className="text-xl text-white/50"> / {count.lines_total}</span>
            </p>
            <p className="mt-2 text-xs text-white/50">Uncounted products are left as they are when posting</p>
          </article>
          <article className="rounded-card bg-accent p-6 text-white">
            <p className="text-sm text-white/80">Net variance</p>
            <p className="mt-4 text-4xl font-semibold tabular-nums">{count.net_variance === null ? "Hidden" : signed(count.net_variance)}</p>
            <p className="mt-2 text-xs text-white/80">
              {count.net_variance === null ? "Blind count: revealed to the reviewer" : "Units, counted minus system"}
            </p>
          </article>
          <article className="rounded-card border border-line bg-white p-6">
            <p className="text-sm text-charcoal/60">Variance at cost</p>
            <p className="mt-4 text-4xl font-semibold tabular-nums">
              {count.variance_value_cents === null ? "—" : formatMoney(count.variance_value_cents, currency)}
            </p>
            <p className="mt-2 text-xs text-charcoal/50">Next FIFO layer cost per unit</p>
          </article>
        </div>
      ) : null}

      <div className="rounded-card border border-line bg-white p-6">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="flex flex-wrap items-center gap-3 text-xl font-semibold">
              <span className="font-mono">{count?.number ?? "…"}</span>
              {count ? <StatusChip status={count.status} /> : null}
            </h2>
            <p className="text-sm text-charcoal/60">
              {count ? `${count.store_name} · ${count.category_name ?? "Every product"}${count.note ? ` · ${count.note}` : ""}` : ""}
            </p>
          </div>
          <div className="flex flex-wrap items-end gap-2">
            <SearchField
              hideLabel
              label="Find a product"
              className="w-56"
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
              placeholder="Find by name, SKU or barcode"
            />
            {editable ? (
              <>
                <GhostButton disabled={busy || dirty === 0} onClick={() => void saveDrafts()}>
                  Save {dirty > 0 ? `${dirty} ` : ""}count{dirty === 1 ? "" : "s"}
                </GhostButton>
                <PrimaryButton disabled={busy || dirty > 0 || (count?.lines_counted ?? 0) === 0} onClick={() => void act("submit")}>
                  <ClipboardList size={16} aria-hidden="true" className="-ml-1 mr-1.5" /> Submit for review
                </PrimaryButton>
              </>
            ) : null}
            {count?.can_review && count.status === "SUBMITTED" ? (
              <GhostButton disabled={busy} onClick={() => void act("reopen")}>
                Reopen for recount
              </GhostButton>
            ) : null}
            {count?.can_review && (count.status === "OPEN" || count.status === "SUBMITTED") ? (
              <>
                <GhostButton disabled={busy} onClick={() => setConfirming("cancel")}>
                  Cancel count
                </GhostButton>
                <PrimaryButton disabled={busy || dirty > 0 || count.lines_counted === 0} onClick={() => setConfirming("post")}>
                  <ClipboardCheck size={16} aria-hidden="true" className="-ml-1 mr-1.5" /> Post variances
                </PrimaryButton>
              </>
            ) : null}
          </div>
        </div>
        <ErrorNote message={error} />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[820px] text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-charcoal/50">
              <tr>
                <th className="pb-3 font-medium">Product</th>
                <th className="pb-3 text-right font-medium">Counted</th>
                {showExpected ? (
                  <>
                    <th className="pb-3 text-right font-medium">System</th>
                    <th className="pb-3 text-right font-medium">Variance</th>
                    <th className="pb-3 text-right font-medium">At cost</th>
                  </>
                ) : null}
                <th className="pb-3 pl-6 font-medium">Counted by</th>
              </tr>
            </thead>
            <tbody>
              {visibleLines.map((line) => {
                const draft = drafts[line.product_id];
                return (
                  <tr key={line.product_id} className="border-t border-line align-top">
                    <td className="py-3">
                      <span className="block font-medium">{line.name}</span>
                      <span className="block font-mono text-xs text-charcoal/50">
                        {line.sku} · {line.barcode}
                      </span>
                      {line.missing_serials?.length ? (
                        <span className="mt-1 block text-xs text-accent">
                          Not found: {line.missing_serials.join(", ")}
                          {count?.status === "POSTED" ? " (quarantined)" : ""}
                        </span>
                      ) : null}
                      {line.unexpected_serials?.length ? (
                        <span className="mt-1 block text-xs text-charcoal/60">
                          Scanned but booked elsewhere: {line.unexpected_serials.join(", ")}. Fix with a manual adjustment.
                        </span>
                      ) : null}
                    </td>
                    <td className="py-3 text-right">
                      {line.is_serialized ? (
                        editable ? (
                          <button
                            type="button"
                            onClick={() => setScanning(line)}
                            className="inline-flex items-center gap-1.5 rounded-full border border-line px-3 py-1.5 text-xs font-semibold tabular-nums hover:border-accent hover:text-accent"
                          >
                            <ScanLine size={14} aria-hidden="true" />
                            {line.counted_qty === null ? "Scan units" : `${line.counted_qty} scanned`}
                          </button>
                        ) : (
                          <span className="font-semibold tabular-nums">{line.counted_qty ?? "—"}</span>
                        )
                      ) : editable ? (
                        <input
                          aria-label={`Counted ${line.name}`}
                          inputMode="numeric"
                          value={draft ?? (line.counted_qty === null ? "" : String(line.counted_qty))}
                          placeholder="—"
                          onChange={(event) =>
                            setDrafts((current) => ({ ...current, [line.product_id]: event.target.value.replace(/[^\d]/g, "") }))
                          }
                          className={`w-24 rounded-xl border px-3 py-2 text-right font-semibold tabular-nums focus:border-accent focus:outline-none ${
                            draft !== undefined ? "border-accent bg-accent/5" : "border-line bg-surface"
                          }`}
                        />
                      ) : (
                        <span className="font-semibold tabular-nums">{line.counted_qty ?? "—"}</span>
                      )}
                    </td>
                    {showExpected ? (
                      <>
                        <td className="py-3 text-right tabular-nums text-charcoal/60">{line.expected_qty ?? "—"}</td>
                        <td
                          className={`py-3 text-right font-semibold tabular-nums ${
                            (line.variance ?? 0) < 0 ? "text-accent" : (line.variance ?? 0) > 0 ? "text-charcoal" : "text-charcoal/40"
                          }`}
                        >
                          {line.variance === null ? "—" : signed(line.variance)}
                        </td>
                        <td className="py-3 text-right tabular-nums text-charcoal/60">
                          {line.variance_value_cents === null ? "—" : formatMoney(line.variance_value_cents, currency)}
                        </td>
                      </>
                    ) : null}
                    <td className="py-3 pl-6 text-xs text-charcoal/60">
                      {line.counted_by_name ?? "Not counted"}
                      {line.counted_at ? <span className="block tabular-nums">{formatDate(line.counted_at)}</span> : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {count && visibleLines.length === 0 ? <p className="py-8 text-sm text-charcoal/60">No products match.</p> : null}
        </div>
      </div>

      {scanning ? (
        <SerialScanModal
          line={scanning}
          busy={busy}
          onClose={() => setScanning(null)}
          onSave={async (serials) => {
            if (await save([{ product_id: scanning.product_id, serials }])) {
              setScanning(null);
              onToast(`${serials.length} ${scanning.name} unit${serials.length === 1 ? "" : "s"} recorded.`);
            }
          }}
        />
      ) : null}
      {confirming && count ? (
        <Modal
          title={confirming === "post" ? `Post ${count.number}?` : `Cancel ${count.number}?`}
          subtitle={
            confirming === "post"
              ? "Each counted product is set to what was counted. Missing IMEI units move to quarantine."
              : "Nothing is posted and the counts are kept for reference."
          }
          onClose={() => setConfirming(null)}
          footer={
            <>
              <GhostButton onClick={() => setConfirming(null)}>Back</GhostButton>
              <PrimaryButton disabled={busy} onClick={() => void act(confirming)}>
                {confirming === "post" ? "Post variances" : "Cancel count"}
              </PrimaryButton>
            </>
          }
        >
          {confirming === "post" ? (
            <p className="rounded-2xl bg-surface px-4 py-3 text-sm tabular-nums">
              Net {signed(count.net_variance ?? 0)} units
              {count.variance_value_cents !== null ? ` · ${formatMoney(count.variance_value_cents, currency)} at cost` : ""} across{" "}
              {count.lines_counted} counted product{count.lines_counted === 1 ? "" : "s"}.
            </p>
          ) : null}
        </Modal>
      ) : null}
      {toast ? <Toast message={toast} onDismiss={dismissToast} /> : null}
    </section>
  );
}

function SerialScanModal({
  line,
  busy,
  onClose,
  onSave,
}: {
  line: StockCountLine;
  busy: boolean;
  onClose: () => void;
  onSave: (serials: { kind: "imei" | "serial"; value: string }[]) => Promise<void>;
}) {
  const [text, setText] = useState("");
  const values = [...new Set(text.split(/[\s,;]+/).map((value) => value.trim()).filter(Boolean))];
  const serials = values.map((value) => ({ kind: /^\d{15}$/.test(value) ? ("imei" as const) : ("serial" as const), value }));

  return (
    <Modal
      title={`Scan ${line.name}`}
      subtitle="Scan every unit on the shelf, one per line. Scanning replaces this product's earlier scan."
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy} onClick={() => void onSave(serials)}>
            Record {serials.length} unit{serials.length === 1 ? "" : "s"}
          </PrimaryButton>
        </>
      }
    >
      <label className="block text-sm font-medium">
        IMEI / serial numbers
        <textarea
          autoFocus
          rows={8}
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder={"490154203237518\n356938035643809"}
          className="mt-1.5 w-full rounded-xl border border-transparent bg-surface px-4 py-3 font-mono text-sm focus:border-accent focus:bg-white focus:outline-none"
        />
      </label>
      {line.scanned_tails.length ? (
        <p className="mt-2 text-xs text-charcoal/60">Previously scanned: {line.scanned_tails.join(", ")}</p>
      ) : null}
    </Modal>
  );
}
