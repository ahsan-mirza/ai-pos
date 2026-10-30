import { countryTax, formatMoney, type CountryTax } from "@ai-pos/shared-types";
import { CountryField } from "@ai-pos/ui";
import { useEffect, useState } from "react";
import { ErrorNote, PrimaryButton, SelectField, TextField } from "../../components/ui/Field";
import { Toggle } from "../../components/ui/Toggle";
import { apiGet, apiPost, apiPut } from "../../lib/api";
import { useCurrency } from "../../lib/currency";
import { errorMessage } from "../users/api";

interface StoreRow {
  id: string;
  code: string;
  name: string;
}

interface BranchTax {
  store_id: string;
  country: string | null;
  city: string | null;
  region: string | null;
  registered: boolean;
  registration_number: string | null;
  secondary_registration_number: string | null;
  legal_name: string | null;
  legal_name_local: string | null;
  prices_include_vat: boolean;
  standard_rate_bps: number;
  configuration_required: boolean;
  country_tax: CountryTax;
}

interface Preview {
  net_cents: number;
  tax_cents: number;
  total_cents: number;
  rate_bps: number;
}

const SAMPLE = 10_000;

export function BranchTaxSettings() {
  const { currency } = useCurrency();
  const [stores, setStores] = useState<StoreRow[]>([]);
  const [storeId, setStoreId] = useState("");
  const [form, setForm] = useState<BranchTax | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    apiGet<StoreRow[]>("/api/v1/stores?limit=200")
      .then((rows) => {
        setStores(rows);
        setStoreId((current) => current || rows[0]?.id || "");
      })
      .catch(() => setError("Branches could not be loaded."));
  }, []);

  useEffect(() => {
    if (!storeId) return;
    let cancelled = false;
    apiGet<BranchTax>(`/api/v1/stores/${storeId}/tax`)
      .then((row) => {
        if (!cancelled) setForm(row);
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(errorMessage(caught, "Branch tax could not be loaded."));
      });
    return () => {
      cancelled = true;
    };
  }, [storeId]);

  useEffect(() => {
    if (!storeId || form === null || !form.country) return;
    let cancelled = false;
    apiPost<Preview>(`/api/v1/stores/${storeId}/tax/preview`, { amount_cents: SAMPLE, category: "STANDARD" })
      .then((row) => {
        if (!cancelled) setPreview(row);
      })
      .catch(() => {
        if (!cancelled) setPreview(null);
      });
    return () => {
      cancelled = true;
    };
  }, [storeId, form]);

  if (stores.length === 0) {
    return error ? <ErrorNote message={error} /> : null;
  }
  const meta = form?.country ? form.country_tax : countryTax("AE");

  const save = async () => {
    if (!form?.country) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const saved = await apiPut<BranchTax>(`/api/v1/stores/${storeId}/tax`, {
        country: form.country,
        city: form.city,
        region: form.region,
        registered: form.registered,
        registration_number: form.registration_number,
        secondary_registration_number: form.secondary_registration_number,
        legal_name: form.legal_name,
        legal_name_local: form.legal_name_local,
        prices_include_vat: form.prices_include_vat,
        standard_rate_bps: form.standard_rate_bps,
        confirm_country_change: true,
      });
      setForm(saved);
      setNotice("Branch tax saved. Sales at this branch use it, and earlier invoices stay as they were.");
    } catch (caught) {
      setError(errorMessage(caught, "Could not save branch tax."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-card border border-line bg-white p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-2xl font-semibold">Branch tax</h2>
          <p className="text-sm text-charcoal/60">
            A sale uses the branch that sells it. Changing one branch does not change the others.
          </p>
        </div>
        <PrimaryButton disabled={busy || form?.country == null} onClick={() => void save()}>
          {busy ? "Saving…" : "Save branch tax"}
        </PrimaryButton>
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="space-y-4">
          <SelectField
            label="Branch"
            value={storeId}
            onChange={setStoreId}
            options={stores.map((store) => ({ value: store.id, label: `${store.name} (${store.code})` }))}
          />
          {form ? (
            <>
              <div className="grid gap-4 md:grid-cols-2">
                <CountryField
                  label="Country"
                  required
                  value={form.country ?? ""}
                  onChange={(iso) => {
                    const next = countryTax(iso);
                    const known = Boolean(form.registration_number);
                    if (known && form.country && form.country !== iso) {
                      const proceed = window.confirm(
                        "This branch already has a tax registration. The number stays, and you need to confirm the rate for the new country.",
                      );
                      if (!proceed) return;
                    }
                    setForm({
                      ...form,
                      country: iso,
                      country_tax: next,
                      prices_include_vat: next.rate_known ? next.prices_include_vat : false,
                      standard_rate_bps: next.rate_known ? (next.standard_rate_bps ?? 0) : form.standard_rate_bps,
                      legal_name_local: next.legal_local_label ? form.legal_name_local : null,
                      secondary_registration_number: next.secondary_registration_label
                        ? form.secondary_registration_number
                        : null,
                    });
                  }}
                />
                <TextField
                  label="City"
                  value={form.city ?? ""}
                  onChange={(event) => setForm({ ...form, city: event.target.value })}
                />
              </div>
              {meta.region_label && meta.region_label !== "Emirate" ? (
                <TextField
                  label={meta.region_label}
                  value={form.region ?? ""}
                  onChange={(event) => setForm({ ...form, region: event.target.value })}
                />
              ) : null}
              <Toggle
                label={`${meta.tax_name} registered`}
                description={
                  form.registered
                    ? "This branch charges the rate below."
                    : "Not registered. Sales at this branch do not add tax."
                }
                checked={form.registered}
                onChange={(value) => setForm({ ...form, registered: value })}
              />
              <div className="grid gap-4 md:grid-cols-2">
                <TextField
                  label={meta.registration_label}
                  value={form.registration_number ?? ""}
                  onChange={(event) => setForm({ ...form, registration_number: event.target.value })}
                />
                {meta.secondary_registration_label ? (
                  <TextField
                    label={meta.secondary_registration_label}
                    value={form.secondary_registration_number ?? ""}
                    onChange={(event) => setForm({ ...form, secondary_registration_number: event.target.value })}
                  />
                ) : null}
                <TextField
                  label="Legal name"
                  value={form.legal_name ?? ""}
                  onChange={(event) => setForm({ ...form, legal_name: event.target.value })}
                />
                {meta.legal_local_label ? (
                  <TextField
                    label={meta.legal_local_label}
                    dir="rtl"
                    value={form.legal_name_local ?? ""}
                    onChange={(event) => setForm({ ...form, legal_name_local: event.target.value })}
                  />
                ) : null}
              </div>
              <Toggle
                label={`Prices include ${meta.tax_name}`}
                description="Shelf prices already include this tax"
                checked={form.prices_include_vat}
                onChange={(value) => setForm({ ...form, prices_include_vat: value })}
              />
              <div className="max-w-[200px]">
                <TextField
                  label={`${meta.tax_name} rate (%)`}
                  inputMode="decimal"
                  hint={
                    meta.rate_known
                      ? "Verified starting rate. Change it if this branch is registered at a different rate."
                      : "No verified default. Enter the rate this branch charges."
                  }
                  value={(form.standard_rate_bps / 100).toString()}
                  onChange={(event) => {
                    const value = Math.round(Number(event.target.value) * 100);
                    if (Number.isFinite(value) && value >= 0 && value <= 5000) {
                      setForm({ ...form, standard_rate_bps: value });
                    }
                  }}
                />
              </div>
              {form.configuration_required ? (
                <p className="rounded-2xl bg-warning/10 px-4 py-3 text-sm">
                  This branch cannot sell until you save a confirmed tax rate. Another branch&apos;s rate is not used.
                </p>
              ) : null}
            </>
          ) : null}
        </div>
        <div className="rounded-2xl bg-charcoal p-5 text-white">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-white/50">
            A {formatMoney(SAMPLE, currency)} item at this branch
          </p>
          {preview && form?.registered ? (
            <dl className="mt-3 space-y-2 text-sm">
              <div className="flex justify-between">
                <dt className="text-white/60">Net</dt>
                <dd className="tabular-nums">{formatMoney(preview.net_cents, currency)}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-white/60">
                  {meta.tax_name} {preview.rate_bps / 100}%
                </dt>
                <dd className="tabular-nums">{formatMoney(preview.tax_cents, currency)}</dd>
              </div>
              <div className="flex justify-between text-base font-semibold">
                <dt>Customer pays</dt>
                <dd className="tabular-nums text-accent">{formatMoney(preview.total_cents, currency)}</dd>
              </div>
            </dl>
          ) : (
            <p className="mt-3 text-sm text-white/70">Not tax-registered. No tax is added.</p>
          )}
          {!meta.rate_known && form?.country ? (
            <p className="mt-4 text-xs text-white/50">The preview uses the rate saved for this branch.</p>
          ) : null}
        </div>
      </div>
      {notice ? (
        <p role="status" className="mt-4 rounded-2xl bg-surface px-4 py-3 text-sm">
          {notice}
        </p>
      ) : null}
      <ErrorNote message={error} />
    </div>
  );
}
