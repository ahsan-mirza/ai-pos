import { useEffect, useRef } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { settingsTabAllowed, settingsTabs, type SettingsTab } from "../../components/layout/navigation";
import { useTenant } from "../../context/TenantContext";
import { useAuth, useIsSuperAdmin } from "../../lib/auth";
import { useCapabilities, useSettingsLabel } from "../../lib/capabilities";
import { useCanManageSettings } from "../../lib/currency";

/** Sections on the General page. They stay in one list with the other settings pages. */
export const generalSections: { id: string; label: string }[] = [
  { id: "currency", label: "Business currency" },
  { id: "branch-tax", label: "Branch tax" },
  { id: "vat", label: "VAT and tax invoices" },
  { id: "receipts", label: "Receipt layout" },
  { id: "till-rules", label: "Till rules" },
  { id: "appearance", label: "Appearance" },
  { id: "business-profile", label: "Business profile" },
  { id: "module-settings", label: "Module settings" },
  { id: "module-setup", label: "Module setup" },
];

const hints: Record<string, string> = {
  "/settings": "Currency, tax, receipts, and appearance",
  "/settings/addons": "Turn modules on or off",
  "/stores": "Branches and warehouses",
  "/roles": "What each role is allowed to do",
  "/settings/addon-access": "Who can use each add-on",
  "/registers": "Devices that sell",
  "/downloads": "POS installer",
  "/settings/currencies": "Extra currencies and rates",
  "/settings/messaging": "Messages sent to customers",
  "/settings/channels": "How delivery orders arrive",
  "/settings/audit-logs": "Who changed what",
};

function onTab(tab: SettingsTab, pathname: string): boolean {
  if (tab.end) return pathname === tab.to;
  return pathname === tab.to || pathname.startsWith(`${tab.to}/`);
}

/** Store settings and the administration pages that now live inside it. */
export function SettingsLayout() {
  const { can } = useAuth();
  const canManageSettings = useCanManageSettings();
  const superAdmin = useIsSuperAdmin();
  const { has } = useCapabilities();
  const { allows } = useTenant();
  const title = useSettingsLabel();
  const { pathname, hash } = useLocation();
  const navRef = useRef<HTMLElement>(null);
  const tabs = settingsTabs.filter((tab) => settingsTabAllowed(tab, { can, canManageSettings, superAdmin, has, allows }));
  const showGeneral = tabs.some((tab) => tab.to === "/settings");
  const openSection = generalSections.some((item) => `#${item.id}` === hash) ? hash.slice(1) : "currency";

  useEffect(() => {
    navRef.current?.querySelector<HTMLElement>('[aria-current="page"]')?.scrollIntoView({ block: "nearest" });
  }, [pathname, hash]);

  return (
    <div className="grid items-start gap-4 md:grid-cols-[minmax(200px,240px)_minmax(0,1fr)] lg:grid-cols-[minmax(220px,260px)_minmax(0,1fr)] xl:grid-cols-[300px_minmax(0,1fr)]">
      <aside className="rounded-card bg-charcoal p-3 text-white sm:p-4 lg:p-5 md:sticky md:top-0 md:max-h-[calc(100dvh-6.5rem)] md:overflow-y-auto">
        <h2 className="px-1 text-base font-semibold sm:text-lg">{title}</h2>
        <p className="mt-1 px-1 text-xs text-white/55">Each section opens on its own.</p>
        <nav ref={navRef} aria-label={title} className="mt-3 max-h-[min(20rem,48vh)] overflow-y-auto overscroll-contain md:max-h-none md:overflow-visible">
          <ul className="space-y-1.5">
            {tabs.map((tab) => {
              const here = onTab(tab, pathname);
              const selected = tab.end ? false : here;
              const grouped = tab.end && here;
              return (
                <li key={tab.to}>
                  <Link
                    to={tab.to}
                    aria-current={selected ? "page" : undefined}
                    className={`block w-full rounded-2xl px-3 py-2.5 text-left transition lg:py-3 ${
                      selected ? "bg-accent" : grouped ? "bg-white/10" : "bg-white/5 hover:bg-white/10"
                    }`}
                  >
                    <span className="block text-sm font-medium lg:text-[15px]">{tab.label}</span>
                    {hints[tab.to] ? (
                      <span className={`mt-0.5 block text-xs ${selected ? "text-white/80" : "text-white/50"}`}>
                        {hints[tab.to]}
                      </span>
                    ) : null}
                  </Link>
                  {tab.to === "/settings" && showGeneral ? (
                    <ul className="ml-3 mt-1 space-y-1 border-l border-white/15 pl-2">
                      {generalSections.map((section) => {
                        const current = pathname === "/settings" && openSection === section.id;
                        return (
                          <li key={section.id}>
                            <Link
                              to={`/settings#${section.id}`}
                              aria-current={current ? "page" : undefined}
                              className={`block rounded-xl px-3 py-2 text-sm transition ${
                                current ? "bg-accent font-medium" : "text-white/75 hover:bg-white/10 hover:text-white"
                              }`}
                            >
                              {section.label}
                            </Link>
                          </li>
                        );
                      })}
                    </ul>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </nav>
      </aside>
      <div className="min-w-0">
        <Outlet />
      </div>
    </div>
  );
}
