import { Permission, type PermissionGroup, type Role } from "@ai-pos/shared-types";
import { Lock, Plus, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useConfirm } from "../../components/ui/ConfirmDialog";
import { ErrorNote, GhostButton, PrimaryButton, TextField } from "../../components/ui/Field";
import { useAuth } from "../../lib/auth";
import { errorMessage, rolesApi } from "../users/api";

interface Draft {
  id: string | null;
  name: string;
  description: string;
  permissions: Set<Permission>;
  isSystem: boolean;
  /** Percent as typed; blank uses the till rules default. */
  discountLimit: string;
}

const emptyDraft = (): Draft => ({
  id: null,
  name: "",
  description: "",
  permissions: new Set(),
  isSystem: false,
  discountLimit: "",
});

function toDraft(role: Role): Draft {
  return {
    id: role.id,
    name: role.name,
    description: role.description,
    permissions: new Set(role.permissions),
    isSystem: role.is_system,
    discountLimit: role.max_discount_bps == null ? "" : String(role.max_discount_bps / 100),
  };
}

/** Typed percent to basis points: blank is null (till default), otherwise 0–100 with up to 2 decimals. */
function limitBps(value: string): number | null | undefined {
  const trimmed = value.trim();
  if (trimmed === "") return null;
  if (!/^\d+(\.\d{1,2})?$/.test(trimmed)) return undefined;
  const bps = Math.round(Number(trimmed) * 100);
  return bps <= 10_000 ? bps : undefined;
}

export function RolesPage() {
  const { can, user: actor, refreshUser } = useAuth();
  const [roles, setRoles] = useState<Role[]>([]);
  const [groups, setGroups] = useState<PermissionGroup[]>([]);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const confirm = useConfirm();
  const manage = can(Permission.RolesManage);

  const load = useCallback(async (selectId?: string) => {
    try {
      const [roleRows, groupRows] = await Promise.all([rolesApi.list(), rolesApi.permissions()]);
      setRoles(roleRows);
      setGroups(groupRows);
      const selected = roleRows.find((role) => role.id === selectId) ?? roleRows[0];
      if (selected) setDraft(toDraft(selected));
    } catch (caught) {
      setError(errorMessage(caught, "Could not load roles."));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const isSuperAdmin = draft.isSystem && draft.name === "Super Admin";
  const held = useMemo(() => new Set(actor?.permissions ?? []), [actor]);
  const locked = !manage || isSuperAdmin;

  const toggle = (permission: Permission) => {
    if (locked || !held.has(permission)) return;
    setDraft((current) => {
      const next = new Set(current.permissions);
      if (next.has(permission)) next.delete(permission);
      else next.add(permission);
      return { ...current, permissions: next };
    });
  };

  const toggleGroup = (group: PermissionGroup, on: boolean) => {
    if (locked) return;
    setDraft((current) => {
      const next = new Set(current.permissions);
      for (const item of group.permissions) {
        if (!held.has(item.key)) continue;
        if (on) next.add(item.key);
        else next.delete(item.key);
      }
      return { ...current, permissions: next };
    });
  };

  const save = async () => {
    if (draft.name.trim().length < 2) {
      setError("Role names need at least 2 characters.");
      return;
    }
    const maxDiscount = limitBps(draft.discountLimit);
    if (maxDiscount === undefined) {
      setError("Enter the discount limit as a percent from 0 to 100, or leave it blank.");
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const permissions = [...draft.permissions].sort();
      const role =
        draft.id === null
          ? await rolesApi.create({
              name: draft.name.trim(),
              description: draft.description.trim(),
              permissions,
              max_discount_bps: maxDiscount,
            })
          : await rolesApi.update(draft.id, {
              ...(draft.isSystem ? {} : { name: draft.name.trim() }),
              description: draft.description.trim(),
              ...(isSuperAdmin ? {} : { permissions, max_discount_bps: maxDiscount }),
            });
      setNotice(`${role.name} saved.`);
      await load(role.id);
      if (actor?.role.id === role.id) await refreshUser();
    } catch (caught) {
      setError(errorMessage(caught, "Could not save the role."));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (draft.id === null) return;
    const accepted = await confirm({
      title: "Delete role",
      message: `Delete the ${draft.name} role?`,
      confirmLabel: "Delete",
      tone: "danger",
    });
    if (!accepted) return;
    try {
      await rolesApi.remove(draft.id);
      setNotice(`${draft.name} deleted.`);
      await load();
    } catch (caught) {
      setError(errorMessage(caught, "Could not delete the role."));
    }
  };

  return (
    <section className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
      <aside className="rounded-card bg-charcoal p-5 text-white">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Roles</h2>
          {manage ? (
            <button
              type="button"
              onClick={() => {
                setDraft(emptyDraft());
                setError(null);
                setNotice(null);
              }}
              className="inline-flex h-9 items-center gap-1 rounded-full bg-accent px-3 text-sm font-semibold"
            >
              <Plus size={15} aria-hidden="true" /> New
            </button>
          ) : null}
        </div>
        <ul className="space-y-2">
          {roles.map((role) => {
            const selected = draft.id === role.id;
            return (
              <li key={role.id}>
                <button
                  type="button"
                  onClick={() => {
                    setDraft(toDraft(role));
                    setError(null);
                    setNotice(null);
                  }}
                  className={`w-full rounded-2xl p-3 text-left transition ${selected ? "bg-accent" : "bg-white/5 hover:bg-white/10"}`}
                >
                  <span className="flex items-center justify-between gap-2">
                    <span className="font-medium">{role.name}</span>
                    {role.is_system ? <Lock size={13} aria-label="System role" /> : null}
                  </span>
                  <span className={`mt-1 block text-xs tabular-nums ${selected ? "text-white/80" : "text-white/50"}`}>
                    {role.permissions.length} permissions · {role.user_count} users
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </aside>

      <div className="rounded-card border border-line bg-white p-6">
        <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-accent text-white">
              <ShieldCheck size={20} aria-hidden="true" />
            </span>
            <div>
              <h2 className="text-2xl font-semibold">{draft.id === null ? "New role" : draft.name}</h2>
              <p className="text-sm text-charcoal/60">
                {isSuperAdmin
                  ? "Super Admin always holds every permission."
                  : draft.isSystem
                    ? "Built-in role. Permissions can be tuned; the name is fixed."
                    : "Custom role."}
              </p>
            </div>
          </div>
          {manage ? (
            <div className="flex gap-2">
              {draft.id !== null && !draft.isSystem ? <GhostButton onClick={() => void remove()}>Delete</GhostButton> : null}
              <PrimaryButton disabled={busy} onClick={() => void save()}>
                {busy ? "Saving…" : draft.id === null ? "Create role" : "Save role"}
              </PrimaryButton>
            </div>
          ) : null}
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <TextField
            label="Name"
            value={draft.name}
            disabled={!manage || draft.isSystem}
            onChange={(event) => setDraft({ ...draft, name: event.target.value })}
          />
          <TextField
            label="Description"
            value={draft.description}
            disabled={!manage}
            onChange={(event) => setDraft({ ...draft, description: event.target.value })}
          />
          <TextField
            label="Discount limit (%)"
            inputMode="decimal"
            placeholder="Till rules default"
            value={draft.discountLimit}
            disabled={locked}
            onChange={(event) => setDraft({ ...draft, discountLimit: event.target.value })}
            hint="The largest discount this role can give at the till without a manager. Needs “Apply discounts”."
          />
        </div>

        <div className="mt-6 grid gap-4 md:grid-cols-2">
          {groups.map((group) => {
            const all = group.permissions.every((item) => draft.permissions.has(item.key));
            return (
              <fieldset key={group.group} className="rounded-2xl border border-line p-4">
                <legend className="sr-only">{group.group}</legend>
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="font-semibold">{group.group}</h3>
                  {!locked ? (
                    <button type="button" className="text-xs font-medium text-accent" onClick={() => toggleGroup(group, !all)}>
                      {all ? "Clear" : "Select all"}
                    </button>
                  ) : null}
                </div>
                <ul className="space-y-2">
                  {group.permissions.map((item) => {
                    const checked = draft.permissions.has(item.key);
                    const grantable = held.has(item.key);
                    return (
                      <li key={item.key}>
                        <label
                          className={`flex items-start gap-3 rounded-xl p-2 ${locked || !grantable ? "opacity-60" : "cursor-pointer hover:bg-surface"}`}
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            disabled={locked || !grantable}
                            onChange={() => toggle(item.key)}
                            className="mt-0.5 h-4 w-4 accent-accent"
                          />
                          <span>
                            <span className="block text-sm font-medium">{item.label}</span>
                            <span className="block font-mono text-[11px] text-charcoal/50">{item.key}</span>
                          </span>
                        </label>
                      </li>
                    );
                  })}
                </ul>
              </fieldset>
            );
          })}
        </div>
        {notice ? <p className="mt-4 text-sm text-charcoal/70">{notice}</p> : null}
        <ErrorNote message={error} />
      </div>
    </section>
  );
}
