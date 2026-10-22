import { Permission } from "@ai-pos/shared-types";
import { useCallback, useState } from "react";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { Toast } from "../../components/ui/Toast";
import { useAuth } from "../../lib/auth";
import { CommissionsTab } from "./CommissionsTab";
import { PayrollTab } from "./PayrollTab";
import { TimesheetsTab } from "./TimesheetsTab";

type Tab = "timesheets" | "commissions" | "payroll";

export function StaffPage() {
  const { can } = useAuth();
  const payroll = can(Permission.PayrollManage);
  const [tab, setTab] = useState<Tab>("timesheets");
  const [toast, setToast] = useState<string | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);

  return (
    <section className="space-y-4">
      <SegmentedControl
        label="Staff"
        value={tab}
        options={[
          { value: "timesheets", label: "Timesheets" },
          { value: "commissions", label: "Commissions" },
          ...(payroll ? [{ value: "payroll" as const, label: "Payroll & WPS" }] : []),
        ]}
        onChange={setTab}
      />
      {tab === "timesheets" ? <TimesheetsTab onToast={setToast} /> : null}
      {tab === "commissions" ? <CommissionsTab onToast={setToast} /> : null}
      {tab === "payroll" && payroll ? <PayrollTab onToast={setToast} /> : null}
      {toast ? <Toast message={toast} onDismiss={dismissToast} /> : null}
    </section>
  );
}
