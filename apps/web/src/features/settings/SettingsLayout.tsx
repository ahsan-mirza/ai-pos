import { useLocale } from "@ai-pos/ui";
import { Menu } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { settingsTabAllowed, settingsTabs } from "../../components/layout/navigation";
import { useTenant } from "../../context/TenantContext";
import { useAuth, useIsSuperAdmin } from "../../lib/auth";
import { useCapabilities, useSettingsLabel } from "../../lib/capabilities";
import { useCanManageSettings } from "../../lib/currency";
import { SettingsMobileDrawer, SettingsNavigationItem, SettingsSidebar } from "./SettingsSidebar";
import {
  generalSections,
  readSettingsNavPreference,
  resolveSettingsNav,
  settingsNavAction,
  storeSettingsNavPreference,
  type SettingsNavMode,
} from "./settingsNav";

export { generalSections };

function openGeneralSection(hash: string): string {
  const id = hash.replace("#", "");
  return generalSections.some((item) => item.id === id) ? id : "currency";
}

/** Store settings and the administration pages that now live inside it. */
export function SettingsLayout() {
  const { t } = useLocale();
  const { can } = useAuth();
  const canManageSettings = useCanManageSettings();
  const superAdmin = useIsSuperAdmin();
  const { has } = useCapabilities();
  const { allows } = useTenant();
  const title = useSettingsLabel();
  const { pathname, hash } = useLocation();
  const navigate = useNavigate();
  const frameRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(() => (typeof window === "undefined" ? 1280 : window.innerWidth));
  const [preference, setPreference] = useState<SettingsNavMode | null>(() => readSettingsNavPreference());
  const [generalOpen, setGeneralOpen] = useState(pathname === "/settings");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [popoverAnchor, setPopoverAnchor] = useState<DOMRect | null>(null);

  const tabs = settingsTabs.filter((tab) => settingsTabAllowed(tab, { can, canManageSettings, superAdmin, has, allows }));
  const showGeneral = tabs.some((tab) => tab.to === "/settings");
  const onGeneral = pathname === "/settings";
  const openSection = openGeneralSection(hash);
  const mode = resolveSettingsNav(preference, width);
  const railMode: SettingsNavMode = mode === "drawer" ? "collapsed" : mode;
  const action = settingsNavAction(railMode, width);

  useEffect(() => {
    const node = frameRef.current;
    if (!node) return;
    const measure = () => setWidth(node.clientWidth);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (onGeneral) setGeneralOpen(true);
  }, [onGeneral, hash]);

  useEffect(() => {
    setDrawerOpen(false);
    setPopoverAnchor(null);
  }, [pathname, hash]);

  useEffect(() => {
    if (!popoverAnchor) return;
    const onPointer = (event: PointerEvent) => {
      const target = event.target;
      if (target instanceof Element && target.closest("[role='menu'], [data-settings-general]")) return;
      setPopoverAnchor(null);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setPopoverAnchor(null);
    };
    document.addEventListener("pointerdown", onPointer);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      window.removeEventListener("keydown", onKey);
    };
  }, [popoverAnchor]);

  const choose = useCallback((next: SettingsNavMode) => {
    storeSettingsNavPreference(next);
    setPreference(next);
  }, []);

  const onAction = () => {
    if (action.next === "drawer") {
      setDrawerOpen(true);
      return;
    }
    choose(action.next);
  };

  const toggleGeneral = (anchor: DOMRect | null) => {
    if (anchor) {
      setPopoverAnchor((current) => (current ? null : anchor));
      return;
    }
    setGeneralOpen((open) => {
      const next = !open;
      if (next && !onGeneral) navigate("/settings");
      return next;
    });
  };

  return (
    <div ref={frameRef} className="flex h-full min-h-0 items-stretch">
      {mode === "drawer" ? null : (
        <SettingsSidebar
          mode={railMode}
          title={t(title)}
          actionLabel={action.label}
          onAction={onAction}
          tabs={tabs}
          pathname={pathname}
          generalOpen={generalOpen}
          openSection={onGeneral ? openSection : ""}
          showGeneral={showGeneral}
          onToggleGeneral={toggleGeneral}
          popoverAnchor={popoverAnchor}
          onClosePopover={() => setPopoverAnchor(null)}
        />
      )}
      <div className="min-h-0 min-w-0 flex-1 overflow-y-auto">
        {mode === "drawer" ? (
          <div className="px-4 pt-4 md:px-6">
            <button
              type="button"
              onClick={() => setDrawerOpen(true)}
              className="inline-flex h-10 items-center gap-2 rounded-xl border border-line bg-white px-3 text-sm font-medium text-charcoal"
            >
              <Menu size={16} aria-hidden="true" />
              {t("Settings menu")}
            </button>
          </div>
        ) : null}
        <Outlet />
      </div>
      <SettingsMobileDrawer open={mode === "drawer" && drawerOpen} title={t(title)} onClose={() => setDrawerOpen(false)}>
        <ul className="space-y-1">
          {tabs.map((tab) => (
            <SettingsNavigationItem
              key={tab.to}
              tab={tab}
              pathname={pathname}
              mode="expanded"
              generalOpen={generalOpen}
              openSection={onGeneral ? openSection : ""}
              showGeneral={showGeneral}
              onToggleGeneral={() => toggleGeneral(null)}
              onNavigate={() => setDrawerOpen(false)}
            />
          ))}
        </ul>
      </SettingsMobileDrawer>
    </div>
  );
}
