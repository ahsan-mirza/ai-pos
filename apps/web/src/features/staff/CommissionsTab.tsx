import { formatMoney, type CommissionBasis, type CommissionReport, type CommissionRule, type Role } from "@ai-pos/shared-types";
import { Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { ErrorNote, FilterSelect, GhostButton, PrimaryButton, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { Toggle } from "../../components/ui/Toggle";
import { apiGet, apiPost, apiPut } from "../../lib/api";
import { useCurrency } from "../../lib/currency";
import { toCents } from "../customers/api";
import { useCategories } from "../inventory/shared";
import { errorMessage, rolesApi } from "../users/api";

const iso = (value: Date) => value.toISOString().slice(0, 10);
const monthStart = () => {
  const now = new Date();
  return iso(new Date(Date.UTC(now.getFullYear(), now.getMonth(), 1)));
};

export function CommissionsTab({ onToast }: { onToast: (text: string) => void }) {
  const { currency } = useCurrency();
  const { categories } = useCategories();
  const [roles, setRoles] = useState<Role[]>([]);
  const [rules, setRules] = useState<CommissionRule[]>([]);
  const [report, setReport] = useState<CommissionReport | null>(null);
  const [from, setFrom] = useState(monthStart());
  const [to, setTo] = useState(iso(new Date()));
  const [editing, setEditing] = useState<CommissionRule | "new" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const money = (cents: number) => formatMoney(cents, currency);

  const load = useCallback(async () => {
    try {
      const [nextRules, nextReport] = await Promise.all([
        apiGet<CommissionRule[]>("/api/v1/staff/commission-rules"),
        apiGet<CommissionReport>(`/api/v1/staff/commissions?from=${from}&to=${to}`),
      ]);
      setRules(nextRules);
      setReport(nextReport);
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "Could not load commissions."));
    }
  }, [from, to]);

  useEffect(() => {
    void load();
    rolesApi
      .list()
      .then(setRoles)
      .catch(() => setRoles([]));
  }, [load]);

  const scope = (rule: CommissionRule) => {
    const names = [
      rule.category_ids.length ? categories.filter((row) => rule.category_ids.includes(row.id)).map((row) => row.name).join(", ") : "All products",
      rule.role_ids.length ? roles.filter((row) => rule.role_ids.includes(row.id)).map((row) => row.name).join(", ") : "everyone",
    ];
    return `${names[0]} · ${names[1]}`;
  };

  return (
    <div className="space-y-4">
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <article className="rounded-card border border-line bg-white p-6">
          <div className="mb-4 flex items-start justify-between gap-3">
            <div>
              <h2 className="text-xl font-semibold">Commission rules</h2>
              <p className="text-sm text-charcoal/60">Each sale line earns under its most specific rule; returns take it back.</p>
            </div>
            <PrimaryButton onClick={() => setEditing("new")}>
              <Plus size={16} aria-hidden="true" className="-ml-1 mr-1.5" /> New rule
            </PrimaryButton>
          </div>
          <ul className="space-y-2">
            {rules.map((rule) => (
              <li key={rule.id}>
                <button
                  type="button"
                  onClick={() => setEditing(rule)}
                  className={`flex w-full items-center justify-between gap-3 rounded-2xl bg-surface p-3 text-left hover:ring-1 hover:ring-accent/40 ${rule.is_active ? "" : "opacity-50"}`}
                >
                  <span className="min-w-0">
                    <span className="block font-semibold">{rule.name}</span>
                    <span className="block truncate text-xs text-charcoal/60">
                      {scope(rule)}
                      {rule.threshold_cents ? ` · after ${money(rule.threshold_cents)}` : ""}
                    </span>
                  </span>
                  <span className="shrink-0 text-right">
                    <span className="block text-lg font-semibold tabular-nums">{(rule.rate_bps / 100).toFixed(2)}%</span>
                    <span className="block text-[11px] text-charcoal/50">of {rule.basis === "NET_SALES" ? "net sales" : "gross profit"}</span>
                  </span>
                </button>
              </li>
            ))}
            {rules.length === 0 ? <li className="rounded-2xl border border-dashed border-line p-6 text-center text-sm text-charcoal/60">No commission rules yet.</li> : null}
          </ul>
        </article>

        <article className="rounded-card border border-line bg-white p-6">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-xl font-semibold">Earned</h2>
              <p className="text-sm text-charcoal/60">{report ? `${money(report.total_cents)} in total` : ""}</p>
            </div>
            <div className="flex gap-3">
              <TextField label="From" type="date" value={from} onChange={(event) => setFrom(event.target.value)} />
              <TextField label="To" type="date" value={to} onChange={(event) => setTo(event.target.value)} />
            </div>
          </div>
          <ErrorNote message={error} />
          <table className="w-full text-left text-sm">
            <tbody>
              {(report?.staff ?? []).map((person) => (
                <tr key={person.user_id} className="border-t border-line first:border-t-0 align-top">
                  <td className="py-2.5">
                    <span className="block font-medium">{person.name}</span>
                    <span className="block text-xs text-charcoal/50">
                      {person.by_rule.map((row) => `${row.rule_name}: ${money(row.basis_cents)}`).join(" · ")}
                    </span>
                  </td>
                  <td className="py-2.5 text-right text-lg font-semibold tabular-nums">{money(person.commission_cents)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {report && report.staff.length === 0 ? <p className="py-6 text-sm text-charcoal/60">No commission earned in this period.</p> : null}
        </article>
      </div>
      {editing ? (
        <RuleModal
          rule={editing === "new" ? null : editing}
          roles={roles}
          categories={categories}
          onClose={() => setEditing(null)}
          onSaved={(saved) => {
            setEditing(null);
            onToast(`${saved.name} saved.`);
            void load();
          }}
        />
      ) : null}
    </div>
  );
}

function RuleModal({
  rule,
  roles,
  categories,
  onClose,
  onSaved,
}: {
  rule: CommissionRule | null;
  roles: Role[];
  categories: { id: string; name: string }[];
  onClose: () => void;
  onSaved: (rule: CommissionRule) => void;
}) {
  const [name, setName] = useState(rule?.name ?? "");
  const [basis, setBasis] = useState<CommissionBasis>(rule?.basis ?? "NET_SALES");
  const [rate, setRate] = useState(rule ? String(rule.rate_bps / 100) : "1");
  const [categoryId, setCategoryId] = useState(rule?.category_ids[0] ?? "");
  const [roleId, setRoleId] = useState(rule?.role_ids[0] ?? "");
  const [threshold, setThreshold] = useState(rule?.threshold_cents ? (rule.threshold_cents / 100).toFixed(2) : "");
  const [active, setActive] = useState(rule?.is_active ?? true);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    const body = {
      name: name.trim(),
      basis,
      rate_bps: Math.round(Number(rate) * 100),
      category_ids: categoryId ? [categoryId] : [],
      role_ids: roleId ? [roleId] : [],
      threshold_cents: threshold ? (toCents(threshold) ?? 0) : 0,
      is_active: active,
    };
    try {
      onSaved(rule ? await apiPut<CommissionRule>(`/api/v1/staff/commission-rules/${rule.id}`, body) : await apiPost<CommissionRule>("/api/v1/staff/commission-rules", body));
    } catch (caught) {
      setError(errorMessage(caught, "Could not save the rule."));
    }
  };

  return (
    <Modal
      title={rule ? `Edit ${rule.name}` : "New commission rule"}
      subtitle="A category or role rule wins over a general one for the same sale line."
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton onClick={() => void save()}>Save rule</PrimaryButton>
        </>
      }
    >
      <div className="space-y-4">
        <TextField label="Name" value={name} maxLength={80} placeholder="Phones 2%" onChange={(event) => setName(event.target.value)} />
        <SegmentedControl
          label="Paid on"
          value={basis}
          options={[
            { value: "NET_SALES", label: "Net sales" },
            { value: "GROSS_PROFIT", label: "Gross profit" },
          ]}
          onChange={setBasis}
        />
        <div className="grid gap-4 md:grid-cols-2">
          <TextField label="Rate (%)" inputMode="decimal" value={rate} onChange={(event) => setRate(event.target.value)} />
          <TextField label="Only above (per person, per period)" inputMode="decimal" value={threshold} placeholder="0.00" onChange={(event) => setThreshold(event.target.value)} />
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <FilterSelect
            label="Category"
            value={categoryId}
            options={[{ value: "", label: "All products" }, ...categories.map((row) => ({ value: row.id, label: row.name }))]}
            onChange={setCategoryId}
          />
          <FilterSelect
            label="Role"
            value={roleId}
            options={[{ value: "", label: "Everyone" }, ...roles.map((row) => ({ value: row.id, label: row.name }))]}
            onChange={setRoleId}
          />
        </div>
        <Toggle checked={active} onChange={setActive} label="Rule on" />
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}
