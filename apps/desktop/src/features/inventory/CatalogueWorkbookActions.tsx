import { useRef, useState } from "react";
import { QuietButton } from "./ui";
import { downloadWorkbook, postWorkbook } from "./workbookClient";
import {
  IMPORT_MODES,
  OFFLINE_MESSAGE,
  TEMPLATE_NAME,
  canCommitReport,
  exportPath,
  importModeLabel,
  workbookFileProblem,
  type ImportMode,
  type WorkbookReport,
} from "./workbook";

type Step = "upload" | "preview" | "validation" | "confirm" | "import" | "results";

const STEPS: { id: Step; label: string }[] = [
  { id: "upload", label: "Upload" },
  { id: "preview", label: "Preview" },
  { id: "validation", label: "Validation" },
  { id: "confirm", label: "Confirmation" },
  { id: "import", label: "Import" },
  { id: "results", label: "Results" },
];

function counts(report: WorkbookReport): string[] {
  return [
    `${report.product_rows} product rows, ${report.menu_rows} menu rows`,
    `${report.created} new, ${report.updated} to update, ${report.unchanged} unchanged`,
    `${report.pricing_created} portions to add, ${report.pricing_updated} portions to update`,
    `${report.modifier_changes} modifier groups to change`,
    `${report.failed} invalid rows, ${report.warnings.length} warnings`,
  ];
}

function Wizard({ onClose, onChanged }: { onClose: () => void; onChanged: () => void }) {
  const [step, setStep] = useState<Step>("upload");
  const [mode, setMode] = useState<ImportMode>("upsert");
  const [file, setFile] = useState<File | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [report, setReport] = useState<WorkbookReport | null>(null);
  const [busy, setBusy] = useState(false);
  const key = useRef<string | null>(null);

  async function preview() {
    if (file === null) return;
    const local = workbookFileProblem(file.name, file.size);
    if (local !== null) {
      setProblem(local);
      return;
    }
    setBusy(true);
    setProblem(null);
    try {
      const result = await postWorkbook("/api/v1/catalogue/workbook/preview", file, { mode });
      if (!result.report) throw new Error("The workbook could not be read.");
      setReport(result.report);
      setStep("preview");
    } catch (caught) {
      setProblem(caught instanceof Error ? caught.message : OFFLINE_MESSAGE);
    } finally {
      setBusy(false);
    }
  }

  async function commit() {
    if (file === null || report === null || !canCommitReport(report)) return;
    if (key.current === null) key.current = crypto.randomUUID();
    setStep("import");
    setBusy(true);
    setProblem(null);
    try {
      const result = await postWorkbook(
        "/api/v1/catalogue/workbook/commit",
        file,
        { mode, job_id: report.job_id, confirm: "true" },
        key.current,
      );
      if (!result.report) throw new Error("The import did not return a result.");
      setReport(result.report);
      setStep("results");
      if (result.report.committed) onChanged();
    } catch (caught) {
      setProblem(caught instanceof Error ? caught.message : OFFLINE_MESSAGE);
      setStep("confirm");
    } finally {
      setBusy(false);
    }
  }

  async function errorReport() {
    if (file === null) return;
    setBusy(true);
    try {
      const result = await postWorkbook("/api/v1/catalogue/workbook/error-report", file, { mode });
      setProblem(result.filename ? `Downloaded ${result.filename}.` : null);
    } catch (caught) {
      setProblem(caught instanceof Error ? caught.message : OFFLINE_MESSAGE);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="dialog" aria-modal="true" aria-labelledby="workbook-import-title">
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white p-5 text-zinc-900 dark:bg-zinc-900 dark:text-zinc-100">
        <h2 id="workbook-import-title" className="text-lg font-semibold">Import Excel</h2>
        <p className="text-sm text-zinc-500">{importModeLabel(mode)}</p>
        <ol className="my-3 flex flex-wrap gap-2 text-xs text-zinc-500">
          {STEPS.map((item) => (
            <li key={item.id} className={item.id === step ? "font-semibold text-zinc-900 dark:text-zinc-100" : ""}>{item.label}</li>
          ))}
        </ol>
        {problem ? <p role="alert" className="mb-3 text-sm text-red-700">{problem}</p> : null}
        {step === "upload" ? (
          <div className="space-y-3">
            <label className="block text-sm font-medium" htmlFor="pos-workbook-mode">Import mode</label>
            <select
              id="pos-workbook-mode"
              className="w-full rounded-xl border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-950"
              value={mode}
              onChange={(event) => {
                setMode(event.target.value as ImportMode);
                key.current = null;
              }}
            >
              {IMPORT_MODES.map((item) => (
                <option key={item.id} value={item.id}>{item.label}</option>
              ))}
            </select>
            <label className="block text-sm font-medium" htmlFor="pos-workbook-file">Workbook</label>
            <input
              id="pos-workbook-file"
              type="file"
              accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              onChange={(event) => {
                const next = event.target.files?.[0] ?? null;
                setFile(next);
                setReport(null);
                key.current = null;
                setProblem(next === null ? null : workbookFileProblem(next.name, next.size));
              }}
            />
            <p className="text-sm text-zinc-500">Use an AxizPOS product workbook, version 1. Nothing is written until you confirm.</p>
          </div>
        ) : null}
        {report && (step === "preview" || step === "confirm" || step === "results") ? (
          <ul className="space-y-1 text-sm">
            {counts(report).map((line) => <li key={line}>{line}</li>)}
            {step === "results" ? (
              <li>{report.committed ? "The catalogue was saved." : "Nothing was written."}{report.replayed ? " This was a repeat of the same import." : ""}</li>
            ) : null}
          </ul>
        ) : null}
        {step === "confirm" ? <p className="mt-3 text-sm">Stock, recipes, and sales stay as they are.</p> : null}
        {step === "import" ? <p className="text-sm">Importing…</p> : null}
        {report && (step === "validation" || step === "results") ? (
          <ul className="max-h-64 space-y-2 overflow-y-auto text-sm">
            {report.errors.length === 0 ? <li>Every row passed the product rules.</li> : null}
            {report.errors.slice(0, 40).map((issue, index) => (
              <li key={`${issue.sheet}-${issue.row}-${index}`}>{issue.sheet} row {issue.row}, {issue.field}: {issue.message}</li>
            ))}
            {report.warnings.slice(0, 10).map((issue, index) => (
              <li key={`warn-${index}`}>{issue.sheet} row {issue.row}, {issue.field}: {issue.message}</li>
            ))}
          </ul>
        ) : null}
        <div className="mt-4 flex flex-wrap justify-end gap-2">
          {step === "upload" ? <QuietButton disabled={busy || file === null} onClick={() => void preview()}>{busy ? "Reading…" : "Preview"}</QuietButton> : null}
          {step === "preview" && report ? <QuietButton onClick={() => setStep("validation")}>Review validation</QuietButton> : null}
          {step === "validation" && report && canCommitReport(report) ? <QuietButton onClick={() => setStep("confirm")}>Continue</QuietButton> : null}
          {step === "validation" && report && !canCommitReport(report) ? <QuietButton disabled={busy} onClick={() => void errorReport()}>Download error report</QuietButton> : null}
          {step === "confirm" ? <QuietButton disabled={busy} onClick={() => void commit()}>Import these changes</QuietButton> : null}
          {step === "results" && report && report.failed > 0 ? <QuietButton disabled={busy} onClick={() => void errorReport()}>Download error report</QuietButton> : null}
          <QuietButton onClick={onClose}>{step === "results" ? "Close" : "Cancel"}</QuietButton>
        </div>
      </div>
    </div>
  );
}

export function CatalogueWorkbookActions({
  online,
  query = "",
  onNotice,
  onChanged,
}: {
  online: boolean;
  query?: string;
  onNotice: (text: string) => void;
  onChanged: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<"export" | "template" | null>(null);

  function offline(): boolean {
    if (online) return false;
    onNotice(OFFLINE_MESSAGE);
    return true;
  }

  async function run(kind: "export" | "template") {
    if (offline()) return;
    setBusy(kind);
    try {
      const filename = kind === "template"
        ? await downloadWorkbook("/api/v1/catalogue/workbook/template", TEMPLATE_NAME)
        : await downloadWorkbook(exportPath(query), "AxizPOS_Product_Menu.xlsx");
      onNotice(kind === "template" ? `Downloaded ${filename}.` : `Exported ${filename}.`);
    } catch (caught) {
      onNotice(caught instanceof Error ? caught.message : OFFLINE_MESSAGE);
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <QuietButton disabled={busy !== null} onClick={() => void run("template")}>
        {busy === "template" ? "Downloading…" : "Download template"}
      </QuietButton>
      <QuietButton disabled={busy !== null} onClick={() => void run("export")}>
        {busy === "export" ? "Exporting…" : "Export Excel"}
      </QuietButton>
      <QuietButton onClick={() => { if (!offline()) setOpen(true); }}>Import Excel</QuietButton>
      {open ? <Wizard onClose={() => setOpen(false)} onChanged={onChanged} /> : null}
    </>
  );
}
