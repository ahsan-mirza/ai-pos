import type { ImportUpload, ProductAttribute } from "@ai-pos/shared-types";
import { useMemo, useState } from "react";
import { Select } from "../../../components/ui/Select";
import { importApi } from "./api";

const UNMAPPED = "__none__";

export function AttributeStep({
  upload,
  attributes,
  mapping,
  onMapping,
  onCreated,
}: {
  upload: ImportUpload;
  attributes: ProductAttribute[];
  mapping: Record<string, string>;
  onMapping: (mapping: Record<string, string>) => void;
  onCreated: (attribute: ProductAttribute) => void;
}) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const used = useMemo(() => new Set(Object.values(mapping).filter(Boolean)), [mapping]);
  const sample = (header: string | undefined) => {
    if (!header) return "";
    const index = upload.headers.indexOf(header);
    return upload.sample_rows.find((row) => row[index])?.[index] ?? "";
  };
  const assign = (key: string, header: string) => {
    const next = { ...mapping };
    if (header === UNMAPPED) delete next[key];
    else {
      for (const other of Object.keys(next)) if (next[other] === header) delete next[other];
      next[key] = header;
    }
    onMapping(next);
  };
  const create = async () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    setError(null);
    try {
      const created = await importApi.createAttribute({ name: trimmed, data_type: "text" });
      onCreated(created);
      setName("");
    } catch {
      setError("That attribute could not be created.");
    }
  };
  const active = attributes.filter((item) => item.active);

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-lg font-semibold">Product specifications</h3>
        <p className="mt-1 max-w-3xl text-sm text-charcoal/70">
          Optional. Skip every column to import products with only the standard fields. A mapped column is stored as a
          specification, not as a variant, serial, or batch.
        </p>
      </div>
      <div className="overflow-x-auto rounded-2xl border border-line">
        <table className="w-full min-w-[40rem] text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs uppercase tracking-wider text-charcoal/50">
              <th className="px-4 py-3">Attribute</th>
              <th className="px-4 py-3">Type</th>
              <th className="px-4 py-3">Spreadsheet column</th>
              <th className="px-4 py-3">Sample</th>
            </tr>
          </thead>
          <tbody>
            {active.map((attribute) => {
              const header = mapping[attribute.key];
              return (
                <tr key={attribute.key} className="border-b border-line last:border-b-0">
                  <th scope="row" className="px-4 py-3 text-left font-medium">
                    {attribute.name}
                    {attribute.required ? <span className="ms-2 text-xs text-accent">Required when mapped</span> : null}
                  </th>
                  <td className="px-4 py-3 text-charcoal/70">
                    {attribute.data_type}
                    {attribute.unit ? ` · ${attribute.unit}` : ""}
                  </td>
                  <td className="px-4 py-3">
                    <Select
                      aria-label={`Column for ${attribute.name}`}
                      value={header || UNMAPPED}
                      options={[
                        { value: UNMAPPED, label: "— Not mapped —" },
                        ...upload.headers.map((item) => ({
                          value: item,
                          label: item,
                          hint: used.has(item) && item !== header ? "Already used" : undefined,
                        })),
                      ]}
                      onChange={(value) => assign(attribute.key, value)}
                    />
                  </td>
                  <td className="px-4 py-3 text-charcoal/60">{sample(header)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-end gap-2">
        <label className="text-sm">
          <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-charcoal/50">Custom attribute</span>
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Name"
            className="h-11 rounded-2xl border border-line px-3"
          />
        </label>
        <button type="button" onClick={() => void create()} className="h-11 rounded-2xl border border-line px-4 text-sm font-semibold">
          Add attribute
        </button>
        {error ? <p className="text-sm text-accent">{error}</p> : null}
      </div>
    </div>
  );
}
