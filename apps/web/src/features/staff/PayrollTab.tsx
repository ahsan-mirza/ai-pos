import {
  formatMoney,
  Permission,
  type Employee,
  type EmployeeProfile,
  type PayrollLine,
  type PayrollPayment,
  type PayrollPaymentStatus,
  type PayrollRun,
  type PayrollRunStatus,
  type PayrollSettings,
  type SalaryComponent,
  type WpsValidation,
} from "@ai-pos/shared-types";
import { formatDate, useLocale } from "@ai-pos/ui";
import { Download, Lock, Play, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { DataTable, type DataTableColumn } from "../../components/ui/DataTable";
import { ErrorNote, FilterSelect, GhostButton, PrimaryButton, SearchField, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { apiBlob, apiGet, apiPost, apiPut } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useCurrency } from "../../lib/currency";
import { toCents } from "../customers/api";
import { storeOptions, useStores } from "../inventory/shared";
import { errorMessage } from "../users/api";
import { hours } from "./TimesheetsTab";

const EMPTY_EMPLOYER: PayrollSettings = {
  employer_id: "",
  bank_routing_code: "",
  bank_name: "",
  employer_reference: "",
  segregate_approval: false,
};

const RUN_LABEL: Record<PayrollRunStatus, string> = {
  DRAFT: "Draft",
  UNDER_REVIEW: "Under review",
  FINALIZED: "Approved",
  CANCELLED: "Cancelled",
};

const PAY_LABEL: Record<PayrollPaymentStatus, string> = {
  NONE: "Not paid",
  GENERATED: "WPS file generated",
  SUBMITTED: "Submitted to the bank",
  PROCESSING: "Bank processing",
  PARTIALLY_PAID: "Partially paid",
  PAID: "Paid",
  REJECTED: "Rejected by the bank",
  FAILED: "Payment failed",
};

const monthName = (year: number, month: number) =>
  new Date(year, month - 1, 1).toLocaleDateString(undefined, { month: "long", year: "numeric" });

const periodEnd = (year: number, month: number) => formatDate(`${year}-${String(month).padStart(2, "0")}-${String(new Date(year, month, 0).getDate()).padStart(2, "0")}`);

const periodStart = (year: number, month: number) => formatDate(`${year}-${String(month).padStart(2, "0")}-01`);

export function PayrollTab({ onToast }: { onToast: (text: string) => void }) {
  const { t } = useLocale();
  const { can } = useAuth();
  const { currency } = useCurrency();
  const { stores } = useStores();
  const allowed = (...keys: Permission[]) => can(Permission.PayrollManage) || keys.some((key) => can(key));
  const canRun = allowed(Permission.PayrollCalculate);
  const canReview = allowed(Permission.PayrollSubmit);
  const canApprove = allowed(Permission.PayrollApprove);
  const canWps = allowed(Permission.PayrollGenerateWps);
  const canPay = allowed(Permission.PayrollRecordPayment);
  const canProfiles = allowed(Permission.PayrollManageProfiles);
  const canExport = allowed(Permission.PayrollExport);
  const [employer, setEmployer] = useState<PayrollSettings>(EMPTY_EMPLOYER);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [runs, setRuns] = useState<PayrollRun[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [year, setYear] = useState(String(new Date().getFullYear()));
  const [month, setMonth] = useState(String(new Date().getMonth() + 1));
  const [branch, setBranch] = useState("");
  const [query, setQuery] = useState("");
  const [lineStatus, setLineStatus] = useState("");
  const [editingEmployee, setEditingEmployee] = useState<Employee | null>(null);
  const [editingLine, setEditingLine] = useState<PayrollLine | null>(null);
  const [paying, setPaying] = useState(false);
  const [wps, setWps] = useState<WpsValidation | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const money = (cents: number) => formatMoney(cents, currency);

  const load = useCallback(async () => {
    try {
      const [settings, people, history] = await Promise.all([
        apiGet<PayrollSettings | null>("/api/v1/staff/payroll/settings"),
        apiGet<Employee[]>("/api/v1/staff/employees"),
        apiGet<PayrollRun[]>("/api/v1/staff/payroll/runs"),
      ]);
      setEmployer(settings ? { ...EMPTY_EMPLOYER, ...settings } : EMPTY_EMPLOYER);
      setEmployees(people);
      setRuns(history);
      setSelected((current) => current ?? history.find((row) => row.status !== "CANCELLED")?.id ?? history[0]?.id ?? null);
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "Could not load payroll."));
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const run = runs.find((row) => row.id === selected) ?? null;
  const replace = (next: PayrollRun) => setRuns((current) => current.map((row) => (row.id === next.id ? next : row)));
  const ready = employees.filter((person) => person.profile?.profile_status === "ACTIVE" && person.profile.is_active).length;
  const excluded = run?.exceptions.filter((row) => row.severity === "EXCLUDED") ?? [];
  const warnings = run?.exceptions.filter((row) => row.severity === "WARNING") ?? [];
  const lines = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (run?.lines ?? []).filter((line) => {
      const matchesQuery = !needle || `${line.name} ${line.employee_code}`.toLowerCase().includes(needle);
      const matchesBranch = !branch || line.store_id === branch;
      const matchesStatus = !lineStatus || line.calculation_status === lineStatus;
      return matchesQuery && matchesBranch && matchesStatus;
    });
  }, [run, query, branch, lineStatus]);

  const act = async (work: () => Promise<PayrollRun>, message: string) => {
    try {
      const next = await work();
      if (runs.some((row) => row.id === next.id)) replace(next);
      else setRuns([next, ...runs]);
      setSelected(next.id);
      onToast(message);
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "Could not update the payroll."));
    }
  };

  const startRun = () => {
    const payrollYear = Number(year);
    const payrollMonth = Number(month);
    void act(
      () =>
        apiPost<PayrollRun>("/api/v1/staff/payroll/runs", {
          year: payrollYear,
          month: payrollMonth,
          store_id: branch || null,
        }),
      t("Payroll drafted."),
    );
  };

  const download = async (path: string, filename: string) => {
    try {
      const blob = await apiBlob(path);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(url);
    } catch (caught) {
      setError(errorMessage(caught, "Could not download the file."));
    }
  };

  const saveEmployer = async () => {
    try {
      setEmployer(await apiPut<PayrollSettings>("/api/v1/staff/payroll/settings", employer));
      onToast(t("WPS employer details saved."));
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "Could not save the employer details."));
    }
  };

  const validateWps = async () => {
    if (!run) return;
    try {
      setWps(await apiPost<WpsValidation>(`/api/v1/staff/payroll/runs/${run.id}/wps/validate`, {}));
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "Could not validate the WPS file."));
    }
  };

  const columns: DataTableColumn<PayrollLine>[] = [
    { id: "code", header: t("Employee code"), cell: (line) => line.employee_code },
    { id: "name", header: t("Employee"), cell: (line) => line.name },
    { id: "branch", header: t("Branch"), cell: (line) => line.store_name || "—" },
    { id: "basic", header: t("Basic"), align: "right", cell: (line) => money(line.basic_cents) },
    { id: "allowances", header: t("Allowances"), align: "right", cell: (line) => money(line.allowances_cents) },
    { id: "overtime", header: t("Overtime"), align: "right", cell: (line) => money(line.overtime_cents) },
    { id: "commission", header: t("Commission"), align: "right", cell: (line) => money(line.commission_cents) },
    { id: "gross", header: t("Gross"), align: "right", cell: (line) => money(line.gross_cents) },
    {
      id: "deductions",
      header: t("Deductions"),
      align: "right",
      cell: (line) => money(line.deductions_cents + line.recurring_deduction_cents + line.leave_deduction_cents),
    },
    { id: "net", header: t("Net payable"), align: "right", cell: (line) => money(line.net_cents) },
    { id: "status", header: t("Status"), cell: (line) => line.calculation_status },
  ];

  const employerReady = employer.employer_id.length === 13 && employer.bank_routing_code.length === 9;

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-semibold text-charcoal">{t("Payroll & WPS")}</h2>
        <p className="text-sm text-charcoal/60">
          {t("Monthly pay uses the active salary profile, approved timesheets, and posted commission. Gratuity and end-of-service stay out of this run.")}
        </p>
      </div>
      <ErrorNote message={error} />
      {!loaded ? <p className="text-sm text-charcoal/60">{t("Loading payroll…")}</p> : null}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label={t("Current period")} value={run ? `${periodStart(run.year, run.month)} – ${periodEnd(run.year, run.month)}` : t("No payroll run")} />
        <Metric label={t("Employees ready")} value={loaded ? String(ready) : "—"} />
        <Metric label={t("Gross payroll")} value={run ? money(run.total_gross_cents) : "—"} />
        <Metric label={t("Net payroll")} value={run ? money(run.total_net_cents) : "—"} />
      </div>

      <article className="rounded-card border border-line bg-white p-6">
        <h3 className="font-semibold">{t("Payroll processing")}</h3>
        <div className="mt-4 grid gap-3 md:grid-cols-4">
          <FilterSelect
            label={t("Month")}
            value={month}
            options={Array.from({ length: 12 }, (_, index) => ({
              value: String(index + 1),
              label: new Date(2026, index, 1).toLocaleDateString(undefined, { month: "long" }),
            }))}
            onChange={setMonth}
          />
          <FilterSelect
            label={t("Year")}
            value={year}
            options={[0, 1, 2].map((offset) => {
              const value = String(new Date().getFullYear() - offset);
              return { value, label: value };
            })}
            onChange={setYear}
          />
          <FilterSelect
            label={t("Branch")}
            value={branch}
            options={[{ value: "", label: t("All branches") }, ...storeOptions(stores)]}
            onChange={setBranch}
          />
          <div className="flex items-end">
            {canRun ? (
              <PrimaryButton onClick={startRun}>
                <Play size={15} aria-hidden="true" className="-ms-1 me-1.5" /> {t("Run payroll")}
              </PrimaryButton>
            ) : null}
          </div>
        </div>
        {run ? (
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium">{monthName(run.year, run.month)}</span>
            <span className="rounded-full bg-surface px-2.5 py-1 text-xs font-semibold">{t(RUN_LABEL[run.status])}</span>
            <span className="rounded-full bg-surface px-2.5 py-1 text-xs font-semibold">{t(PAY_LABEL[run.payment_status])}</span>
            {run.status === "DRAFT" && canRun ? (
              <GhostButton onClick={() => void act(() => apiPost<PayrollRun>(`/api/v1/staff/payroll/runs/${run.id}/recalculate`, {}), t("Payroll recalculated."))}>
                <RefreshCw size={15} aria-hidden="true" className="-ms-1 me-1.5" /> {t("Recalculate")}
              </GhostButton>
            ) : null}
            {run.status === "DRAFT" && canReview ? (
              <GhostButton onClick={() => void act(() => apiPost<PayrollRun>(`/api/v1/staff/payroll/runs/${run.id}/submit`, {}), t("Submitted for review."))}>
                {t("Submit for review")}
              </GhostButton>
            ) : null}
            {run.status === "UNDER_REVIEW" && canApprove ? (
              <PrimaryButton onClick={() => void act(() => apiPost<PayrollRun>(`/api/v1/staff/payroll/runs/${run.id}/approve`, {}), t("Payroll approved."))}>
                <Lock size={15} aria-hidden="true" className="-ms-1 me-1.5" /> {t("Approve")}
              </PrimaryButton>
            ) : null}
            {run.status === "UNDER_REVIEW" && canApprove ? (
              <GhostButton
                onClick={() =>
                  void act(
                    () => apiPost<PayrollRun>(`/api/v1/staff/payroll/runs/${run.id}/reject`, { note: "Returned for correction" }),
                    t("Payroll returned."),
                  )
                }
              >
                {t("Return for correction")}
              </GhostButton>
            ) : null}
            {(run.status === "DRAFT" || run.status === "UNDER_REVIEW") && canRun ? (
              <GhostButton onClick={() => void act(() => apiPost<PayrollRun>(`/api/v1/staff/payroll/runs/${run.id}/cancel`, { note: "" }), t("Payroll cancelled."))}>
                {t("Cancel draft")}
              </GhostButton>
            ) : null}
            {run.status === "FINALIZED" && canWps ? (
              <GhostButton onClick={() => void validateWps()}>{t("Validate WPS")}</GhostButton>
            ) : null}
            {run.status === "FINALIZED" && canWps ? (
              <PrimaryButton onClick={() => void download(`/api/v1/staff/payroll/runs/${run.id}/wps.sif`, `payroll-${run.year}${String(run.month).padStart(2, "0")}.SIF`)}>
                <Download size={15} aria-hidden="true" className="-ms-1 me-1.5" /> {t("Generate WPS preview")}
              </PrimaryButton>
            ) : null}
            {run.status === "FINALIZED" && canPay ? (
              <GhostButton onClick={() => setPaying(true)}>{t("Record payment")}</GhostButton>
            ) : null}
          </div>
        ) : null}
        {excluded.length || warnings.length ? (
          <ul className="mt-4 space-y-1 text-sm">
            {[...excluded, ...warnings].map((row) => (
              <li key={`${row.user_id}-${row.code}`} className={row.severity === "EXCLUDED" ? "text-danger" : "text-charcoal/70"}>
                {row.name ? `${row.name}: ` : ""}
                {row.message}
              </li>
            ))}
          </ul>
        ) : null}
      </article>

      <article className="rounded-card border border-line bg-white p-6">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h3 className="font-semibold">{t("Payroll register")}</h3>
            <p className="text-sm text-charcoal/60">
              {run
                ? t("Totals below are the full payroll, not the rows on this page. Deductions {deductions}.", {
                    deductions: money(run.total_deductions_cents),
                  })
                : t("Run a payroll month to see the register.")}
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <SearchField label={t("Search employees")} value={query} onChange={(event) => setQuery(event.target.value)} />
            <FilterSelect
              label={t("Calculation")}
              value={lineStatus}
              options={[
                { value: "", label: t("All statuses") },
                { value: "OK", label: "OK" },
                { value: "WARNING", label: t("Warning") },
              ]}
              onChange={setLineStatus}
            />
          </div>
        </div>
        {run ? (
          <>
            <div className="hidden md:block">
              <DataTable
                aria-label={t("Payroll register")}
                columns={columns}
                data={lines}
                getRowId={(line) => line.id}
                onRowClick={(line) => setEditingLine(line)}
                variant="flush"
                pagination={{ mode: "client", resetKey: `${run.id}:${query}:${branch}:${lineStatus}` }}
                emptyState={{ title: t("No employees match"), description: t("Change the search or filters.") }}
              />
            </div>
            <ul className="space-y-2 md:hidden">
              {lines.map((line) => (
                <li key={line.id}>
                  <button type="button" onClick={() => setEditingLine(line)} className="w-full rounded-2xl border border-line p-3 text-start">
                    <span className="block font-medium">{line.name}</span>
                    <span className="block text-xs text-charcoal/50">{line.employee_code}</span>
                    <span className="mt-1 block text-sm font-semibold tabular-nums">{money(line.net_cents)}</span>
                  </button>
                </li>
              ))}
              {lines.length === 0 ? <li className="text-sm text-charcoal/60">{t("No employees match")}</li> : null}
            </ul>
          </>
        ) : (
          <p className="rounded-2xl border border-dashed border-line p-8 text-center text-sm text-charcoal/60">
            {t("Add payroll details for your staff, then run this month's payroll.")}
          </p>
        )}
      </article>

      <div className="grid gap-4 xl:grid-cols-2">
        <article className="rounded-card bg-charcoal p-6 text-white">
          <h3 className="font-semibold">{t("WPS employer")}</h3>
          <p className="mt-1 text-xs text-white/60">
            {t("This preview follows the EDR and SCR layout already used here. It is not a MOHRE receipt and it does not mean the bank has paid.")}
          </p>
          <p className={`mt-2 text-xs font-semibold ${employerReady ? "text-white" : "text-accent"}`}>
            {employerReady ? t("Employer configuration is complete.") : t("Employer configuration is missing a 13-digit establishment ID or a 9-digit routing code.")}
          </p>
          <div className="mt-3 grid gap-2">
            <input aria-label={t("MOHRE establishment ID")} value={employer.employer_id} maxLength={13} placeholder={t("Establishment ID (13 digits)")} onChange={(event) => setEmployer({ ...employer, employer_id: event.target.value.replace(/\D/g, "") })} className="w-full rounded-xl bg-white/10 px-3 py-2 font-mono text-sm text-white placeholder:text-white/40 focus:outline-none focus:ring-2 focus:ring-accent" />
            <input aria-label={t("Employer bank routing code")} value={employer.bank_routing_code} maxLength={9} placeholder={t("Bank routing code (9 digits)")} onChange={(event) => setEmployer({ ...employer, bank_routing_code: event.target.value.replace(/\D/g, "") })} className="w-full rounded-xl bg-white/10 px-3 py-2 font-mono text-sm text-white placeholder:text-white/40 focus:outline-none focus:ring-2 focus:ring-accent" />
            <input aria-label={t("Salary bank")} value={employer.bank_name} maxLength={80} placeholder={t("Salary bank")} onChange={(event) => setEmployer({ ...employer, bank_name: event.target.value })} className="w-full rounded-xl bg-white/10 px-3 py-2 text-sm text-white placeholder:text-white/40 focus:outline-none focus:ring-2 focus:ring-accent" />
            <input aria-label={t("Employer reference")} value={employer.employer_reference} maxLength={40} placeholder={t("Employer reference")} onChange={(event) => setEmployer({ ...employer, employer_reference: event.target.value })} className="w-full rounded-xl bg-white/10 px-3 py-2 text-sm text-white placeholder:text-white/40 focus:outline-none focus:ring-2 focus:ring-accent" />
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={employer.segregate_approval} onChange={(event) => setEmployer({ ...employer, segregate_approval: event.target.checked })} />
              {t("The person who prepares a payroll cannot approve it")}
            </label>
            {canWps ? (
              <button type="button" onClick={() => void saveEmployer()} className="h-9 w-full rounded-full bg-accent text-sm font-semibold">
                {t("Save employer")}
              </button>
            ) : null}
          </div>
          {wps ? (
            <div className="mt-3 text-xs text-white/80">
              <p>{wps.provider_note}</p>
              {wps.issues.length ? (
                <ul className="mt-2 space-y-1">
                  {wps.issues.map((issue) => (
                    <li key={`${issue.code}-${issue.employee_code}`}>{issue.name ? `${issue.name}: ` : ""}{issue.message}</li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2">{wps.ready ? t("WPS validation passed.") : t("WPS validation is not ready.")}</p>
              )}
            </div>
          ) : null}
        </article>

        <article className="rounded-card border border-line bg-white p-6">
          <h3 className="font-semibold">{t("Employee payroll profiles")}</h3>
          <ul className="mt-3 space-y-1.5">
            {employees.map((person) => (
              <li key={person.user_id}>
                <button type="button" onClick={() => canProfiles && setEditingEmployee(person)} className="flex w-full items-center justify-between gap-2 rounded-xl px-2 py-1.5 text-start text-sm hover:bg-surface">
                  <span className="min-w-0">
                    <span className="block truncate font-medium">{person.name}</span>
                    <span className="block truncate text-xs text-charcoal/50">
                      {[person.profile?.employee_code, person.store_name || person.role_name, person.employment_status === "ACTIVE" ? t("Active") : t("Inactive")].filter(Boolean).join(" · ")}
                    </span>
                  </span>
                  <span className={`shrink-0 text-xs ${person.profile?.profile_status === "ACTIVE" ? "" : "font-semibold text-accent"}`}>
                    {person.profile?.profile_status === "ACTIVE" ? t("Salary active") : t("Add payroll details")}
                  </span>
                </button>
              </li>
            ))}
            {loaded && employees.length === 0 ? <li className="text-sm text-charcoal/60">{t("No employees to show.")}</li> : null}
          </ul>
        </article>
      </div>

      <article className="rounded-card border border-line bg-white p-6">
        <h3 className="font-semibold">{t("Payroll history")}</h3>
        {runs.length === 0 ? <p className="mt-3 text-sm text-charcoal/60">{t("No payroll runs yet.")}</p> : null}
        <ul className="mt-3 divide-y divide-line">
          {runs.map((row) => (
            <li key={row.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
              <button type="button" onClick={() => setSelected(row.id)} className="text-start font-medium">
                {monthName(row.year, row.month)}
              </button>
              <span>{t(RUN_LABEL[row.status])}</span>
              <span>{t(PAY_LABEL[row.payment_status])}</span>
              <span className="tabular-nums">{money(row.total_net_cents)}</span>
              <span className="text-charcoal/60">{row.lines.length}</span>
            </li>
          ))}
        </ul>
      </article>

      {editingEmployee && canProfiles ? (
        <EmployeeModal
          employee={editingEmployee}
          onClose={() => setEditingEmployee(null)}
          onSaved={(people) => {
            setEmployees(people);
            setEditingEmployee(null);
            onToast(t("Payroll details saved."));
          }}
        />
      ) : null}
      {editingLine && run ? (
        <LineModal
          run={run}
          line={editingLine}
          canEdit={run.status === "DRAFT" && canRun}
          canDownload={run.status === "FINALIZED" && (canExport || can(Permission.PayrollView) || can(Permission.PayrollManage))}
          onDownload={() => void download(`/api/v1/staff/payroll/payslips/${editingLine.id}.pdf`, `payslip-${editingLine.employee_code}.pdf`)}
          onClose={() => setEditingLine(null)}
          onSaved={(next) => {
            replace(next);
            setEditingLine(null);
            onToast(t("Pay updated."));
          }}
        />
      ) : null}
      {paying && run ? (
        <PaymentModal
          run={run}
          onClose={() => setPaying(false)}
          onSaved={() => {
            setPaying(false);
            onToast(t("Payment recorded."));
            void load();
          }}
        />
      ) : null}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <article className="rounded-card border border-line bg-white p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-charcoal/45">{label}</p>
      <p className="mt-1 text-lg font-semibold tabular-nums">{value}</p>
    </article>
  );
}

const cents = (value: string) => (value.trim() ? (toCents(value) ?? 0) : 0);
const amount = (value: number | undefined) => (value ? (value / 100).toFixed(2) : "");

function EmployeeModal({ employee, onClose, onSaved }: { employee: Employee; onClose: () => void; onSaved: (people: Employee[]) => void }) {
  const { t } = useLocale();
  const [person, setPerson] = useState(employee);
  const profile = person.profile;
  const [jobTitle, setJobTitle] = useState(profile?.job_title ?? "");
  const [nationality, setNationality] = useState(profile?.nationality ?? "");
  const [phone, setPhone] = useState(profile?.phone ?? "");
  const [joined, setJoined] = useState(profile?.joined_on ?? "");
  const [birth, setBirth] = useState(profile?.date_of_birth ?? "");
  const [employmentType, setEmploymentType] = useState(profile?.employment_type ?? "");
  const [emiratesId, setEmiratesId] = useState(profile?.emirates_id ?? "");
  const [passport, setPassport] = useState(profile?.passport_number ?? "");
  const [labour, setLabour] = useState("");
  const [routing, setRouting] = useState("");
  const [iban, setIban] = useState("");
  const [bankName, setBankName] = useState(profile?.bank_name ?? "");
  const [holder, setHolder] = useState("");
  const [basic, setBasic] = useState(amount(profile?.basic_salary_cents));
  const [housing, setHousing] = useState(amount(profile?.housing_allowance_cents));
  const [transport, setTransport] = useState(amount(profile?.transport_allowance_cents));
  const [food, setFood] = useState(amount(profile?.food_allowance_cents));
  const [other, setOther] = useState(amount(profile?.other_allowance_cents));
  const [variable, setVariable] = useState(amount(profile?.variable_allowance_cents));
  const [recurring, setRecurring] = useState(amount(profile?.recurring_deduction_cents));
  const [overtime, setOvertime] = useState(String(profile?.overtime_rate_pct ?? 125));
  const [overtimeEligible, setOvertimeEligible] = useState(profile?.overtime_eligible ?? true);
  const [commissionEligible, setCommissionEligible] = useState(profile?.commission_eligible ?? true);
  const [effective, setEffective] = useState(profile?.effective_from ?? "");
  const [active, setActive] = useState(profile?.is_active ?? true);
  const [extras, setExtras] = useState<{ name: string; kind: "ALLOWANCE" | "DEDUCTION"; amount: string; taxable: boolean }[]>(
    () =>
      (profile?.components ?? [])
        .filter((row) => !["HOUSING", "TRANSPORT", "FOOD", "OTHER", "VARIABLE", "RECURRING"].includes(row.code))
        .map((row) => ({ name: row.name, kind: row.kind, amount: amount(row.amount_cents), taxable: row.taxable })),
  );
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [detailsReady, setDetailsReady] = useState(!employee.profile);

  useEffect(() => {
    void apiGet<Employee>(`/api/v1/staff/employees/${employee.user_id}`)
      .then((detail) => {
        setPerson(detail);
        const next = detail.profile;
        if (!next || next.iban_masked) return;
        setLabour(next.labour_id);
        setRouting(next.bank_routing_code);
        setIban(next.iban || "AE");
        setHolder(next.account_holder);
        setBankName(next.bank_name);
        setEmiratesId(next.emirates_id);
        setPassport(next.passport_number);
      })
      .catch(() => undefined)
      .finally(() => setDetailsReady(true));
  }, [employee.user_id]);

  const save = async (status: "DRAFT" | "ACTIVE") => {
    const nextErrors: Record<string, string> = {};
    if (status === "ACTIVE") {
      if (!/^\d{14}$/.test(labour)) nextErrors.labour = t("Enter the 14-digit MOHRE personal number.");
      if (!/^\d{9}$/.test(routing)) nextErrors.routing = t("Enter the 9-digit bank routing code.");
      if (!/^AE\d{21}$/.test(iban.replace(/\s/g, "").toUpperCase())) nextErrors.iban = t("Enter a UAE IBAN: AE followed by 21 digits.");
    }
    setFieldErrors(nextErrors);
    if (Object.keys(nextErrors).length) return;
    const components: SalaryComponent[] = extras
      .filter((row) => row.name.trim())
      .map((row, index) => ({
        name: row.name.trim(),
        kind: row.kind,
        code: `EXTRA_${index + 1}`,
        amount_cents: cents(row.amount),
        taxable: row.taxable,
        active: true,
      }));
    const body: Omit<EmployeeProfile, "employee_code" | "iban_masked"> = {
      job_title: jobTitle.trim(),
      nationality: nationality.trim(),
      phone: phone.trim(),
      joined_on: joined || null,
      date_of_birth: birth || null,
      employment_type: employmentType.trim(),
      emirates_id: emiratesId.replace(/\D/g, ""),
      passport_number: passport.trim(),
      labour_id: labour.trim(),
      bank_name: bankName.trim(),
      account_holder: holder.trim(),
      bank_routing_code: routing.trim(),
      iban: status === "DRAFT" && iban.trim() === "AE" ? "" : iban.replace(/\s/g, "").toUpperCase(),
      basic_salary_cents: cents(basic),
      housing_allowance_cents: cents(housing),
      transport_allowance_cents: cents(transport),
      food_allowance_cents: cents(food),
      other_allowance_cents: cents(other),
      variable_allowance_cents: cents(variable),
      recurring_deduction_cents: cents(recurring),
      components,
      overtime_rate_pct: Number(overtime) || 125,
      overtime_eligible: overtimeEligible,
      commission_eligible: commissionEligible,
      salary_frequency: "MONTHLY",
      profile_status: status,
      effective_from: effective || null,
      is_active: status === "ACTIVE" && active,
    };
    try {
      onSaved(await apiPut<Employee[]>(`/api/v1/staff/employees/${employee.user_id}`, body));
    } catch (caught) {
      setError(errorMessage(caught, "Could not save the payroll details."));
    }
  };

  return (
    <Modal
      title={t("{name} · payroll", { name: person.name })}
      subtitle={t("The employee code stays with this person. A new effective date keeps the previous salary for approved payrolls.")}
      width="lg"
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>{t("Cancel")}</GhostButton>
          <GhostButton onClick={() => void save("DRAFT")} disabled={!detailsReady}>{t("Save draft")}</GhostButton>
          <PrimaryButton onClick={() => void save("ACTIVE")} disabled={!detailsReady}>{t("Activate salary profile")}</PrimaryButton>
        </>
      }
    >
      <div className="grid gap-4 md:grid-cols-2">
        <section className="md:col-span-2 rounded-2xl bg-surface p-3 text-sm">
          <p className="text-xs font-semibold uppercase tracking-wide text-charcoal/45">{t("Employee information")}</p>
          <p className="mt-2 font-medium">{person.name}</p>
          <p className="text-charcoal/70">{profile?.employee_code ?? t("Assigned when you save")}</p>
          <p className="text-charcoal/70">{[person.store_name, person.role_name, person.employment_status === "ACTIVE" ? t("Active") : t("Inactive")].filter(Boolean).join(" · ")}</p>
          {profile?.joined_on ? <p className="text-charcoal/70">{t("Joined {date}", { date: formatDate(profile.joined_on) })}</p> : null}
        </section>
        <TextField label={t("Job title")} value={jobTitle} maxLength={80} onChange={(event) => setJobTitle(event.target.value)} />
        <TextField label={t("Employment type")} value={employmentType} maxLength={24} onChange={(event) => setEmploymentType(event.target.value)} />
        <TextField label={t("Nationality")} value={nationality} maxLength={60} onChange={(event) => setNationality(event.target.value)} />
        <TextField label={t("Phone")} value={phone} maxLength={20} onChange={(event) => setPhone(event.target.value)} />
        <TextField label={t("Date of birth")} type="date" value={birth} onChange={(event) => setBirth(event.target.value)} />
        <TextField label={t("Date joined")} type="date" value={joined} onChange={(event) => setJoined(event.target.value)} />
        <TextField label={t("Emirates ID")} value={emiratesId} maxLength={18} inputMode="numeric" onChange={(event) => setEmiratesId(event.target.value)} />
        <TextField label={t("Passport number")} value={passport} maxLength={20} onChange={(event) => setPassport(event.target.value.toUpperCase())} />
        <p className="md:col-span-2 text-xs font-semibold uppercase tracking-wide text-charcoal/45">{t("Salary structure")}</p>
        <TextField label={t("Basic salary")} inputMode="decimal" value={basic} onChange={(event) => setBasic(event.target.value)} />
        <TextField label={t("Housing allowance")} inputMode="decimal" value={housing} onChange={(event) => setHousing(event.target.value)} />
        <TextField label={t("Transport allowance")} inputMode="decimal" value={transport} onChange={(event) => setTransport(event.target.value)} />
        <TextField label={t("Food allowance")} inputMode="decimal" value={food} onChange={(event) => setFood(event.target.value)} />
        <TextField label={t("Other fixed allowances")} inputMode="decimal" value={other} onChange={(event) => setOther(event.target.value)} />
        <TextField label={t("Variable allowances")} inputMode="decimal" value={variable} onChange={(event) => setVariable(event.target.value)} />
        <TextField label={t("Recurring deductions")} inputMode="decimal" value={recurring} onChange={(event) => setRecurring(event.target.value)} />
        <TextField label={t("Overtime rate")} inputMode="numeric" value={overtime} onChange={(event) => setOvertime(event.target.value.replace(/\D/g, ""))} />
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={overtimeEligible} onChange={(event) => setOvertimeEligible(event.target.checked)} />
          {t("Eligible for approved overtime")}
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={commissionEligible} onChange={(event) => setCommissionEligible(event.target.checked)} />
          {t("Eligible for commission")}
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} />
          {t("Salary profile active")}
        </label>
        <TextField label={t("Effective date")} type="date" value={effective} onChange={(event) => setEffective(event.target.value)} />
        <div className="md:col-span-2 space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-wide text-charcoal/45">{t("Other components")}</p>
            <GhostButton onClick={() => setExtras([...extras, { name: "", kind: "ALLOWANCE", amount: "", taxable: false }])}>{t("Add component")}</GhostButton>
          </div>
          {extras.map((row, index) => (
            <div key={index} className="grid gap-2 md:grid-cols-[1fr_8rem_8rem_auto]">
              <TextField label={t("Component name")} value={row.name} onChange={(event) => setExtras(extras.map((item, itemIndex) => (itemIndex === index ? { ...item, name: event.target.value } : item)))} />
              <FilterSelect label={t("Type")} value={row.kind} options={[{ value: "ALLOWANCE", label: t("Allowance") }, { value: "DEDUCTION", label: t("Deduction") }]} onChange={(kind) => setExtras(extras.map((item, itemIndex) => (itemIndex === index ? { ...item, kind } : item)))} />
              <TextField label={t("Amount")} inputMode="decimal" value={row.amount} onChange={(event) => setExtras(extras.map((item, itemIndex) => (itemIndex === index ? { ...item, amount: event.target.value } : item)))} />
              <label className="mt-7 flex items-center gap-2 text-sm">
                <input type="checkbox" checked={row.taxable} onChange={(event) => setExtras(extras.map((item, itemIndex) => (itemIndex === index ? { ...item, taxable: event.target.checked } : item)))} />
                {t("Taxable")}
              </label>
            </div>
          ))}
        </div>
        <p className="md:col-span-2 text-xs font-semibold uppercase tracking-wide text-charcoal/45">{t("Bank and WPS")}</p>
        <TextField label={t("Bank name")} value={bankName} maxLength={80} onChange={(event) => setBankName(event.target.value)} />
        <TextField label={t("Account holder")} value={holder} maxLength={80} onChange={(event) => setHolder(event.target.value)} />
        <TextField label={t("MOHRE personal number")} value={labour} maxLength={14} error={fieldErrors.labour} onChange={(event) => setLabour(event.target.value.replace(/\D/g, ""))} />
        <TextField label={t("Employee bank routing code")} value={routing} maxLength={9} error={fieldErrors.routing} onChange={(event) => setRouting(event.target.value.replace(/\D/g, ""))} />
        <TextField label={t("IBAN")} value={iban} maxLength={27} error={fieldErrors.iban} onChange={(event) => setIban(event.target.value.toUpperCase())} />
        {person.salary_history.length ? (
          <div className="md:col-span-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-charcoal/45">{t("Salary history")}</p>
            <ul className="mt-2 space-y-1 text-sm">
              {person.salary_history.map((row) => (
                <li key={row.id}>
                  {formatDate(row.effective_from)}
                  {row.effective_to ? ` – ${formatDate(row.effective_to)}` : ""} · {row.status}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}

function LineModal({
  run,
  line,
  canEdit,
  canDownload,
  onDownload,
  onClose,
  onSaved,
}: {
  run: PayrollRun;
  line: PayrollLine;
  canEdit: boolean;
  canDownload: boolean;
  onDownload: () => void;
  onClose: () => void;
  onSaved: (run: PayrollRun) => void;
}) {
  const { t } = useLocale();
  const { currency } = useCurrency();
  const money = (value: number) => formatMoney(value, currency);
  const [bonus, setBonus] = useState(amount(line.bonus_cents));
  const [deductions, setDeductions] = useState(amount(line.deductions_cents));
  const [leave, setLeave] = useState(String(line.unpaid_leave_days || ""));
  const [note, setNote] = useState(line.note);
  const [error, setError] = useState<string | null>(null);
  const save = async () => {
    try {
      onSaved(
        await apiPut<PayrollRun>(`/api/v1/staff/payroll/runs/${run.id}/lines/${line.id}`, {
          bonus_cents: cents(bonus),
          deductions_cents: cents(deductions),
          unpaid_leave_days: Number(leave) || 0,
          note: note.trim(),
        }),
      );
    } catch (caught) {
      setError(errorMessage(caught, "Could not update the line."));
    }
  };
  return (
    <Modal
      title={`${line.name} · ${monthName(run.year, run.month)}`}
      subtitle={line.formula || t("Gross earnings = basic salary + allowances + overtime + commission + other earnings.")}
      width="lg"
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>{t("Cancel")}</GhostButton>
          {canDownload ? <GhostButton onClick={onDownload}>{t("Payslip")}</GhostButton> : null}
          {canEdit ? <PrimaryButton onClick={() => void save()}>{t("Save")}</PrimaryButton> : null}
        </>
      }
    >
      <ul className="space-y-1 text-sm">
        {line.components.map((row) => (
          <li key={`${row.kind}-${row.name}`} className="flex justify-between gap-3">
            <span>
              {row.name}
              {row.source ? <span className="block text-xs text-charcoal/50">{row.source}</span> : null}
            </span>
            <span className="tabular-nums">{money(row.cents)}</span>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-sm">{t("Gross")} {money(line.gross_cents)} · {t("Net payable")} {money(line.net_cents)}</p>
      {line.overtime_minutes ? <p className="text-xs text-charcoal/50">{hours(line.overtime_minutes)}</p> : null}
      {canEdit ? (
        <div className="mt-4 grid gap-4 md:grid-cols-3">
          <TextField label={t("Bonus")} inputMode="decimal" value={bonus} onChange={(event) => setBonus(event.target.value)} />
          <TextField label={t("Other deductions")} inputMode="decimal" value={deductions} onChange={(event) => setDeductions(event.target.value)} />
          <TextField label={t("Unpaid leave days")} inputMode="numeric" value={leave} onChange={(event) => setLeave(event.target.value.replace(/\D/g, ""))} />
          <div className="md:col-span-3">
            <TextField label={t("Note")} value={note} maxLength={255} onChange={(event) => setNote(event.target.value)} />
          </div>
        </div>
      ) : null}
      <ErrorNote message={error} />
    </Modal>
  );
}

function PaymentModal({ run, onClose, onSaved }: { run: PayrollRun; onClose: () => void; onSaved: () => void }) {
  const { t } = useLocale();
  const [amountValue, setAmountValue] = useState(amount(run.total_net_cents));
  const [reference, setReference] = useState("");
  const [status, setStatus] = useState<PayrollPaymentStatus>("PAID");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const save = async () => {
    try {
      await apiPost<PayrollPayment[]>(`/api/v1/staff/payroll/runs/${run.id}/payments`, {
        amount_cents: cents(amountValue),
        reference: reference.trim(),
        status,
        note: note.trim(),
      });
      onSaved();
    } catch (caught) {
      setError(errorMessage(caught, "Could not record the payment."));
    }
  };
  return (
    <Modal
      title={t("Record payment")}
      subtitle={t("Generating a WPS file does not mark this payroll paid. Record the bank result here.")}
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>{t("Cancel")}</GhostButton>
          <PrimaryButton onClick={() => void save()}>{t("Save")}</PrimaryButton>
        </>
      }
    >
      <div className="grid gap-4 md:grid-cols-2">
        <TextField label={t("Amount")} inputMode="decimal" value={amountValue} onChange={(event) => setAmountValue(event.target.value)} />
        <TextField label={t("Bank reference")} value={reference} maxLength={40} onChange={(event) => setReference(event.target.value)} />
        <FilterSelect
          label={t("Payment status")}
          value={status}
          options={[
            { value: "SUBMITTED", label: t("Submitted to the bank") },
            { value: "PROCESSING", label: t("Bank processing") },
            { value: "PAID", label: t("Paid") },
            { value: "PARTIALLY_PAID", label: t("Partially paid") },
            { value: "REJECTED", label: t("Rejected by the bank") },
            { value: "FAILED", label: t("Payment failed") },
          ]}
          onChange={(value) => setStatus(value)}
        />
        <TextField label={t("Note")} value={note} maxLength={255} onChange={(event) => setNote(event.target.value)} />
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}
