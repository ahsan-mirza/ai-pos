import { GENDER_LABELS, type Brand, type Category, type Gender, type ProductModel } from "@ai-pos/shared-types";
import { useRef, useState } from "react";
import { ErrorNote, GhostButton, PrimaryButton, SelectField, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { useTenant } from "../../context/TenantContext";
import { message, modelsApi } from "./api";
import { codeError, fieldErrors, useInvalidFocus, type FieldErrors } from "./formErrors";

const GENDERS = Object.entries(GENDER_LABELS) as [Gender, string][];

export function ModelFormModal({
  model,
  brands,
  categories,
  initialBrandId,
  onClose,
  onSaved,
}: {
  model: ProductModel | null;
  brands: Brand[];
  categories: Category[];
  initialBrandId: string;
  onClose: () => void;
  onSaved: (saved: ProductModel) => Promise<void>;
}) {
  const { isFashion } = useTenant();
  const [brandId, setBrandId] = useState(model?.brand_id ?? initialBrandId);
  const [subCategoryId, setSubCategoryId] = useState(model?.sub_category_id ?? "");
  const [name, setName] = useState(model?.name ?? "");
  const [code, setCode] = useState(model?.code ?? "");
  const [year, setYear] = useState(model?.release_year ? String(model.release_year) : "");
  const [description, setDescription] = useState(model?.description ?? "");
  const [season, setSeason] = useState(model?.season ?? "");
  const [collection, setCollection] = useState(model?.collection ?? "");
  const [gender, setGender] = useState<Gender | "">(model?.gender ?? "");
  const [material, setMaterial] = useState(model?.material ?? "");
  const [fit, setFit] = useState(model?.fit ?? "");
  const [care, setCare] = useState(model?.care ?? "");
  const [fields, setFields] = useState<FieldErrors>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const formRef = useRef<HTMLDivElement>(null);
  const focusInvalid = useInvalidFocus(formRef);

  const clearField = (key: string) =>
    setFields((current) => {
      if (!current[key]) return current;
      const next = { ...current };
      delete next[key];
      return next;
    });

  const subOptions = categories.flatMap((category) =>
    category.sub_categories.map((sub) => ({
      value: sub.id,
      label: `${category.name} > ${sub.name}`,
    })),
  );

  const save = async () => {
    const next: FieldErrors = {};
    if (!model && brandId === "") next.brand_id = "Choose a brand.";
    if (!model && subCategoryId === "") next.sub_category_id = "Choose a category.";
    if (name.trim() === "") next.name = "Model name is required.";
    const codeProblem = codeError(code);
    if (codeProblem) next.code = codeProblem;
    const releaseYear = year.trim() === "" ? null : Number(year);
    if (releaseYear !== null && (!Number.isInteger(releaseYear) || releaseYear < 1980 || releaseYear > 2100)) {
      next.release_year = "Release year must be between 1980 and 2100.";
    }
    setFields(next);
    setError(null);
    if (Object.keys(next).length > 0) {
      focusInvalid();
      return;
    }
    const fashion = isFashion
      ? {
          season: season.trim() || null,
          collection: collection.trim() || null,
          gender: gender || null,
          material: material.trim() || null,
          fit: fit.trim() || null,
          care: care.trim() || null,
        }
      : {};
    const body = {
      name: name.trim(),
      code: code.trim() || null,
      release_year: releaseYear,
      description: description.trim(),
      ...fashion,
    };
    setBusy(true);
    try {
      const saved = model
        ? await modelsApi.update(model.id, body)
        : await modelsApi.create({ ...body, brand_id: brandId, sub_category_id: subCategoryId });
      await onSaved(saved);
    } catch (caught) {
      const apiFields = fieldErrors(caught);
      if (Object.keys(apiFields).length > 0) {
        setFields(apiFields);
        focusInvalid();
      } else setError(message(caught, "Could not save the model."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title={model ? `Edit ${model.name}` : "New model"}
      subtitle="A model sits under one brand and one sub-category. Its sellable SKUs are products."
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy} onClick={() => void save()}>
            {busy ? "Saving…" : "Save"}
          </PrimaryButton>
        </>
      }
    >
      <div ref={formRef} className="grid gap-4 md:grid-cols-2">
        <SelectField
          label="Brand"
          value={brandId}
          placeholder="Choose a brand"
          disabled={model !== null}
          options={brands.map((brand) => ({ value: brand.id, label: brand.name }))}
          error={fields.brand_id}
          onChange={setBrandId}
        />
        <SelectField
          label="Category"
          value={subCategoryId}
          placeholder="Category > sub-category"
          disabled={model !== null}
          options={subOptions}
          error={fields.sub_category_id}
          onChange={setSubCategoryId}
        />
        <TextField
          label="Model name"
          value={name}
          autoFocus
          placeholder="e.g. Pixel 9 Pro"
          error={fields.name}
          onChange={(event) => {
            setName(event.target.value);
            clearField("name");
          }}
        />
        <TextField
          label="Model code"
          value={code}
          className="font-mono"
          placeholder="e.g. G8VOU"
          hint="Optional family or manufacturer code."
          error={fields.code}
          onChange={(event) => {
            setCode(event.target.value);
            clearField("code");
          }}
        />
        <TextField
          label="Release year"
          inputMode="numeric"
          value={year}
          placeholder="2024"
          error={fields.release_year}
          onChange={(event) => {
            setYear(event.target.value);
            clearField("release_year");
          }}
        />
        {isFashion ? (
          <>
            <TextField label="Season" value={season} placeholder="SS26" onChange={(event) => setSeason(event.target.value)} />
            <TextField label="Collection" value={collection} onChange={(event) => setCollection(event.target.value)} />
            <SelectField
              label="Gender"
              value={gender}
              placeholder="Any"
              options={[{ value: "", label: "Any" }, ...GENDERS.map(([value, label]) => ({ value, label }))]}
              onChange={(value) => setGender(value as Gender | "")}
            />
            <TextField label="Material" value={material} onChange={(event) => setMaterial(event.target.value)} />
            <TextField label="Fit" value={fit} onChange={(event) => setFit(event.target.value)} />
            <TextField label="Care" value={care} onChange={(event) => setCare(event.target.value)} />
          </>
        ) : null}
        <div className="md:col-span-2">
          <TextField
            label="Description"
            value={description}
            placeholder="Notes for this model"
            onChange={(event) => setDescription(event.target.value)}
          />
        </div>
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}
