import {
  DISPENSING_CLASS_LABELS,
  formatMoney,
  DISPENSING_CLASSES,
  DOSAGE_FORMS,
  PHARMACY_KIND_LABELS,
  PHARMACY_PRODUCT_KINDS,
  PRICE_CONTROL_LABELS,
  PRICE_CONTROLS,
  STRENGTH_UNITS,
  emptyPharmacyDraft,
  type PharmacyDraft,
  type PharmacyProductDetail,
} from "@ai-pos/shared-types";
import { useEffect } from "react";
import { SelectField, TextField } from "../../components/ui/Field";
import { apiGet } from "../../lib/api";

export function PharmacyFields({
  productId,
  value,
  onChange,
}: {
  productId: string | null;
  value: PharmacyDraft;
  onChange: (next: PharmacyDraft) => void;
}) {
  useEffect(() => {
    if (productId === null) return;
    let live = true;
    void apiGet<PharmacyProductDetail>(`/api/v1/pharmacy/products/${productId}`)
      .then((row) => {
        if (live) onChange(draftFromDetail(row));
      })
      .catch(() => {
        if (live) onChange(emptyPharmacyDraft());
      });
    return () => {
      live = false;
    };
  }, [productId]);

  const patch = (part: Partial<PharmacyDraft>) => onChange({ ...value, ...part });
  const medicine = value.product_kind === "MEDICINE";

  return (
    <div id="product-section-pharmacy" className="mt-6 space-y-6 scroll-mt-4">
      <section className="space-y-3">
        <h3 className="text-sm font-semibold">Medicine identity</h3>
        <div className="grid gap-4 md:grid-cols-2">
          <SelectField
            label="Product kind"
            value={value.product_kind}
            options={PHARMACY_PRODUCT_KINDS.map((kind) => ({ value: kind, label: PHARMACY_KIND_LABELS[kind] }))}
            onChange={(next) => patch({ product_kind: next as PharmacyDraft["product_kind"] })}
          />
          <SelectField
            label="Dispensing class"
            value={value.dispensing_class}
            placeholder="Choose a class"
            options={DISPENSING_CLASSES.map((item) => ({ value: item, label: DISPENSING_CLASS_LABELS[item] }))}
            onChange={(next) => patch({ dispensing_class: next as PharmacyDraft["dispensing_class"] })}
          />
          <TextField label="Generic name" value={value.generic_name} onChange={(event) => patch({ generic_name: event.target.value })} />
          <TextField label="Manufacturer" value={value.manufacturer} onChange={(event) => patch({ manufacturer: event.target.value })} />
          <TextField
            label="Marketing authorization holder"
            value={value.marketing_authorization_holder}
            onChange={(event) => patch({ marketing_authorization_holder: event.target.value })}
          />
          <TextField label="Country of origin" value={value.country_of_origin} onChange={(event) => patch({ country_of_origin: event.target.value })} />
        </div>
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-sm font-semibold">Active ingredients</h3>
          <button
            type="button"
            className="text-xs font-medium text-accent"
            onClick={() =>
              patch({
                ingredients: [...value.ingredients, { name: "", strength_amount: "", strength_unit: "mg", is_active_ingredient: true }],
              })
            }
          >
            Add ingredient
          </button>
        </div>
        {value.ingredients.map((row, index) => (
          <div key={index} className="grid gap-3 md:grid-cols-[1fr_8rem_8rem_auto]">
            <TextField
              label={index === 0 ? "Ingredient" : ""}
              value={row.name}
              onChange={(event) => patch({ ingredients: replaceAt(value.ingredients, index, { ...row, name: event.target.value }) })}
            />
            <TextField
              label={index === 0 ? "Strength" : ""}
              value={row.strength_amount}
              onChange={(event) =>
                patch({ ingredients: replaceAt(value.ingredients, index, { ...row, strength_amount: event.target.value }) })
              }
            />
            <SelectField
              label={index === 0 ? "Unit" : ""}
              value={row.strength_unit}
              options={STRENGTH_UNITS.map((unit) => ({ value: unit, label: unit }))}
              onChange={(next) => patch({ ingredients: replaceAt(value.ingredients, index, { ...row, strength_unit: next }) })}
            />
            <button
              type="button"
              className="self-end pb-2 text-xs text-charcoal/60"
              onClick={() => patch({ ingredients: value.ingredients.filter((_, item) => item !== index) })}
            >
              Remove
            </button>
          </div>
        ))}
      </section>

      {medicine ? (
        <section className="grid gap-4 md:grid-cols-2">
          <TextField label="Strength" value={value.strength_amount} onChange={(event) => patch({ strength_amount: event.target.value })} />
          <SelectField
            label="Strength unit"
            value={value.strength_unit}
            options={STRENGTH_UNITS.map((unit) => ({ value: unit, label: unit }))}
            onChange={(next) => patch({ strength_unit: next })}
          />
          <TextField label="Concentration" value={value.concentration} onChange={(event) => patch({ concentration: event.target.value })} />
          <SelectField
            label="Dosage form"
            value={value.dosage_form}
            placeholder="Choose a form"
            options={DOSAGE_FORMS.map((form) => ({ value: form, label: form }))}
            onChange={(next) => patch({ dosage_form: next })}
          />
          <TextField label="Route" value={value.route} onChange={(event) => patch({ route: event.target.value })} />
        </section>
      ) : null}

      <section className="grid gap-4 md:grid-cols-2">
        <h3 className="md:col-span-2 text-sm font-semibold">Pack and units</h3>
        <TextField label="Pack size" value={value.pack_size_label} onChange={(event) => patch({ pack_size_label: event.target.value })} />
        <TextField
          label="Units per pack"
          value={value.units_per_pack}
          hint="Whole number of base units. One box of 10 is 10, not 0.1."
          onChange={(event) => patch({ units_per_pack: event.target.value })}
        />
        <TextField label="Base unit" value={value.base_unit_code} onChange={(event) => patch({ base_unit_code: event.target.value })} />
        <TextField label="Selling unit" value={value.selling_unit_code} onChange={(event) => patch({ selling_unit_code: event.target.value })} />
      </section>

      <section className="grid gap-4 md:grid-cols-2">
        <h3 className="md:col-span-2 text-sm font-semibold">Registration and storage</h3>
        <TextField label="GTIN" value={value.gtin} onChange={(event) => patch({ gtin: event.target.value })} />
        <TextField
          label="Manufacturer reference"
          value={value.manufacturer_product_ref}
          onChange={(event) => patch({ manufacturer_product_ref: event.target.value })}
        />
        <TextField
          label="Registration number"
          value={value.registration_number}
          hint="Leave blank when it has not been supplied. Nothing is generated."
          onChange={(event) => patch({ registration_number: event.target.value })}
        />
        <TextField
          label="Registration authority"
          value={value.registration_authority}
          onChange={(event) => patch({ registration_authority: event.target.value })}
        />
        <TextField label="Storage" value={value.storage_condition} onChange={(event) => patch({ storage_condition: event.target.value })} />
        <TextField label="Minimum °C" value={value.temp_min_c} onChange={(event) => patch({ temp_min_c: event.target.value })} />
        <TextField label="Maximum °C" value={value.temp_max_c} onChange={(event) => patch({ temp_max_c: event.target.value })} />
      </section>

      <section className="grid gap-4 md:grid-cols-2">
        <h3 className="md:col-span-2 text-sm font-semibold">Official price</h3>
        <SelectField
          label="Price control"
          value={value.price_control}
          options={PRICE_CONTROLS.map((item) => ({ value: item, label: PRICE_CONTROL_LABELS[item] }))}
          onChange={(next) => patch({ price_control: next as PharmacyDraft["price_control"] })}
        />
        {value.price_control === "MINIMUM" || value.price_control === "FIXED" ? (
          <TextField
            label="Official minimum"
            value={value.min_price_cents}
            hint="Leave blank to keep the official price missing."
            onChange={(event) => patch({ min_price_cents: event.target.value })}
          />
        ) : null}
        {value.price_control === "MAXIMUM" || value.price_control === "FIXED" ? (
          <TextField
            label="Official maximum"
            value={value.max_price_cents}
            hint="Leave blank to keep the official price missing."
            onChange={(event) => patch({ max_price_cents: event.target.value })}
          />
        ) : null}
      </section>
      <section className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-sm font-semibold">Documents</h3>
          <button
            type="button"
            className="text-xs font-medium text-accent"
            onClick={() => patch({ documents: [...value.documents, { kind: "leaflet", title: "", reference: "" }] })}
          >
            Add document
          </button>
        </div>
        {value.documents.length === 0 ? <p className="text-xs text-charcoal/50">No leaflet or registration file is attached.</p> : null}
        {value.documents.map((row, index) => (
          <div key={index} className="grid gap-3 md:grid-cols-[10rem_1fr_1fr_auto]">
            <SelectField
              label={index === 0 ? "Kind" : ""}
              value={row.kind}
              options={[
                { value: "leaflet", label: "Leaflet" },
                { value: "registration", label: "Registration" },
                { value: "supplier", label: "Supplier" },
                { value: "other", label: "Other" },
              ]}
              onChange={(next) =>
                patch({
                  documents: value.documents.map((item, itemIndex) =>
                    itemIndex === index ? { ...item, kind: next as PharmacyDraft["documents"][number]["kind"] } : item,
                  ),
                })
              }
            />
            <TextField
              label={index === 0 ? "Title" : ""}
              value={row.title}
              onChange={(event) =>
                patch({
                  documents: value.documents.map((item, itemIndex) =>
                    itemIndex === index ? { ...item, title: event.target.value } : item,
                  ),
                })
              }
            />
            <TextField
              label={index === 0 ? "Reference" : ""}
              value={row.reference}
              onChange={(event) =>
                patch({
                  documents: value.documents.map((item, itemIndex) =>
                    itemIndex === index ? { ...item, reference: event.target.value } : item,
                  ),
                })
              }
            />
            <button
              type="button"
              className="self-end pb-2 text-xs text-charcoal/60"
              onClick={() => patch({ documents: value.documents.filter((_, itemIndex) => itemIndex !== index) })}
            >
              Remove
            </button>
          </div>
        ))}
      </section>
      <p className="text-xs text-charcoal/50">Manufacturer lot and expiry are recorded on the stock batch, not on this product.</p>
    </div>
  );
}

export function PharmacyDetail({ detail }: { detail: PharmacyProductDetail }) {
  const rows: [string, string][] = [
    ["Generic name", show(detail.generic_name)],
    ["Brand", show(detail.brand)],
    ["Category", [detail.category, detail.sub_category].filter(Boolean).join(" / ") || "Not recorded"],
    ["Kind", detail.product_kind],
    ["Dispensing class", detail.dispensing_class],
    ["Classification source", detail.classification_source],
    ["Ingredients", detail.ingredients.length === 0 ? "Not recorded" : detail.ingredients.map(ingredientLine).join("; ")],
    ["Strength", show(detail.strength_display || text(detail.strength_amount))],
    ["Concentration", show(detail.concentration)],
    ["Dosage form", show(detail.dosage_form)],
    ["Route", show(detail.route)],
    ["Pack", packLine(detail)],
    ["SKU", show(detail.sku)],
    ["Barcode", show(detail.barcode)],
    ["GTIN", show(detail.gtin)],
    ["Manufacturer", show(detail.manufacturer)],
    ["Registration", show(detail.registration_number)],
    ["Official price", officialLine(detail)],
    ["Storage", show(detail.storage_condition)],
    ["Status", detail.is_active ? "Active" : "Inactive"],
  ];
  return (
    <section>
      <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-charcoal/50">Pharmacy</h4>
      <dl className="grid gap-x-6 sm:grid-cols-2">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-baseline justify-between gap-4 border-b border-line py-2.5 text-sm">
            <dt className="shrink-0 text-charcoal/60">{label}</dt>
            <dd className={`min-w-0 text-right font-medium ${value === "Not recorded" ? "text-charcoal/40" : ""}`}>{value}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-3 text-xs text-charcoal/50">
        Manufacturer lot and expiry are stock-batch facts. They are not stored on this product.
      </p>
    </section>
  );
}

function show(value: string | null | undefined): string {
  const cleaned = (value ?? "").trim();
  return cleaned === "" ? "Not recorded" : cleaned;
}

function ingredientLine(row: PharmacyProductDetail["ingredients"][number]): string {
  const strength = text(row.strength_amount);
  return strength ? `${row.name} ${strength} ${row.strength_unit}` : row.name;
}

function packLine(detail: PharmacyProductDetail): string {
  const pack = detail.pack_size_label.trim();
  const factor = `${detail.units_per_pack} ${detail.base_unit_code}`;
  if (!pack) return `1 selling unit = ${factor}`;
  return `${pack} · 1 selling unit = ${factor}`;
}

function officialLine(detail: PharmacyProductDetail): string {
  if (detail.official_price_state === "NOT_REQUIRED") return "Not required";
  if (detail.official_price_state === "MISSING") return "Missing — a sale that requires this price stays blocked";
  const amount = detail.max_price_cents ?? detail.min_price_cents;
  return amount === null ? "Entered" : formatMoney(amount, "AED");
}

function replaceAt<T>(rows: T[], index: number, next: T): T[] {
  return rows.map((row, item) => (item === index ? next : row));
}

function text(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "";
  return String(value);
}

function draftFromDetail(row: PharmacyProductDetail): PharmacyDraft {
  const money = (cents: number | null) => (cents === null ? "" : (cents / 100).toFixed(2));
  return {
    ...emptyPharmacyDraft(),
    product_kind: row.product_kind,
    dispensing_class: row.dispensing_class,
    generic_name: row.generic_name,
    manufacturer: row.manufacturer,
    marketing_authorization_holder: row.marketing_authorization_holder,
    country_of_origin: row.country_of_origin,
    description: row.description,
    gtin: row.gtin,
    manufacturer_product_ref: row.manufacturer_product_ref,
    dosage_form: row.dosage_form,
    route: row.route,
    strength_amount: text(row.strength_amount),
    strength_unit: row.strength_unit,
    concentration: row.concentration,
    pack_size_label: row.pack_size_label,
    units_per_pack: String(row.units_per_pack),
    base_unit_code: row.base_unit_code,
    selling_unit_code: row.selling_unit_code,
    storage_condition: row.storage_condition,
    temp_min_c: text(row.temp_min_c),
    temp_max_c: text(row.temp_max_c),
    cold_chain: row.cold_chain,
    handling_instructions: row.handling_instructions,
    warnings_text: row.warnings_text,
    registration_number: row.registration_number ?? "",
    registration_authority: row.registration_authority ?? "",
    price_control: row.price_control,
    min_price_cents: money(row.min_price_cents),
    max_price_cents: money(row.max_price_cents),
    offline_policy: row.offline_policy,
    ingredients:
      row.ingredients.length > 0
        ? row.ingredients.map((item) => ({
            name: item.name,
            strength_amount: text(item.strength_amount),
            strength_unit: item.strength_unit,
            is_active_ingredient: item.is_active_ingredient,
          }))
        : emptyPharmacyDraft().ingredients,
    documents: row.documents.map((item) => ({
      kind: item.kind as PharmacyDraft["documents"][number]["kind"],
      title: item.title,
      reference: item.reference,
    })),
  };
}
