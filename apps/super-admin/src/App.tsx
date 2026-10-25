import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Shell } from "./components/Shell";
import { SessionProvider, useSession } from "./lib/session";
import { AddonsPage, BillingPage, PackagesPage, SubscriptionsPage } from "./pages/CommercialPage";
import { MailPage } from "./pages/MailPage";
import { LoginPage } from "./pages/LoginPage";
import { RequestsPage } from "./pages/RequestsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { TenantDrawer } from "./pages/TenantDrawer";
import { TenantsPage } from "./pages/TenantsPage";
import { UsersPage } from "./pages/UsersPage";
import { WhatsAppPage } from "./pages/WhatsAppPage";

const basename = import.meta.env.BASE_URL === "/" ? undefined : import.meta.env.BASE_URL.replace(/\/$/, "");

function Console() {
  const { status } = useSession();
  if (status === "checking") {
    return <div className="flex min-h-screen items-center justify-center bg-[#f8fafc] text-sm text-charcoal/60">Loading…</div>;
  }
  if (status === "signed-out") return <LoginPage />;
  return (
    <BrowserRouter basename={basename}>
      <Routes>
        <Route element={<Shell />}>
          <Route index element={<Navigate to="/tenants" replace />} />
          <Route path="tenants" element={<TenantsPage />}>
            <Route path=":tenantId" element={<TenantDrawer />} />
          </Route>
          <Route path="requests" element={<RequestsPage />} />
          <Route path="packages" element={<PackagesPage />} />
          <Route path="billing" element={<BillingPage />} />
          <Route path="addons" element={<AddonsPage />} />
          <Route path="subscriptions" element={<SubscriptionsPage />} />
          <Route path="settings" element={<SettingsPage />}>
            <Route index element={<Navigate to="whatsapp" replace />} />
            <Route path="whatsapp" element={<WhatsAppPage />} />
            <Route path="landing" element={<Navigate to="/settings/whatsapp" replace />} />
            <Route path="email" element={<MailPage />} />
            <Route path="users" element={<UsersPage />} />
          </Route>
          <Route path="landing" element={<Navigate to="/settings/whatsapp" replace />} />
          <Route path="email" element={<Navigate to="/settings/email" replace />} />
          <Route path="*" element={<Navigate to="/tenants" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export function App() {
  return (
    <SessionProvider>
      <Console />
    </SessionProvider>
  );
}
