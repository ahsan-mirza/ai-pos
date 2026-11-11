import { profileSpec } from "@ai-pos/shared-types";
import { useLocale } from "@ai-pos/ui";
import { useCallback, useEffect, useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { apiGet } from "../../lib/api";
import { useTenant } from "../../context/TenantContext";
import { FirstWinChecklist } from "../../features/onboarding/FirstWinChecklist";
import { PracticeBanner, PracticeProvider, TaxPortalBanner } from "../../features/onboarding/practice";
import { portalRouteAllowed } from "../../lib/industry";
import { portalHomePath } from "../../lib/portal-home";
import { SaleReturnLive } from "../../features/returns/saleReturnLive";
import { StoreScopeProvider } from "../../lib/storeScope";
import { FeatureAccessProvider } from "../../lib/featureAccess";
import { AssistantDrawer } from "../../features/assistant/AssistantDrawer";
import { AssistantProvider } from "../../features/assistant/AssistantProvider";
import { PwaChrome } from "../../pwa/PwaChrome";
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
  const [subscriptionLocked, setSubscriptionLocked] = useState(false);
  const [access, setAccess] = useState<BillingAccess | null>(null);

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
      <SaleReturnLive />
      <PracticeProvider>
        <AssistantProvider>
          <FeatureAccessProvider>
          <div className="flex h-dvh w-screen overflow-hidden bg-[#f8fafc] font-sans text-charcoal">
            <Sidebar
              collapsed={collapsed}
              mobileOpen={mobileOpen}
              onCloseMobile={closeMobile}
              subscriptionLocked={subscriptionLocked}
            />
            <div className="flex min-w-0 flex-1 flex-col">
              <PwaChrome />
              <PracticeBanner />
              <TaxPortalBanner />
              <SubscriptionNotice access={access} onAccess={setSubscriptionLocked} onLoaded={setAccess} />
              <Header collapsed={collapsed} onToggleCollapsed={toggleCollapsed} onOpenMobile={() => setMobileOpen(true)} />
              <div className="relative min-h-0 flex-1">
                <main className="h-full overflow-y-auto overflow-x-hidden">
                  <IndustryGate subscriptionLocked={subscriptionLocked} access={access} />
                </main>
                <AssistantDrawer />
              </div>
            </div>
          </div>
          <FirstWinChecklist />
          </FeatureAccessProvider>
        </AssistantProvider>
      </PracticeProvider>
    </StoreScopeProvider>
  );
}

interface BillingAccess {
  state: string;
  operational?: boolean;
  attention: { kind: string; invoice_id: string; reason: string | null } | null;
}

function SubscriptionNotice({
  access,
  onAccess,
  onLoaded,
}: {
  access: BillingAccess | null;
  onAccess: (locked: boolean) => void;
  onLoaded: (access: BillingAccess | null) => void;
}) {
  const { pathname } = useLocation();
  useEffect(() => {
    let cancelled = false;
    apiGet<BillingAccess>("/api/v1/billing/access")
      .then((found) => {
        if (!cancelled) {
          onLoaded(found);
          const kind = found.attention?.kind;
          const proofBlocks = kind === "pending_review" || kind === "rejected" || kind === "revoked";
          onAccess(found.operational === false || proofBlocks);
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [onAccess, onLoaded, pathname]);
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
          ? "We have received your payment proof. Our team will review it and update your subscription status. Your paid features will remain locked until verification and activation are complete."
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
function lockCopy(access: BillingAccess | null, t: (text: string) => string): { title: string; body: string } {
  const kind = access?.attention?.kind;
  if (kind === "pending_review") {
    return {
      title: t("Subscription activation required"),
      body: t(
        "Your subscription payment is awaiting verification. Paid business features will become available once the Company Console administrator verifies your payment.",
      ),
    };
  }
  if (kind === "rejected") {
    return {
      title: t("Subscription activation required"),
      body: access?.attention?.reason
        ? access.attention.reason
        : t("The payment proof was not accepted. Submit a corrected receipt. Paid features stay locked until it is verified."),
    };
  }
  if (kind === "revoked") {
    return {
      title: t("Subscription activation required"),
      body: t("This subscription is not active. Paid features stay locked until it is restored."),
    };
  }
  if (access?.state === "restricted") {
    return {
      title: t("Subscription activation required"),
      body: t("This subscription is past its grace period. Paid features stay locked until it is renewed."),
    };
  }
  return {
    title: t("Subscription activation required"),
    body: t("Paid features stay locked until a payment is submitted, verified, and the subscription is activated."),
  };
}

function IndustryGate({
  subscriptionLocked,
  access,
}: {
  subscriptionLocked: boolean;
  access: BillingAccess | null;
}) {
  const { pathname } = useLocation();
  const { t } = useLocale();
  const { storedProfile, ready, recognized, businessType } = useTenant();
  if (subscriptionLocked && pathname !== "/subscription") {
    const copy = lockCopy(access, t);
    const rejected = access?.attention?.kind === "rejected";
    return (
      <section className="m-4 max-w-lg rounded-card border border-line bg-white p-6 md:m-6">
        <h1 className="text-xl font-semibold">{copy.title}</h1>
        <p className="mt-2 text-sm text-charcoal/70">{copy.body}</p>
        <p className="mt-4 flex flex-wrap gap-4 text-sm font-semibold">
          <Link to="/subscription" className="text-accent">
            {t("View Invoice")}
          </Link>
          {rejected || access?.attention?.kind === "awaiting_proof" ? (
            <Link to="/subscription" className="text-accent">
              {t("Submit Payment Receipt")}
            </Link>
          ) : null}
          <a href="mailto:info@axizpos.com" className="text-accent">
            {t("Contact Support")}
          </a>
        </p>
      </section>
    );
  }
  const allowed = portalRouteAllowed(pathname, ready ? storedProfile : null);
  if (!allowed && !ready) return null;
  if (!allowed) {
    const name = recognized ? profileSpec(businessType).label : "This business";
    return (
      <section className="m-4 max-w-lg rounded-card border border-line bg-white p-6 md:m-6">
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

/** Shared page gutter. Full-bleed workspaces such as Purchase Batches render outside it. */
export function PageFrame() {
  return (
    <div className="px-4 py-4 md:px-6 md:py-5">
      <Outlet />
    </div>
  );
}
