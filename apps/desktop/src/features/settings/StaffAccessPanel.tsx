import { useCallback, useEffect, useState } from "react";
import { ui } from "../../components/shell/tokens";
import {
  createRegisterStaff,
  disableRegisterStaff,
  editRegisterStaff,
  inTauri,
  listRegisterStaff,
  registerStaffSeats,
  resetRegisterStaffPin,
  submitStaffProvisioning,
  type RegisterStaffRow,
  type StaffSeatReport,
} from "../../lib/tauri";
import { pinIsAcceptable, rolesActorMayGrant, seatLabel, staffStatus, type StaffRow } from "./staffAccess";

function asRow(row: RegisterStaffRow): StaffRow {
  return {
    name: row.full_name,
    username: row.username,
    role: row.role_name,
    branch: row.store_id,
    provisioning: row.provisioning_status as StaffRow["provisioning"],
    active: row.is_active === 1,
  };
}

export function StaffAccessPanel({ actorRole }: { actorRole: string }) {
  const roles = rolesActorMayGrant(actorRole);
  const [rows, setRows] = useState<RegisterStaffRow[]>([]);
  const [seats, setSeats] = useState<StaffSeatReport | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [username, setUsername] = useState("");
  const [fullName, setFullName] = useState("");
  const [roleName, setRoleName] = useState(roles[0] ?? "Cashier");
  const [pin, setPin] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editRole, setEditRole] = useState("Cashier");
  const [resetFor, setResetFor] = useState<string | null>(null);
  const [nextPin, setNextPin] = useState("");

  const reload = useCallback(async () => {
    if (!inTauri()) return;
    const [people, seat] = await Promise.all([listRegisterStaff(), registerStaffSeats()]);
    setRows(people);
    setSeats(seat);
  }, []);

  useEffect(() => {
    void reload().catch((caught: unknown) => setNotice(caught instanceof Error ? caught.message : "Staff could not be loaded."));
  }, [reload]);

  const create = async () => {
    if (!pinIsAcceptable(pin)) {
      setNotice("A register PIN is four digits.");
      return;
    }
    setNotice(null);
    try {
      const label = await createRegisterStaff({ username: username.trim(), fullName: fullName.trim(), roleName, pin });
      setPin("");
      setUsername("");
      setFullName("");
      setNotice(label);
      await reload();
      try {
        await submitStaffProvisioning();
      } catch (caught) {
        const detail = caught instanceof Error ? caught.message : "";
        setNotice(detail || `${label} The server has not accepted this person yet.`);
      }
    } catch (caught) {
      setNotice(caught instanceof Error ? caught.message : typeof caught === "string" && caught.trim() ? caught : "Staff could not be created.");
    }
  };

  return (
    <section aria-labelledby="staff-access-title" className={`rounded-2xl border p-6 ${ui.panel} ${ui.border}`}>
      <h2 id="staff-access-title" className="text-lg font-semibold">
        Staff & Access
      </h2>
      <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-300">
        {seats?.trusted
          ? `Staff seats ${seatLabel(seats.active, seats.limit)}. A person created here stays on this register until the server accepts them.`
          : "Staff seats need a trusted entitlement. Connect this register before creating staff."}
      </p>
      {notice ? <p className="mt-3 text-sm">{notice}</p> : null}
      {!inTauri() ? (
        <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-300">Open the AxizPOS window to create or change staff.</p>
      ) : (
        <>
          <ul className="mt-4 divide-y divide-zinc-200 dark:divide-zinc-700">
            {rows.map((row) => {
              const view = asRow(row);
              return (
                <li key={row.user_id} className="flex flex-wrap items-center gap-3 py-3">
                  <div className="min-w-0 flex-1">
                    <p className="font-medium">{row.full_name}</p>
                    <p className="text-sm text-zinc-600 dark:text-zinc-300">
                      {row.username} · {row.role_name} · {staffStatus(view)}
                    </p>
                  </div>
                  <button type="button" className="min-h-11 rounded-full px-4 text-sm" onClick={() => { setEditing(row.user_id); setEditName(row.full_name); setEditRole(row.role_name); }}>
                    Edit
                  </button>
                  <button type="button" className="min-h-11 rounded-full px-4 text-sm" onClick={() => { setResetFor(row.user_id); setNextPin(""); }}>
                    Reset PIN
                  </button>
                  <button
                    type="button"
                    className="min-h-11 rounded-full px-4 text-sm"
                    onClick={() => {
                      void disableRegisterStaff(row.user_id)
                        .then(async () => {
                          await reload();
                          try {
                            await submitStaffProvisioning();
                          } catch (caught) {
                            const detail = caught instanceof Error ? caught.message : "";
                            setNotice(detail || "Disabled on this register. The server has not accepted it yet.");
                          }
                        })
                        .catch((caught: unknown) => setNotice(caught instanceof Error ? caught.message : "Staff could not be disabled."));
                    }}
                  >
                    Disable
                  </button>
                </li>
              );
            })}
          </ul>
          {editing ? (
            <form
              className="mt-4 grid gap-3"
              onSubmit={(event) => {
                event.preventDefault();
                void editRegisterStaff({ userId: editing, fullName: editName, roleName: editRole })
                  .then(async () => {
                    setEditing(null);
                    await reload();
                    try {
                      await submitStaffProvisioning();
                    } catch (caught) {
                      const detail = caught instanceof Error ? caught.message : "";
                      setNotice(detail || "Saved on this register. The server has not accepted the change yet.");
                    }
                  })
                  .catch((caught: unknown) => setNotice(caught instanceof Error ? caught.message : "Staff could not be edited."));
              }}
            >
              <label className="text-sm">
                Display name
                <input className="mt-1 min-h-11 w-full rounded-xl border px-3" value={editName} onChange={(event) => setEditName(event.target.value)} />
              </label>
              <label className="text-sm">
                Role
                <select className="mt-1 min-h-11 w-full rounded-xl border px-3" value={editRole} onChange={(event) => setEditRole(event.target.value)}>
                  {roles.map((role) => (
                    <option key={role}>{role}</option>
                  ))}
                </select>
              </label>
              <button type="submit" className="box-border inline-flex h-12 items-center justify-center rounded-xl bg-primary px-4 text-sm font-semibold text-white transition-colors hover:bg-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 disabled:opacity-40">
                Save staff
              </button>
            </form>
          ) : null}
          {resetFor ? (
            <form
              className="mt-4 grid gap-3"
              onSubmit={(event) => {
                event.preventDefault();
                if (!pinIsAcceptable(nextPin)) {
                  setNotice("A register PIN is four digits.");
                  return;
                }
                void resetRegisterStaffPin(resetFor, nextPin)
                  .then(async () => {
                    setNextPin("");
                    setResetFor(null);
                    setNotice("PIN reset on this register. Other registers receive it after the server accepts it.");
                    try {
                      await submitStaffProvisioning();
                    } catch (caught) {
                      const detail = caught instanceof Error ? caught.message : "";
                      setNotice(detail || "PIN reset on this register. The server has not accepted it yet.");
                    }
                  })
                  .catch((caught: unknown) => setNotice(caught instanceof Error ? caught.message : "The PIN could not be reset."));
              }}
            >
              <label className="text-sm">
                New PIN
                <input className="mt-1 min-h-11 w-full rounded-xl border px-3" type="password" inputMode="numeric" autoComplete="new-password" value={nextPin} onChange={(event) => setNextPin(event.target.value)} />
              </label>
              <button type="submit" className="box-border inline-flex h-12 items-center justify-center rounded-xl bg-primary px-4 text-sm font-semibold text-white transition-colors hover:bg-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 disabled:opacity-40">
                Save PIN
              </button>
            </form>
          ) : null}
          <form
            className="mt-4 grid gap-3"
            onSubmit={(event) => {
              event.preventDefault();
              void create();
            }}
          >
            <h3 className="font-medium">Create staff</h3>
            <label className="text-sm">
              Display name
              <input className="mt-1 min-h-11 w-full rounded-xl border px-3" value={fullName} onChange={(event) => setFullName(event.target.value)} />
            </label>
            <label className="text-sm">
              Username
              <input className="mt-1 min-h-11 w-full rounded-xl border px-3" value={username} onChange={(event) => setUsername(event.target.value)} />
            </label>
            <label className="text-sm">
              Role
              <select className="mt-1 min-h-11 w-full rounded-xl border px-3" value={roleName} onChange={(event) => setRoleName(event.target.value)}>
                {roles.map((role) => (
                  <option key={role}>{role}</option>
                ))}
              </select>
            </label>
            <label className="text-sm">
              PIN
              <input className="mt-1 min-h-11 w-full rounded-xl border px-3" type="password" inputMode="numeric" autoComplete="new-password" value={pin} onChange={(event) => setPin(event.target.value)} />
            </label>
            <button type="submit" className="box-border inline-flex h-12 items-center justify-center rounded-xl bg-primary px-4 text-sm font-semibold text-white transition-colors hover:bg-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 disabled:opacity-40" disabled={seats !== null && !seats.trusted}>
              Create staff
            </button>
          </form>
        </>
      )}
    </section>
  );
}
