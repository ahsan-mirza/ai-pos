import { NavLink, Outlet } from "react-router-dom";
import { useTenant } from "../../context/TenantContext";
import { useAuth, useIsSuperAdmin } from "../../lib/auth";
import { useCapabilities } from "../../lib/capabilities";
import { useCanManageSettings } from "../../lib/currency";
import { settingsTabAllowed, settingsTabs } from "../../components/layout/navigation";

/** Store settings and the administration pages that now live inside it. */
export function SettingsLayout() {
  const { can } = useAuth();
  const canManageSettings = useCanManageSettings();
  const superAdmin = useIsSuperAdmin();
  const { has } = useCapabilities();
  const { allows } = useTenant();
  const tabs = settingsTabs.filter((tab) => settingsTabAllowed(tab, { can, canManageSettings, superAdmin, has, allows }));

  return (
    <div className="flex min-h-full flex-col">
      <nav
        aria-label="Store settings"
        className="no-scrollbar sticky top-0 z-20 flex h-12 shrink-0 gap-1 overflow-x-auto border-b border-line bg-white px-2 md:px-3 lg:px-4"
      >
        {tabs.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            end={tab.end}
            className={({ isActive }) =>
              `relative flex shrink-0 items-center whitespace-nowrap px-3 text-[13px] outline-none transition-colors after:absolute after:inset-x-2 after:bottom-0 after:h-0.5 after:rounded-full after:transition-colors focus-visible:bg-charcoal/[0.04] ${
                isActive
                  ? "font-semibold text-charcoal after:bg-accent"
                  : "font-medium text-charcoal/55 after:bg-transparent hover:text-charcoal hover:after:bg-line"
              }`
            }
          >
            {tab.label}
          </NavLink>
        ))}
      </nav>
      <div className="flex-1">
        <Outlet />
      </div>
    </div>
  );
}
