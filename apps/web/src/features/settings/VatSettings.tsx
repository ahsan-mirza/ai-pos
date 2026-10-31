import {
  TAX_AUTHORITY_LABELS,
  countryTax,
  formatMoney,
  isSaudiVatNumber,
  lineTax,
  type BusinessSettings,
  type TaxSettingsUpdate,
} from "@ai-pos/shared-types";
import { CountryField } from "@ai-pos/ui";
import { Landmark } from "lucide-react";
import { useEffect, useState } from "react";
import { ErrorNote, PrimaryButton, TextField } from "../../components/ui/Field";
import { Toggle } from "../../components/ui/Toggle";
import { apiPut } from "../../lib/api";
import { useCurrency } from "../../lib/currency";
import { errorMessage } from "../users/api";
import { EInvoicingPanel } from "./EInvoicingPanel";

const SAMPLE = 10_500;

function taxForm(row: BusinessSettings): TaxSettingsUpdate {
  return {
    vat_registered: Boolean(row.vat_registered),
    trn: row.trn ?? null,
    legal_name: row.legal_name ?? null,
    legal_name_ar: row.legal_name_ar ?? null,
    prices_include_vat: Boolean(row.prices_include_vat),
    standard_rate_bps: row.standard_rate_bps ?? 500,
    tax_authority: row.tax_authority ?? "fta",
    country: row.country ?? null,
    location: row.location ?? null,
  };
}

export function VatSettings() {
  const { currency, settings, loadError, applySettings } = useCurrency();
  const [form, setForm] = useState<TaxSettingsUpdate | null>(null);
  const [saved, setSaved] = useState<TaxSettingsUpdate | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const dirty = form !== null && saved !== null && JSON.stringify(form) !== JSON.stringify(saved);

  useEffect(() => {
    if (settings === null || dirty) return;
    const next = taxForm(settings);
    setForm(next);
    setSaved(next);
  }, [settings, dirty]);

  if (form === null) {
    return (
      <div className="rounded-card border border-line bg-white p-6 text-sm text-charcoal/60">
        {loadError ?? "Loading VAT settings…"}
      </div>
    );
  }

  const rate = form.standard_rate_bps;
  const meta = countryTax(form.country || "AE");
  const chargedRate = form.vat_registered ? rate : 0;
  const preview = lineTax(SAMPLE, 1, chargedRate, form.vat_registered && form.prices_include_vat);
  const changed = JSON.stringify(form) !== JSON.stringify(saved);
  const inclusiveChanged = saved !== null && saved.prices_include_vat !== form.prices_include_vat;
  const authority = TAX_AUTHORITY_LABELS[form.tax_authority];
  const countryMoved = Boolean(form.country) && form.country !== (saved?.country ?? null);
  const localTax = form.country !== "AE" && form.country !== "SA";
  const trnInvalid =
    form.tax_authority === "zatca" && Boolean(form.trn) && form.trn?.length === 15 && !isSaudiVatNumber(form.trn ?? "");

  const save = async () => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const row = await apiPut<BusinessSettings>("/api/v1/settings/tax", {
        ...form,
        trn: form.trn?.trim() || null,
        legal_name: form.legal_name?.trim() || null,
        legal_name_ar: form.legal_name_ar?.trim() || null,
        location: form.location?.trim() || null,
      });
      const next = taxForm(row);
      setSaved(next);
      setForm(next);
      applySettings(row);
      setNotice("VAT settings saved. Registers apply them on their next sync.");
    } catch (caught) {
      setError(errorMessage(caught, "Could not save VAT settings."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-card border border-line bg-white p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-accent text-white">
            <Landmark size={20} aria-hidden="true" />
          </span>
          <div>
            <h2 className="text-2xl font-semibold">VAT and tax invoices</h2>
            <p className="text-sm text-charcoal/60">
              Tax follows the store&apos;s country. The register charges this rate and prints it on the tax invoice.
            </p>
          </div>
        </div>
        <PrimaryButton disabled={!changed || busy || trnInvalid} onClick={() => void save()}>
          {busy ? "Saving…" : "Save VAT settings"}
        </PrimaryButton>
      </div>

      <div className="mt-6 grid gap-4 xl:grid-cols-[minmax(0,1fr)_280px]">
        <div className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <CountryField
              label="Country"
              required
              value={form.country ?? ""}
              onChange={(iso) => {
                const rule = countryTax(iso);
                const trn = rule.tax_authority === "zatca" ? (form.trn ?? "").replace(/\D/g, "").slice(0, 15) : form.trn;
                setForm({
                  ...form,
                  country: iso,
                  trn,
                  tax_authority: rule.tax_authority,
                  standard_rate_bps: rule.rate_known ? (rule.standard_rate_bps ?? 0) : 0,
                  prices_include_vat: rule.rate_known ? rule.prices_include_vat : false,
                });
              }}
            />
            <TextField
              label="Location"
              maxLength={120}
              value={form.location ?? ""}
              hint="City or area. Each branch keeps its own address."
              onChange={(event) => setForm({ ...form, location: event.target.value })}
            />
          </div>
          <div className="rounded-2xl border border-accent bg-accent/5 p-3">
            <p className="text-sm font-semibold">{localTax ? "Standard tax invoice" : authority.name}</p>
            <p className="text-xs text-charcoal/60">
              {form.country === "SA"
                ? "Saudi Arabia uses ZATCA: signed, hash-chained e-invoices with QR codes (Fatoora phase 2). VAT is 15%."
                : form.country === "AE" || !form.country
                  ? "The UAE uses the Federal Tax Authority: full and simplified tax invoices, and PINT AE export. VAT is 5%."
                  : meta.rate_known
                    ? "The rate below is this country's verified starting rate. Save, then adjust it if yours is different."
                    : `No verified ${meta.tax_name.toLowerCase()} rate is stored for this country. Enter the rate this business charges. It is not assumed.`}
            </p>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <Toggle
              label={`${meta.tax_name} registered`}
              description="Charge this tax and validate it on every sale from branches that use the business settings"
              checked={form.vat_registered}
              onChange={(value) => setForm({ ...form, vat_registered: value })}
            />
            <Toggle
              label={`Prices include ${meta.tax_name}`}
              description="Starting choice for a new product. Each product has its own Price includes tax checkbox."
              checked={form.prices_include_vat}
              onChange={(value) => setForm({ ...form, prices_include_vat: value })}
            />
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            <TextField
              label={meta.registration_label}
              maxLength={32}
              value={form.trn ?? ""}
              hint={
                form.tax_authority === "zatca"
                  ? trnInvalid
                    ? "Saudi VAT numbers start and end with 3"
                    : "15 digits, starting and ending with 3. Leave blank if you are not VAT-registered."
                  : form.country === "AE" || !form.country
                    ? "15 digits for a UAE TRN. Leave blank if you are not tax-registered."
                    : "Your tax registration number. Leave blank if you are not tax-registered."
              }
              onChange={(event) => {
                const raw = event.target.value.toUpperCase();
                const next =
                  form.tax_authority === "zatca"
                    ? raw.replace(/\D/g, "").slice(0, 15)
                    : raw.replace(/[^A-Z0-9 -]/g, "").slice(0, 32);
                setForm({ ...form, trn: next });
              }}
            />
            <TextField
              label="Legal name"
              value={form.legal_name ?? ""}
              onChange={(event) => setForm({ ...form, legal_name: event.target.value })}
            />
            {meta.legal_local_label ? (
              <TextField
                label={meta.legal_local_label}
                dir="rtl"
                value={form.legal_name_ar ?? ""}
                onChange={(event) => setForm({ ...form, legal_name_ar: event.target.value })}
              />
            ) : null}
          </div>
          <div className="max-w-[200px]">
            <TextField
              label="Standard rate (%)"
              inputMode="decimal"
              disabled={countryMoved}
              hint={countryMoved ? "Set from the country. Save, then adjust the rate if yours is different." : undefined}
              value={(rate / 100).toString()}
              onChange={(event) => {
                const value = Math.round(Number(event.target.value) * 100);
                if (Number.isFinite(value) && value >= 0 && value <= 5000) setForm({ ...form, standard_rate_bps: value });
              }}
            />
          </div>
          {inclusiveChanged ? (
            <p className="rounded-2xl bg-warning/10 px-4 py-3 text-sm text-charcoal">
              This changes the starting choice for new products. Products already saved keep their own Price includes
              tax setting, and sales already recorded are not recalculated.
            </p>
          ) : null}
        </div>
        <div className="rounded-2xl bg-charcoal p-5 text-white">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-white/50">A {formatMoney(SAMPLE, currency)} item</p>
          <dl className="mt-3 space-y-2 text-sm">
            <div className="flex justify-between">
              <dt className="text-white/60">Net</dt>
              <dd className="tabular-nums">{formatMoney(preview.net_cents, currency)}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-white/60">
                {form.vat_registered ? `${meta.tax_name} ${chargedRate / 100}%` : "Tax"}
              </dt>
              <dd className="tabular-nums">{formatMoney(preview.tax_cents, currency)}</dd>
            </div>
            <div className="flex justify-between text-base font-semibold">
              <dt>Customer pays</dt>
              <dd className="tabular-nums text-accent">{formatMoney(preview.line_total_cents, currency)}</dd>
            </div>
          </dl>
          {!form.vat_registered ? (
            <p className="mt-4 text-xs text-white/50">Not tax-registered. No tax is added.</p>
          ) : !meta.rate_known ? (
            <p className="mt-4 text-xs text-white/50">This rate is the one you entered. It is not a verified country default.</p>
          ) : null}
        </div>
      </div>
      {notice ? <p role="status" className="mt-4 rounded-2xl bg-surface px-4 py-3 text-sm">{notice}</p> : null}
      <ErrorNote message={error} />
      {saved?.tax_authority === "zatca" ? <EInvoicingPanel refreshKey={settings?.updated_at ?? ""} /> : null}
    </div>
  );
}
