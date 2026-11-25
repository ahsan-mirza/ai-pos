import { useRef, useState } from "react";
import { GhostButton, PrimaryButton } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
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

function IssueList({ report }: { report: WorkbookReport }) {
  const rows = report.errors.slice(0, 40);
  if (rows.length === 0) return <p className="text-sm text-charcoal/70">Every row passed the product rules.</p>;
  return (
    <ul className="max-h-64 space-y-2 overflow-y-auto text-sm">
      {rows.map((issue, index) => (
        <li key={`${issue.sheet}-${issue.row}-${issue.field}-${index}`}>
          <span className="font-medium">{issue.sheet}</span> row {issue.row}, {issue.field}: {issue.message}
        </li>
      ))}
      {report.errors.length > rows.length ? <li>{report.errors.length - rows.length} more rows are in the error report.</li> : null}
    </ul>
  );
}

function Wizard({
  onClose,
  onChanged,
}: {
  onClose: () => void;
  onChanged: () => void;
}) {
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
    <Modal
      title="Import Excel"
      subtitle={importModeLabel(mode)}
      width="lg"
      onClose={onClose}
      footer={
        <>
          {step === "upload" ? (
            <PrimaryButton type="button" disabled={busy || file === null} onClick={() => void preview()}>
              {busy ? "Reading…" : "Preview"}
            </PrimaryButton>
          ) : null}
          {step === "preview" && report ? (
            <PrimaryButton type="button" onClick={() => setStep("validation")}>Review validation</PrimaryButton>
          ) : null}
          {step === "validation" && report && canCommitReport(report) ? (
            <PrimaryButton type="button" onClick={() => setStep("confirm")}>Continue</PrimaryButton>
          ) : null}
          {step === "validation" && report && !canCommitReport(report) ? (
            <GhostButton type="button" disabled={busy} onClick={() => void errorReport()}>Download error report</GhostButton>
          ) : null}
          {step === "confirm" ? (
            <PrimaryButton type="button" disabled={busy} onClick={() => void commit()}>Import these changes</PrimaryButton>
          ) : null}
          {step === "results" && report && report.failed > 0 ? (
            <GhostButton type="button" disabled={busy} onClick={() => void errorReport()}>Download error report</GhostButton>
          ) : null}
          <GhostButton type="button" onClick={onClose}>{step === "results" ? "Close" : "Cancel"}</GhostButton>
        </>
      }
    >
      <ol className="mb-4 flex flex-wrap gap-2 text-xs text-charcoal/60">
        {STEPS.map((item) => (
          <li key={item.id} className={item.id === step ? "font-semibold text-charcoal" : ""}>{item.label}</li>
        ))}
      </ol>
      {problem ? <p role="alert" className="mb-3 text-sm text-red-700">{problem}</p> : null}
      {step === "upload" ? (
        <div className="space-y-3">
          <label className="block text-sm font-medium" htmlFor="catalogue-workbook-mode">Import mode</label>
          <select
            id="catalogue-workbook-mode"
            className="w-full rounded-xl border border-line px-3 py-2 text-sm"
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
          <label className="block text-sm font-medium" htmlFor="catalogue-workbook-file">Workbook</label>
          <input
            id="catalogue-workbook-file"
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
          <p className="text-sm text-charcoal/60">Use an AxizPOS product workbook, version 1. Formulas and macros are refused. Nothing is written until you confirm.</p>
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
      {step === "confirm" ? (
        <p className="mt-3 text-sm text-charcoal/70">Stock, recipes, and sales stay as they are. Confirm to write the rows above.</p>
      ) : null}
      {step === "import" ? <p className="text-sm">Importing…</p> : null}
      {report && (step === "validation" || step === "results") ? (
        <div className="space-y-3">
          <IssueList report={report} />
          {report.warnings.slice(0, 10).map((issue, index) => (
            <p key={`${issue.field}-${index}`} className="text-sm text-charcoal/70">
              {issue.sheet} row {issue.row}, {issue.field}: {issue.message}
            </p>
          ))}
        </div>
      ) : null}
    </Modal>
  );
}

export function CatalogueWorkbookActions({
  query = "",
  onNotice,
  onChanged,
}: {
  query?: string;
  onNotice: (text: string) => void;
  onChanged: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<"export" | "template" | null>(null);

  async function run(kind: "export" | "template") {
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
      <GhostButton type="button" disabled={busy !== null} onClick={() => void run("template")}>
        {busy === "template" ? "Downloading…" : "Download template"}
      </GhostButton>
      <GhostButton type="button" disabled={busy !== null} onClick={() => void run("export")}>
        {busy === "export" ? "Exporting…" : "Export Excel"}
      </GhostButton>
      <GhostButton type="button" onClick={() => setOpen(true)}>Import Excel</GhostButton>
      {open ? (
        <Wizard
          onClose={() => setOpen(false)}
          onChanged={onChanged}
        />
      ) : null}
    </>
  );
}
