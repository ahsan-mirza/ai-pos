import { Capability, Permission, capabilitySpec } from "@ai-pos/shared-types";
import { useCallback, useState, type ReactNode } from "react";
import { BrowserRouter, Link, Navigate, Route, Routes } from "react-router-dom";
import { AppShell, PageFrame } from "./components/layout/AppShell";
import { ConfirmProvider } from "./components/ui/ConfirmDialog";
import { DashboardPage } from "./features/analytics/DashboardPage";
import { DeepAnalyticsPage } from "./features/analytics/DeepAnalyticsPage";
import { AuditPage } from "./features/audit/AuditPage";
import { AccountPage } from "./features/account/AccountPage";
import { LoginPage } from "./features/auth/LoginPage";
import { portalHomePath } from "./lib/portal-home";
import { CustomersPage } from "./features/customers/CustomersPage";
import { CustomerStatementPage } from "./features/customers/CustomerStatementPage";
import { BatchesPage } from "./features/inventory/batches/BatchesPage";
import { BrandsPage } from "./features/inventory/BrandsPage";
import { ModelsPage } from "./features/inventory/ModelsPage";
import { CategoriesPage } from "./features/inventory/CategoriesPage";
import { UnitsPage } from "./features/inventory/UnitsPage";
import { InventoryLayout } from "./features/inventory/InventoryLayout";
import { SettingsLayout } from "./features/settings/SettingsLayout";
import { InventoryPage } from "./features/inventory/InventoryPage";
import { PriceChangesPage } from "./features/inventory/PriceChangesPage";
import { PriceListsPage } from "./features/inventory/PriceListsPage";
import { PricingPage } from "./features/inventory/PricingPage";
import { MarkdownsPage } from "./features/inventory/MarkdownsPage";
import { PurchaseOrdersPage } from "./features/inventory/PurchaseOrdersPage";
import { ReplenishmentPage } from "./features/inventory/ReplenishmentPage";
import { StockCountsPage } from "./features/inventory/StockCountsPage";
import { ExpiringStockPage } from "./features/inventory/ExpiringStockPage";
import { WastePage } from "./features/inventory/WastePage";
import { FloorPlanPage } from "./features/menu/FloorPlanPage";
import { KitchenStationsPage } from "./features/menu/KitchenStationsPage";
import { RecipesPage } from "./features/menu/RecipesPage";
import { KitchenAgentPage } from "./features/inventory/KitchenAgentPage";
import { RecipeUsagePage } from "./features/menu/RecipeUsagePage";
import { KdsApp } from "./features/kds/KdsApp";
import { TableOrderApp } from "./features/table-order/TableOrderApp";
import { ModifiersPage } from "./features/menu/ModifiersPage";
import { MealsPage } from "./features/menu/MealsPage";
import { SerialTrackerPage } from "./features/inventory/SerialTrackerPage";
import { SizeCurvePage } from "./features/inventory/SizeCurvePage";
import { StockPage } from "./features/inventory/StockPage";
import { TransfersPage } from "./features/inventory/TransfersPage";
import { RepairsPage } from "./features/repairs/RepairsPage";
import { ReturnsPage } from "./features/returns/ReturnsPage";
import { RegistersPage } from "./features/registers/RegistersPage";
import { DownloadsPage } from "./features/downloads/DownloadsPage";
import { VatReportPage } from "./features/reports/VatReportPage";
import { ExportsPage } from "./features/reports/ExportsPage";
import { TipsReportPage } from "./features/reports/TipsReportPage";
import { ChannelsPage } from "./features/channels/ChannelsPage";
import { ShiftsPage } from "./features/shifts/ShiftsPage";
import { ChequesPage } from "./features/cheques/ChequesPage";
import { PaymentsPage } from "./features/payments/PaymentsPage";
import { StoreCreditPage } from "./features/returns/StoreCreditPage";
import { GiftCardsPage } from "./features/returns/GiftCardsPage";
import { PayablesPage } from "./features/payables/PayablesPage";
import { ExpensesPage } from "./features/expenses/ExpensesPage";
import { ConsignmentPage } from "./features/consignment/ConsignmentPage";
import { TradeInsPage } from "./features/tradeins/TradeInsPage";
import { PromotionsPage } from "./features/promotions/PromotionsPage";
import { InsightsPage } from "./features/insights/InsightsPage";
import { ManagementReportsPage } from "./features/reports/ManagementReportsPage";
import { StaffPage } from "./features/staff/StaffPage";
import { BankPage } from "./features/bank/BankPage";
import { ManagerMobilePage } from "./features/manager/ManagerMobilePage";
import { AssistantPage } from "./features/assistant/AssistantPage";
import { AccountingPage } from "./features/accounting/AccountingPage";
import { MessagingPage } from "./features/messaging/MessagingPage";
import { CurrenciesPage } from "./features/currencies/CurrenciesPage";
import { MarginPage } from "./features/margin/MarginPage";
import { WarrantyPage } from "./features/warranty/WarrantyPage";
import { RolesPage } from "./features/roles/RolesPage";
import { QuotationsPage } from "./features/sales/QuotationsPage";
import { DeliveryPodPage } from "./features/salesOrders/DeliveryPodPage";
import { SalesOrdersPage } from "./features/salesOrders/SalesOrdersPage";
import { ReordersPage } from "./features/reorders/ReordersPage";
import { AddonAccessPage } from "./features/settings/AddonAccessPage";
import { AddonLibraryPage } from "./features/settings/AddonLibraryPage";
import { SettingsPage } from "./features/settings/SettingsPage";
import { StoresPage } from "./features/stores/StoresPage";
import { UsersPage } from "./features/users/UsersPage";
import { AuthProvider, useAuth, useIsSuperAdmin } from "./lib/auth";
import { useCapability, useSettingsLabel } from "./lib/capabilities";
import { TenantProvider } from "./context/TenantContext";
import { CurrencyProvider, useCanManageSettings } from "./lib/currency";
import { SubscriptionPaymentPage } from "./features/billing/SubscriptionPaymentPage";
import { OnboardingWizard } from "./features/onboarding/OnboardingWizard";
import { SignupApp } from "./features/signup/SignupApp";
import { WelcomeHandoff, isWelcomeHandoff } from "./features/signup/WelcomeHandoff";

function RequirePermission({
  permission,
  businessWide = false,
  framed = false,
  children,
}: {
  permission: Permission;
  businessWide?: boolean;
  /** Full-bleed routes render outside `PageFrame`, so the notice adds its own margin. */
  framed?: boolean;
  children: ReactNode;
}) {
  const { can, user } = useAuth();
  if (!can(permission) || (businessWide && user?.store_id !== null)) {
    return (
      <section className={`rounded-card border border-line bg-white p-8 ${framed ? "m-4 md:m-6 lg:m-8" : ""}`}>
        <h2 className="text-2xl font-semibold">Not available</h2>
        <p className="mt-2 text-sm text-charcoal/60">Your role does not include access to this page.</p>
      </section>
    );
  }
  return children;
}

function RequireSuperAdmin({ children }: { children: ReactNode }) {
  if (useIsSuperAdmin()) return children;
  return (
    <section className="rounded-card border border-line bg-white p-8">
      <h2 className="text-2xl font-semibold">Not available</h2>
      <p className="mt-2 text-sm text-charcoal/60">Only a Super Admin can download the AxizPOS Register installer.</p>
    </section>
  );
}

function RequireCapability({ capability, children }: { capability: Capability; children: ReactNode }) {
  const enabled = useCapability(capability);
  const canManageSettings = useCanManageSettings();
  const settingsName = useSettingsLabel();
  if (enabled) return children;
  return (
    <section className="rounded-card border border-line bg-white p-8">
      <h2 className="text-2xl font-semibold">{capabilitySpec(capability).label} is switched off</h2>
      <p className="mt-2 text-sm text-charcoal/60">
        This module is not enabled for your business type. Your data is kept and comes back when it is switched on.
      </p>
      {canManageSettings ? (
        <Link
          to="/settings#business-profile"
          className="mt-5 inline-flex h-10 items-center rounded-lg bg-accent px-4 text-sm font-semibold text-white hover:bg-accent/90"
        >
          Manage modules
        </Link>
      ) : (
        <p className="mt-2 text-sm text-charcoal/60">Ask a business-wide admin to turn it on in {settingsName}.</p>
      )}
    </section>
  );
}

function DashboardRoute() {
  return (
    <RequirePermission permission={Permission.PortalReportsRead}>
      <DashboardPage />
    </RequirePermission>
  );
}

function Portal() {
  const { status } = useAuth();
  const [welcoming, setWelcoming] = useState(isWelcomeHandoff);
  const welcomed = useCallback(() => setWelcoming(false), []);
  if (welcoming) return <WelcomeHandoff onDone={welcomed} />;
  if (status === "checking") {
    return <div className="flex min-h-screen items-center justify-center bg-canvas text-sm text-charcoal/60">Loading…</div>;
  }
  if (status === "signed-out") return <LoginPage />;
  return (
    <BrowserRouter>
      <OnboardingWizard />
      <Routes>
        <Route
          path="m"
          element={
            <RequirePermission permission={Permission.PortalReportsRead} framed>
              <ManagerMobilePage />
            </RequirePermission>
          }
        />
        <Route
          path="deliveries/:noteId"
          element={
            <RequirePermission permission={Permission.SalesOrders} framed>
              <RequireCapability capability={Capability.SalesOrders}>
                <DeliveryPodPage />
              </RequireCapability>
            </RequirePermission>
          }
        />
        <Route element={<AppShell />}>
          <Route path="inventory" element={<InventoryLayout />}>
            <Route index element={<Navigate to="stock" replace />} />
            <Route element={<PageFrame />}>
              <Route path="stock" element={<StockPage />} />
              <Route path="products" element={<InventoryPage />} />
              <Route path="pricing" element={<RequireCapability capability={Capability.WholesalePricing}><PricingPage /></RequireCapability>} />
              <Route path="price-lists" element={<PriceListsPage />} />
              <Route path="price-changes" element={<PriceChangesPage />} />
              <Route path="categories" element={<CategoriesPage />} />
              <Route path="brands" element={<BrandsPage />} />
              <Route path="models" element={<ModelsPage />} />
              <Route path="units" element={<UnitsPage />} />
              <Route path="purchase-orders" element={<PurchaseOrdersPage />} />
              <Route path="markdowns" element={<RequireCapability capability={Capability.VariantsMatrix}><MarkdownsPage /></RequireCapability>} />
              <Route path="size-curve" element={<RequireCapability capability={Capability.VariantsMatrix}><SizeCurvePage /></RequireCapability>} />
              <Route
                path="replenishment"
                element={
                  <RequirePermission permission={Permission.ReplenishmentManage}>
                    <ReplenishmentPage />
                  </RequirePermission>
                }
              />
              <Route path="counts" element={<StockCountsPage />} />
              <Route path="expiring" element={<RequireCapability capability={Capability.Fefo}><ExpiringStockPage /></RequireCapability>} />
              <Route path="waste" element={<RequireCapability capability={Capability.Fefo}><WastePage /></RequireCapability>} />
              <Route path="modifiers" element={<RequireCapability capability={Capability.MenuModifiers}><ModifiersPage /></RequireCapability>} />
              <Route path="meals" element={<RequireCapability capability={Capability.MenuModifiers}><MealsPage /></RequireCapability>} />
              <Route path="floor-plan" element={<RequireCapability capability={Capability.Tables}><FloorPlanPage /></RequireCapability>} />
              <Route path="kitchen" element={<RequireCapability capability={Capability.Kds}><KitchenStationsPage /></RequireCapability>} />
              <Route path="recipes" element={<RequireCapability capability={Capability.Recipes}><RecipesPage /></RequireCapability>} />
              <Route path="kitchen-agent" element={<RequireCapability capability={Capability.Recipes}><KitchenAgentPage /></RequireCapability>} />
              <Route path="recipe-usage" element={<RequireCapability capability={Capability.Recipes}><RecipeUsagePage /></RequireCapability>} />
              <Route path="transfers" element={<TransfersPage />} />
              <Route path="serials" element={<RequireCapability capability={Capability.SerialTracking}><SerialTrackerPage /></RequireCapability>} />
            </Route>
            <Route
              path="batches"
              element={
                <RequirePermission permission={Permission.PortalInventoryManage} framed>
                  <BatchesPage />
                </RequirePermission>
              }
            />
          </Route>
          <Route element={<PageFrame />}>
          <Route index element={<DashboardRoute />} />
          <Route path="dashboard" element={<DashboardRoute />} />
          <Route path="account" element={<AccountPage />} />
          <Route
            path="subscription"
            element={
              <RequirePermission permission={Permission.SettingsManage} businessWide>
                <SubscriptionPaymentPage />
              </RequirePermission>
            }
          />
          <Route
            path="customers"
            element={
              <RequirePermission permission={Permission.CustomersManage}>
                <CustomersPage />
              </RequirePermission>
            }
          />
          <Route
            path="customers/:customerId"
            element={
              <RequirePermission permission={Permission.CustomersManage}>
                <CustomerStatementPage />
              </RequirePermission>
            }
          />
          <Route path="sales" element={<Navigate to="/sales/quotations" replace />} />
          <Route
            path="sales/quotations"
            element={
              <RequirePermission permission={Permission.PortalReportsRead}>
                <RequireCapability capability={Capability.QuotesLayaway}><QuotationsPage /></RequireCapability>
              </RequirePermission>
            }
          />
          <Route
            path="sales-orders"
            element={
              <RequirePermission permission={Permission.SalesOrders}>
                <RequireCapability capability={Capability.SalesOrders}><SalesOrdersPage /></RequireCapability>
              </RequirePermission>
            }
          />
          <Route
            path="reorders"
            element={
              <RequirePermission permission={Permission.CustomersManage}>
                <RequireCapability capability={Capability.CustomerReorders}><ReordersPage /></RequireCapability>
              </RequirePermission>
            }
          />
          <Route path="repairs" element={<RequireCapability capability={Capability.Repairs}><RepairsPage /></RequireCapability>} />
          <Route path="repairs/:ticketId" element={<RequireCapability capability={Capability.Repairs}><RepairsPage /></RequireCapability>} />
          <Route
            path="returns"
            element={
              <RequirePermission permission={Permission.PortalReportsRead}>
                <ReturnsPage />
              </RequirePermission>
            }
          />
          <Route
            path="users"
            element={
              <RequirePermission permission={Permission.UsersRead}>
                <UsersPage />
              </RequirePermission>
            }
          />
          <Route path="admin/activity" element={<Navigate to="/settings/audit-logs" replace />} />
          <Route
            path="warranties"
            element={
              <RequirePermission permission={Permission.PortalAccess}>
                <RequireCapability capability={Capability.Warranty}><WarrantyPage /></RequireCapability>
              </RequirePermission>
            }
          />
          <Route
            path="margin"
            element={
              <RequirePermission permission={Permission.PortalReportsRead}>
                <MarginPage />
              </RequirePermission>
            }
          />
          <Route
            path="expenses"
            element={
              <RequirePermission permission={Permission.ExpensesManage}>
                <ExpensesPage />
              </RequirePermission>
            }
          />
          <Route
            path="payables"
            element={
              <RequirePermission permission={Permission.PayablesManage}>
                <PayablesPage />
              </RequirePermission>
            }
          />          <Route
            path="consignment"
            element={
              <RequirePermission permission={Permission.PayablesManage}>
                <RequireCapability capability={Capability.Consignment}>
                  <ConsignmentPage />
                </RequireCapability>
              </RequirePermission>
            }
          />
          <Route
            path="staff"
            element={
              <RequirePermission permission={Permission.StaffManage}>
                <StaffPage />
              </RequirePermission>
            }
          />
          <Route
            path="assistant"
            element={
              <RequirePermission permission={Permission.PortalReportsRead}>
                <AssistantPage />
              </RequirePermission>
            }
          />
          <Route
            path="accounting"
            element={
              <RequirePermission permission={Permission.AccountingManage}>
                <AccountingPage />
              </RequirePermission>
            }
          />
          <Route
            path="bank"
            element={
              <RequirePermission permission={Permission.BankingManage}>
                <BankPage />
              </RequirePermission>
            }
          />
          <Route
            path="insights"
            element={
              <RequirePermission permission={Permission.PortalReportsRead}>
                <InsightsPage />
              </RequirePermission>
            }
          />
          <Route
            path="reports/management"
            element={
              <RequirePermission permission={Permission.PortalReportsRead}>
                <ManagementReportsPage />
              </RequirePermission>
            }
          />
          <Route
            path="analytics/deep"
            element={
              <RequirePermission permission={Permission.PortalReportsRead}>
                <RequireCapability capability={Capability.DeepAnalytics}>
                  <DeepAnalyticsPage />
                </RequireCapability>
              </RequirePermission>
            }
          />
          <Route
            path="promotions"
            element={
              <RequirePermission permission={Permission.PromotionsManage}>
                <RequireCapability capability={Capability.Promotions}><PromotionsPage /></RequireCapability>
              </RequirePermission>
            }
          />
          <Route
            path="trade-ins"
            element={
              <RequirePermission permission={Permission.PortalReportsRead}>
                <RequireCapability capability={Capability.TradeIn}><TradeInsPage /></RequireCapability>
              </RequirePermission>
            }
          />
          <Route
            path="store-credit"
            element={
              <RequirePermission permission={Permission.PortalReportsRead}>
                <StoreCreditPage />
              </RequirePermission>
            }
          />
          <Route
            path="gift-cards"
            element={
              <RequirePermission permission={Permission.GiftCardsManage}>
                <RequireCapability capability={Capability.GiftCards}><GiftCardsPage /></RequireCapability>
              </RequirePermission>
            }
          />
          <Route
            path="payments"
            element={
              <RequirePermission permission={Permission.PortalReportsRead}>
                <PaymentsPage />
              </RequirePermission>
            }
          />
          <Route
            path="cheques"
            element={
              <RequirePermission permission={Permission.ChequesManage}>
                <RequireCapability capability={Capability.Cheques}><ChequesPage /></RequireCapability>
              </RequirePermission>
            }
          />
          <Route
            path="shifts"
            element={
              <RequirePermission permission={Permission.PortalReportsRead}>
                <ShiftsPage />
              </RequirePermission>
            }
          />
          <Route
            path="reports/exports"
            element={
              <RequirePermission permission={Permission.ReportsVat}>
                <ExportsPage />
              </RequirePermission>
            }
          />
          <Route
            path="reports/tips"
            element={
              <RequirePermission permission={Permission.PortalReportsRead}>
                <RequireCapability capability={Capability.TipsServiceCharge}><TipsReportPage /></RequireCapability>
              </RequirePermission>
            }
          />
          <Route
            path="reports/vat"
            element={
              <RequirePermission permission={Permission.ReportsVat}>
                <VatReportPage />
              </RequirePermission>
            }
          />
          </Route>
          <Route element={<SettingsLayout />}>
            <Route element={<PageFrame />}>
              <Route path="stores" element={<StoresPage />} />
              <Route
                path="roles"
                element={
                  <RequirePermission permission={Permission.UsersRead}>
                    <RolesPage />
                  </RequirePermission>
                }
              />
              <Route
                path="settings/addons"
                element={
                  <RequirePermission permission={Permission.SettingsManage} businessWide>
                    <AddonLibraryPage />
                  </RequirePermission>
                }
              />
              <Route
                path="settings/addon-access"
                element={
                  <RequirePermission permission={Permission.UsersRead}>
                    <AddonAccessPage />
                  </RequirePermission>
                }
              />
              <Route
                path="settings"
                element={
                  <RequirePermission permission={Permission.SettingsManage} businessWide>
                    <SettingsPage />
                  </RequirePermission>
                }
              />
              <Route
                path="settings/audit-logs"
                element={
                  <RequirePermission permission={Permission.AuditRead}>
                    <AuditPage />
                  </RequirePermission>
                }
              />
              <Route
                path="settings/currencies"
                element={
                  <RequirePermission permission={Permission.CurrenciesManage}>
                    <RequireCapability capability={Capability.MultiCurrency}><CurrenciesPage /></RequireCapability>
                  </RequirePermission>
                }
              />
              <Route
                path="settings/channels"
                element={
                  <RequirePermission permission={Permission.SettingsManage}>
                    <RequireCapability capability={Capability.DeliveryChannels}><ChannelsPage /></RequireCapability>
                  </RequirePermission>
                }
              />
              <Route
                path="settings/messaging"
                element={
                  <RequirePermission permission={Permission.MessagingManage}>
                    <MessagingPage />
                  </RequirePermission>
                }
              />
              <Route
                path="registers"
                element={
                  <RequirePermission permission={Permission.DevicesManage}>
                    <RegistersPage />
                  </RequirePermission>
                }
              />
              <Route
                path="downloads"
                element={
                  <RequireSuperAdmin>
                    <DownloadsPage />
                  </RequireSuperAdmin>
                }
              />
            </Route>
          </Route>
          <Route path="*" element={<Navigate to={portalHomePath()} replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export function App() {
  // Signup is public and tenant-free, so it renders before the auth gate on any host.
  if (window.location.pathname.startsWith("/signup")) return <SignupApp />;
  // The kitchen display signs in with a device token, not a staff session.
  if (window.location.pathname.startsWith("/kds")) return <KdsApp />;
  // Waiter handheld and the tablet left on a table. Same device-token sign-in as the kitchen display.
  if (window.location.pathname === "/table" || window.location.pathname.startsWith("/table/")) return <TableOrderApp />;
  return (
    <AuthProvider>
      <CurrencyProvider>
        <TenantProvider>
          <ConfirmProvider>
            <Portal />
          </ConfirmProvider>
        </TenantProvider>
      </CurrencyProvider>
    </AuthProvider>
  );
}
