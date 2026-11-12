import { Permission } from "@ai-pos/shared-types";
import { AxizTabs, useLocale } from "@ai-pos/ui";
import { useCallback, useState } from "react";
import { tabBarClass } from "../../components/layout/AppShell";
import { Toast } from "../../components/ui/Toast";
import { useAuth } from "../../lib/auth";
import { CommissionsTab } from "./CommissionsTab";
import { PayrollTab } from "./PayrollTab";
import { TimesheetsTab } from "./TimesheetsTab";

type Tab = "timesheets" | "commissions" | "payroll";

const PAYROLL_ACCESS = [
  Permission.PayrollManage,
  Permission.PayrollView,
  Permission.PayrollManageProfiles,
  Permission.PayrollCalculate,
  Permission.PayrollSubmit,
  Permission.PayrollApprove,
  Permission.PayrollGenerateWps,
  Permission.PayrollRecordPayment,
  Permission.PayrollExport,
] as const;

export function StaffPage() {
  const { can } = useAuth();
  const { t } = useLocale();
  const staff = can(Permission.StaffManage);
  const payroll = PAYROLL_ACCESS.some((item) => can(item));
  const [tab, setTab] = useState<Tab>(staff ? "timesheets" : "payroll");
  const [toast, setToast] = useState<string | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);

  if (!staff && !payroll) {
    return (
      <section className="rounded-card border border-line bg-white p-6">
        <h2 className="text-2xl font-semibold">{t("Not available")}</h2>
        <p className="mt-2 text-sm text-charcoal/60">{t("Your role does not include access to this page.")}</p>
      </section>
    );
  }

  return (
    <section>
      <AxizTabs
        ariaLabel={t("Staff")}
        className={tabBarClass}
        activeTab={tab}
        onChange={(id) => setTab(id as Tab)}
        tabs={[
          ...(staff
            ? [
                { id: "timesheets", label: t("Timesheets") },
                { id: "commissions", label: t("Commissions") },
              ]
            : []),
          ...(payroll ? [{ id: "payroll", label: t("Payroll & WPS") }] : []),
        ]}
      />
      <div className="pt-4 md:pt-5">
        {tab === "timesheets" ? <TimesheetsTab onToast={setToast} /> : null}
        {tab === "commissions" ? <CommissionsTab onToast={setToast} /> : null}
        {tab === "payroll" && payroll ? <PayrollTab onToast={setToast} /> : null}
      </div>
      {toast ? <Toast message={toast} onDismiss={dismissToast} /> : null}
    </section>
  );
}
