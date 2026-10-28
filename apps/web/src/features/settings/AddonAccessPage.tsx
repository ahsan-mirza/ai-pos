import { Permission } from "@ai-pos/shared-types";
import { useCallback, useEffect, useState } from "react";
import { useConfirm } from "../../components/ui/ConfirmDialog";
import { ErrorNote, PrimaryButton, SearchField } from "../../components/ui/Field";
import { apiGet, apiPut } from "../../lib/api";
import { useAuth } from "../../lib/auth";

interface AddonAction {
  permission: string;
  label: string;
}

interface AddonModule {
  key: string;
  label: string;
  entitlement: "active" | "expired" | "suspended" | "unavailable";
  actions: AddonAction[];
}

interface AddonUser {
  user_id: string;
  full_name: string;
  username: string;
  role_name: string;
  is_active: boolean;
  source: "grant" | "role" | "revoked" | "none" | "inactive";
  allowed: boolean;
  permissions: string[];
}

interface AccessEvent {
  id: string;
  action: string;
  user_name: string | null;
  occurred_at: string;
  status: string | null;
  permissions: string[];
}

const SOURCE: Record<AddonUser["source"], string> = {
  grant: "Granted directly",
  role: "From their role",
  revoked: "Revoked",
  none: "No access",
  inactive: "Add-on inactive",
};

export function AddonAccessPage() {
  const { can } = useAuth();
  const confirm = useConfirm();
  const manage = can(Permission.UsersUpdate);
  const [modules, setModules] = useState<AddonModule[]>([]);
  const [moduleKey, setModuleKey] = useState("");
  const [users, setUsers] = useState<AddonUser[]>([]);
  const [history, setHistory] = useState<AccessEvent[]>([]);
  const [query, setQuery] = useState("");
  const [role, setRole] = useState("");
  const [status, setStatus] = useState("");
  const [access, setAccess] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const selected = modules.find((module) => module.key === moduleKey) ?? null;
  const active = selected?.entitlement === "active";

  const loadModules = useCallback(async () => {
    const rows = await apiGet<AddonModule[]>("/api/v1/addon-access/modules");
    setModules(rows);
    setModuleKey((current) => current || rows[0]?.key || "");
  }, []);

  const loadUsers = useCallback(async () => {
    if (!moduleKey) {
      setUsers([]);
      setHistory([]);
      return;
    }
    const params = new URLSearchParams({ module_key: moduleKey });
    if (query.trim()) params.set("q", query.trim());
    if (status) params.set("status", status);
    if (access) params.set("access", access);
    const [people, events] = await Promise.all([
      apiGet<AddonUser[]>(`/api/v1/addon-access/users?${params.toString()}`),
      apiGet<AccessEvent[]>(`/api/v1/addon-access/history?module_key=${encodeURIComponent(moduleKey)}&limit=20`),
    ]);
    setUsers(people);
    setHistory(events);
  }, [moduleKey, query, status, access]);

  useEffect(() => {
    void loadModules().catch((caught: unknown) => setError(caught instanceof Error ? caught.message : "Could not load add-ons."));
  }, [loadModules]);

  useEffect(() => {
    void loadUsers().catch((caught: unknown) => setError(caught instanceof Error ? caught.message : "Could not load users."));
  }, [loadUsers]);

  const roles = [...new Set(users.map((person) => person.role_name))].sort();
  const visible = role ? users.filter((person) => person.role_name === role) : users;

  async function apply(userIds: string[], grant: boolean, permissions?: string[]) {
    if (!selected || !active) return;
    const chosen = permissions ?? (grant ? selected.actions.map((action) => action.permission) : []);
    const bulk = userIds.length > 1 || permissions === undefined;
    if (!grant || bulk) {
      const verb = grant ? "Grant" : "Revoke";
      const accepted = await confirm({
        title: `${verb} ${selected.label}`,
        message: `${verb} access for ${userIds.length} user${userIds.length === 1 ? "" : "s"}? ${
          grant ? "They receive every action this add-on supports." : "Other users keep their access."
        }`,
        confirmLabel: verb,
        tone: grant ? "default" : "danger",
      });
      if (!accepted) return;
    }
    try {
      await apiPut("/api/v1/addon-access/assignments", {
        changes: userIds.map((user_id) => ({
          user_id,
          module_key: selected.key,
          status: grant ? "granted" : "revoked",
          permissions: chosen,
        })),
      });
      setPicked([]);
      setNotice(grant ? "Access granted." : "Access revoked.");
      setError(null);
      await loadUsers();
    } catch (caught) {
      setNotice(null);
      setError(caught instanceof Error ? caught.message : "Could not update access.");
    }
  }

  return (
    <section className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold">Add-on access</h1>
        <p className="mt-1 text-sm text-charcoal/60">
          A paid add-on is available only to people you grant it to, or whose role already contains that add-on's
          permissions. Revoking one person leaves everyone else as they are.
        </p>
      </header>
      <ErrorNote message={error} />
      {notice ? <p className="text-sm text-charcoal/70">{notice}</p> : null}
      {modules.length === 0 ? (
        <p className="rounded-2xl border border-line bg-white px-4 py-6 text-sm text-charcoal/60">
          This store has no paid add-ons yet. Access can be assigned after a subscription is verified.
        </p>
      ) : (
        <>
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-sm font-medium">
              Add-on
              <select
                value={moduleKey}
                onChange={(event) => {
                  setModuleKey(event.target.value);
                  setPicked([]);
                }}
                className="mt-1 block h-10 rounded-xl border border-line bg-white px-3"
              >
                {modules.map((module) => (
                  <option key={module.key} value={module.key}>
                    {module.label} ({module.entitlement})
                  </option>
                ))}
              </select>
            </label>
            <SearchField value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Name, username, or role" label="Search" />
            <label className="text-sm font-medium">
              Status
              <select value={status} onChange={(event) => setStatus(event.target.value)} className="mt-1 block h-10 rounded-xl border border-line bg-white px-3">
                <option value="">Any status</option>
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
              </select>
            </label>
            <label className="text-sm font-medium">
              Access
              <select value={access} onChange={(event) => setAccess(event.target.value)} className="mt-1 block h-10 rounded-xl border border-line bg-white px-3">
                <option value="">Any access</option>
                <option value="grant">Granted directly</option>
                <option value="role">From their role</option>
                <option value="revoked">Revoked</option>
                <option value="none">No access</option>
              </select>
            </label>
            <label className="text-sm font-medium">
              Role
              <select value={role} onChange={(event) => setRole(event.target.value)} className="mt-1 block h-10 rounded-xl border border-line bg-white px-3">
                <option value="">Any role</option>
                {roles.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {selected && !active ? (
            <p className="text-sm text-charcoal/70">
              This add-on is {selected.entitlement}. Existing assignments stay visible, and they do not open the add-on.
            </p>
          ) : null}
          {manage && active ? (
            <div className="flex gap-2">
              <PrimaryButton disabled={picked.length === 0} onClick={() => void apply(picked, true)}>
                Grant selected
              </PrimaryButton>
              <PrimaryButton disabled={picked.length === 0} onClick={() => void apply(picked, false)}>
                Revoke selected
              </PrimaryButton>
            </div>
          ) : null}
          <div className="overflow-x-auto rounded-2xl border border-line bg-white">
            <table className="w-full text-sm">
              <thead className="text-left text-charcoal/50">
                <tr>
                  <th className="px-3 py-2" />
                  <th className="px-3 py-2">User</th>
                  <th className="px-3 py-2">Role</th>
                  <th className="px-3 py-2">Access</th>
                  <th className="px-3 py-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((person) => (
                  <tr key={person.user_id} className="border-t border-line">
                    <td className="px-3 py-2">
                      <input
                        type="checkbox"
                        checked={picked.includes(person.user_id)}
                        onChange={(event) =>
                          setPicked((current) =>
                            event.target.checked ? [...current, person.user_id] : current.filter((id) => id !== person.user_id),
                          )
                        }
                        aria-label={`Select ${person.full_name}`}
                      />
                    </td>
                    <td className="px-3 py-2">
                      <div className="font-medium">{person.full_name}</div>
                      <div className="text-charcoal/50">{person.username}{person.is_active ? "" : " · inactive"}</div>
                    </td>
                    <td className="px-3 py-2">{person.role_name}</td>
                    <td className="px-3 py-2">{SOURCE[person.source]}</td>
                    <td className="px-3 py-2">
                      {manage && active && selected ? (
                        <div className="flex flex-wrap items-center gap-3">
                          {selected.actions.map((action) => (
                            <label key={action.permission} className="inline-flex items-center gap-1">
                              <input
                                type="checkbox"
                                checked={person.permissions.includes(action.permission)}
                                onChange={(event) => {
                                  const next = event.target.checked
                                    ? [...person.permissions, action.permission]
                                    : person.permissions.filter((item) => item !== action.permission);
                                  void apply([person.user_id], true, next);
                                }}
                              />
                              {action.label}
                            </label>
                          ))}
                          <button
                            type="button"
                            className="text-charcoal/70 underline"
                            onClick={() => void apply([person.user_id], !person.allowed)}
                          >
                            {person.allowed ? "Revoke" : "Grant"}
                          </button>
                        </div>
                      ) : (
                        person.permissions.join(", ") || "—"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div>
            <h2 className="text-sm font-semibold">Recent changes</h2>
            <ul className="mt-2 space-y-1 text-sm text-charcoal/70">
              {history.length === 0 ? <li>No changes yet.</li> : null}
              {history.map((event) => (
                <li key={event.id}>
                  {event.user_name ?? "Someone"} {event.action.endsWith("revoke") ? "revoked" : "granted"} access
                  {event.occurred_at ? ` · ${event.occurred_at.slice(0, 16).replace("T", " ")}` : ""}
                </li>
              ))}
            </ul>
          </div>
        </>
      )}
    </section>
  );
}
