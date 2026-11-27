import { GENDER_LABELS, type CatalogAttributes } from "@ai-pos/shared-types";
import type { FilterControlProps } from "@ai-pos/ui";
import { useEffect, useState } from "react";
import { FilterSelect } from "../../components/ui/Field";
import { modelsApi } from "./api";

export interface FashionFilterValue {
  season: string | null;
  collection: string | null;
  gender: string | null;
}

export const NO_FASHION_FILTER: FashionFilterValue = { season: null, collection: null, gender: null };

export function encodeFashionFilter(value: FashionFilterValue): string {
  return JSON.stringify([value.season ?? "", value.collection ?? "", value.gender ?? ""]);
}

export function fashionFilterValue(encoded: string): FashionFilterValue {
  try {
    const parsed = JSON.parse(encoded) as unknown;
    if (!Array.isArray(parsed)) return NO_FASHION_FILTER;
    const [season, collection, gender] = parsed;
    return {
      season: typeof season === "string" && season ? season : null,
      collection: typeof collection === "string" && collection ? collection : null,
      gender: typeof gender === "string" && gender ? gender : null,
    };
  } catch {
    return NO_FASHION_FILTER;
  }
}

export function FashionFilterControl({ value, setValue }: FilterControlProps) {
  return <FashionFilters value={fashionFilterValue(value)} onChange={(next) => setValue(encodeFashionFilter(next))} />;
}

/** Season, collection and gender pickers; each shows only once the catalogue uses that attribute. */
export function FashionFilters({
  value,
  onChange,
}: {
  value: FashionFilterValue;
  onChange: (value: FashionFilterValue) => void;
}) {
  const [attributes, setAttributes] = useState<CatalogAttributes | null>(null);

  useEffect(() => {
    void modelsApi.attributes().then(setAttributes, () => setAttributes(null));
  }, []);

  if (attributes === null) return null;
  const any = (label: string) => ({ value: "", label });
  return (
    <>
      {attributes.seasons.length ? (
        <FilterSelect
          label="Season"
          value={value.season ?? ""}
          options={[any("All seasons"), ...attributes.seasons.map((season) => ({ value: season, label: season }))]}
          onChange={(season) => onChange({ ...value, season: season || null })}
          className="w-36"
        />
      ) : null}
      {attributes.collections.length ? (
        <FilterSelect
          label="Collection"
          value={value.collection ?? ""}
          options={[any("All collections"), ...attributes.collections.map((name) => ({ value: name, label: name }))]}
          onChange={(collection) => onChange({ ...value, collection: collection || null })}
          className="w-44"
        />
      ) : null}
      {attributes.genders.length ? (
        <FilterSelect
          label="Gender"
          value={value.gender ?? ""}
          options={[any("Everyone"), ...attributes.genders.map((gender) => ({ value: gender, label: GENDER_LABELS[gender] }))]}
          onChange={(gender) => onChange({ ...value, gender: gender || null })}
          className="w-36"
        />
      ) : null}
    </>
  );
}
