import { Permission, type Role, type Store, type User } from "@ai-pos/shared-types";
import { KeyRound, Pencil, Plus, Smartphone, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { useConfirm } from "../../components/ui/ConfirmDialog";
import { ErrorNote, PrimaryButton } from "../../components/ui/Field";
import { useAuth } from "../../lib/auth";
import { errorMessage, rolesApi, storesApi, usersApi } from "./api";
import { CredentialModal } from "./CredentialModal";
import { UserFormModal } from "./UserFormModal";

type Dialog =
  | { kind: "form"; user: User | null }
  | { kind: "password"; user: User }
  | { kind: "pin"; user: User }
  | null;

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

function Badge({ on, label }: { on: boolean; label: string }) {
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${on ? "bg-charcoal text-white" : "bg-surface text-charcoal/40"}`}
    >
      {label}
    </span>
  );
}

export function UsersPage() {
  const { can, user: actor } = useAuth();
  const [users, setUsers] = useState<User[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [stores, setStores] = useState<Store[]>([]);
  const [query, setQuery] = useState("");
  const [dialog, setDialog] = useState<Dialog>(null);
  const [error, setError] = useState<string | null>(null);
  const confirm = useConfirm();

  const load = useCallback(async () => {
    try {
      const [userRows, roleRows, storeRows] = await Promise.all([usersApi.list(), rolesApi.list(), storesApi.list()]);
      setUsers(userRows);
      setRoles(roleRows);
      setStores(storeRows);
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "Could not load users."));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const storeName = useMemo(() => new Map(stores.map((store) => [store.id, store.name])), [stores]);
  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (needle === "") return users;
    return users.filter((user) =>
      [user.full_name, user.username, user.email, user.role.name].some((value) => value.toLowerCase().includes(needle)),
    );
  }, [users, query]);

  const active = users.filter((user) => user.is_active);
  const posCount = active.filter((user) => user.has_pos_access).length;
  const portalCount = active.filter((user) => user.has_portal_access).length;

  const saved = (next: User) => {
    setUsers((current) => {
      const exists = current.some((user) => user.id === next.id);
      return exists ? current.map((user) => (user.id === next.id ? next : user)) : [...current, next];
    });
    setDialog(null);
    void load();
  };

  const remove = async (user: User) => {
    const accepted = await confirm({
      title: "Delete user",
      message: `Delete ${user.full_name}? This cannot be undone.`,
      confirmLabel: "Delete",
      tone: "danger",
    });
    if (!accepted) return;
    try {
      await usersApi.remove(user.id);
      setUsers((current) => current.filter((item) => item.id !== user.id));
    } catch (caught) {
      setError(errorMessage(caught, "Could not delete the user."));
    }
  };

  return (
    <section className="space-y-4">
      <div className="grid gap-4 md:grid-cols-3">
        <article className="rounded-card bg-charcoal p-6 text-white">
          <p className="text-sm text-white/60">Active staff</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{active.length}</p>
          <p className="mt-2 text-xs text-white/50">{users.length - active.length} disabled</p>
        </article>
        <article className="rounded-card bg-accent p-6 text-white">
          <p className="text-sm text-white/80">POS access</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{posCount}</p>
          <div className="mt-3 flex h-2 overflow-hidden rounded-full bg-white/25">
            <span className="bg-white" style={{ width: `${active.length ? (posCount / active.length) * 100 : 0}%` }} />
          </div>
        </article>
        <article className="rounded-card border border-line bg-white p-6">
          <p className="text-sm text-charcoal/60">Web portal access</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{portalCount}</p>
          <p className="mt-2 text-xs text-charcoal/50">{roles.length} roles defined</p>
        </article>
      </div>

      <div className="rounded-card border border-line bg-white p-6">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-2xl font-semibold">Users</h2>
            <p className="text-sm text-charcoal/60">
              {actor?.store_id ? `Staff at ${storeName.get(actor.store_id) ?? "your store"}.` : "Staff across every store."}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search name, username, role"
              className="h-11 w-64 rounded-full border border-line bg-surface px-4 text-sm"
            />
            {can(Permission.UsersCreate) ? (
              <PrimaryButton onClick={() => setDialog({ kind: "form", user: null })}>
                <span className="inline-flex items-center gap-2">
                  <Plus size={16} aria-hidden="true" /> New user
                </span>
              </PrimaryButton>
            ) : null}
          </div>
        </div>
        <ErrorNote message={error} />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[860px] text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-charcoal/50">
              <tr>
                <th className="pb-3 font-medium">User</th>
                <th className="pb-3 font-medium">Role</th>
                <th className="pb-3 font-medium">Store</th>
                <th className="pb-3 font-medium">Access</th>
                <th className="pb-3 font-medium">Status</th>
                <th className="pb-3 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((user) => (
                <tr key={user.id} className="border-t border-line">
                  <td className="py-3">
                    <div className="flex items-center gap-3">
                      <span className="flex h-9 w-9 items-center justify-center rounded-full bg-charcoal text-xs font-semibold text-white">
                        {initials(user.full_name)}
                      </span>
                      <span>
                        <span className="block font-medium">{user.full_name}</span>
                        <span className="block text-xs text-charcoal/50">
                          @{user.username} · {user.email}
                        </span>
                      </span>
                    </div>
                  </td>
                  <td className="py-3">
                    <span className="rounded-full border border-line px-3 py-1 text-xs font-medium">{user.role.name}</span>
                  </td>
                  <td className="py-3">{user.store_id ? (storeName.get(user.store_id) ?? "Unknown store") : "All stores"}</td>
                  <td className="py-3">
                    <div className="flex gap-1">
                      <Badge on={user.has_pos_access} label="POS" />
                      <Badge on={user.has_portal_access} label="Portal" />
                    </div>
                  </td>
                  <td className="py-3">
                    {user.locked_until && new Date(user.locked_until) > new Date() ? (
                      <span className="text-xs font-semibold text-accent">Locked</span>
                    ) : user.is_active ? (
                      <span className="text-xs font-semibold">Active</span>
                    ) : (
                      <span className="text-xs text-charcoal/50">Disabled</span>
                    )}
                  </td>
                  <td className="py-3">
                    <div className="flex justify-end gap-1">
                      {can(Permission.UsersUpdate) ? (
                        <>
                          <IconButton label="Edit" onClick={() => setDialog({ kind: "form", user })}>
                            <Pencil size={15} />
                          </IconButton>
                          <IconButton label="Reset password" onClick={() => setDialog({ kind: "password", user })}>
                            <KeyRound size={15} />
                          </IconButton>
                          <IconButton label="Set POS PIN" onClick={() => setDialog({ kind: "pin", user })}>
                            <Smartphone size={15} />
                          </IconButton>
                        </>
                      ) : null}
                      {can(Permission.UsersDelete) && user.id !== actor?.id ? (
                        <IconButton label="Delete" onClick={() => void remove(user)}>
                          <Trash2 size={15} />
                        </IconButton>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {visible.length === 0 ? <p className="py-8 text-sm text-charcoal/60">No users match that search.</p> : null}
        </div>
      </div>

      {dialog?.kind === "form" ? (
        <UserFormModal user={dialog.user} roles={roles} stores={stores} onClose={() => setDialog(null)} onSaved={saved} />
      ) : null}
      {dialog?.kind === "password" || dialog?.kind === "pin" ? (
        <CredentialModal user={dialog.user} kind={dialog.kind} onClose={() => setDialog(null)} onSaved={saved} />
      ) : null}
    </section>
  );
}

function IconButton({ label, onClick, children }: { label: string; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className="flex h-9 w-9 items-center justify-center rounded-full border border-line hover:border-accent hover:text-accent"
    >
      {children}
    </button>
  );
}
