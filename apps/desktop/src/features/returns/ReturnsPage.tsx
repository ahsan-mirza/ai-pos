import {
  RefundMethod,
  formatMoney,
  type OverrideReason,
  type ReceiptItem,
  type ReturnUpsert,
} from "@ai-pos/shared-types";
import {
  Check,
  CheckCircle2,
  ChevronRight,
  Clock3,
  FileText,
  Gift,
  History,
  Printer,
  ReceiptText,
  Repeat2,
  RotateCcw,
  ScanLine,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { DrawerFooter, DrawerHeader, TotalsBreakdown, drawerShell } from "../../components/shell/Drawer";
import type { SyncState } from "../../components/shell/HeaderBar";
import { PageFrame } from "../../components/shell/RegisterShell";
import { SearchInput } from "../../components/shell/SearchInput";
import { useShell, useShellPage } from "../../components/shell/ShellContext";
import { ui } from "../../components/shell/tokens";
import {
  inTauri,
  nextDocumentNumber,
  openDocumentPdf,
  recentReturns,
  type CashierProfile,
  type LocalReturn,
} from "../../lib/tauri";
import type { CashierSession } from "../auth/session";
import { printReceipt } from "../printing/print";
import type { ReceiptDoc } from "@ai-pos/receipt";
import { creditNoteReceipt, giftReceiptFromLookup } from "../printing/saleReceipt";
import { activeShiftId } from "../shifts/shift";
import { BarcodeWedge } from "../checkout/BarcodeWedge";
import { startExchange } from "../checkout/exchange";
import { useBusinessCurrency } from "../checkout/currency";
import { ImeiModal } from "../checkout/ImeiModal";
import { useSyncEngine } from "../checkout/useSyncEngine";
import { DataTable, type DataTableColumn } from "../../components/DataTable";
import { ManagerApprovalModal } from "../../components/ManagerApprovalModal";
import { RefundTenders } from "./RefundTenders";
import { ReturnLineCard } from "./ReturnLineCard";
import {
  allowedRefundMethods,
  buildReturnEvent,
  daysSinceSale,
  defaultCondition,
  defaultReason,
  invoiceNumber,
  isExchangeOnly,
  isOutsideWindow,
  overrideLabels,
  paymentLabels,
  priceLines,
  refundMethodLabels,
  remainingQuantity,
  requiredOverrides,
  restockInstruction,
  returnTotals,
  storeCreditCode,
  type LineDraft,
  type PricedLine,
  type ReturnDraft,
  type ReturnTotals,
} from "./returnMath";
import { findReceipt, submitReturn, verifyApprover, type LoadedReceipt, type ReturnBatch } from "./returnsClient";

type Step = "lookup" | "items" | "refund" | "done";

const steps: { id: Exclude<Step, "done">; label: string }[] = [
  { id: "lookup", label: "Receipt" },
  { id: "items", label: "Items" },
  { id: "refund", label: "Refund" },
];

const emptyAmounts: Record<RefundMethod, string> = { cash: "", original_card: "", original_bnpl: "", store_credit: "" };

interface Approval {
  approver: CashierProfile;
  reasons: OverrideReason[];
  note: string;
}

interface Completed {
  kind: "recorded" | "queued";
  message: string | null;
  invoice: string;
  returnId: string;
  receiptDoc: ReceiptDoc;
  currency: string;
  totals: ReturnTotals;
  lines: PricedLine[];
  tenders: { method: RefundMethod; amount: number }[];
  creditCode: string;
  approverName: string | null;
  restock: string[];
}

function parseCents(value: string): number | null {
  const trimmed = value.trim();
  if (trimmed === "") return 0;
  if (!/^\d+(\.\d{1,2})?$/.test(trimmed)) return null;
  return Math.round(Number(trimmed) * 100);
}

const toAmount = (cents: number) => (cents / 100).toFixed(2);

interface ReturnsPageProps {
  session: CashierSession;
}

export function ReturnsPage({ session }: ReturnsPageProps) {
  const [step, setStep] = useState<Step>("lookup");
  const [code, setCode] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [loaded, setLoaded] = useState<LoadedReceipt | null>(null);
  const [drafts, setDrafts] = useState<Record<string, LineDraft>>({});
  const [waiveFee, setWaiveFee] = useState(false);
  const [serialFor, setSerialFor] = useState<ReceiptItem | null>(null);
  const [amounts, setAmounts] = useState<Record<RefundMethod, string>>(emptyAmounts);
  const [notes, setNotes] = useState("");
  const [approval, setApproval] = useState<Approval | null>(null);
  const [askApproval, setAskApproval] = useState(false);
  const [busy, setBusy] = useState(false);
  const [completed, setCompleted] = useState<Completed | null>(null);
  const [recent, setRecent] = useState<LocalReturn[]>([]);
  const [pulse, setPulse] = useState(0);
  const batchRef = useRef<ReturnBatch | null>(null);
  const { report, desktop } = useSyncEngine(pulse);
  const codeInput = useRef<HTMLInputElement>(null);
  useShellPage(busy, setNotice);
  const { navigate } = useShell();

  const receipt = loaded?.receipt ?? null;
  const businessCurrency = useBusinessCurrency();
  const currency = receipt?.currency ?? businessCurrency;
  const lines = useMemo(() => (receipt ? priceLines(receipt, drafts, waiveFee) : []), [receipt, drafts, waiveFee]);
  const totals = useMemo(() => returnTotals(lines), [lines]);
  const required = receipt ? requiredOverrides(receipt, lines, session.user.permissions, new Date()) : [];
  const approved = approval !== null && required.every((reason) => approval.reasons.includes(reason));
  const needsApproval = required.length > 0 && !approved;
  const exchangeOnly = receipt ? isExchangeOnly(receipt, new Date()) : false;
  const allowed = receipt ? allowedRefundMethods(receipt.payment_method, exchangeOnly) : [];

  const tenders = allowed.map((method) => ({ method, amount: parseCents(amounts[method]) }));
  const tenderSum = tenders.reduce((sum, tender) => sum + (tender.amount ?? 0), 0);
  const cardAmount = tenders.find((tender) => tender.method === RefundMethod.OriginalCard)?.amount ?? 0;
  const tenderProblem = !receipt
    ? null
    : tenders.some((tender) => tender.amount === null)
      ? "Enter amounts like 12.50."
      : cardAmount > receipt.card_refundable_cents
        ? `Card reversal cannot exceed ${formatMoney(receipt.card_refundable_cents, currency)}.`
        : tenderSum !== totals.total
          ? `Tenders add up to ${formatMoney(tenderSum, currency)}; the refund is ${formatMoney(totals.total, currency)}.`
          : null;

  const missingSerial = lines.some((line) => line.item.is_serialized && line.draft.serialValue === null);
  const itemsReady = lines.length > 0 && !missingSerial && totals.total > 0;

  const loadRecent = useCallback(() => {
    if (!inTauri()) return;
    recentReturns(8)
      .then(setRecent)
      .catch(() => setRecent([]));
  }, []);

  useEffect(loadRecent, [loadRecent, pulse]);

  const reset = useCallback(() => {
    setStep("lookup");
    setCode("");
    setLoaded(null);
    setDrafts({});
    setWaiveFee(false);
    setAmounts(emptyAmounts);
    setNotes("");
    setApproval(null);
    setCompleted(null);
    setNotice(null);
    batchRef.current = null;
  }, []);

  const lookup = useCallback(
    async (raw: string) => {
      const value = raw.trim();
      if (busy || value === "") return;
      if (value.length < 8) {
        setNotice("Enter the full receipt barcode or the 8-character invoice number.");
        return;
      }
      setBusy(true);
      setNotice(null);
      try {
        const found = await findReceipt(value);
        setLoaded(found);
        setCode(found.receipt.invoice);
        setDrafts({});
        setWaiveFee(false);
        setApproval(null);
        setAmounts(emptyAmounts);
        batchRef.current = null;
        setStep("items");
        const left = found.receipt.items.some((item) => remainingQuantity(item) > 0);
        setNotice(
          !left
            ? "Every item on this sale has already been returned."
            : found.source === "cache"
              ? `The server is unreachable, so this is the copy cached on this register. ${found.message ?? ""}`.trim()
              : found.source === "register"
                ? "This sale was rung up on this register and has not synced yet. The return will sync after it."
                : null,
        );
      } catch (error) {
        setNotice(error instanceof Error ? error.message : String(error));
      } finally {
        setBusy(false);
      }
    },
    [busy],
  );

  const toggleLine = (item: ReceiptItem) => {
    const current = drafts[item.sale_item_id];
    if (current !== undefined) {
      const next = { ...drafts };
      delete next[item.sale_item_id];
      setDrafts(next);
      return;
    }
    setDrafts({
      ...drafts,
      [item.sale_item_id]: {
        quantity: item.is_serialized ? 1 : remainingQuantity(item),
        condition: receipt ? defaultCondition(receipt.policy) : "unopened_resealable",
        reason: receipt ? defaultReason(receipt.policy) : "changed_mind",
        serialValue: null,
        serialKind: null,
      },
    });
    if (item.is_serialized) setSerialFor(item);
  };

  const patchLine = (saleItemId: string, patch: Partial<LineDraft>) => {
    setDrafts((current) => {
      const draft = current[saleItemId];
      return draft === undefined ? current : { ...current, [saleItemId]: { ...draft, ...patch } };
    });
  };

  const goToRefund = () => {
    if (!receipt || !itemsReady) return;
    const next = { ...emptyAmounts };
    const primary = allowed[0] ?? RefundMethod.StoreCredit;
    if (primary === RefundMethod.OriginalCard) {
      const card = Math.min(totals.total, receipt.card_refundable_cents);
      if (card > 0) next.original_card = toAmount(card);
      if (totals.total - card > 0) next.store_credit = toAmount(totals.total - card);
    } else {
      next[primary] = toAmount(totals.total);
    }
    setAmounts(next);
    setNotice(null);
    setStep("refund");
  };

  const fillRemainder = (method: RefundMethod) => {
    const others = tenders
      .filter((tender) => tender.method !== method)
      .reduce((sum, tender) => sum + (tender.amount ?? 0), 0);
    let rest = Math.max(0, totals.total - others);
    if (method === RefundMethod.OriginalCard && receipt) rest = Math.min(rest, receipt.card_refundable_cents);
    setAmounts((current) => ({ ...current, [method]: rest > 0 ? toAmount(rest) : "" }));
  };

  const refund = async () => {
    if (!receipt || busy || needsApproval || tenderProblem !== null || !itemsReady) return;
    const chosen = tenders.flatMap((tender) =>
      tender.amount !== null && tender.amount > 0 ? [{ method: tender.method, amount: tender.amount }] : [],
    );
    const draft: ReturnDraft = {
      receipt,
      lines,
      tenders: chosen,
      cashierId: session.user.id,
      notes,
      approval:
        required.length > 0 && approval !== null
          ? { approverId: approval.approver.id, reasons: required, note: approval.note }
          : null,
    };
    const signature = JSON.stringify([
      receipt.sale_id,
      lines.map((line) => [line.item.sale_item_id, line.draft, line.fee]),
      chosen,
      notes.trim(),
      draft.approval,
    ]);
    let batch = batchRef.current;
    if (batch === null || batch.signature !== signature) {
      const creditCode = storeCreditCode();
      const creditNoteNumber = inTauri() ? await nextDocumentNumber("CN").catch(() => null) : null;
      batch = {
        batchId: crypto.randomUUID(),
        signature,
        creditCode,
        events: [buildReturnEvent({ ...draft, creditNoteNumber, shiftId: activeShiftId() }, creditCode)],
        enqueued: false,
      };
      batchRef.current = batch;
    }

    setBusy(true);
    setNotice(null);
    try {
      const outcome = await submitReturn(batch);
      if (outcome.kind === "recorded" || outcome.kind === "queued") {
        batchRef.current = null;
        const payload = batch.events[0]?.payload as { id?: string; credit_note_number?: string | null } | undefined;
        const receiptDoc = creditNoteReceipt({
          number: payload?.credit_note_number ?? `CN-${(payload?.id ?? "").slice(0, 8).toUpperCase()}`,
          invoice: receipt.invoice,
          lines: lines.map((line) => ({
            name: line.item.name,
            quantity: line.draft.quantity,
            unitCents: line.item.unit_price_cents,
            refundCents: line.refund,
            detail: line.draft.serialValue ? `IMEI ${line.draft.serialValue}` : null,
          })),
          subtotalCents: totals.total - totals.tax,
          taxCents: totals.tax,
          totalCents: totals.total,
          tenders: chosen.map((tender) => ({ label: refundMethodLabels[tender.method], amountCents: tender.amount })),
          cashier: session.user.full_name,
          currency,
        });
        void printReceipt(receiptDoc, { kickDrawer: chosen.some((tender) => tender.method === RefundMethod.Cash) }).then(
          (printed) => {
            if (printed.message) setNotice(`Credit note not printed: ${printed.message}`);
          },
        );
        setCompleted({
          kind: outcome.kind,
          message: outcome.kind === "queued" ? outcome.message : null,
          invoice: receipt.invoice,
          returnId: payload?.id ?? "",
          receiptDoc,
          currency,
          totals,
          lines,
          tenders: chosen,
          creditCode: batch.creditCode,
          approverName: draft.approval ? (approval?.approver.full_name ?? null) : null,
          restock: lines.map((line) => restockInstruction(line, receipt.policy)),
        });
        const recorded = batch.events[0]?.payload as ReturnUpsert | undefined;
        if (!inTauri() && recorded) {
          // The browser preview has no SQLite history, so it lists this session's returns.
          const entry: LocalReturn = {
            id: recorded.id,
            sale_id: receipt.sale_id,
            batch_id: batch.batchId,
            status: outcome.kind === "recorded" ? "synced" : "pending",
            error: null,
            created_at: Math.floor(Date.now() / 1000),
            payload: recorded,
          };
          setRecent((current) => [entry, ...current].slice(0, 8));
        }
        setApproval(null);
        setStep("done");
      } else if (outcome.kind === "rejected") {
        batchRef.current = null;
        setNotice(`Return not recorded: ${outcome.message}`);
      } else {
        setNotice(`Return not recorded: ${outcome.message} Refund again to retry.`);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (/approval/i.test(message)) setApproval(null);
      setNotice(message);
    } finally {
      setBusy(false);
      setPulse((value) => value + 1);
    }
  };

  const statusText = desktop
    ? report.message
    : "Browser preview posts returns straight to the API; the Tauri shell queues them in SQLite when offline.";
  const activeIndex = steps.findIndex((item) => item.id === step);
  const now = new Date();
  const canChooseRefund = step === "items" && itemsReady && !busy;
  const sync: SyncState = desktop
    ? {
        tone: report.pending > 0 ? "pending" : "synced",
        label: report.pending > 0 ? `${report.pending} unsynced` : "Synced",
        title: statusText,
      }
    : { tone: "live", label: "Live", title: statusText };

  return (
    <>
      <BarcodeWedge
        onScan={(scan) => {
          if (step === "lookup") void lookup(scan);
        }}
      />
      <PageFrame
        title="Returns & Exchanges"
        sync={sync}
        drawer={
            <aside
              aria-label="Refund summary"
              className={`${drawerShell} max-h-[45vh] shrink-0 border-t lg:max-h-none lg:w-[400px] lg:border-l lg:border-t-0 xl:w-[440px]`}
            >
              <DrawerHeader
                title="Refund Summary"
                count={lines.length > 0 ? `${lines.length} item${lines.length === 1 ? "" : "s"}` : undefined}
                badge={
                  <span className="rounded-full bg-emerald-500/10 px-2.5 py-1 text-[11px] font-semibold tabular-nums text-emerald-700 ring-1 ring-emerald-500/20 dark:text-emerald-300">
                    {desktop ? `${report.pending} unsynced` : "Live"}
                  </span>
                }
              />

              <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto px-5 py-4">
                {step === "done" && completed ? (
                  <RefundBreakdown
                    currency={completed.currency}
                    subtotal={completed.totals.subtotal}
                    taxRefund={completed.totals.tax}
                    restockingFee={completed.totals.fee}
                    totalRefund={completed.totals.total}
                    totalLabel="Refunded"
                  />
                ) : (
                  <>
                    <ul className="space-y-2">
                      {lines.length === 0 ? (
                        <li className="rounded-2xl border border-dashed border-zinc-300 px-4 py-6 text-center text-sm text-zinc-500 dark:border-zinc-700 dark:text-zinc-400">
                          {receipt ? "Tick the items the customer is returning." : "Find the original sale to start a return."}
                        </li>
                      ) : null}
                      {lines.map((line) => (
                        <li
                          key={line.item.sale_item_id}
                          className="rounded-xl border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-950"
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <p className="truncate text-sm font-medium">{line.item.name}</p>
                              <p className="text-xs tabular-nums text-zinc-500 dark:text-zinc-400">
                                {line.draft.quantity} × {formatMoney(line.item.unit_price_cents, currency)}
                                {line.item.is_serialized && line.draft.serialValue === null ? " · scan the unit" : ""}
                              </p>
                            </div>
                            <span className="text-sm font-semibold tabular-nums">{formatMoney(line.refund, currency)}</span>
                          </div>
                        </li>
                      ))}
                    </ul>

                    <div className="mt-5">
                      <RefundBreakdown
                        currency={currency}
                        subtotal={totals.subtotal}
                        taxRefund={totals.tax}
                        restockingFee={totals.fee}
                        feeLabel={waiveFee && totals.policyFee > 0 ? "Waived" : undefined}
                        totalRefund={totals.total}
                        totalLabel="Total Refund"
                      />
                    </div>

                    {totals.policyFee > 0 && step !== "lookup" ? (
                      <button
                        type="button"
                        disabled={busy}
                        aria-pressed={waiveFee}
                        onClick={() => setWaiveFee((value) => !value)}
                        className="mt-3 h-10 w-full rounded-xl border border-zinc-200 bg-white text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-100 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-200 dark:hover:bg-zinc-800"
                      >
                        {waiveFee ? "Charge the restocking fee" : "Waive the restocking fee"}
                      </button>
                    ) : null}

                    {required.length > 0 && lines.length > 0 ? (
                      <div className="mt-4 rounded-2xl border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-950">
                        <p className="flex items-center gap-2 text-sm font-semibold">
                          {approved ? (
                            <ShieldCheck size={16} className="text-emerald-600 dark:text-emerald-400" aria-hidden="true" />
                          ) : (
                            <ShieldAlert size={16} className="text-primary-500" aria-hidden="true" />
                          )}
                          {approved ? `Approved by ${approval?.approver.full_name}` : "Manager approval needed"}
                        </p>
                        <ul className="mt-2 space-y-1 text-xs text-zinc-600 dark:text-zinc-400">
                          {required.map((reason) => (
                            <li key={reason}>{overrideLabels[reason]}</li>
                          ))}
                        </ul>
                        {!approved ? (
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => setAskApproval(true)}
                            className="mt-3 h-10 w-full rounded-xl bg-zinc-900 text-sm font-semibold text-white hover:bg-zinc-800 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-white"
                          >
                            Manager PIN
                          </button>
                        ) : null}
                      </div>
                    ) : null}
                  </>
                )}
              </div>

              <DrawerFooter>
                {step === "lookup" || step === "items" ? (
                  <button type="button" disabled={!canChooseRefund} onClick={goToRefund} className={ui.primaryAction}>
                    {step === "lookup"
                      ? "Choose refund method"
                      : missingSerial
                        ? "Scan each returned unit"
                        : "Choose refund method"}
                  </button>
                ) : null}
                {step === "refund" ? (
                  <>
                    <button
                      type="button"
                      disabled={busy || needsApproval || tenderProblem !== null}
                      onClick={() => void refund()}
                      className={ui.primaryAction}
                    >
                      {busy ? "Recording return…" : `Refund ${formatMoney(totals.total, currency)}`}
                    </button>
                    <button type="button" disabled={busy} onClick={() => setStep("items")} className={ui.ghostAction}>
                      Back to items
                    </button>
                  </>
                ) : null}
                {step === "done" ? (
                  <button type="button" onClick={reset} className={ui.primaryAction}>
                    <RotateCcw size={18} aria-hidden="true" /> Next return
                  </button>
                ) : null}
                {step === "items" ? (
                  <button type="button" disabled={busy} onClick={reset} className={ui.ghostAction}>
                    Start over
                  </button>
                ) : null}
              </DrawerFooter>
            </aside>
        }
      >
          <div className="space-y-6 p-5">
            {step !== "done" ? (
              <ol className="flex flex-wrap items-center gap-2" aria-label="Return steps">
                {steps.map((item, index) => {
                  const state = item.id === step ? "current" : index < activeIndex ? "complete" : "upcoming";
                  return (
                    <li key={item.id} className="flex items-center gap-2">
                      <StepPill index={index + 1} label={item.label} state={state} />
                      {index < steps.length - 1 ? (
                        <span
                          aria-hidden="true"
                          className={`h-px w-6 ${index < activeIndex ? "bg-primary-500" : "bg-zinc-200 dark:bg-zinc-800"}`}
                        />
                      ) : null}
                    </li>
                  );
                })}
              </ol>
            ) : null}

            {notice ? (
              <p
                role="status"
                className="rounded-2xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm text-zinc-800 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-200"
              >
                {notice}
              </p>
            ) : null}

            {step === "lookup" ? (
              <>
                <section className="rounded-2xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                    <p className="text-sm font-semibold">Scan the receipt barcode or enter the invoice number</p>
                    <span className="flex items-center gap-2 text-xs text-zinc-500 dark:text-zinc-400">
                      <span className="relative flex h-2 w-2">
                        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60 motion-reduce:animate-none" />
                        <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
                      </span>
                      Scanner ready
                    </span>
                  </div>
                  <SearchInput
                    id="receipt-code"
                    label="Receipt barcode or invoice number"
                    inputRef={codeInput}
                    value={code}
                    placeholder="e.g. 3F9A21C7"
                    onChange={setCode}
                    onSubmit={(value) => void lookup(value)}
                    actionLabel="Find Sale"
                    icon={ScanLine}
                    busy={busy}
                    autoFocus
                    uppercase
                  />
                </section>

                <RecentReturnsTable entries={recent} busy={busy} onOpen={(invoice) => void lookup(invoice)} />
              </>
            ) : null}

            {step === "items" && receipt ? (
              <div>
                <div className="grid gap-px overflow-hidden rounded-2xl border border-zinc-200 bg-zinc-200 text-sm sm:grid-cols-4 dark:border-zinc-800 dark:bg-zinc-800">
                  <ReceiptFact label="Invoice" mono>
                    {receipt.invoice}
                  </ReceiptFact>
                  <ReceiptFact label="Sold">
                    {new Date(receipt.created_at).toLocaleDateString()} · {daysSinceSale(receipt, now)}d ago
                  </ReceiptFact>
                  <ReceiptFact label="Paid by">{paymentLabels[receipt.payment_method]}</ReceiptFact>
                  <ReceiptFact label="Total / refunded">
                    {formatMoney(receipt.total_cents, currency)} / {formatMoney(receipt.refunded_cents, currency)}
                  </ReceiptFact>
                </div>
                <div className="mt-2 flex justify-end gap-2">
                  {inTauri() && loaded?.source !== "register" ? (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() =>
                        void openDocumentPdf("gift_receipt", receipt.sale_id, receipt.invoice).catch((error: unknown) =>
                          setNotice(error instanceof Error ? error.message : String(error)),
                        )
                      }
                      className={`${ui.secondaryAction} h-10 px-4`}
                    >
                      <FileText size={16} aria-hidden="true" /> A4 gift receipt
                    </button>
                  ) : null}
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() =>
                      void printReceipt(giftReceiptFromLookup(receipt, session.user.full_name), {
                        kickDrawer: false,
                        manual: true,
                      }).then((outcome) => setNotice(outcome.message ?? `Gift receipt for ${receipt.invoice} printed.`))
                    }
                    className={`${ui.secondaryAction} h-10 px-4`}
                  >
                    <Gift size={16} aria-hidden="true" /> Gift receipt
                  </button>
                </div>
                {isOutsideWindow(receipt, now) ? (
                  <p className="mt-3 flex items-center gap-2 rounded-2xl bg-primary-500/10 px-4 py-3 text-sm font-medium text-primary-700 dark:text-primary-300">
                    <Clock3 size={16} aria-hidden="true" />
                    Outside the {receipt.policy.window_days + (receipt.policy.exchange_window_days ?? 0)}-day return
                    window. A manager must approve this return.
                  </p>
                ) : exchangeOnly ? (
                  <p className="mt-3 flex items-center gap-2 rounded-2xl bg-amber-500/10 px-4 py-3 text-sm font-medium text-amber-800 dark:text-amber-200">
                    <Clock3 size={16} aria-hidden="true" />
                    Past the {receipt.policy.window_days}-day refund window: exchange or store credit only.
                  </p>
                ) : null}
                <ul className="mt-4 space-y-3">
                  {receipt.items.map((item) => (
                    <ReturnLineCard
                      key={item.sale_item_id}
                      item={item}
                      policy={receipt.policy}
                      currency={currency}
                      priced={lines.find((line) => line.item.sale_item_id === item.sale_item_id)}
                      disabled={busy}
                      onToggle={() => toggleLine(item)}
                      onChange={(patch) => patchLine(item.sale_item_id, patch)}
                      onVerifySerial={() => setSerialFor(item)}
                    />
                  ))}
                </ul>
              </div>
            ) : null}

            {step === "refund" && receipt ? (
              <div className="space-y-5">
                <RefundTenders
                  receipt={receipt}
                  allowed={allowed}
                  amounts={amounts}
                  total={totals.total}
                  disabled={busy}
                  onChange={(method, value) => setAmounts((current) => ({ ...current, [method]: value }))}
                  onFill={fillRemainder}
                />
                {tenderProblem ? (
                  <p className="text-sm font-medium text-primary-700 dark:text-primary-300">{tenderProblem}</p>
                ) : null}
                <label className="block text-sm font-semibold" htmlFor="return-notes">
                  Notes (optional)
                  <textarea
                    id="return-notes"
                    rows={3}
                    maxLength={1000}
                    value={notes}
                    onChange={(event) => setNotes(event.target.value)}
                    placeholder="Packaging, accessories included, customer comments"
                    className="mt-2 w-full resize-none rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm font-normal text-zinc-900 placeholder:text-zinc-400 focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500/20 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-100 dark:placeholder:text-zinc-500"
                  />
                </label>
              </div>
            ) : null}

            {step === "done" && completed ? (
              <div>
                <div className="flex flex-wrap items-center gap-3">
                  <span
                    className={`flex h-12 w-12 items-center justify-center rounded-2xl ${
                      completed.kind === "recorded"
                        ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                        : "bg-primary-500/10 text-primary-600 dark:text-primary-400"
                    }`}
                  >
                    {completed.kind === "recorded" ? <CheckCircle2 size={22} /> : <Clock3 size={22} />}
                  </span>
                  <div className="min-w-0">
                    <h2 className="text-2xl font-semibold">
                      {completed.kind === "recorded" ? "Return recorded" : "Saved on this register"}
                    </h2>
                    <p className="text-sm text-zinc-600 dark:text-zinc-400">
                      Invoice {completed.invoice}
                      {completed.kind === "queued"
                        ? ` · It will sync when the API is reachable. (${completed.message ?? ""})`
                        : ""}
                      {completed.approverName ? ` · Approved by ${completed.approverName}` : ""}
                    </p>
                  </div>
                  <div className="ml-auto flex gap-2">
                    <button
                      type="button"
                      onClick={() =>
                        void printReceipt(completed.receiptDoc, { kickDrawer: false, manual: true }).then((printed) =>
                          setNotice(printed.message ?? `Credit note ${completed.receiptDoc.number} sent to the printer.`),
                        )
                      }
                      className={outlineButton}
                    >
                      <Printer size={16} aria-hidden="true" /> Print credit note
                    </button>
                    {inTauri() && completed.returnId ? (
                      <button
                        type="button"
                        title="A4 tax credit note (once the return has synced)"
                        onClick={() =>
                          void openDocumentPdf("credit_note", completed.returnId, completed.receiptDoc.number).catch(
                            (error: unknown) => setNotice(error instanceof Error ? error.message : String(error)),
                          )
                        }
                        className={outlineButton}
                      >
                        <ReceiptText size={16} aria-hidden="true" /> A4 PDF
                      </button>
                    ) : null}
                  </div>
                </div>

                <h3 className={sectionLabel}>Pay the customer</h3>
                <ul className="mt-3 grid gap-3 md:grid-cols-3">
                  {completed.tenders.map((tender) => (
                    <li
                      key={tender.method}
                      className="rounded-2xl border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-800 dark:bg-zinc-900"
                    >
                      <p className="text-xs font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                        {refundMethodLabels[tender.method]}
                      </p>
                      <p className="mt-1 text-2xl font-semibold tabular-nums">
                        {formatMoney(tender.amount, completed.currency)}
                      </p>
                      <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
                        {tender.method === RefundMethod.Cash
                          ? "Pay out from the drawer."
                          : tender.method === RefundMethod.OriginalCard
                            ? "Run a refund on the card terminal against the original payment."
                            : "Give the customer this code:"}
                      </p>
                      {tender.method === RefundMethod.StoreCredit ? (
                        <>
                          <p className="mt-2 rounded-xl bg-primary-500 px-3 py-2 text-center font-mono text-base font-semibold tracking-wider text-white">
                            {completed.creditCode}
                          </p>
                          <button
                            type="button"
                            onClick={() => {
                              const first = completed.lines[0];
                              startExchange({
                                voucherCode: completed.creditCode,
                                balanceCents: tender.amount,
                                productId: first?.item.product_id ?? "",
                                productName: first?.item.name ?? "the item",
                              });
                              navigate("checkout");
                            }}
                            className="mt-2 flex min-h-11 w-full items-center justify-center gap-2 rounded-xl border border-primary-500 px-3 py-2 text-sm font-semibold leading-tight text-primary-600 transition hover:bg-primary-500/10 dark:text-primary-400"
                          >
                            <Repeat2 size={16} className="shrink-0" aria-hidden="true" /> Exchange size or colour
                          </button>
                        </>
                      ) : null}
                    </li>
                  ))}
                </ul>

                <h3 className={sectionLabel}>Returned stock</h3>
                <ul className="mt-3 divide-y divide-zinc-200 rounded-2xl border border-zinc-200 dark:divide-zinc-800 dark:border-zinc-800">
                  {completed.lines.map((line, index) => (
                    <li key={line.item.sale_item_id} className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
                      <span>
                        <span className="font-medium">{line.item.name}</span>
                        <span className="text-zinc-500 dark:text-zinc-400"> × {line.draft.quantity}</span>
                      </span>
                      <span className="rounded-full bg-zinc-100 px-3 py-1 text-xs font-semibold text-zinc-700 dark:bg-zinc-800 dark:text-zinc-200">
                        {completed.restock[index]}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
      </PageFrame>

      {serialFor ? (
        <ImeiModal
          productName={serialFor.name}
          title="Verify returned unit"
          description={
            serialFor.serial_last4
              ? `Scan the ${serialFor.serial_kind === "imei" ? "IMEI" : "serial"} on the device. The unit sold ends in ${serialFor.serial_last4}.`
              : `Scan the IMEI or serial on the ${serialFor.name}.`
          }
          confirmLabel="Verify unit"
          check={(value, kind) => {
            const expectedFull = loaded?.serials[serialFor.sale_item_id];
            if (serialFor.serial_kind !== null && kind !== serialFor.serial_kind) {
              return `This sale recorded ${serialFor.serial_kind === "imei" ? "an IMEI" : "a serial number"}.`;
            }
            if (expectedFull !== undefined ? value !== expectedFull : !value.endsWith(serialFor.serial_last4 ?? "")) {
              return "That is not the unit on this receipt.";
            }
            return null;
          }}
          onClose={() => {
            if (drafts[serialFor.sale_item_id]?.serialValue === null) {
              const next = { ...drafts };
              delete next[serialFor.sale_item_id];
              setDrafts(next);
            }
            setSerialFor(null);
          }}
          onConfirm={(value, kind) => {
            patchLine(serialFor.sale_item_id, { serialValue: value, serialKind: kind });
            setSerialFor(null);
          }}
        />
      ) : null}

      {askApproval ? (
        <ManagerApprovalModal
          reasons={required.map((reason) => overrideLabels[reason])}
          subtitle={`A manager other than ${session.user.full_name} must enter their PIN.`}
          verify={(username, pin) => verifyApprover(session, username, pin)}
          remote={{ kind: "REFUND", requestedById: session.user.id, title: `Refund needs approval (${session.user.full_name})` }}
          onClose={() => setAskApproval(false)}
          onApproved={(approver, note) => {
            setApproval({ approver, reasons: required, note });
            setAskApproval(false);
          }}
        />
      ) : null}
    </>
  );
}

const outlineButton =
  "inline-flex items-center gap-2 rounded-full border border-zinc-300 px-4 py-2 text-sm font-semibold text-zinc-800 transition-colors hover:border-primary-500 hover:text-primary-600 dark:border-zinc-700 dark:text-zinc-100 dark:hover:border-primary-500 dark:hover:text-primary-400";
const sectionLabel = "mt-8 text-xs font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400";

function StepPill({ index, label, state }: { index: number; label: string; state: "current" | "complete" | "upcoming" }) {
  return (
    <span
      aria-current={state === "current" ? "step" : undefined}
      className={`flex h-10 items-center gap-2 rounded-full px-4 text-sm font-semibold transition-colors ${
        state === "current"
          ? "bg-primary-500 text-white shadow-md shadow-primary-500/25"
          : state === "complete"
            ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
            : "bg-zinc-100 text-zinc-500 dark:bg-zinc-900 dark:text-zinc-400"
      }`}
    >
      {state === "complete" ? <Check size={15} strokeWidth={2.5} aria-hidden="true" /> : null}
      <span className="tabular-nums">{index}.</span>
      {label}
    </span>
  );
}

function ReceiptFact({ label, mono = false, children }: { label: string; mono?: boolean; children: ReactNode }) {
  return (
    <div className="bg-white p-4 dark:bg-zinc-950">
      <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400">{label}</p>
      <p className={`mt-0.5 font-semibold tabular-nums ${mono ? "font-mono" : ""}`}>{children}</p>
    </div>
  );
}

function RefundBreakdown({
  currency,
  subtotal,
  taxRefund,
  restockingFee,
  totalRefund,
  feeLabel,
  totalLabel,
}: {
  currency: string;
  subtotal: number;
  taxRefund: number;
  restockingFee: number;
  totalRefund: number;
  feeLabel?: string;
  totalLabel: string;
}) {
  return (
    <TotalsBreakdown
      rows={[
        { label: "Items", value: formatMoney(subtotal, currency) },
        { label: "Tax refund", value: formatMoney(taxRefund, currency) },
        { label: "Restocking fee", value: feeLabel ?? `−${formatMoney(restockingFee, currency)}` },
      ]}
      totalLabel={totalLabel}
      total={formatMoney(totalRefund, currency)}
    />
  );
}

type RefundKind = "completed" | "store_credit" | "reversed";

const refundKinds: Record<RefundKind, { label: string; className: string }> = {
  completed: {
    label: "Completed",
    className: "bg-emerald-500/10 text-emerald-700 ring-emerald-500/20 dark:text-emerald-300",
  },
  store_credit: {
    label: "Store Credit",
    className: "bg-primary-500/10 text-primary-700 ring-primary-500/25 dark:text-primary-300",
  },
  reversed: { label: "Reversed", className: "bg-sky-500/10 text-sky-700 ring-sky-500/20 dark:text-sky-300" },
};

/** Card refunds are reversals; refunds paid entirely as a credit code are store credit; anything else was paid out. */
function refundKind(entry: LocalReturn): RefundKind {
  const methods = entry.payload.tenders.map((tender) => tender.method);
  if (methods.includes(RefundMethod.OriginalCard)) return "reversed";
  if (methods.length > 0 && methods.every((method) => method === RefundMethod.StoreCredit)) return "store_credit";
  return "completed";
}

const syncLabels: Record<LocalReturn["status"], { label: string; className: string }> = {
  synced: { label: "Synced", className: "text-zinc-500 dark:text-zinc-400" },
  pending: { label: "Queued", className: "text-amber-600 dark:text-amber-400" },
  rejected: { label: "Rejected", className: "text-red-600 dark:text-red-400" },
};

function RecentReturnsTable({
  entries,
  busy,
  onOpen,
}: {
  entries: LocalReturn[];
  busy: boolean;
  onOpen: (invoice: string) => void;
}) {
  const columns: DataTableColumn<LocalReturn>[] = [
    {
      id: "credit-note",
      header: "Credit note",
      cell: (entry) => (
        <>
          <span className="block font-mono text-sm font-semibold">
            {entry.payload.credit_note_number ?? `CN-${entry.id.slice(0, 8).toUpperCase()}`}
          </span>
          <span className="block font-mono text-xs text-zinc-500 dark:text-zinc-400">
            Sale {invoiceNumber(entry.payload.original_sale_id)}
          </span>
        </>
      ),
    },
    {
      id: "processed",
      header: "Processed",
      className: "text-zinc-700 dark:text-zinc-300",
      cell: (entry) =>
        new Date(entry.created_at * 1000).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }),
    },
    { id: "items", header: "Items", align: "right", cell: (entry) => entry.payload.items.length },
    {
      id: "status",
      header: "Status",
      cell: (entry) => {
        const kind = refundKinds[refundKind(entry)];
        const sync = syncLabels[entry.status];
        return (
          <>
            <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ${kind.className}`}>
              {kind.label}
            </span>
            <span title={entry.error ?? undefined} className={`ml-2 text-xs font-medium ${sync.className}`}>
              {sync.label}
            </span>
          </>
        );
      },
    },
    {
      id: "amount",
      header: "Amount",
      align: "right",
      className: "font-semibold",
      cell: (entry) => formatMoney(entry.payload.total_refund_cents, entry.payload.currency),
    },
    {
      id: "open",
      header: <span className="sr-only">Open</span>,
      width: 40,
      className: "text-zinc-400 group-hover:text-primary-500 dark:text-zinc-500",
      cell: () => <ChevronRight size={16} aria-hidden="true" />,
    },
  ];

  return (
    <section aria-labelledby="recent-returns-title">
      <div className="flex items-end justify-between gap-3">
        <div>
          <h2 id="recent-returns-title" className="text-base font-semibold">
            Recent Activity
          </h2>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">Returns processed on this register. Select one to reopen its sale.</p>
        </div>
      </div>
      <DataTable
        aria-label="Recent returns"
        className="mt-3"
        minWidth="640px"
        columns={columns}
        data={entries}
        getRowId={(entry) => entry.id}
        onRowClick={(entry) => {
          if (!busy) onOpen(invoiceNumber(entry.payload.original_sale_id));
        }}
        rowClassName={() => "group"}
        emptyState={{
          icon: History,
          title: "No returns yet this shift",
          description: "Scan a receipt above to process the first one.",
        }}
        pagination={{ mode: "client", pageSize: 10, pageSizeOptions: [10, 25, 50] }}
      />
    </section>
  );
}
