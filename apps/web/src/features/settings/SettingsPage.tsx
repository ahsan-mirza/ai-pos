import { profileSpec, type Store } from "@ai-pos/shared-types";
import { countryOption } from "@ai-pos/ui";
import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { apiGet } from "../../lib/api";
import { useCapabilities } from "../../lib/capabilities";
import { generalSections } from "./SettingsLayout";
import { useCurrency } from "../../lib/currency";
import { useStoreScope } from "../../lib/storeScope";
import { AppearanceSettings } from "./AppearanceSettings";
import { BusinessProfileSettings } from "./BusinessProfileSettings";
import { CurrencySettings } from "./CurrencySettings";
import { ModuleSettingsPanel } from "./ModuleSettingsPanel";
import { ModuleShortcuts } from "./ModuleShortcuts";
import { ReceiptSettingsCard } from "./ReceiptSettings";
import { TillRulesSettings } from "./TillRulesSettings";
import { BranchTaxSettings } from "./BranchTaxSettings";
import { VatSettings } from "./VatSettings";

export function SettingsPage() {
  const { settings } = useCurrency();
  const { storeId } = useStoreScope();
  const [branches, setBranches] = useState<Store[]>([]);
  const { profile, enabled } = useCapabilities();
  const spec = profileSpec(profile);
  const { hash } = useLocation();
  const requested = hash.replace("#", "");
  const section = generalSections.some((item) => item.id === requested) ? requested : "currency";

  useEffect(() => {
    let live = true;
    apiGet<Store[]>("/api/v1/stores?limit=200")
      .then((rows) => {
        if (live) setBranches(rows);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);

  const selected = storeId
    ? branches.find((store) => store.id === storeId)
    : branches.length === 1
      ? branches[0]
      : undefined;
  const firstCountry = branches[0]?.country;
  const sharedCountry =
    branches.length > 0 && branches.every((store) => store.country && store.country === firstCountry) ? firstCountry : null;
  const countryCode = selected?.country || sharedCountry || settings?.country || "";
  const location = selected?.city || settings?.location || "";

  return (
    <section className="grid gap-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <h1 className="truncate text-3xl font-semibold tracking-tight">{spec.settingsLabel}</h1>
          <p className="mt-1 text-sm text-charcoal/60">Business-wide settings shared by every branch and register.</p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {settings?.store_code ? (
            <p className="font-mono text-sm font-semibold tracking-tight text-charcoal" title="Store code">
              {settings.store_code}
            </p>
          ) : null}
          <Link
            to="/settings#business-profile"
            className="inline-flex max-w-full items-center gap-2 rounded-full border border-line bg-white px-3 py-1.5 text-sm font-medium hover:border-charcoal/20"
          >
            <span className="h-2 w-2 rounded-full bg-accent" aria-hidden="true" />
            {spec.shortLabel}
            <span className="text-charcoal/50">
              · {enabled.size} module{enabled.size === 1 ? "" : "s"} on
            </span>
          </Link>
        </div>
      </header>
      {settings ? (
        <dl className="grid grid-cols-2 gap-3 rounded-card border border-line bg-white p-4 text-sm sm:grid-cols-3 xl:grid-cols-5">
          <div>
            <dt className="text-charcoal/50">Country</dt>
            <dd className="font-medium">
              {countryCode ? (countryOption(countryCode)?.name ?? countryCode) : "Not recorded"}
            </dd>
          </div>
          <div>
            <dt className="text-charcoal/50">Location</dt>
            <dd className="font-medium">{location || "Not recorded"}</dd>
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

      {section === "currency" ? (
        <div id="currency">
          <CurrencySettings />
        </div>
      ) : null}
      {section === "branch-tax" ? (
        <div id="branch-tax">
          <BranchTaxSettings />
        </div>
      ) : null}
      {section === "vat" ? (
        <div id="vat">
          <VatSettings />
        </div>
      ) : null}
      {section === "receipts" ? (
        <div id="receipts">
          <ReceiptSettingsCard />
        </div>
      ) : null}
      {section === "till-rules" ? (
        <div>
          <TillRulesSettings />
        </div>
      ) : null}
      {section === "appearance" ? (
        <div id="appearance">
          <AppearanceSettings />
        </div>
      ) : null}
      {section === "business-profile" ? (
        <div>
          <BusinessProfileSettings />
        </div>
      ) : null}
      {section === "module-settings" ? (
        <div id="module-settings">
          <ModuleSettingsPanel />
        </div>
      ) : null}
      {section === "module-setup" ? (
        <div id="module-setup">
          <ModuleShortcuts />
        </div>
      ) : null}
    </section>
  );
}
