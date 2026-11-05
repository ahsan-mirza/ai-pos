import { ChevronDown } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
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
  "/settings/addons": "Browse and purchase add-ons",
  "/stores": "Branches and warehouses",
  "/roles": "What each role is allowed to do",
  "/settings/addon-access": "Who can use each add-on",
  "/registers": "Devices that sell",
  "/downloads": "POS installer",
  "/settings/currencies": "Extra currencies and rates",
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
  const navigate = useNavigate();
  const navRef = useRef<HTMLElement>(null);
  const tabs = settingsTabs.filter((tab) => settingsTabAllowed(tab, { can, canManageSettings, superAdmin, has, allows }));
  const showGeneral = tabs.some((tab) => tab.to === "/settings");
  const onGeneral = pathname === "/settings";
  const openSection = generalSections.some((item) => `#${item.id}` === hash) ? hash.slice(1) : "currency";
  const [generalOpen, setGeneralOpen] = useState(onGeneral);

  useEffect(() => {
    if (onGeneral) setGeneralOpen(true);
  }, [onGeneral, hash]);

  useEffect(() => {
    navRef.current?.querySelector<HTMLElement>('[aria-current="page"]')?.scrollIntoView({ block: "nearest" });
  }, [pathname, hash, generalOpen]);

  const toggleGeneral = () => {
    setGeneralOpen((open) => {
      const next = !open;
      if (next && !onGeneral) navigate("/settings");
      return next;
    });
  };

  return (
    <div className="grid items-start gap-4 md:grid-cols-[minmax(200px,240px)_minmax(0,1fr)] lg:grid-cols-[minmax(220px,260px)_minmax(0,1fr)] xl:grid-cols-[300px_minmax(0,1fr)]">
      <aside className="flex max-h-[min(32rem,calc(100dvh-6.5rem))] flex-col overflow-hidden rounded-card bg-charcoal p-3 text-white sm:p-4 md:sticky md:top-0 md:max-h-[calc(100dvh-6.5rem)] lg:p-5">
        <div className="shrink-0">
          <h2 className="px-1 text-base font-semibold sm:text-lg">{title}</h2>
          <p className="mt-1 px-1 text-xs text-white/55">Each section opens on its own.</p>
        </div>
        <nav ref={navRef} aria-label={title} className="mt-3 min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1 [scrollbar-gutter:stable]">
          <ul className="space-y-1.5">
            {tabs.map((tab) => {
              const here = onTab(tab, pathname);
              const selected = tab.end ? false : here;
              const grouped = tab.end && here;
              const rowClass = `block w-full rounded-2xl px-3 py-2.5 text-left outline-none transition focus-visible:ring-2 focus-visible:ring-white/70 lg:py-3 ${
                selected ? "bg-accent" : grouped ? "bg-white/10" : "bg-white/5 hover:bg-white/10"
              }`;
              return (
                <li key={tab.to}>
                  {tab.to === "/settings" && showGeneral ? (
                    <button
                      type="button"
                      className={`${rowClass} flex items-center justify-between gap-2`}
                      aria-expanded={generalOpen}
                      aria-controls="settings-general-sections"
                      onClick={toggleGeneral}
                    >
                      <span>
                        <span className="block text-sm font-medium lg:text-[15px]">{tab.label}</span>
                        {hints[tab.to] ? (
                          <span className={`mt-0.5 block text-xs ${selected ? "text-white/80" : "text-white/50"}`}>
                            {hints[tab.to]}
                          </span>
                        ) : null}
                      </span>
                      <ChevronDown
                        aria-hidden="true"
                        className={`h-4 w-4 shrink-0 text-white/70 transition-transform duration-200 ${generalOpen ? "rotate-180" : ""}`}
                      />
                    </button>
                  ) : (
                    <Link to={tab.to} aria-current={selected ? "page" : undefined} className={rowClass}>
                      <span className="block text-sm font-medium lg:text-[15px]">{tab.label}</span>
                      {hints[tab.to] ? (
                        <span className={`mt-0.5 block text-xs ${selected ? "text-white/80" : "text-white/50"}`}>
                          {hints[tab.to]}
                        </span>
                      ) : null}
                    </Link>
                  )}
                  {tab.to === "/settings" && showGeneral ? (
                    <div className={`grid transition-[grid-template-rows] duration-200 ease-out ${generalOpen ? "grid-rows-[1fr]" : "grid-rows-[0fr]"}`}>
                      <div className="min-h-0 overflow-hidden" {...(generalOpen ? {} : { inert: true })}>
                        <ul id="settings-general-sections" className="ml-3 mt-1 space-y-1 border-l border-white/15 pl-2">
                          {generalSections.map((section) => {
                            const current = onGeneral && openSection === section.id;
                            return (
                              <li key={section.id}>
                                <Link
                                  to={`/settings#${section.id}`}
                                  aria-current={current ? "page" : undefined}
                                  className={`block rounded-xl px-3 py-2 text-sm outline-none transition focus-visible:ring-2 focus-visible:ring-white/70 ${
                                    current ? "bg-accent font-medium" : "text-white/75 hover:bg-white/10 hover:text-white"
                                  }`}
                                >
                                  {section.label}
                                </Link>
                              </li>
                            );
                          })}
                        </ul>
                      </div>
                    </div>
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
