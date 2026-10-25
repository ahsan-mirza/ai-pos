import {
  IMPORT_FIELDS,
  IMPORT_SOURCE_LABELS,
  type ImportField,
  type ImportMapping,
  type ImportOptions,
  type ImportUpload,
  type MappingTemplate,
} from "@ai-pos/shared-types";
import { AlertTriangle, BookmarkPlus, Check, Trash2, Wand2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Select } from "../../../components/ui/Select";
import { Toggle } from "../../../components/ui/Toggle";

const UNMAPPED = "__none__";

export function missingRequired(mapping: ImportMapping, options: ImportOptions): string[] {
  return IMPORT_FIELDS.filter(
    (spec) => spec.required && !(spec.field === "code" && options.auto_generate_codes) && !mapping[spec.field],
  ).map((spec) => spec.label);
}

export function MappingStep({
  upload,
  mapping,
  onMapping,
  options,
  onOptions,
  templates,
  templateId,
  onApplyTemplate,
  onDeleteTemplate,
  saveAs,
  onSaveAs,
  supplierName,
}: {
  upload: ImportUpload;
  mapping: ImportMapping;
  onMapping: (mapping: ImportMapping) => void;
  options: ImportOptions;
  onOptions: (options: ImportOptions) => void;
  templates: MappingTemplate[];
  templateId: string;
  onApplyTemplate: (id: string) => void;
  onDeleteTemplate: (id: string) => void;
  saveAs: string | null;
  onSaveAs: (name: string | null) => void;
  supplierName: string | null;
}) {
  const [hovered, setHovered] = useState<string | null>(null);
  const columnOf = useMemo(() => {
    const byHeader = new Map<string, ImportField>();
    for (const [field, header] of Object.entries(mapping)) if (header) byHeader.set(header, field as ImportField);
    return byHeader;
  }, [mapping]);
  const sample = (header: string | undefined) => {
    if (!header) return null;
    const index = upload.headers.indexOf(header);
    return upload.sample_rows.find((row) => row[index])?.[index] ?? null;
  };
  const headerOptions = [
    { value: UNMAPPED, label: "— Not mapped —" },
    ...upload.headers.map((header) => ({
      value: header,
      label: header,
      hint: columnOf.has(header) ? `Used by ${IMPORT_FIELDS.find((s) => s.field === columnOf.get(header))?.label}` : undefined,
    })),
  ];
  const assign = (field: ImportField, header: string) => {
    const next: ImportMapping = { ...mapping };
    if (header === UNMAPPED) delete next[field];
    else {
      for (const key of Object.keys(next) as ImportField[]) if (next[key] === header) delete next[key];
      next[field] = header;
    }
    onMapping(next);
  };
  const missing = missingRequired(mapping, options);
  const fieldLabel = (field: ImportField) => IMPORT_FIELDS.find((spec) => spec.field === field)?.label ?? field;

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
      <div className="space-y-4">
        <div className="flex flex-wrap items-end gap-3 rounded-2xl border border-line bg-surface/50 p-3">
          <div className="min-w-[200px] flex-1">
            <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-[#6B7280]">
              Mapping template
            </span>
            <Select
              aria-label="Mapping template"
              value={templateId}
              placeholder={templates.length ? "Load a saved template" : "No saved templates yet"}
              disabled={templates.length === 0}
              options={templates.map((template) => ({
                value: template.id,
                label: template.name,
                hint: template.supplier_name ?? "Any supplier",
              }))}
              onChange={onApplyTemplate}
            />
          </div>
          {templateId ? (
            <button
              type="button"
              onClick={() => onDeleteTemplate(templateId)}
              aria-label="Delete template"
              className="flex h-11 w-11 items-center justify-center rounded-full border border-line bg-white text-charcoal/60 transition hover:border-accent hover:text-accent"
            >
              <Trash2 size={16} aria-hidden="true" />
            </button>
          ) : null}
        </div>

        <ul className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-white">
          {IMPORT_FIELDS.map((spec) => {
            const header = mapping[spec.field];
            const value = sample(header);
            const optional = !spec.required || (spec.field === "code" && options.auto_generate_codes);
            const unmet = !optional && !header;
            return (
              <li
                key={spec.field}
                onMouseEnter={() => setHovered(header ?? null)}
                onMouseLeave={() => setHovered(null)}
                className={`grid grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] items-center gap-3 px-4 py-3 transition-colors ${
                  unmet ? "bg-accent/[0.04]" : ""
                }`}
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-semibold">{spec.label}</span>
                    {optional ? (
                      <span className="text-[10px] font-semibold uppercase tracking-wider text-charcoal/40">
                        Optional
                      </span>
                    ) : (
                      <span className="rounded-full bg-accent px-1.5 py-px text-[9px] font-bold uppercase tracking-wider text-white">
                        Required
                      </span>
                    )}
                  </div>
                  <span className="mt-0.5 block truncate text-xs text-charcoal/50">
                    {value ? (
                      <>
                        e.g. <span className="font-mono text-charcoal/70">{value}</span>
                      </>
                    ) : (
                      spec.hint ?? "\u00a0"
                    )}
                  </span>
                </div>
                <Select
                  aria-label={`Column for ${spec.label}`}
                  value={header ?? UNMAPPED}
                  options={headerOptions}
                  onChange={(next) => assign(spec.field, next)}
                />
              </li>
            );
          })}
        </ul>

        <Toggle
          label="Auto-generate SKU & barcode"
          description="Rows without a code get a new SKU and an in-store EAN-13 barcode."
          checked={options.auto_generate_codes}
          onChange={(checked) => onOptions({ ...options, auto_generate_codes: checked })}
        />

        <div className="rounded-2xl border border-line p-3">
          <label className="flex items-center gap-3 text-sm font-medium">
            <input
              type="checkbox"
              checked={saveAs !== null}
              onChange={(event) =>
                onSaveAs(event.target.checked ? `${supplierName ?? IMPORT_SOURCE_LABELS[upload.import_source]} layout` : null)
              }
              className="h-4 w-4 rounded accent-accent"
            />
            <BookmarkPlus size={16} className="text-charcoal/50" aria-hidden="true" />
            Save this mapping as a template {supplierName ? `for ${supplierName}` : ""}
          </label>
          {saveAs !== null ? (
            <input
              aria-label="Template name"
              value={saveAs}
              maxLength={80}
              onChange={(event) => onSaveAs(event.target.value)}
              className="mt-2.5 h-10 w-full rounded-full border border-line bg-surface px-4 text-sm focus:border-accent focus:bg-white focus:outline-none"
            />
          ) : null}
        </div>

        {missing.length ? (
          <p className="flex items-start gap-2 rounded-2xl bg-warning/10 px-4 py-3 text-sm text-warning" role="status">
            <AlertTriangle size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
            Map a column for {missing.join(", ")}.
          </p>
        ) : (
          <p className="flex items-center gap-2 rounded-2xl bg-charcoal/[0.04] px-4 py-3 text-sm text-charcoal/70">
            <Check size={16} className="text-accent" aria-hidden="true" />
            Every required field is mapped.
          </p>
        )}
      </div>

      <div className="min-w-0">
        <div className="mb-2 flex items-center justify-between gap-3">
          <h3 className="text-sm font-semibold">File preview</h3>
          <span className="inline-flex items-center gap-1.5 text-xs text-charcoal/50">
            <Wand2 size={13} aria-hidden="true" />
            {upload.total_rows} rows · first {upload.sample_rows.length} shown
          </span>
        </div>
        <div className="overflow-auto rounded-2xl border border-line">
          <table className="w-full min-w-max text-left text-xs">
            <thead>
              <tr className="bg-charcoal text-white">
                {upload.headers.map((header) => {
                  const field = columnOf.get(header);
                  return (
                    <th
                      key={header}
                      className={`whitespace-nowrap px-3 py-2.5 align-bottom font-semibold transition-colors ${
                        hovered === header ? "bg-accent" : ""
                      }`}
                    >
                      {field ? (
                        <span className="mb-1 block text-[9px] font-bold uppercase tracking-wider text-accent">
                          {hovered === header ? <span className="text-white">{fieldLabel(field)}</span> : fieldLabel(field)}
                        </span>
                      ) : (
                        <span className="mb-1 block text-[9px] font-bold uppercase tracking-wider text-white/30">
                          Ignored
                        </span>
                      )}
                      {header}
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {upload.sample_rows.map((row, index) => (
                <tr key={index} className="border-t border-line">
                  {upload.headers.map((header, column) => (
                    <td
                      key={header}
                      className={`max-w-[220px] truncate whitespace-nowrap px-3 py-2 tabular-nums ${
                        columnOf.has(header) ? "text-charcoal" : "text-charcoal/35"
                      } ${hovered === header ? "bg-accent/[0.06]" : ""}`}
                    >
                      {row[column] || <span className="text-charcoal/20">—</span>}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {upload.warnings.length ? (
          <ul className="mt-3 space-y-1 text-xs text-charcoal/60">
            {upload.warnings.map((warning) => (
              <li key={warning} className="flex items-start gap-1.5">
                <AlertTriangle size={13} className="mt-px shrink-0 text-accent" aria-hidden="true" />
                {warning}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </div>
  );
}
