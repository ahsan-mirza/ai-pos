import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Shell } from "./components/Shell";
import { SessionProvider, useSession } from "./lib/session";
import { LoginPage } from "./pages/LoginPage";
import { RequestsPage } from "./pages/RequestsPage";
import { TenantDrawer } from "./pages/TenantDrawer";
import { TenantsPage } from "./pages/TenantsPage";

function Console() {
  const { status } = useSession();
  if (status === "checking") {
    return <div className="flex min-h-screen items-center justify-center bg-charcoal text-sm text-white/60">Loading…</div>;
  }
  if (status === "signed-out") return <LoginPage />;
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Shell />}>
          <Route index element={<Navigate to="/tenants" replace />} />
          <Route path="tenants" element={<TenantsPage />}>
            <Route path=":tenantId" element={<TenantDrawer />} />
          </Route>
          <Route path="requests" element={<RequestsPage />} />
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
