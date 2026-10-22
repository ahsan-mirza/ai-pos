import { IMPORT_ACCEPT, IMPORT_MAX_FILE_BYTES, type Store, type Supplier } from "@ai-pos/shared-types";
import { FileSpreadsheet, FileText, Plus, UploadCloud, X } from "lucide-react";
import { useRef, useState, type DragEvent, type ReactNode } from "react";
import { GhostButton, SelectField } from "../../../components/ui/Field";
import { message } from "../api";
import { storeOptions } from "../shared";
import { formatBytes, importApi } from "./api";

const ACCEPTED = IMPORT_ACCEPT.split(",");

export function fileProblem(file: File): string | null {
  const name = file.name.toLowerCase();
  if (!ACCEPTED.some((suffix) => name.endsWith(suffix))) return "Choose an Excel (.xlsx), CSV or PDF invoice file.";
  if (file.size > IMPORT_MAX_FILE_BYTES) return "Purchase files are limited to 10 MB.";
  if (file.size === 0) return "That file is empty.";
  return null;
}

function FileIcon({ name }: { name: string }) {
  const Icon = name.toLowerCase().endsWith(".pdf") ? FileText : FileSpreadsheet;
  return <Icon size={22} aria-hidden="true" />;
}

export function UploadStep({
  file,
  onFile,
  stores,
  storeId,
  onStore,
  storePinned,
  suppliers,
  supplierId,
  onSupplier,
  onSupplierCreated,
  extra,
}: {
  extra?: ReactNode;
  file: File | null;
  onFile: (file: File | null, problem: string | null) => void;
  stores: Store[];
  storeId: string;
  onStore: (id: string) => void;
  storePinned: boolean;
  suppliers: Supplier[];
  supplierId: string;
  onSupplier: (id: string) => void;
  onSupplierCreated: (supplier: Supplier) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [adding, setAdding] = useState(false);
  const [supplierName, setSupplierName] = useState("");
  const [supplierError, setSupplierError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const take = (picked: File | undefined) => {
    if (picked === undefined) return;
    onFile(picked, fileProblem(picked));
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    take(event.dataTransfer.files[0]);
  };

  const addSupplier = async () => {
    if (supplierName.trim().length < 2) {
      setSupplierError("Enter at least 2 characters.");
      return;
    }
    setSaving(true);
    try {
      const created = await importApi.createSupplier({ name: supplierName.trim() });
      onSupplierCreated(created);
      setAdding(false);
      setSupplierName("");
      setSupplierError(null);
    } catch (caught) {
      setSupplierError(message(caught, "Could not add the supplier."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
      <div>
        <div
          role="button"
          tabIndex={0}
          aria-label="Upload a purchase file"
          onClick={() => input.current?.click()}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              input.current?.click();
            }
          }}
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={`flex min-h-[260px] cursor-pointer flex-col items-center justify-center rounded-3xl border-2 border-dashed px-6 py-10 text-center transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/30 ${
            dragging
              ? "scale-[1.01] border-accent bg-accent/[0.06]"
              : "border-charcoal/15 bg-surface/60 hover:border-accent/60 hover:bg-accent/[0.03]"
          }`}
        >
          <span
            className={`flex h-14 w-14 items-center justify-center rounded-2xl transition-colors ${
              dragging ? "bg-accent text-white" : "bg-white text-accent shadow-sm ring-1 ring-line"
            }`}
          >
            <UploadCloud size={26} aria-hidden="true" />
          </span>
          <p className="mt-4 text-base font-semibold">
            {dragging ? "Drop to upload" : "Drag & drop your purchase file"}
          </p>
          <p className="mt-1 text-sm text-charcoal/60">
            or <span className="font-semibold text-accent underline-offset-2 hover:underline">browse</span> from this
            computer
          </p>
          <div className="mt-5 flex flex-wrap justify-center gap-1.5">
            {[".xlsx", ".csv", ".pdf"].map((suffix) => (
              <span
                key={suffix}
                className="rounded-full bg-white px-2.5 py-1 font-mono text-[11px] font-semibold text-charcoal/60 ring-1 ring-line"
              >
                {suffix}
              </span>
            ))}
            <span className="rounded-full px-2.5 py-1 text-[11px] font-medium text-charcoal/50">Up to 10 MB</span>
          </div>
          <input
            ref={input}
            type="file"
            accept={IMPORT_ACCEPT}
            className="sr-only"
            tabIndex={-1}
            onChange={(event) => {
              take(event.target.files?.[0]);
              event.target.value = "";
            }}
          />
        </div>
        {file ? (
          <div className="mt-3 flex items-center gap-3 rounded-2xl border border-line bg-white px-4 py-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-accent/10 text-accent">
              <FileIcon name={file.name} />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-semibold">{file.name}</span>
              <span className="block text-xs tabular-nums text-charcoal/50">{formatBytes(file.size)}</span>
            </span>
            <button
              type="button"
              aria-label="Remove file"
              onClick={() => onFile(null, null)}
              className="flex h-8 w-8 items-center justify-center rounded-full text-charcoal/60 transition hover:bg-surface hover:text-charcoal"
            >
              <X size={16} aria-hidden="true" />
            </button>
          </div>
        ) : null}
        <p className="mt-3 text-xs leading-relaxed text-charcoal/50">
          Title blocks above the table are skipped automatically. PDF invoices are read table-first; scanned images
          without a text layer cannot be read.
        </p>
      </div>

      <div className="space-y-5">
        <SelectField
          label="Store branch"
          hint="Stock lands at this branch as a new cost-tracked batch."
          value={storeId}
          disabled={storePinned}
          placeholder="Choose a branch"
          options={storeOptions(stores.filter((store) => store.is_active !== false))}
          onChange={onStore}
        />
        <div>
          <SelectField
            label="Supplier (optional)"
            hint="Loads this supplier's saved column mapping."
            value={supplierId}
            searchable
            options={[
              { value: "", label: "No supplier" },
              ...suppliers.map((supplier) => ({
                value: supplier.id,
                label: supplier.name,
                hint: supplier.batch_count ? `${supplier.batch_count} batch${supplier.batch_count === 1 ? "" : "es"}` : supplier.code,
              })),
            ]}
            onChange={onSupplier}
          />
          {adding ? (
            <div className="mt-3 rounded-2xl border border-line bg-surface/60 p-3">
              <label className="block text-xs font-semibold text-charcoal/70" htmlFor="new-supplier">
                New supplier name
              </label>
              <div className="mt-1.5 flex gap-2">
                <input
                  id="new-supplier"
                  autoFocus
                  value={supplierName}
                  onChange={(event) => setSupplierName(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      void addSupplier();
                    }
                  }}
                  placeholder="e.g. Gulf Mobile Trading"
                  className="h-10 min-w-0 flex-1 rounded-full border border-line bg-white px-4 text-sm focus:border-accent focus:outline-none"
                />
                <button
                  type="button"
                  disabled={saving}
                  onClick={() => void addSupplier()}
                  className="h-10 rounded-full bg-charcoal px-4 text-sm font-semibold text-white transition hover:bg-black disabled:opacity-40"
                >
                  Add
                </button>
                <GhostButton onClick={() => setAdding(false)}>Cancel</GhostButton>
              </div>
              {supplierError ? <p className="mt-2 text-xs text-accent">{supplierError}</p> : null}
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setAdding(true)}
              className="mt-2 inline-flex items-center gap-1.5 rounded-full px-1 text-sm font-semibold text-accent transition hover:text-accent-hover"
            >
              <Plus size={15} aria-hidden="true" /> Add supplier
            </button>
          )}
        </div>
      </div>
      {extra ? <div className="mt-4">{extra}</div> : null}
    </div>
  );
}
