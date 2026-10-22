import { formatMoney, type Employee, type EmployeeProfile, type PayrollLine, type PayrollRun, type PayrollSettings } from "@ai-pos/shared-types";
import { Download, Lock, Play, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { ErrorNote, GhostButton, PrimaryButton, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { apiBlob, apiGet, apiPost, apiPut } from "../../lib/api";
import { useCurrency } from "../../lib/currency";
import { toCents } from "../customers/api";
import { errorMessage } from "../users/api";
import { hours } from "./TimesheetsTab";

const monthName = (run: Pick<PayrollRun, "year" | "month">) =>
  new Date(run.year, run.month - 1, 1).toLocaleDateString(undefined, { month: "long", year: "numeric" });

export function PayrollTab({ onToast }: { onToast: (text: string) => void }) {
  const { currency } = useCurrency();
  const [employer, setEmployer] = useState<PayrollSettings>({ employer_id: "", bank_routing_code: "" });
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [runs, setRuns] = useState<PayrollRun[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [editingEmployee, setEditingEmployee] = useState<Employee | null>(null);
  const [editingLine, setEditingLine] = useState<PayrollLine | null>(null);
  const [error, setError] = useState<string | null>(null);
  const money = (cents: number) => formatMoney(cents, currency);

  const load = useCallback(async () => {
    try {
      const [settings, people, history] = await Promise.all([
        apiGet<PayrollSettings | null>("/api/v1/staff/payroll/settings"),
        apiGet<Employee[]>("/api/v1/staff/employees"),
        apiGet<PayrollRun[]>("/api/v1/staff/payroll/runs"),
      ]);
      if (settings) setEmployer(settings);
      setEmployees(people);
      setRuns(history);
      setSelected((current) => current ?? history[0]?.id ?? null);
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "Could not load payroll."));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const run = runs.find((row) => row.id === selected) ?? null;
  const replace = (next: PayrollRun) => setRuns((current) => current.map((row) => (row.id === next.id ? next : row)));

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
    const now = new Date();
    void act(
      () => apiPost<PayrollRun>("/api/v1/staff/payroll/runs", { year: now.getFullYear(), month: now.getMonth() + 1 }),
      `Payroll for ${monthName({ year: now.getFullYear(), month: now.getMonth() + 1 })} drafted.`,
    );
  };

  const download = async () => {
    if (!run) return;
    try {
      const blob = await apiBlob(`/api/v1/staff/payroll/runs/${run.id}/wps.sif`);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${employer.employer_id}-${run.year}${String(run.month).padStart(2, "0")}.SIF`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (caught) {
      setError(errorMessage(caught, "Could not build the WPS file."));
    }
  };

  const saveEmployer = async () => {
    try {
      setEmployer(await apiPut<PayrollSettings>("/api/v1/staff/payroll/settings", employer));
      onToast("WPS employer details saved.");
    } catch (caught) {
      setError(errorMessage(caught, "Could not save the employer details."));
    }
  };

  return (
    <div className="space-y-4">
      <ErrorNote message={error} />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <article className="rounded-card border border-line bg-white p-6">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-xl font-semibold">{run ? `Payroll · ${monthName(run)}` : "Payroll"}</h2>
              <p className="text-sm text-charcoal/60">
                Basic and allowances from each profile, overtime from approved timesheets, commission from the rules.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {run?.status === "DRAFT" ? (
                <>
                  <GhostButton onClick={() => void act(() => apiPost<PayrollRun>(`/api/v1/staff/payroll/runs/${run.id}/recalculate`, {}), "Payroll recalculated.")}>
                    <RefreshCw size={15} aria-hidden="true" className="-ml-1 mr-1.5" /> Recalculate
                  </GhostButton>
                  <PrimaryButton onClick={() => void act(() => apiPost<PayrollRun>(`/api/v1/staff/payroll/runs/${run.id}/finalize`, {}), "Payroll finalized and locked.")}>
                    <Lock size={15} aria-hidden="true" className="-ml-1 mr-1.5" /> Finalize
                  </PrimaryButton>
                </>
              ) : null}
              {run?.status === "FINALIZED" ? (
                <PrimaryButton onClick={() => void download()}>
                  <Download size={15} aria-hidden="true" className="-ml-1 mr-1.5" /> WPS file (SIF)
                </PrimaryButton>
              ) : null}
              <GhostButton onClick={startRun}>
                <Play size={15} aria-hidden="true" className="-ml-1 mr-1.5" /> Run this month
              </GhostButton>
            </div>
          </div>
          {runs.length > 1 ? (
            <div className="mb-4 flex flex-wrap gap-1.5">
              {runs.map((row) => (
                <button
                  key={row.id}
                  type="button"
                  onClick={() => setSelected(row.id)}
                  className={`rounded-full px-3 py-1 text-xs font-semibold ${row.id === selected ? "bg-charcoal text-white" : "bg-surface text-charcoal/70"}`}
                >
                  {monthName(row)}
                  {row.status === "DRAFT" ? " · draft" : ""}
                </button>
              ))}
            </div>
          ) : null}
          {run ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[820px] text-left text-sm">
                <thead className="text-xs uppercase tracking-wide text-charcoal/50">
                  <tr>
                    <th className="pb-2 font-medium">Employee</th>
                    <th className="pb-2 text-right font-medium">Basic + allowances</th>
                    <th className="pb-2 text-right font-medium">Overtime</th>
                    <th className="pb-2 text-right font-medium">Commission</th>
                    <th className="pb-2 text-right font-medium">Bonus</th>
                    <th className="pb-2 text-right font-medium">Deductions</th>
                    <th className="pb-2 text-right font-medium">Net pay</th>
                  </tr>
                </thead>
                <tbody>
                  {run.lines.map((line) => (
                    <tr
                      key={line.id}
                      onClick={() => run.status === "DRAFT" && setEditingLine(line)}
                      className={`border-t border-line align-top ${run.status === "DRAFT" ? "cursor-pointer hover:bg-surface/60" : ""}`}
                    >
                      <td className="py-2.5">
                        <span className="block font-medium">{line.name}</span>
                        <span className="block font-mono text-xs text-charcoal/50">{line.employee_code}</span>
                        {line.note ? <span className="block text-xs text-charcoal/60">{line.note}</span> : null}
                      </td>
                      <td className="py-2.5 text-right tabular-nums">{money(line.basic_cents + line.allowances_cents)}</td>
                      <td className="py-2.5 text-right tabular-nums">
                        {money(line.overtime_cents)}
                        {line.overtime_minutes ? <span className="block text-[11px] text-charcoal/50">{hours(line.overtime_minutes)}</span> : null}
                      </td>
                      <td className="py-2.5 text-right tabular-nums">{money(line.commission_cents)}</td>
                      <td className="py-2.5 text-right tabular-nums">{money(line.bonus_cents)}</td>
                      <td className="py-2.5 text-right tabular-nums">
                        {line.deductions_cents + line.leave_deduction_cents ? `(${money(line.deductions_cents + line.leave_deduction_cents)})` : "—"}
                        {line.unpaid_leave_days ? <span className="block text-[11px] text-charcoal/50">{line.unpaid_leave_days} unpaid day(s)</span> : null}
                      </td>
                      <td className="py-2.5 text-right font-semibold tabular-nums">{money(line.net_cents)}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t border-line">
                    <td className="pt-3 text-xs text-charcoal/60">{run.status === "DRAFT" ? "Click a line to add a bonus, deduction or unpaid leave." : `Finalized ${run.finalized_at ? new Date(run.finalized_at).toLocaleDateString() : ""}`}</td>
                    <td colSpan={5} />
                    <td className="pt-3 text-right text-lg font-semibold tabular-nums">{money(run.total_net_cents)}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          ) : (
            <p className="rounded-2xl border border-dashed border-line p-8 text-center text-sm text-charcoal/60">
              Add payroll details for your staff, then run this month's payroll.
            </p>
          )}
        </article>

        <div className="space-y-4">
          <article className="rounded-card bg-charcoal p-6 text-white">
            <h3 className="font-semibold">WPS employer</h3>
            <p className="text-xs text-white/60">From your MOHRE establishment card and your salary bank.</p>
            <div className="mt-3 space-y-2">
              <input
                aria-label="MOHRE establishment ID"
                value={employer.employer_id}
                maxLength={13}
                placeholder="Establishment ID (13 digits)"
                onChange={(event) => setEmployer({ ...employer, employer_id: event.target.value.replace(/\D/g, "") })}
                className="w-full rounded-xl bg-white/10 px-3 py-2 font-mono text-sm text-white placeholder:text-white/40 focus:outline-none focus:ring-2 focus:ring-accent"
              />
              <input
                aria-label="Employer bank routing code"
                value={employer.bank_routing_code}
                maxLength={9}
                placeholder="Bank routing code (9 digits)"
                onChange={(event) => setEmployer({ ...employer, bank_routing_code: event.target.value.replace(/\D/g, "") })}
                className="w-full rounded-xl bg-white/10 px-3 py-2 font-mono text-sm text-white placeholder:text-white/40 focus:outline-none focus:ring-2 focus:ring-accent"
              />
              <button type="button" onClick={() => void saveEmployer()} className="h-9 w-full rounded-full bg-accent text-sm font-semibold">
                Save
              </button>
            </div>
          </article>
          <article className="rounded-card border border-line bg-white p-6">
            <h3 className="font-semibold">Employees</h3>
            <ul className="mt-3 space-y-1.5">
              {employees.map((person) => (
                <li key={person.user_id}>
                  <button
                    type="button"
                    onClick={() => setEditingEmployee(person)}
                    className="flex w-full items-center justify-between gap-2 rounded-xl px-2 py-1.5 text-left text-sm hover:bg-surface"
                  >
                    <span className="min-w-0">
                      <span className="block truncate font-medium">{person.name}</span>
                      <span className="block text-xs text-charcoal/50">{person.role_name}</span>
                    </span>
                    <span className={`shrink-0 text-xs tabular-nums ${person.profile ? "" : "font-semibold text-accent"}`}>
                      {person.profile ? money(person.profile.basic_salary_cents) : "Add details"}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </article>
        </div>
      </div>
      {editingEmployee ? (
        <EmployeeModal
          employee={editingEmployee}
          onClose={() => setEditingEmployee(null)}
          onSaved={(people) => {
            setEmployees(people);
            setEditingEmployee(null);
            onToast("Payroll details saved.");
          }}
        />
      ) : null}
      {editingLine && run ? (
        <LineModal
          runId={run.id}
          line={editingLine}
          onClose={() => setEditingLine(null)}
          onSaved={(next) => {
            replace(next);
            setEditingLine(null);
            onToast(`${editingLine.name}'s pay updated.`);
          }}
        />
      ) : null}
    </div>
  );
}

const cents = (value: string) => (value.trim() ? (toCents(value) ?? 0) : 0);
const amount = (value: number | undefined) => (value ? (value / 100).toFixed(2) : "");

function EmployeeModal({ employee, onClose, onSaved }: { employee: Employee; onClose: () => void; onSaved: (people: Employee[]) => void }) {
  const profile = employee.profile;
  const [code, setCode] = useState(profile?.employee_code ?? "");
  const [labour, setLabour] = useState(profile?.labour_id ?? "");
  const [routing, setRouting] = useState(profile?.bank_routing_code ?? "");
  const [iban, setIban] = useState(profile?.iban ?? "AE");
  const [basic, setBasic] = useState(amount(profile?.basic_salary_cents));
  const [housing, setHousing] = useState(amount(profile?.housing_allowance_cents));
  const [transport, setTransport] = useState(amount(profile?.transport_allowance_cents));
  const [other, setOther] = useState(amount(profile?.other_allowance_cents));
  const [overtime, setOvertime] = useState(String(profile?.overtime_rate_pct ?? 125));
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    const body: EmployeeProfile = {
      employee_code: code.trim(),
      labour_id: labour.trim(),
      bank_routing_code: routing.trim(),
      iban: iban.replace(/\s/g, "").toUpperCase(),
      basic_salary_cents: cents(basic),
      housing_allowance_cents: cents(housing),
      transport_allowance_cents: cents(transport),
      other_allowance_cents: cents(other),
      overtime_rate_pct: Number(overtime) || 125,
      is_active: true,
    };
    try {
      onSaved(await apiPut<Employee[]>(`/api/v1/staff/employees/${employee.user_id}`, body));
    } catch (caught) {
      setError(errorMessage(caught, "Could not save the payroll details."));
    }
  };

  return (
    <Modal
      title={`${employee.name} · payroll`}
      subtitle="Monthly amounts. The labour ID, routing code and IBAN go into the WPS file."
      width="lg"
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton onClick={() => void save()}>Save</PrimaryButton>
        </>
      }
    >
      <div className="grid gap-4 md:grid-cols-2">
        <TextField label="Employee code" value={code} maxLength={20} onChange={(event) => setCode(event.target.value)} />
        <TextField label="MOHRE personal number (14 digits)" value={labour} maxLength={14} onChange={(event) => setLabour(event.target.value.replace(/\D/g, ""))} />
        <TextField label="Bank routing code (9 digits)" value={routing} maxLength={9} onChange={(event) => setRouting(event.target.value.replace(/\D/g, ""))} />
        <TextField label="IBAN" value={iban} maxLength={27} onChange={(event) => setIban(event.target.value.toUpperCase())} />
        <TextField label="Basic salary" inputMode="decimal" value={basic} onChange={(event) => setBasic(event.target.value)} />
        <TextField label="Housing allowance" inputMode="decimal" value={housing} onChange={(event) => setHousing(event.target.value)} />
        <TextField label="Transport allowance" inputMode="decimal" value={transport} onChange={(event) => setTransport(event.target.value)} />
        <TextField label="Other allowances" inputMode="decimal" value={other} onChange={(event) => setOther(event.target.value)} />
        <TextField label="Overtime rate (% of hourly basic)" inputMode="numeric" value={overtime} onChange={(event) => setOvertime(event.target.value.replace(/\D/g, ""))} />
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}

function LineModal({ runId, line, onClose, onSaved }: { runId: string; line: PayrollLine; onClose: () => void; onSaved: (run: PayrollRun) => void }) {
  const [bonus, setBonus] = useState(amount(line.bonus_cents));
  const [deductions, setDeductions] = useState(amount(line.deductions_cents));
  const [leave, setLeave] = useState(String(line.unpaid_leave_days || ""));
  const [note, setNote] = useState(line.note);
  const [error, setError] = useState<string | null>(null);
  const save = async () => {
    try {
      onSaved(
        await apiPut<PayrollRun>(`/api/v1/staff/payroll/runs/${runId}/lines/${line.id}`, {
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
      title={`${line.name} · this month`}
      subtitle="Unpaid leave deducts a thirtieth of basic and allowances per day."
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton onClick={() => void save()}>Save</PrimaryButton>
        </>
      }
    >
      <div className="grid gap-4 md:grid-cols-3">
        <TextField label="Bonus" inputMode="decimal" value={bonus} onChange={(event) => setBonus(event.target.value)} />
        <TextField label="Deductions" inputMode="decimal" value={deductions} onChange={(event) => setDeductions(event.target.value)} />
        <TextField label="Unpaid leave days" inputMode="numeric" value={leave} onChange={(event) => setLeave(event.target.value.replace(/\D/g, ""))} />
      </div>
      <div className="mt-4">
        <TextField label="Note" value={note} maxLength={255} placeholder="Salary advance recovery" onChange={(event) => setNote(event.target.value)} />
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}
