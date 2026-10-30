import { Permission, type UnitOfMeasure } from "@ai-pos/shared-types";
import { Package, Plus, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useConfirm } from "../../components/ui/ConfirmDialog";
import { ErrorNote, PrimaryButton, TextField } from "../../components/ui/Field";
import { useAuth } from "../../lib/auth";
import { errorMessage } from "../users/api";
import { unitsApi, useUnits } from "./units";

/** Packs products are sold in (piece, box of 10, carton of 100, and the business's own such as a case of 24). */
export function UnitsPage() {
  const { can } = useAuth();
  const canEdit = can(Permission.PortalInventoryManage);
  const { units, error, reload } = useUnits();
  const [form, setForm] = useState({ code: "", name: "", short_name: "", factor: "" });
  const [busy, setBusy] = useState(false);
  const confirm = useConfirm();
  const [failure, setFailure] = useState<string | null>(null);

  const create = async (event: FormEvent) => {
    event.preventDefault();
    const factor = Number(form.factor);
    if (!Number.isInteger(factor) || factor < 2) {
      setFailure("A pack holds at least 2 pieces.");
      return;
    }
    setBusy(true);
    setFailure(null);
    try {
      await unitsApi.create({ code: form.code, name: form.name, short_name: form.short_name || form.name, factor });
      setForm({ code: "", name: "", short_name: "", factor: "" });
      await reload();
    } catch (caught) {
      setFailure(errorMessage(caught, "Could not add the unit."));
    } finally {
      setBusy(false);
    }
  };

  const act = async (work: () => Promise<unknown>, fallback: string) => {
    setFailure(null);
    try {
      await work();
      await reload();
    } catch (caught) {
      setFailure(errorMessage(caught, fallback));
    }
  };

  const toggle = (unit: UnitOfMeasure) =>
    void act(() => unitsApi.update(unit.id ?? "", { is_active: !unit.is_active }), "Could not change the unit.");
  const remove = (unit: UnitOfMeasure) => {
    void (async () => {
      const accepted = await confirm({
        title: "Delete unit",
        message: `Delete ${unit.name}?`,
        confirmLabel: "Delete",
        tone: "danger",
      });
      if (!accepted) return;
      void act(() => unitsApi.remove(unit.id ?? ""), "Could not delete the unit.");
    })();
  };

  return (
    <section className="space-y-4">
      <div className="rounded-card border border-line bg-white p-6">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-accent text-white">
            <Package size={20} aria-hidden="true" />
          </span>
          <div>
            <h2 className="text-2xl font-semibold">Units of measure</h2>
            <p className="text-sm text-charcoal/60">
              Packs a product can be sold in. Stock always counts pieces (or grams for weighed goods); a pack is a whole
              number of pieces. Choose which packs each product sells in on the product form.
            </p>
          </div>
        </div>
        <ErrorNote message={error ?? failure} />
      </div>

      <article className="overflow-x-auto rounded-card border border-line bg-white p-5">
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-charcoal/50">
            <tr>
              <th className="pb-2 font-medium">Unit</th>
              <th className="pb-2 font-medium">Code</th>
              <th className="pb-2 text-right font-medium">Pieces</th>
              <th className="pb-2 text-right font-medium">Products</th>
              <th className="pb-2" />
            </tr>
          </thead>
          <tbody>
            {units.map((unit) => (
              <tr key={unit.code} className={`border-t border-line ${unit.is_active ? "" : "text-charcoal/40"}`}>
                <td className="py-2.5">
                  <span className="font-medium">{unit.name}</span>
                  <span className="ml-2 rounded-full bg-surface px-2 py-0.5 text-[11px] font-semibold">{unit.short_name}</span>
                  {unit.is_system ? <span className="ml-2 text-[11px] text-charcoal/50">built in</span> : null}
                  {!unit.is_active ? <span className="ml-2 text-[11px]">switched off</span> : null}
                </td>
                <td className="py-2.5 font-mono text-xs">{unit.code}</td>
                <td className="py-2.5 text-right tabular-nums">{unit.factor}</td>
                <td className="py-2.5 text-right tabular-nums">{unit.products}</td>
                <td className="py-2.5 pl-4 text-right">
                  {canEdit && !unit.is_system ? (
                    <span className="inline-flex items-center gap-3">
                      <button type="button" onClick={() => toggle(unit)} className="text-xs font-semibold text-accent hover:underline">
                        {unit.is_active ? "Switch off" : "Switch on"}
                      </button>
                      <button
                        type="button"
                        aria-label={`Delete ${unit.name}`}
                        onClick={() => remove(unit)}
                        className="text-charcoal/50 hover:text-red-600"
                      >
                        <Trash2 size={15} aria-hidden="true" />
                      </button>
                    </span>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </article>

      {canEdit ? (
        <form onSubmit={(event) => void create(event)} className="rounded-card border border-line bg-white p-5">
          <h3 className="text-base font-semibold">Add a unit</h3>
          <div className="mt-3 grid gap-3 sm:grid-cols-4">
            <TextField
              label="Code"
              placeholder="CASE_24"
              value={form.code}
              required
              onChange={(event) => setForm({ ...form, code: event.target.value })}
            />
            <TextField
              label="Name"
              placeholder="Case of 24"
              value={form.name}
              required
              onChange={(event) => setForm({ ...form, name: event.target.value })}
            />
            <TextField
              label="Short name"
              placeholder="Case"
              value={form.short_name}
              onChange={(event) => setForm({ ...form, short_name: event.target.value })}
            />
            <TextField
              label="Pieces per unit"
              inputMode="numeric"
              placeholder="24"
              value={form.factor}
              required
              onChange={(event) => setForm({ ...form, factor: event.target.value.replace(/\D/g, "") })}
            />
          </div>
          <p className="mt-2 text-xs text-charcoal/60">The piece count is fixed once the unit exists; add a new unit to change it.</p>
          <div className="mt-4">
            <PrimaryButton type="submit" disabled={busy}>
              <Plus size={15} aria-hidden="true" /> {busy ? "Adding…" : "Add unit"}
            </PrimaryButton>
          </div>
        </form>
      ) : null}
    </section>
  );
}
