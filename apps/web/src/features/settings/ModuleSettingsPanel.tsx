import { Capability, DEFAULT_MODULE_SETTINGS, type BusinessSettings, type ModuleSettings } from "@ai-pos/shared-types";
import { SlidersHorizontal } from "lucide-react";
import { useEffect, useState } from "react";
import { ErrorNote, PrimaryButton, SelectField, TextField } from "../../components/ui/Field";
import { Toggle } from "../../components/ui/Toggle";
import { apiGet, apiPut } from "../../lib/api";
import { useCapabilities } from "../../lib/capabilities";
import { useCurrency } from "../../lib/currency";
import { errorMessage } from "../users/api";

function merged(raw: ModuleSettings | undefined): ModuleSettings {
  return { ...DEFAULT_MODULE_SETTINGS, ...(raw ?? {}) };
}

const percent = (bps: number) => (bps / 100).toString();
const toBps = (value: string) => Math.round((Number.parseFloat(value || "0") || 0) * 100);

/** Settings of the optional modules this business has switched on (expiry alerts, scale labels, service, kitchen). */
export function ModuleSettingsPanel() {
  const { settings, applySettings } = useCurrency();
  const { has } = useCapabilities();
  const [draft, setDraft] = useState<ModuleSettings>(() => merged(settings?.module_settings));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [categories, setCategories] = useState<{ id: string; name: string }[]>([]);
  const groceryTill = has(Capability.Fefo) || has(Capability.WeighedItems);

  useEffect(() => {
    if (!groceryTill) return;
    void apiGet<{ id: string; name: string }[]>("/api/v1/categories")
      .then(setCategories)
      .catch(() => setCategories([]));
  }, [groceryTill]);

  useEffect(() => setDraft(merged(settings?.module_settings)), [settings?.module_settings]);

  const sections = [Capability.Fefo, Capability.WeighedItems, Capability.TipsServiceCharge, Capability.Kds, Capability.Repairs].filter(has);
  if (sections.length === 0) return null;

  const barcodes = draft.weighed_items.embedded_barcodes;
  const service = draft.tips_service_charge;

  async function save() {
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      applySettings(await apiPut<BusinessSettings>("/api/v1/settings/modules", draft));
      setSaved(true);
    } catch (caught) {
      setError(errorMessage(caught, "Could not save the module settings."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-card border border-line bg-white p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-charcoal text-white">
            <SlidersHorizontal size={20} aria-hidden="true" />
          </span>
          <div>
            <h2 className="text-2xl font-semibold">Module settings</h2>
            <p className="text-sm text-charcoal/60">How the modules you switched on behave at every register.</p>
          </div>
        </div>
        <PrimaryButton disabled={busy} onClick={() => void save()}>
          {busy ? "Saving…" : saved ? "Saved" : "Save module settings"}
        </PrimaryButton>
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-2">
        {has(Capability.Fefo) ? (
          <fieldset className="space-y-3 rounded-2xl border border-line p-4">
            <legend className="px-1 text-sm font-semibold">Expiry-first stock</legend>
            <TextField
              label="Alert window (days)"
              type="number"
              min={1}
              max={365}
              value={String(draft.fefo.alert_days)}
              hint="Batches expiring this soon show on Inventory > Expiring and in the daily summary."
              onChange={(event) => setDraft({ ...draft, fefo: { alert_days: Number(event.target.value) || 1 } })}
            />
          </fieldset>
        ) : null}

        {has(Capability.WeighedItems) ? (
          <fieldset className="space-y-3 rounded-2xl border border-line p-4">
            <legend className="px-1 text-sm font-semibold">Scale labels (EAN-13)</legend>
            <TextField
              label="Label prefixes"
              value={barcodes.prefixes.join(", ")}
              hint="Two-digit prefixes your scales print, e.g. 20, 21, 22."
              onChange={(event) =>
                setDraft({
                  ...draft,
                  weighed_items: {
                    embedded_barcodes: {
                      ...barcodes,
                      prefixes: event.target.value.split(/[\s,]+/).map((item) => item.trim()).filter(Boolean),
                    },
                  },
                })
              }
            />
            <div className="grid gap-3 sm:grid-cols-2">
              <SelectField<"weight" | "price">
                label="Label carries"
                value={barcodes.mode}
                options={[
                  { value: "weight", label: "Weight (grams)" },
                  { value: "price", label: "Price" },
                ]}
                onChange={(mode) => setDraft({ ...draft, weighed_items: { embedded_barcodes: { ...barcodes, mode } } })}
              />
              <SelectField<string>
                label="PLU digits"
                value={String(barcodes.plu_length)}
                options={["4", "5", "6"].map((value) => ({ value, label: value }))}
                onChange={(value) =>
                  setDraft({ ...draft, weighed_items: { embedded_barcodes: { ...barcodes, plu_length: Number(value) } } })
                }
              />
            </div>
          </fieldset>
        ) : null}

        {groceryTill ? (
          <fieldset className="space-y-3 rounded-2xl border border-line p-4">
            <legend className="px-1 text-sm font-semibold">Bag fee</legend>
            <Toggle
              label="Cashiers can add a bag"
              description="Off by default. A bag is never added unless someone taps Add bag."
              checked={draft.bags.enabled}
              onChange={(enabled) => setDraft({ ...draft, bags: { ...draft.bags, enabled } })}
            />
            <TextField
              label="Fee"
              type="number"
              min={0}
              value={String(draft.bags.fee_cents / 100)}
              hint="Per bag, in the store currency."
              onChange={(event) =>
                setDraft({
                  ...draft,
                  bags: { ...draft.bags, fee_cents: Math.round((Number(event.target.value) || 0) * 100) },
                })
              }
            />
            <SelectField<"STANDARD" | "ZERO" | "EXEMPT">
              label="Tax"
              value={draft.bags.tax_category}
              options={[
                { value: "STANDARD", label: "Standard" },
                { value: "ZERO", label: "Zero rated" },
                { value: "EXEMPT", label: "Exempt" },
              ]}
              onChange={(tax_category) => setDraft({ ...draft, bags: { ...draft.bags, tax_category } })}
            />
          </fieldset>
        ) : null}

        {groceryTill ? (
          <fieldset className="space-y-3 rounded-2xl border border-line p-4">
            <legend className="px-1 text-sm font-semibold">Department keys</legend>
            <p className="text-sm text-charcoal/60">Shortcuts on the register. They filter the catalogue; they do not create products.</p>
            <div className="flex flex-wrap gap-2">
              {categories.map((category) => {
                const on = draft.department_keys.keys.some((key) => key.category_id === category.id);
                return (
                  <button
                    key={category.id}
                    type="button"
                    aria-pressed={on}
                    className={`h-11 rounded-2xl px-3 text-sm font-semibold ${on ? "bg-accent text-white" : "border border-line"}`}
                    onClick={() => {
                      const keys = on
                        ? draft.department_keys.keys.filter((key) => key.category_id !== category.id)
                        : [...draft.department_keys.keys, { category_id: category.id, label: category.name }].slice(0, 16);
                      setDraft({ ...draft, department_keys: { keys } });
                    }}
                  >
                    {category.name}
                  </button>
                );
              })}
            </div>
          </fieldset>
        ) : null}

        {has(Capability.TipsServiceCharge) ? (
          <fieldset className="space-y-3 rounded-2xl border border-line p-4">
            <legend className="px-1 text-sm font-semibold">Service charge & tips</legend>
            <div className="grid gap-3 sm:grid-cols-2">
              <TextField
                label="Service charge (%)"
                inputMode="decimal"
                value={percent(service.service_charge_bps)}
                hint="0 turns the automatic charge off."
                onChange={(event) =>
                  setDraft({ ...draft, tips_service_charge: { ...service, service_charge_bps: toBps(event.target.value) } })
                }
              />
              <TextField
                label="From covers"
                type="number"
                min={0}
                value={String(service.min_covers)}
                hint="0 = every table."
                onChange={(event) =>
                  setDraft({ ...draft, tips_service_charge: { ...service, min_covers: Number(event.target.value) || 0 } })
                }
              />
            </div>
            <Toggle
              label="Dine-in only"
              description="Takeaway and delivery orders never carry the service charge."
              checked={service.dine_in_only}
              onChange={(dine_in_only) => setDraft({ ...draft, tips_service_charge: { ...service, dine_in_only } })}
            />
            <Toggle
              label="Service charge is taxable"
              description="Adds VAT on the service charge at the standard rate."
              checked={service.service_charge_taxable}
              onChange={(service_charge_taxable) =>
                setDraft({ ...draft, tips_service_charge: { ...service, service_charge_taxable } })
              }
            />
            <TextField
              label="Tip buttons (%)"
              value={service.tip_presets_bps.map(percent).join(", ")}
              hint="Up to four quick tip choices on the payment screen."
              onChange={(event) =>
                setDraft({
                  ...draft,
                  tips_service_charge: {
                    ...service,
                    tip_presets_bps: event.target.value
                      .split(/[\s,]+/)
                      .filter(Boolean)
                      .map(toBps)
                      .filter((bps) => bps > 0)
                      .slice(0, 4),
                  },
                })
              }
            />
          </fieldset>
        ) : null}

        {has(Capability.Kds) ? (
          <fieldset className="space-y-3 rounded-2xl border border-line p-4">
            <legend className="px-1 text-sm font-semibold">Kitchen display</legend>
            <div className="grid gap-3 sm:grid-cols-2">
              <TextField
                label="Amber after (minutes)"
                type="number"
                min={1}
                value={String(draft.kds.warn_minutes)}
                onChange={(event) => setDraft({ ...draft, kds: { ...draft.kds, warn_minutes: Number(event.target.value) || 1 } })}
              />
              <TextField
                label="Red after (minutes)"
                type="number"
                min={2}
                value={String(draft.kds.late_minutes)}
                onChange={(event) => setDraft({ ...draft, kds: { ...draft.kds, late_minutes: Number(event.target.value) || 2 } })}
              />
            </div>
          </fieldset>
        ) : null}

        {has(Capability.Repairs) ? (
          <fieldset className="space-y-3 rounded-2xl border border-line p-4 lg:col-span-2">
            <legend className="px-1 text-sm font-semibold">Repairs</legend>
            <div className="grid gap-3 sm:grid-cols-3">
              <TextField
                label="Repair warranty (days)"
                type="number"
                min={0}
                max={730}
                value={String(draft.repairs.warranty_days)}
                hint="Cover on parts and labour after the invoice. 0 turns it off."
                onChange={(event) =>
                  setDraft({ ...draft, repairs: { ...draft.repairs, warranty_days: Number(event.target.value) || 0 } })
                }
              />
              <TextField
                label="Approval link (hours)"
                type="number"
                min={1}
                max={720}
                value={String(draft.repairs.approval_link_hours)}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    repairs: { ...draft.repairs, approval_link_hours: Number(event.target.value) || 1 },
                  })
                }
              />
              <TextField
                label="Suggested deposit (%)"
                type="number"
                min={0}
                max={100}
                value={percent(draft.repairs.deposit_bps)}
                onChange={(event) =>
                  setDraft({ ...draft, repairs: { ...draft.repairs, deposit_bps: toBps(event.target.value) } })
                }
              />
            </div>
            <label className="block text-sm font-medium">
              Terms on the job card
              <textarea
                value={draft.repairs.terms}
                maxLength={2000}
                rows={4}
                onChange={(event) => setDraft({ ...draft, repairs: { ...draft.repairs, terms: event.target.value } })}
                className="mt-1.5 w-full rounded-xl border border-transparent bg-surface px-4 py-3 text-sm font-normal text-charcoal focus:border-accent focus:bg-white focus:outline-none"
              />
            </label>
          </fieldset>
        ) : null}
      </div>
      <ErrorNote message={error} />
    </div>
  );
}
