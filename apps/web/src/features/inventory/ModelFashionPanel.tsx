import {
  GENDER_LABELS,
  type CatalogAttributes,
  type FashionAttributes,
  type Gender,
  type Product,
  type ProductModel,
} from "@ai-pos/shared-types";
import { Shirt } from "lucide-react";
import { useEffect, useId, useMemo, useState } from "react";
import { ErrorNote, PrimaryButton, SelectField, TextField } from "../../components/ui/Field";
import { message, modelsApi } from "./api";
import { PhotoGallery } from "./PhotoGallery";

const FIELDS = ["season", "collection", "gender", "material", "fit", "care"] as const;

function formOf(model: ProductModel): Record<(typeof FIELDS)[number], string> {
  return {
    season: model.season ?? "",
    collection: model.collection ?? "",
    gender: model.gender ?? "",
    material: model.material ?? "",
    fit: model.fit ?? "",
    care: model.care ?? "",
  };
}

/** A datalist of values already used in the catalogue, so seasons and collections stay consistent. */
function Suggestions({ id, values }: { id: string; values: string[] }) {
  return (
    <datalist id={id}>
      {values.map((value) => (
        <option key={value} value={value} />
      ))}
    </datalist>
  );
}

/** Season, collection, gender, material, fit and care for a model (copied to every variant), and its photos. */
export function ModelFashionPanel({
  model,
  variants,
  canEdit,
  onSaved,
}: {
  model: ProductModel;
  variants: Product[];
  canEdit: boolean;
  onSaved: (model: ProductModel) => void;
}) {
  const [form, setForm] = useState(() => formOf(model));
  const [picker, setPicker] = useState<CatalogAttributes | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const ids = useId();

  useEffect(() => setForm(formOf(model)), [model]);
  useEffect(() => {
    void modelsApi.attributes().then(setPicker, () => setPicker(null));
  }, []);

  const colours = useMemo(() => {
    const values = new Set<string>();
    for (const variant of variants) {
      const entry = Object.entries(variant.variant_attributes ?? {}).find(([key]) => /colou?r/i.test(key));
      if (entry) values.add(entry[1]);
    }
    return [...values].sort();
  }, [variants]);

  const changed = FIELDS.some((field) => form[field] !== formOf(model)[field]);

  const save = async () => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const body: FashionAttributes = {};
      for (const field of FIELDS) {
        if (form[field] === formOf(model)[field]) continue;
        const value = form[field].trim();
        if (field === "gender") body.gender = (value || null) as Gender | null;
        else body[field] = value || null;
      }
      const saved = await modelsApi.update(model.id, body);
      onSaved(saved);
      setNotice(`Saved and copied to ${model.variant_count} variant${model.variant_count === 1 ? "" : "s"}.`);
    } catch (caught) {
      setError(message(caught, "Could not save the model details."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="mb-6 grid gap-4 rounded-2xl border border-line p-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <div>
        <div className="mb-3 flex items-center justify-between gap-2">
          <h3 className="flex items-center gap-2 text-base font-semibold">
            <Shirt size={16} aria-hidden="true" className="text-accent" /> Fashion details
          </h3>
          {canEdit ? (
            <PrimaryButton disabled={!changed || busy} onClick={() => void save()}>
              {busy ? "Saving…" : "Save details"}
            </PrimaryButton>
          ) : null}
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <TextField
            label="Season"
            placeholder="SS26"
            list={`${ids}-seasons`}
            value={form.season}
            disabled={!canEdit}
            onChange={(event) => setForm({ ...form, season: event.target.value.toUpperCase() })}
          />
          <TextField
            label="Collection"
            placeholder="Resort Edit"
            list={`${ids}-collections`}
            value={form.collection}
            disabled={!canEdit}
            onChange={(event) => setForm({ ...form, collection: event.target.value })}
          />
          <SelectField
            label="Gender"
            value={form.gender}
            disabled={!canEdit}
            options={[
              { value: "", label: "Not set" },
              ...(Object.keys(GENDER_LABELS) as Gender[]).map((value) => ({ value, label: GENDER_LABELS[value] })),
            ]}
            onChange={(value) => setForm({ ...form, gender: value })}
          />
          <TextField
            label="Fit"
            placeholder="Slim, regular, relaxed"
            list={`${ids}-fits`}
            value={form.fit}
            disabled={!canEdit}
            onChange={(event) => setForm({ ...form, fit: event.target.value })}
          />
          <TextField
            label="Material"
            placeholder="100% organic cotton"
            list={`${ids}-materials`}
            value={form.material}
            disabled={!canEdit}
            onChange={(event) => setForm({ ...form, material: event.target.value })}
          />
          <TextField
            label="Care"
            placeholder="Machine wash 30°C"
            value={form.care}
            disabled={!canEdit}
            onChange={(event) => setForm({ ...form, care: event.target.value })}
          />
        </div>
        <Suggestions id={`${ids}-seasons`} values={picker?.seasons ?? []} />
        <Suggestions id={`${ids}-collections`} values={picker?.collections ?? []} />
        <Suggestions id={`${ids}-fits`} values={picker?.fits ?? []} />
        <Suggestions id={`${ids}-materials`} values={picker?.materials ?? []} />
        {notice ? <p className="mt-3 text-sm text-charcoal/70">{notice}</p> : null}
        <ErrorNote message={error} />
      </div>
      <PhotoGallery path={`/api/v1/product-models/${model.id}/images`} canManage={canEdit} colours={colours} />
    </section>
  );
}
