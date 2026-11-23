import type { ReceiptDoc } from "@ai-pos/receipt";
import { AlertTriangle, ReceiptText } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { ui } from "../../components/shell/tokens";
import {
  applyReceiptChoice,
  finishPrint,
  PRINTER_UNAVAILABLE_MESSAGE,
  printConfirmationSlips,
  type PrintGate,
  type ReceiptPrompt,
} from "./receiptConfirmation";

interface ReceiptConfirmationModalProps {
  prompt: ReceiptPrompt;
  onDismiss: () => void;
  onPrinted: (message: string) => void;
  onPrint: (
    slip: ReceiptDoc,
    options: { kickDrawer: false; manual: true },
  ) => Promise<{ printed: boolean; message: string | null }>;
  onDownloadPdf: () => Promise<void>;
  /** Opens on the printer-failure panel. Checkout leaves this unset and starts at the question. */
  initialPhase?: "ask" | "failed";
  initialError?: string | null;
}

/** Asks once after a settled payment. Printing uses the slips already saved on the prompt. */
export function ReceiptConfirmationModal({
  prompt,
  onDismiss,
  onPrinted,
  onPrint,
  onDownloadPdf,
  initialPhase = "ask",
  initialError = null,
}: ReceiptConfirmationModalProps) {
  const titleId = useId();
  const questionId = useId();
  const gate = useRef<PrintGate>({ printing: false, attempts: 0, payments: 1 });
  const printedSlips = useRef(0);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  const [phase, setPhase] = useState<"ask" | "printing" | "failed">(initialPhase);
  const [error, setError] = useState<string | null>(initialError);
  const [pdfNote, setPdfNote] = useState<string | null>(null);
  const [pdfBusy, setPdfBusy] = useState(false);
  const printing = phase === "printing";

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || printing) return;
      event.preventDefault();
      onDismiss();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onDismiss, printing]);

  const runPrint = async (choice: "yes" | "retry") => {
    const decision = applyReceiptChoice(choice, gate.current);
    gate.current = decision.gate;
    if (!decision.print) return;
    setPhase("printing");
    setError(null);
    let result: { printed: number; error: string | null };
    try {
      result = await printConfirmationSlips(prompt.slips, onPrint, printedSlips.current);
    } catch {
      result = { printed: printedSlips.current, error: PRINTER_UNAVAILABLE_MESSAGE };
    }
    if (!alive.current) return;
    if (result.error) {
      printedSlips.current = result.printed;
      gate.current = finishPrint(gate.current);
      setPhase("failed");
      setError(result.error);
      return;
    }
    onPrinted(
      prompt.documentKind === "invoice"
        ? `Invoice ${prompt.invoiceNumber} sent to the printer.`
        : `Receipt ${prompt.invoiceNumber} sent to the printer.`,
    );
  };

  const download = async () => {
    if (pdfBusy) return;
    setPdfBusy(true);
    setPdfNote(null);
    try {
      await onDownloadPdf();
      setPdfNote("Invoice PDF opened.");
    } catch (caught) {
      setPdfNote(caught instanceof Error ? caught.message : "The PDF could not be opened.");
    } finally {
      setPdfBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={questionId}
        aria-busy={printing}
        className="modal-card max-w-lg"
      >
        <div className="flex items-start gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-primary text-white">
            <ReceiptText size={20} aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="text-2xl font-semibold">
              {prompt.heading}
            </h2>
            <p className="text-sm text-charcoal/60 dark:text-zinc-400">Invoice {prompt.invoiceNumber}</p>
          </div>
        </div>

        <dl className="mt-5 space-y-2 text-base">
          {prompt.customerName ? (
            <div className="flex items-baseline justify-between gap-4">
              <dt className="text-charcoal/60 dark:text-zinc-400">Customer</dt>
              <dd className="min-w-0 truncate font-semibold">{prompt.customerName}</dd>
            </div>
          ) : null}
          <div className="flex items-baseline justify-between gap-4">
            <dt className="text-charcoal/60 dark:text-zinc-400">Payment method</dt>
            <dd className="font-semibold">{prompt.methodLabel}</dd>
          </div>
          {prompt.receivedLabel && prompt.receivedText ? (
            <div className="flex items-baseline justify-between gap-4 text-lg">
              <dt className="font-medium">{prompt.receivedLabel}</dt>
              <dd className="font-semibold tabular-nums">{prompt.receivedText}</dd>
            </div>
          ) : null}
          {prompt.changeText ? (
            <div className="flex items-baseline justify-between gap-4">
              <dt className="text-charcoal/60 dark:text-zinc-400">Change due</dt>
              <dd className="font-semibold tabular-nums">{prompt.changeText}</dd>
            </div>
          ) : null}
          {prompt.remainingLabel && prompt.remainingText ? (
            <div className="flex items-baseline justify-between gap-4 text-lg">
              <dt className="font-medium">{prompt.remainingLabel}</dt>
              <dd className="font-semibold tabular-nums">{prompt.remainingText}</dd>
            </div>
          ) : null}
        </dl>

        <p id={questionId} className="mt-5 text-base font-medium">
          {printing ? "Printing receipt…" : prompt.question}
        </p>
        {phase === "failed" && error ? (
          <p role="alert" className="mt-3 flex items-start gap-2 rounded-2xl bg-red-500/10 px-4 py-3 text-sm text-red-700 dark:text-red-200">
            <AlertTriangle size={18} aria-hidden="true" className="mt-0.5 shrink-0" />
            <span>{error}</span>
          </p>
        ) : null}
        {pdfNote ? <p className="mt-3 text-sm text-charcoal/70 dark:text-zinc-300">{pdfNote}</p> : null}

        {phase === "failed" ? (
          <div className="mt-6 flex flex-col gap-3 sm:flex-row">
            <button type="button" className={`${ui.secondaryAction} min-h-14 w-full flex-1 px-4 text-base`} onClick={onDismiss}>
              Close
            </button>
            {prompt.pdfAvailable ? (
              <button
                type="button"
                className={`${ui.secondaryAction} min-h-14 w-full flex-1 px-4 text-base`}
                disabled={pdfBusy}
                onClick={() => void download()}
              >
                {pdfBusy ? "Opening PDF…" : "Download PDF"}
              </button>
            ) : null}
            <button
              type="button"
              className={`${ui.primaryAction} min-h-14 w-full flex-1`}
              onClick={() => void runPrint("retry")}
            >
              Retry Print
            </button>
          </div>
        ) : (
          <div className="mt-6 flex flex-col gap-3 sm:flex-row">
            <button
              type="button"
              className={`${ui.secondaryAction} min-h-14 w-full flex-1 px-4 text-base`}
              disabled={printing}
              onClick={onDismiss}
            >
              No, Skip
            </button>
            <button
              type="button"
              className={`${ui.primaryAction} min-h-14 w-full flex-1`}
              disabled={printing}
              autoFocus
              onClick={() => void runPrint("yes")}
            >
              {printing ? "Printing receipt…" : "Yes, Print Receipt"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
