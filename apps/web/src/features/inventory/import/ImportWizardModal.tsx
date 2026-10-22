import {
  Capability,
  IMPORT_FIELDS,
  formatMoney,
  type BatchDetail,
  type ImportMapping,
  type ImportOptions,
  type ImportPreview,
  type ImportPreviewRow,
  type ImportRow,
  type ImportUpload,
  type MappingTemplate,
  type Supplier,
} from "@ai-pos/shared-types";
import { ArrowLeft, ArrowRight, CheckCircle2, Layers, Loader2, X } from "lucide-react";
import { useCallback, useEffect, useId, useMemo, useState } from "react";
import { ErrorNote, GhostButton, PrimaryButton } from "../../../components/ui/Field";
import { Toggle } from "../../../components/ui/Toggle";
import { useAuth } from "../../../lib/auth";
import { useCapability } from "../../../lib/capabilities";
import { message } from "../api";
import { useStores } from "../shared";
import { importApi } from "./api";
import { MappingStep, missingRequired } from "./MappingStep";
import { PreviewStep } from "./PreviewStep";
import { UploadStep, fileProblem } from "./UploadStep";
import { StepProgress } from "./WizardParts";

const DEFAULT_OPTIONS: ImportOptions = { auto_generate_codes: false, update_master_price: false };

function toRow(row: ImportPreviewRow): ImportRow {
  return {
    row_number: row.row_number,
    include: row.include,
    name: row.name,
    code: row.code,
    quantity: row.quantity,
    cost_cents: row.cost_cents,
    price_cents: row.price_cents,
    model_number: row.model_number,
    category: row.category,
    sub_category: row.sub_category,
    serials: row.serials,
    expiry_date: row.expiry_date,
  };
}

/** Templates only apply when every header they name exists in this file. */
function fits(template: MappingTemplate, headers: string[]): boolean {
  return Object.values(template.mapping).every((header) => !header || headers.includes(header));
}

export function ImportWizardModal({
  onClose,
  onCommitted,
  onViewBatch,
}: {
  onClose: () => void;
  onCommitted: (batch: BatchDetail) => void;
  onViewBatch: (batch: BatchDetail) => void;
}) {
  const titleId = useId();
  const { user } = useAuth();
  const { stores } = useStores();
  const [step, setStep] = useState(1);
  const [file, setFile] = useState<File | null>(null);
  const [storeId, setStoreId] = useState(user?.store_id ?? "");
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [supplierId, setSupplierId] = useState("");
  const [upload, setUpload] = useState<ImportUpload | null>(null);
  const [mapping, setMapping] = useState<ImportMapping>({});
  const [options, setOptions] = useState<ImportOptions>(DEFAULT_OPTIONS);
  const [templates, setTemplates] = useState<MappingTemplate[]>([]);
  const [templateId, setTemplateId] = useState("");
  const [saveAs, setSaveAs] = useState<string | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [rows, setRows] = useState<ImportPreviewRow[]>([]);
  const [dirty, setDirty] = useState(false);
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState<"upload" | "preview" | "recheck" | "commit" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [committed, setCommitted] = useState<BatchDetail | null>(null);
  const consignmentModule = useCapability(Capability.Consignment);
  const [consignment, setConsignment] = useState(false);

  const supplier = suppliers.find((item) => item.id === supplierId) ?? null;
  const store = stores.find((item) => item.id === storeId) ?? null;

  useEffect(() => {
    if (!storeId && stores.length === 1 && stores[0]) setStoreId(stores[0].id);
  }, [stores, storeId]);

  useEffect(() => {
    importApi
      .suppliers()
      .then(setSuppliers)
      .catch(() => setSuppliers([]));
  }, []);

  useEffect(() => {
    let cancelled = false;
    importApi
      .templates(supplierId || null)
      .then((list) => {
        if (!cancelled) setTemplates(list);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [supplierId]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && busy === null) onClose();
    };
    window.addEventListener("keydown", onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [onClose, busy]);

  const usableTemplates = useMemo(
    () => (upload ? templates.filter((template) => fits(template, upload.headers)) : templates),
    [templates, upload],
  );

  const applyTemplate = useCallback(
    (id: string) => {
      const template = templates.find((item) => item.id === id);
      if (!template) return;
      setTemplateId(id);
      setMapping(template.mapping);
      setOptions((current) => ({ ...current, auto_generate_codes: template.options.auto_generate_codes }));
    },
    [templates],
  );

  const goMapping = async () => {
    if (!file || !storeId) return;
    setError(null);
    if (upload && upload.file_name === file.name) {
      setStep(2);
      return;
    }
    setBusy("upload");
    try {
      const parsed = await importApi.upload(file);
      setUpload(parsed);
      const preferred = templates.find((template) => template.supplier_id === (supplierId || null) && fits(template, parsed.headers));
      if (supplierId && preferred) {
        setTemplateId(preferred.id);
        setMapping(preferred.mapping);
        setOptions((current) => ({ ...current, auto_generate_codes: preferred.options.auto_generate_codes }));
      } else {
        setTemplateId("");
        setMapping(parsed.suggested_mapping);
      }
      setPreview(null);
      setStep(2);
    } catch (caught) {
      setError(message(caught, "The file could not be read."));
    } finally {
      setBusy(null);
    }
  };

  const runPreview = async (edited: ImportPreviewRow[] | null) => {
    if (!upload) return;
    setError(null);
    setBusy(edited ? "recheck" : "preview");
    try {
      const result = await importApi.preview({
        upload_id: upload.upload_id,
        store_id: storeId,
        mapping,
        options,
        rows: edited ? edited.map(toRow) : undefined,
      });
      setPreview(result);
      setRows(result.rows);
      setDirty(false);
      setStep(3);
    } catch (caught) {
      setError(message(caught, "The rows could not be checked."));
    } finally {
      setBusy(null);
    }
  };

  const updateRow = (rowNumber: number, patch: Partial<ImportPreviewRow>) => {
    setRows((current) => current.map((row) => (row.row_number === rowNumber ? { ...row, ...patch } : row)));
    if (!("include" in patch && Object.keys(patch).length === 1)) setDirty(true);
  };

  const commit = async () => {
    if (!upload || !preview) return;
    setError(null);
    setBusy("commit");
    try {
      const batch = await importApi.commit({
        upload_id: upload.upload_id,
        store_id: storeId,
        supplier_id: supplierId || null,
        mapping,
        options,
        rows: rows.map(toRow),
        save_template_as: saveAs?.trim() ? saveAs.trim() : null,
        notes,
        consignment: consignment && Boolean(supplierId),
      });
      setCommitted(batch);
      onCommitted(batch);
    } catch (caught) {
      setError(message(caught, "The batch could not be committed."));
      if (dirty) await runPreview(rows);
    } finally {
      setBusy(null);
    }
  };

  const deleteTemplate = async (id: string) => {
    try {
      await importApi.deleteTemplate(id);
      setTemplates((current) => current.filter((template) => template.id !== id));
      setTemplateId("");
    } catch (caught) {
      setError(message(caught, "The template could not be deleted."));
    }
  };

  const included = rows.filter((row) => row.include);
  const blocking = included.filter((row) => row.status === "ERROR").length;
  const missing = missingRequired(mapping, options);
  const canNext =
    step === 1
      ? file !== null && storeId !== "" && fileProblem(file) === null
      : step === 2
        ? missing.length === 0
        : false;

  return (
    <div
      className="modal-backdrop fixed inset-0 z-50 flex items-center justify-center bg-[#222026]/40 p-3 backdrop-blur-sm sm:p-6"
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="modal-card flex max-h-[94vh] w-full max-w-6xl flex-col overflow-hidden rounded-3xl border border-white/60 bg-white/95 shadow-2xl backdrop-blur-xl"
      >
        <header className="sticky top-0 z-20 flex-none border-b border-line bg-white px-5 pb-5 pt-5 sm:px-7">
          <div className="mb-5 flex items-start justify-between gap-4">
            <div className="flex items-center gap-3">
              <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-accent text-white">
                <Layers size={20} aria-hidden="true" />
              </span>
              <div>
                <h2 id={titleId} className="text-xl font-semibold">
                  Import purchases
                </h2>
                <p className="text-sm text-charcoal/60">
                  {committed
                    ? "Batch committed."
                    : store
                      ? `Into ${store.code} · ${store.name}${supplier ? ` from ${supplier.name}` : ""}`
                      : "Excel, CSV or PDF invoice into a cost-tracked FIFO batch."}
                </p>
              </div>
            </div>
            <button
              type="button"
              aria-label="Close"
              disabled={busy !== null}
              onClick={onClose}
              className="-mr-1 -mt-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-charcoal/70 transition-colors hover:bg-gray-100 hover:text-charcoal disabled:opacity-40"
            >
              <X size={18} aria-hidden="true" />
            </button>
          </div>
          <StepProgress step={committed ? 4 : step} />
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-6 sm:px-7">
          {committed ? (
            <div className="mx-auto flex max-w-lg flex-col items-center py-8 text-center">
              <span className="flex h-16 w-16 items-center justify-center rounded-full bg-accent/10 text-accent">
                <CheckCircle2 size={34} aria-hidden="true" />
              </span>
              <h3 className="mt-5 text-2xl font-semibold">{committed.batch_number}</h3>
              <p className="mt-1 text-sm text-charcoal/60">
                {committed.line_count} lines · {committed.total_items_count.toLocaleString()} units received at{" "}
                {committed.store_code}
              </p>
              <dl className="mt-6 grid w-full grid-cols-2 gap-3">
                <div className="rounded-2xl bg-surface px-4 py-3">
                  <dt className="text-[11px] font-semibold uppercase tracking-wider text-[#6B7280]">Batch cost</dt>
                  <dd className="mt-1 text-lg font-semibold tabular-nums">
                    {formatMoney(committed.total_cost_amount, committed.currency)}
                  </dd>
                </div>
                <div className="rounded-2xl bg-surface px-4 py-3">
                  <dt className="text-[11px] font-semibold uppercase tracking-wider text-[#6B7280]">Status</dt>
                  <dd className="mt-1 text-lg font-semibold">Active · FIFO</dd>
                </div>
              </dl>
            </div>
          ) : step === 1 ? (
            <UploadStep
              file={file}
              onFile={(next, problem) => {
                setFile(next);
                setError(problem);
                if (next?.name !== upload?.file_name) setUpload(null);
              }}
              stores={stores}
              storeId={storeId}
              onStore={setStoreId}
              storePinned={Boolean(user?.store_id)}
              suppliers={suppliers}
              supplierId={supplierId}
              onSupplier={(id) => {
                setSupplierId(id);
                setTemplateId("");
              }}
              onSupplierCreated={(created) => {
                setSuppliers((current) => [...current, created].sort((a, b) => a.name.localeCompare(b.name)));
                setSupplierId(created.id);
              }}
              extra={
                consignmentModule ? (
                  <Toggle
                    label="Consignment stock"
                    description={
                      supplierId
                        ? "The supplier owns these units until they sell; you settle sold units from Consignment."
                        : "Choose the supplier above: consignment stock belongs to them until it sells."
                    }
                    checked={consignment}
                    disabled={!supplierId}
                    onChange={setConsignment}
                  />
                ) : null
              }
            />
          ) : step === 2 && upload ? (
            <MappingStep
              upload={upload}
              mapping={mapping}
              onMapping={(next) => {
                setMapping(next);
                setTemplateId("");
              }}
              options={options}
              onOptions={setOptions}
              templates={usableTemplates}
              templateId={templateId}
              onApplyTemplate={applyTemplate}
              onDeleteTemplate={(id) => void deleteTemplate(id)}
              saveAs={saveAs}
              onSaveAs={setSaveAs}
              supplierName={supplier?.name ?? null}
            />
          ) : step === 3 && preview ? (
            <PreviewStep
              preview={preview}
              rows={rows}
              onRow={updateRow}
              dirty={dirty}
              rechecking={busy === "recheck"}
              onRecheck={() => void runPreview(rows)}
              options={options}
              onOptions={setOptions}
              notes={notes}
              onNotes={setNotes}
            />
          ) : null}
          <ErrorNote message={error} />
        </div>

        <footer className="sticky bottom-0 z-20 flex flex-none flex-wrap items-center justify-between gap-3 border-t border-line bg-white px-5 py-4 sm:px-7">
          <span className="text-xs text-charcoal/50">
            {committed
              ? "Stock, IMEIs and the audit trail were updated."
              : step === 2
                ? `${IMPORT_FIELDS.filter((spec) => mapping[spec.field]).length} of ${IMPORT_FIELDS.length} fields mapped`
                : step === 3
                  ? `${included.length} line${included.length === 1 ? "" : "s"} will be committed`
                  : "Your original file is kept with the batch."}
          </span>
          <div className="flex flex-wrap gap-3">
            {committed ? (
              <>
                <GhostButton onClick={onClose}>Close</GhostButton>
                <PrimaryButton onClick={() => onViewBatch(committed)}>
                  <span className="inline-flex items-center gap-2">
                    View batch <ArrowRight size={16} aria-hidden="true" />
                  </span>
                </PrimaryButton>
              </>
            ) : (
              <>
                {step > 1 ? (
                  <GhostButton disabled={busy !== null} onClick={() => setStep(step - 1)}>
                    <span className="inline-flex items-center gap-2">
                      <ArrowLeft size={16} aria-hidden="true" /> Back
                    </span>
                  </GhostButton>
                ) : (
                  <GhostButton onClick={onClose}>Cancel</GhostButton>
                )}
                {step === 1 ? (
                  <PrimaryButton disabled={!canNext || busy !== null} onClick={() => void goMapping()}>
                    <span className="inline-flex items-center gap-2">
                      {busy === "upload" ? <Loader2 size={16} className="animate-spin" aria-hidden="true" /> : null}
                      {busy === "upload" ? "Reading file…" : "Map columns"}
                      {busy === "upload" ? null : <ArrowRight size={16} aria-hidden="true" />}
                    </span>
                  </PrimaryButton>
                ) : step === 2 ? (
                  <PrimaryButton disabled={!canNext || busy !== null} onClick={() => void runPreview(null)}>
                    <span className="inline-flex items-center gap-2">
                      {busy === "preview" ? <Loader2 size={16} className="animate-spin" aria-hidden="true" /> : null}
                      {busy === "preview" ? "Checking rows…" : "Preview import"}
                      {busy === "preview" ? null : <ArrowRight size={16} aria-hidden="true" />}
                    </span>
                  </PrimaryButton>
                ) : (
                  <PrimaryButton
                    disabled={busy !== null || dirty || blocking > 0 || included.length === 0}
                    onClick={() => void commit()}
                  >
                    <span className="inline-flex items-center gap-2">
                      {busy === "commit" ? <Loader2 size={16} className="animate-spin" aria-hidden="true" /> : null}
                      {busy === "commit" ? "Committing…" : dirty ? "Re-check rows first" : "Finish & commit"}
                    </span>
                  </PrimaryButton>
                )}
              </>
            )}
          </div>
        </footer>
      </div>
    </div>
  );
}
