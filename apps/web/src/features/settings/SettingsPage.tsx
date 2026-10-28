import { profileSpec } from "@ai-pos/shared-types";
import { countryOption } from "@ai-pos/ui";
import { useCapabilities } from "../../lib/capabilities";
import { useCurrency } from "../../lib/currency";
import { AppearanceSettings } from "./AppearanceSettings";
import { BusinessProfileSettings } from "./BusinessProfileSettings";
import { CurrencySettings } from "./CurrencySettings";
import { ModuleSettingsPanel } from "./ModuleSettingsPanel";
import { ModuleShortcuts } from "./ModuleShortcuts";
import { ReceiptSettingsCard } from "./ReceiptSettings";
import { TillRulesSettings } from "./TillRulesSettings";
import { VatSettings } from "./VatSettings";

function SectionHeading({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="mt-4 xl:col-span-2">
      <h2 className="text-xs font-semibold uppercase tracking-[0.14em] text-charcoal/45">{title}</h2>
      <p className="mt-0.5 text-sm text-charcoal/60">{hint}</p>
    </div>
  );
}

export function SettingsPage() {
  const { settings } = useCurrency();
  const { profile, enabled } = useCapabilities();
  const spec = profileSpec(profile);

  return (
    <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
      <header className="flex flex-wrap items-end justify-between gap-3 xl:col-span-2">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">{spec.settingsLabel}</h1>
          <p className="mt-1 text-sm text-charcoal/60">Business-wide settings shared by every branch and register.</p>
        </div>
        <a
          href="#business-profile"
          className="inline-flex items-center gap-2 rounded-full border border-line bg-white px-3 py-1.5 text-sm font-medium hover:border-charcoal/20"
        >
          <span className="h-2 w-2 rounded-full bg-accent" aria-hidden="true" />
          {spec.shortLabel}
          <span className="text-charcoal/50">
            · {enabled.size} module{enabled.size === 1 ? "" : "s"} on
          </span>
        </a>
      </header>
      {settings ? (
        <dl className="grid gap-3 rounded-card border border-line bg-white p-4 text-sm sm:grid-cols-3 xl:col-span-2 xl:grid-cols-5">
          <div>
            <dt className="text-charcoal/50">Country</dt>
            <dd className="font-medium">
              {settings.country ? (countryOption(settings.country)?.name ?? settings.country) : "Not recorded"}
            </dd>
          </div>
          <div>
            <dt className="text-charcoal/50">Location</dt>
            <dd className="font-medium">{settings.location || "Not recorded"}</dd>
          </div>
          <div>
            <dt className="text-charcoal/50">Currency</dt>
            <dd className="font-medium">{settings.currency}</dd>
          </div>
          <div>
            <dt className="text-charcoal/50">Store code</dt>
            <dd className="font-mono font-medium">{settings.store_code || "—"}</dd>
          </div>
          <div>
            <dt className="text-charcoal/50">Tax registration number</dt>
            <dd className="font-medium">{settings.trn || "Not registered"}</dd>
          </div>
        </dl>
      ) : null}

      <SectionHeading title="General" hint="Currency, tax, receipts and the look of the portal and registers." />

      <div className="xl:col-span-2">
        <CurrencySettings />
      </div>

      <div className="xl:col-span-2">
        <VatSettings />
      </div>

      <div className="xl:col-span-2">
        <ReceiptSettingsCard />
      </div>

      <div className="xl:col-span-2">
        <TillRulesSettings />
      </div>

      <div className="xl:col-span-2">
        <AppearanceSettings />
      </div>

      <SectionHeading
        title="Business type & modules"
        hint={`What your ${spec.shortLabel.toLowerCase()} business runs on: the portal and registers show only these modules.`}
      />

      <div className="xl:col-span-2">
        <BusinessProfileSettings />
      </div>

      <div className="xl:col-span-2">
        <ModuleSettingsPanel />
      </div>

      <div className="xl:col-span-2">
        <ModuleShortcuts />
      </div>
    </section>
  );
}
