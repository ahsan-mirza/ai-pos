import {
  TAX_AUTHORITY_LABELS,
  formatMoney,
  isSaudiVatNumber,
  lineTax,
  type BusinessSettings,
  type TaxAuthority,
  type TaxSettingsUpdate,
} from "@ai-pos/shared-types";
import { Landmark } from "lucide-react";
import { useEffect, useState } from "react";
import { ErrorNote, PrimaryButton, TextField } from "../../components/ui/Field";
import { Toggle } from "../../components/ui/Toggle";
import { apiPut } from "../../lib/api";
import { useCurrency } from "../../lib/currency";
import { errorMessage } from "../users/api";
import { EInvoicingPanel } from "./EInvoicingPanel";

const AUTHORITIES: TaxAuthority[] = ["fta", "zatca"];

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
  const preview = lineTax(SAMPLE, 1, rate, form.prices_include_vat);
  const changed = JSON.stringify(form) !== JSON.stringify(saved);
  const inclusiveChanged = saved !== null && saved.prices_include_vat !== form.prices_include_vat;
  const authority = TAX_AUTHORITY_LABELS[form.tax_authority];
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
              The API recomputes VAT on every sale and prints these details on {authority.name} tax invoices.
            </p>
          </div>
        </div>
        <PrimaryButton disabled={!changed || busy || trnInvalid} onClick={() => void save()}>
          {busy ? "Saving…" : "Save VAT settings"}
        </PrimaryButton>
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="space-y-4">
          <fieldset>
            <legend className="mb-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-charcoal/50">Tax authority</legend>
            <div className="grid gap-3 sm:grid-cols-2">
              {AUTHORITIES.map((code) => {
                const option = TAX_AUTHORITY_LABELS[code];
                const selected = form.tax_authority === code;
                return (
                  <label
                    key={code}
                    className={`flex cursor-pointer flex-col rounded-2xl border p-3 transition ${
                      selected ? "border-accent bg-accent/5" : "border-line hover:bg-surface"
                    }`}
                  >
                    <input
                      type="radio"
                      name="tax-authority"
                      value={code}
                      checked={selected}
                      onChange={() => setForm({ ...form, tax_authority: code })}
                      className="sr-only"
                    />
                    <span className="text-sm font-semibold">{option.name}</span>
                    <span className="text-xs text-charcoal/60">
                      {code === "zatca"
                        ? "Signed, hash-chained e-invoices with QR codes (Fatoora phase 2)."
                        : "Full and simplified tax invoices; PINT AE e-invoice export."}
                    </span>
                  </label>
                );
              })}
            </div>
          </fieldset>
          <div className="grid gap-3 md:grid-cols-2">
            <Toggle
              label="VAT registered"
              description="Charge VAT and validate it on every sale"
              checked={form.vat_registered}
              onChange={(value) => setForm({ ...form, vat_registered: value })}
            />
            <Toggle
              label="Prices include VAT"
              description="Shelf prices are VAT-inclusive (UAE retail rule)"
              checked={form.prices_include_vat}
              onChange={(value) => setForm({ ...form, prices_include_vat: value })}
            />
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            <TextField
              label={authority.taxId}
              inputMode="numeric"
              maxLength={15}
              value={form.trn ?? ""}
              hint={
                form.tax_authority === "zatca"
                  ? trnInvalid
                    ? "Saudi VAT numbers start and end with 3"
                    : "15 digits, starting and ending with 3"
                  : "15-digit Tax Registration Number"
              }
              onChange={(event) => setForm({ ...form, trn: event.target.value.replace(/\D/g, "") })}
            />
            <TextField
              label="Legal name"
              value={form.legal_name ?? ""}
              onChange={(event) => setForm({ ...form, legal_name: event.target.value })}
            />
            <TextField
              label="Legal name (Arabic)"
              dir="rtl"
              value={form.legal_name_ar ?? ""}
              onChange={(event) => setForm({ ...form, legal_name_ar: event.target.value })}
            />
          </div>
          <div className="max-w-[200px]">
            <TextField
              label="Standard rate (%)"
              inputMode="decimal"
              value={(rate / 100).toString()}
              onChange={(event) => {
                const value = Math.round(Number(event.target.value) * 100);
                if (Number.isFinite(value) && value >= 0 && value <= 5000) setForm({ ...form, standard_rate_bps: value });
              }}
            />
          </div>
          {inclusiveChanged ? (
            <p className="rounded-2xl bg-accent/10 px-4 py-3 text-sm text-charcoal">
              Switching this reinterprets every catalog price: {formatMoney(SAMPLE, currency)} will{" "}
              {form.prices_include_vat ? "already include" : "have VAT added on top of"} its VAT. Sync every register
              first.
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
              <dt className="text-white/60">VAT {rate / 100}%</dt>
              <dd className="tabular-nums">{formatMoney(preview.tax_cents, currency)}</dd>
            </div>
            <div className="flex justify-between text-base font-semibold">
              <dt>Customer pays</dt>
              <dd className="tabular-nums text-accent">{formatMoney(preview.line_total_cents, currency)}</dd>
            </div>
          </dl>
          {!form.vat_registered ? (
            <p className="mt-4 text-xs text-white/50">Not registered: registers' tax is accepted as sent.</p>
          ) : null}
        </div>
      </div>
      {notice ? <p role="status" className="mt-4 rounded-2xl bg-surface px-4 py-3 text-sm">{notice}</p> : null}
      <ErrorNote message={error} />
      {saved?.tax_authority === "zatca" ? <EInvoicingPanel refreshKey={settings?.updated_at ?? ""} /> : null}
    </div>
  );
}
