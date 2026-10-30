import { profileSpec } from "@ai-pos/shared-types";
import { useCallback, useEffect, useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { apiGet } from "../../lib/api";
import { useTenant } from "../../context/TenantContext";
import { FirstWinChecklist } from "../../features/onboarding/FirstWinChecklist";
import { PracticeBanner, PracticeProvider, TaxPortalBanner } from "../../features/onboarding/practice";
import { portalRouteAllowed } from "../../lib/industry";
import { portalHomePath } from "../../lib/portal-home";
import { StoreScopeProvider } from "../../lib/storeScope";
import { AssistantDrawer } from "../../features/assistant/AssistantDrawer";
import { AssistantProvider } from "../../features/assistant/AssistantProvider";
import { Header } from "./Header";
import { Sidebar } from "./Sidebar";

const COLLAPSED_KEY = "ai-pos.sidebar-collapsed";

function isTyping(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))
  );
}

export function AppShell() {
  const { pathname } = useLocation();
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(COLLAPSED_KEY) === "1");
  const [mobileOpen, setMobileOpen] = useState(false);

  const toggleCollapsed = useCallback(() => {
    setCollapsed((value) => {
      localStorage.setItem(COLLAPSED_KEY, value ? "0" : "1");
      return !value;
    });
  }, []);
  const closeMobile = useCallback(() => setMobileOpen(false), []);

  useEffect(() => setMobileOpen(false), [pathname]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "[" || event.metaKey || event.ctrlKey || event.altKey || isTyping(event.target)) return;
      if (document.querySelector(".modal-backdrop")) return;
      event.preventDefault();
      toggleCollapsed();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggleCollapsed]);

  return (
    <StoreScopeProvider>
      <PracticeProvider>
        <AssistantProvider>
          <div className="flex h-dvh w-screen overflow-hidden bg-[#f8fafc] font-sans text-charcoal">
            <Sidebar collapsed={collapsed} mobileOpen={mobileOpen} onCloseMobile={closeMobile} />
            <div className="flex min-w-0 flex-1 flex-col">
              <PracticeBanner />
              <TaxPortalBanner />
              <SubscriptionNotice />
              <Header collapsed={collapsed} onToggleCollapsed={toggleCollapsed} onOpenMobile={() => setMobileOpen(true)} />
              <div className="relative min-h-0 flex-1">
                <main className="h-full overflow-y-auto overflow-x-hidden">
                  <IndustryGate />
                </main>
                <AssistantDrawer />
              </div>
            </div>
          </div>
          <FirstWinChecklist />
        </AssistantProvider>
      </PracticeProvider>
    </StoreScopeProvider>
  );
}

function SubscriptionNotice() {
  const { pathname } = useLocation();
  const [access, setAccess] = useState<{
    state: string;
    attention: { kind: string; invoice_id: string; reason: string | null } | null;
  } | null>(null);
  useEffect(() => {
    let cancelled = false;
    apiGet<{ state: string; attention: { kind: string; invoice_id: string; reason: string | null } | null }>(
      "/api/v1/billing/access",
    )
      .then((found) => {
        if (!cancelled) setAccess(found);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [pathname]);
  const attention = access?.attention;
  if (attention) {
    const title =
      attention.kind === "pending_review"
        ? "Payment Verification Pending"
        : attention.kind === "rejected"
          ? "Payment Proof Needs Attention"
          : attention.kind === "revoked"
            ? "Subscription access was updated"
            : "Payment Required";
    const message =
      attention.kind === "rejected" && attention.reason
        ? attention.reason
        : attention.kind === "pending_review"
          ? "We have received your payment proof. Our team will review it and update your subscription status. Your features will remain locked until verification is complete."
          : attention.kind === "revoked"
            ? "The previous activation was revoked. Paid features stay locked until a payment is verified again."
            : "Your invoice is ready. Transfer the amount shown on your invoice and submit your payment proof. Your subscription features will remain locked until payment is verified.";
    return (
      <div className="border-b border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950" role="status">
        <p className="font-semibold">{title}</p>
        <p className="mt-1">{message}</p>
        <p className="mt-2 flex flex-wrap gap-3">
          <Link to="/subscription" className="font-semibold underline">
            View Invoice
          </Link>
          {attention.kind === "awaiting_proof" || attention.kind === "rejected" ? (
            <Link to="/subscription" className="font-semibold underline">
              {attention.kind === "rejected" ? "Resubmit Payment Proof" : "Submit Payment Proof"}
            </Link>
          ) : (
            <Link to="/subscription" className="font-semibold underline">
              View submission status
            </Link>
          )}
        </p>
      </div>
    );
  }
  if (access?.state !== "grace" && access?.state !== "restricted") return null;
  const text =
    access.state === "grace"
      ? "Your AxizPOS subscription payment is overdue. Complete the bank transfer and submit the receipt before the grace period ends."
      : "This subscription is past its grace period. Billing and receipt upload stay open so the store can pay and recover.";
  return (
    <p className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-950" role="status">
      {text}{" "}
      <Link to="/subscription" className="font-semibold underline">
        View Invoice
      </Link>
    </p>
  );
}

/** Blocks a deep link when this business type does not use the page. */
function IndustryGate() {
  const { pathname } = useLocation();
  const { storedProfile, ready, recognized, businessType } = useTenant();
  const allowed = portalRouteAllowed(pathname, ready ? storedProfile : null);
  if (!allowed && !ready) return null;
  if (!allowed) {
    const name = recognized ? profileSpec(businessType).label : "This business";
    return (
      <section className="m-6 max-w-lg rounded-card border border-line bg-white p-8">
        <h1 className="text-xl font-semibold">Not part of this portal</h1>
        <p className="mt-2 text-sm text-charcoal/70">{name} does not use this page.</p>
        <Link to={portalHomePath()} className="mt-4 inline-block text-sm font-semibold text-accent">
          Back to the dashboard
        </Link>
      </section>
    );
  }
  return <Outlet />;
}

/** Padding for card-based pages; full-bleed workspaces such as Purchase Batches render outside it. */
export function PageFrame() {
  return (
    <div className="p-4 md:p-6 lg:p-8">
      <Outlet />
    </div>
  );
}
