import { acceptBusinessSettings, Capability, capabilitySpec, isSupportedCurrency, profileSpec, type BusinessSettings, Permission } from "@ai-pos/shared-types";
import { useCallback, useEffect, useState } from "react";
import { useShell } from "../../components/shell/ShellContext";
import { terminal } from "../../config/terminal";
import { getBusinessSettings } from "../../lib/api";
import { fetchBusinessCurrency, inTauri, refreshRegisterPermissions } from "../../lib/tauri";
import { refreshBrowserPermissions } from "../auth/session";
import { useAppVersion } from "../../lib/appVersion";
import { useCapabilities } from "../../lib/capabilities";
import { activeStore, useBusinessSettingsMeta } from "../checkout/currency";
import { AppearancePanel } from "./AppearancePanel";
import { BusinessIdentityPanel } from "./BusinessIdentityPanel";
import { BusinessTypeCard } from "./BusinessTypeCard";
import { CurrencyPanel } from "./CurrencyPanel";
import { ExportDataPage } from "../restaurant/ExportDataPage";
import { LaundryOpsPage } from "./LaundryOpsPage";
import { canManageStaff } from "./staffAccess";
import { StaffAccessPanel } from "./StaffAccessPanel";
import { settingsAuditSummary } from "./settingsAudit";
import { readSettingsRail, searchSettings, settingsLocation, settingsSection, storeSettingsRail, visibleSettings } from "./settingsRoutes";
import {
  SettingsLayout,
  SettingsOverview,
  SettingsPageHeader,
  SettingsReadOnlyNotice,
  SettingsScopeBadge,
  SettingsSectionCard,
  SettingsSidebar,
  StoreInformationSummary,
} from "./settingsUi";

const PRO = "Managed in Business Pro. This register shows the current value and does not edit it.";

function blank(value: string | null | undefined, empty = "Not set"): string {
  const text = value?.trim() ?? "";
  return text === "" ? empty : text;
}

export function SettingsWorkspace() {
  const { session, registerStatus, onSession } = useShell();
  const { profile, enabled } = useCapabilities();
  const version = useAppVersion();
  const staff = canManageStaff(session.user.role_name, session.user.permissions);
  const reports = session.user.permissions.includes(Permission.PortalReportsRead);
  const routes = visibleSettings(profile, staff, reports);
  const business = routes.filter((item) => item.group === "business");
  const system = routes.filter((item) => item.group === "system");
  const [section, setSection] = useState(() => settingsSection(typeof window === "undefined" ? "" : window.location.hash));
  const [query, setQuery] = useState("");
  const [collapsed, setCollapsed] = useState(() => readSettingsRail() ?? false);
  const [businessOpen, setBusinessOpen] = useState(true);
  const [systemOpen, setSystemOpen] = useState(true);
  const [settings, setSettings] = useState<BusinessSettings | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const spec = profileSpec(profile);
  const page = routes.find((item) => item.id === section);
  const active = page?.id ?? "overview";
  const canManage = session.user.permissions.includes(Permission.SettingsManage) && session.user.store_id === null;
  const store = activeStore();
  const activation = terminal();
  const meta = useBusinessSettingsMeta();
  const restrictedReason = session.user.store_id !== null
    ? "A branch user cannot change the tenant business identity."
    : "Your role cannot change business settings.";

  const applyLoaded = useCallback((next: BusinessSettings) => {
    setSettings((current) => (!current || acceptBusinessSettings(current, next) ? next : current));
    setLoadError(null);
  }, []);

  useEffect(() => {
    if (active !== "hardware" || session.mode === "offline") return;
    let cancelled = false;
    const apply = (permissions: string[]) => {
      if (cancelled) return;
      if (permissions.join("\n") === session.user.permissions.join("\n")) return;
      onSession({ ...session, user: { ...session.user, permissions } });
    };
    if (inTauri()) {
      void refreshRegisterPermissions().then(apply).catch(() => undefined);
    } else {
      void refreshBrowserPermissions().then((permissions) => {
        if (permissions) apply(permissions);
      });
    }
    return () => {
      cancelled = true;
    };
  }, [active, onSession, session]);

  const loadSettings = useCallback(() => {
    if (session.mode === "offline") {
      setLoadError("This register is offline. Showing the last settings it stored.");
      return;
    }
    if (inTauri()) {
      void fetchBusinessCurrency()
        .then((snapshot) => {
          if (!snapshot.currency || !isSupportedCurrency(snapshot.currency)) return;
          const tax = snapshot.tax;
          const profileSnapshot = snapshot.profile;
          applyLoaded({
            currency: snapshot.currency,
            supported_currencies: [snapshot.currency],
            updated_at: tax?.updated_at?.trim() ?? "",
            updated_by_name: tax?.updated_by_name ?? null,
            country: tax?.country ?? null,
            location: tax?.location ?? null,
            timezone: tax?.timezone || "Asia/Dubai",
            legal_name: tax?.legal_name ?? null,
            legal_name_ar: tax?.legal_name_ar ?? null,
            entitlement_revision: tax?.entitlement_revision ?? profileSnapshot?.entitlement_revision ?? undefined,
            trn: tax?.trn ?? null,
            prices_include_vat: tax?.prices_include_vat,
            standard_rate_bps: tax?.standard_rate_bps,
            vat_registered: Boolean(tax?.enforced),
            business_profile: profileSnapshot?.business_profile ?? undefined,
            capabilities: profileSnapshot?.capabilities,
            planned_capabilities: profileSnapshot?.planned_capabilities,
            store_code: profileSnapshot?.tenant_id ?? undefined,
          });
        })
        .catch((caught: unknown) => {
          setLoadError(caught instanceof Error ? caught.message : "Business settings could not be loaded.");
        });
      return;
    }
    void getBusinessSettings()
      .then(applyLoaded)
      .catch((caught: unknown) => {
        setLoadError(caught instanceof Error ? caught.message : "Business settings could not be loaded.");
      });
  }, [applyLoaded, session.mode]);

  useEffect(() => {
    const sync = () => {
      const next = settingsSection(window.location.hash);
      setSection(next);
      const group = routes.find((item) => item.id === next)?.group;
      if (group === "business") setBusinessOpen(true);
      if (group === "system") setSystemOpen(true);
    };
    window.addEventListener("hashchange", sync);
    window.addEventListener("popstate", sync);
    return () => {
      window.removeEventListener("hashchange", sync);
      window.removeEventListener("popstate", sync);
    };
  }, [routes]);

  useEffect(() => {
    loadSettings();
    const timer = window.setInterval(loadSettings, 20_000);
    return () => window.clearInterval(timer);
  }, [loadSettings]);

  useEffect(() => {
    if (!meta.updatedAt && meta.entitlementRevision < 1) return;
    setSettings((current) => {
      if (!current) return current;
      const next: BusinessSettings = {
        ...current,
        legal_name: meta.legalName,
        legal_name_ar: meta.legalNameAr,
        country: meta.country,
        location: meta.location,
        updated_at: meta.updatedAt || current.updated_at,
        updated_by_name: meta.updatedByName,
        timezone: meta.timezone,
        entitlement_revision: meta.entitlementRevision || current.entitlement_revision,
      };
      return acceptBusinessSettings(current, next) ? next : current;
    });
  }, [meta]);

  const select = (id: string) => {
    const next = settingsLocation(id);
    if (window.location.hash !== next) {
      const base = `${window.location.pathname}${window.location.search}`;
      window.history.pushState({ posView: "settings", section: id }, "", `${base}${next}`);
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    }
    setSection(id);
    setQuery("");
  };

  const modules = [...enabled].map((item) => capabilitySpec(item).label);
  const profileNote =
    profile === "laundry"
      ? "Laundry services, workflows, stations, machines, quality, and tags are their own pages."
      : profile === "grocery"
        ? "Weighed items, bag fees, and expiry alerts follow the modules turned on for this grocery business."
        : profile === "restaurant" || profile === "cafe"
          ? "Menu, tables, and kitchen modules follow the restaurant profile. They are not laundry or grocery controls."
          : "Catalogue, variants, pricing, and stock rules follow this retail profile.";

  return (
    <div data-settings-frame className="flex h-full min-h-0 overflow-hidden">
      <SettingsLayout
        sidebar={
          <SettingsSidebar
            title="Settings"
            collapsed={collapsed}
            onToggle={() => setCollapsed((value) => {
              storeSettingsRail(!value);
              return !value;
            })}
            query={query}
            onQuery={setQuery}
            business={business}
            system={system}
            results={searchSettings(routes, query)}
            active={active}
            businessOpen={businessOpen}
            systemOpen={systemOpen}
            onToggleBusiness={() => setBusinessOpen((value) => !value)}
            onToggleSystem={() => setSystemOpen((value) => !value)}
            onSelect={select}
          />
        }
      >
        <div className="mx-auto flex max-w-6xl flex-col gap-4">
          <SettingsPageHeader
            title={active === "overview" ? "Settings" : page?.label ?? "Settings"}
            subtitle={active === "overview" ? "Manage business operations, register behavior, devices, and access." : page?.description ?? ""}
            business={blank(settings?.legal_name ?? store.name, store.name || "This business")}
            typeLabel={spec.shortLabel}
            modules={enabled.size}
          />
          <p className="text-sm text-zinc-500">
            Branch {blank(store.name)} · {activation?.activated ? "Activated" : "Not activated"}
            {activation?.register_code ? ` · ${activation.register_code}` : ""}
          </p>
          {page && active !== "overview" ? <SettingsScopeBadge scope={page.scope} managed={page.managed} /> : null}
          {active === "overview" || active === "currency" ? (
            <StoreInformationSummary
              country={blank(settings?.country)}
              location={blank(settings?.location)}
              currency={settings?.currency ?? store.currency}
              storeCode={blank(settings?.store_code ?? store.code)}
              taxNumber={blank(settings?.trn, "Not registered")}
            />
          ) : null}
          {loadError && active !== "diagnostics" ? <p role="alert" className="text-sm text-red-700">{loadError}</p> : null}
          {active === "overview" ? <SettingsOverview business={business} system={system} onOpen={select} /> : null}
          {active === "currency" ? <CurrencyPanel settings={settings} canManage={canManage} onSaved={setSettings} /> : null}
          {active === "appearance" ? <AppearancePanel cashier={session.user.full_name} part="appearance" /> : null}
          {active === "hardware" ? (
            <AppearancePanel
              cashier={session.user.full_name}
              part="hardware"
              canConfigure={
                session.user.permissions.includes(Permission.PosAccess) ||
                session.user.permissions.includes(Permission.DevicesManage) ||
                session.user.permissions.includes(Permission.SettingsManage)
              }
            />
          ) : null}
          {active === "business-profile" ? (
            <div className="space-y-4">
              <BusinessTypeCard />
              <BusinessIdentityPanel
                settings={settings}
                canManage={canManage}
                restrictedReason={restrictedReason}
                offline={session.mode === "offline"}
                onSaved={applyLoaded}
                onReload={loadSettings}
              />
              <SettingsSectionCard>
                <h2 className="text-lg font-semibold">Store code</h2>
                <p className="mt-2 text-sm font-semibold">{blank(settings?.store_code ?? store.code)}</p>
                <p className="mt-2 text-sm text-zinc-600">Read only. The store code is the tenant sign-in code and is not a branch setting.</p>
              </SettingsSectionCard>
            </div>
          ) : null}
          {active === "tax" ? (
            <SettingsReadOnlyNotice
              title="Tax and invoicing"
              detail={`${settings?.vat_registered ? `VAT registered${settings.trn ? `, ${settings.trn}` : ""}.` : "Not registered."} ${settings?.prices_include_vat ? "Prices include VAT." : "Prices exclude VAT."} ${PRO}`}
            />
          ) : null}
          {active === "sales" ? (
            <SettingsReadOnlyNotice title="Sales and POS rules" detail={`Return window ${settings?.pos_policy?.returns.window_days ?? "—"} days. Discount and refund rules stay on the server. ${PRO}`} />
          ) : null}
          {active === "catalogue" ? <SettingsReadOnlyNotice title="Products and inventory" detail={`${profileNote} ${PRO}`} /> : null}
          {active === "customers" ? (
            <SettingsReadOnlyNotice title="Customers and loyalty" detail={enabled.has(Capability.Loyalty) ? `Loyalty is enabled. Programme rules are ${PRO}` : "Loyalty is not enabled for this business. Customer lookup on the floor uses the existing customer list."} />
          ) : null}
          {active === "export" ? (
            <ExportDataPage storeId={session.user.store_id} canCustomers={session.user.permissions.includes(Permission.CustomersManage)} />
          ) : null}
          {active === "staff" ? <StaffAccessPanel actorRole={session.user.role_name} /> : null}
          {active === "modules" ? (
            <SettingsSectionCard>
              <h2 className="text-lg font-semibold">Enabled modules</h2>
              {modules.length > 0 ? <ul className="mt-3 flex flex-wrap gap-2">{modules.map((label) => <li key={label} className="rounded-full bg-zinc-100 px-3 py-1 text-xs font-medium">{label}</li>)}</ul> : <p className="mt-3 text-sm text-zinc-500">No modules are enabled.</p>}
              <p className="mt-3 text-sm text-zinc-600">{PRO} Add-on purchases and access are not edited here.</p>
            </SettingsSectionCard>
          ) : null}
          {active === "workflows" ? <SettingsReadOnlyNotice title="Workflows and operations" detail={profile === "laundry" ? "Open Laundry workflows, stations, machines, and quality in the list. Those pages are read-only." : `${PRO} This profile has no laundry production settings.`} /> : null}
          {active === "laundry-services" ? <LaundryOpsPage topic="services" permissions={session.user.permissions} /> : null}
          {active === "laundry-workflows" ? <LaundryOpsPage topic="workflows" permissions={session.user.permissions} /> : null}
          {active === "laundry-stations" ? <LaundryOpsPage topic="stations" permissions={session.user.permissions} /> : null}
          {active === "laundry-machines" ? <LaundryOpsPage topic="machines" permissions={session.user.permissions} /> : null}
          {active === "laundry-quality" ? <LaundryOpsPage topic="quality" permissions={session.user.permissions} /> : null}
          {active === "laundry-tags" ? <LaundryOpsPage topic="tags" permissions={session.user.permissions} /> : null}
          {active === "integrations" ? <SettingsReadOnlyNotice title="Integrations" detail={`${PRO} API tokens, private keys, and payment secrets are not shown on this register.`} /> : null}
          {active === "notifications" ? (
            profile === "laundry" ? <LaundryOpsPage topic="notifications" permissions={session.user.permissions} /> : <SettingsReadOnlyNotice title="Notifications" detail={`${PRO} This register does not edit business alerts.`} />
          ) : null}
          {active === "audit" ? (
            <SettingsReadOnlyNotice
              title="Audit trail"
              detail={settingsAuditSummary(settings?.updated_at, settings?.updated_by_name, settings?.timezone)}
            />
          ) : null}
          {active === "terminal" ? (
            <SettingsSectionCard>
              <h2 className="text-lg font-semibold">This terminal</h2>
              <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
                <div><dt className="text-zinc-500">Business</dt><dd className="font-semibold">{blank(activation?.tenant_name ?? store.name)}</dd></div>
                <div><dt className="text-zinc-500">Branch</dt><dd className="font-semibold">{blank(store.name)} · {blank(store.code)}</dd></div>
                <div><dt className="text-zinc-500">Register</dt><dd className="font-semibold">{blank(activation?.register_code, "Not assigned")}</dd></div>
                <div><dt className="text-zinc-500">Activation</dt><dd className="font-semibold">{activation?.activated ? "Activated" : "Not activated"}</dd></div>
                <div><dt className="text-zinc-500">Profile</dt><dd className="font-semibold">{spec.label}</dd></div>
              </dl>
            </SettingsSectionCard>
          ) : null}
          {active === "connectivity" ? (
            <SettingsReadOnlyNotice title="Connectivity" detail={registerStatus ? `${registerStatus.label}. ${registerStatus.title}` : "The open page has not published a connection reading yet."} />
          ) : null}
          {active === "security" ? <SettingsReadOnlyNotice title="Security and session" detail={`Signed in as ${session.user.full_name} (${session.user.role_name})${session.mode === "offline" ? ", offline unlock" : ""}. Lock register stays in the outer sidebar. This screen does not issue an online token or change the PIN policy.`} /> : null}
          {active === "keyboard" ? <SettingsReadOnlyNotice title="Keyboard" detail="The touch keyboard opens from the Keyboard control on the bottom status bar. Shortcut editing is not available on this register." /> : null}
          {active === "sync" ? <SettingsReadOnlyNotice title="Sync and local data" detail={registerStatus ? `${registerStatus.label}. ${registerStatus.title} There is no reset or force-sync control here.` : "Queue counts appear in the bottom bar when a page publishes them. There is no reset control here."} /> : null}
          {active === "updates" ? <SettingsSectionCard><h2 className="text-lg font-semibold">Application version</h2><p className="mt-2 text-sm">v{version}. Updates use the existing update prompt. This page does not download an installer.</p></SettingsSectionCard> : null}
          {active === "diagnostics" ? <SettingsReadOnlyNotice title="Diagnostics" detail={loadError ? `Business settings could not be loaded: ${loadError}` : "Business settings loaded. Tokens, PINs, and customer records are not included in this view."} /> : null}
        </div>
      </SettingsLayout>
    </div>
  );
}
