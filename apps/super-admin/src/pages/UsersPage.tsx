import { Select } from "@ai-pos/ui";
import type { Operator, OperatorRole } from "@ai-pos/shared-types";
import { useEffect, useState } from "react";
import { PageHeader } from "../components/PageHeader";
import { ErrorNote, Field, PrimaryButton } from "../components/ui";
import { ConsoleError, api, errorText } from "../lib/api";
import { when } from "../lib/format";
import { useSession } from "../lib/session";

type CreateField = "full_name" | "email" | "password" | "confirm";
type RowField = "role" | "password" | "confirm";

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const ROLES: { value: OperatorRole; label: string }[] = [
  { value: "ADMIN", label: "Admin" },
  { value: "SUPPORT", label: "Support" },
];

function passwordProblem(password: string): string | null {
  if (password.length < 8) return "Operator passwords are at least 8 characters.";
  if (!/[A-Z]/.test(password)) return "Operator passwords need an uppercase letter.";
  if (!/\d/.test(password)) return "Operator passwords need a number.";
  if (!/[^A-Za-z0-9]/.test(password)) return "Operator passwords need a special character.";
  return null;
}

function sentence(raw: string): string {
  const text = raw.replace(/^Value error,\s*/i, "").trim();
  return text.endsWith(".") ? text : `${text}.`;
}

function detailFields(caught: ConsoleError): Partial<Record<CreateField | "role", string>> {
  const next: Partial<Record<CreateField | "role", string>> = {};
  if (!Array.isArray(caught.details)) return next;
  for (const item of caught.details) {
    if (item === null || typeof item !== "object") continue;
    const record = item as { loc?: unknown; msg?: unknown };
    const parts = Array.isArray(record.loc) ? record.loc.map(String) : [];
    const name = parts.filter((part) => part !== "body" && !/^\d+$/.test(part)).at(-1);
    if (name === "full_name" || name === "email" || name === "password" || name === "role") {
      next[name] = sentence(String(record.msg ?? caught.message));
    }
  }
  return next;
}

export function UsersPage() {
  const { operator, signOut } = useSession();
  const admin = operator?.role === "ADMIN";
  const [rows, setRows] = useState<Operator[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<OperatorRole>("SUPPORT");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [createErrors, setCreateErrors] = useState<Partial<Record<CreateField, string>>>({});
  const [rowRole, setRowRole] = useState<Record<string, OperatorRole>>({});
  const [rowPassword, setRowPassword] = useState<Record<string, string>>({});
  const [rowConfirm, setRowConfirm] = useState<Record<string, string>>({});
  const [rowErrors, setRowErrors] = useState<Record<string, Partial<Record<RowField, string>>>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!admin) return;
    api
      .get<Operator[]>("/operators")
      .then((found) => {
        setRows(found);
        setRowRole(Object.fromEntries(found.map((row) => [row.id, row.role])));
      })
      .catch((caught: unknown) => setError(errorText(caught, "Could not load users.")));
  }, [admin]);

  if (!admin) {
    return (
      <section className="max-w-xl">
        <PageHeader title="Users" description="Only an admin can manage users." />
      </section>
    );
  }

  const clearCreate = (field: CreateField) => setCreateErrors((current) => ({ ...current, [field]: undefined }));

  const create = () => {
    const next: Partial<Record<CreateField, string>> = {};
    if (name.trim() === "") next.full_name = "Enter a name.";
    if (email.trim() === "") next.email = "Enter an email address.";
    else if (!EMAIL.test(email.trim())) next.email = "Enter a valid email address.";
    const passwordError = password === "" ? "Enter a password." : passwordProblem(password);
    if (passwordError) next.password = passwordError;
    else if (password !== confirm) next.confirm = "Passwords do not match.";
    setCreateErrors(next);
    if (Object.keys(next).length > 0) {
      setError(null);
      return;
    }
    setBusy(true);
    api
      .post<Operator>("/operators", {
        full_name: name.trim(),
        email: email.trim(),
        role,
        password,
      })
      .then((created) => {
        setRows((current) => [...current, created].sort((left, right) => left.full_name.localeCompare(right.full_name)));
        setRowRole((current) => ({ ...current, [created.id]: created.role }));
        setName("");
        setEmail("");
        setRole("SUPPORT");
        setPassword("");
        setConfirm("");
        setCreateErrors({});
        setError(null);
      })
      .catch((caught: unknown) => {
        if (caught instanceof ConsoleError && caught.code === "operator_exists") {
          setCreateErrors({ email: "An operator with this email already exists." });
          setError(null);
          return;
        }
        const mapped = caught instanceof ConsoleError ? detailFields(caught) : {};
        if (Object.keys(mapped).length > 0) {
          setCreateErrors(mapped);
          setError(null);
        } else {
          setError(errorText(caught, "Could not create the user."));
        }
      })
      .finally(() => setBusy(false));
  };

  const saveRow = (row: Operator) => {
    const nextRole = rowRole[row.id] ?? row.role;
    const nextPassword = rowPassword[row.id] ?? "";
    const nextConfirm = rowConfirm[row.id] ?? "";
    const next: Partial<Record<RowField, string>> = {};
    if (nextPassword !== "") {
      const passwordError = passwordProblem(nextPassword);
      if (passwordError) next.password = passwordError;
      else if (nextPassword !== nextConfirm) next.confirm = "Passwords do not match.";
    }
    setRowErrors((current) => ({ ...current, [row.id]: next }));
    if (Object.keys(next).length > 0) {
      setError(null);
      return;
    }
    const body: { role: OperatorRole; password?: string } = { role: nextRole };
    if (nextPassword !== "") body.password = nextPassword;
    setBusy(true);
    api
      .patch<Operator>(`/operators/${row.id}`, body)
      .then((updated) => {
        if (nextPassword !== "" && updated.id === operator?.id) {
          signOut();
          return;
        }
        setRows((current) => current.map((item) => (item.id === updated.id ? updated : item)));
        setRowRole((current) => ({ ...current, [updated.id]: updated.role }));
        setRowPassword((current) => ({ ...current, [updated.id]: "" }));
        setRowConfirm((current) => ({ ...current, [updated.id]: "" }));
        setRowErrors((current) => ({ ...current, [updated.id]: {} }));
        setError(null);
      })
      .catch((caught: unknown) => {
        if (caught instanceof ConsoleError && caught.code === "last_admin") {
          setRowErrors((current) => ({
            ...current,
            [row.id]: { role: "The last console admin cannot be changed to Support." },
          }));
          setError(null);
          return;
        }
        const mapped = caught instanceof ConsoleError ? detailFields(caught) : {};
        if (mapped.password || mapped.role) {
          setRowErrors((current) => ({ ...current, [row.id]: { password: mapped.password, role: mapped.role } }));
          setError(null);
        } else {
          setError(errorText(caught, "Could not update the user."));
        }
      })
      .finally(() => setBusy(false));
  };

  return (
    <section className="max-w-3xl">
      <PageHeader
        title="Users"
        description="Admins manage billing, mail, WhatsApp, and these users. Support can work with stores only."
      />
      <div className="mt-6 space-y-4 rounded-3xl border border-line bg-white p-5">
        <h2 className="text-lg font-semibold">New user</h2>
        <Field
          label="Name"
          value={name}
          autoComplete="off"
          error={createErrors.full_name}
          onChange={(event) => {
            clearCreate("full_name");
            setName(event.target.value);
          }}
        />
        <Field
          label="Email"
          type="email"
          value={email}
          autoComplete="off"
          error={createErrors.email}
          onChange={(event) => {
            clearCreate("email");
            setEmail(event.target.value);
          }}
        />
        <label className="block text-sm font-medium text-charcoal">
          Role
          <Select
            className="mt-1.5"
            aria-label="Role"
            value={role}
            onChange={(value) => setRole(value as OperatorRole)}
            options={ROLES}
          />
        </label>
        <Field
          label="Password"
          type="password"
          value={password}
          autoComplete="new-password"
          error={createErrors.password}
          onChange={(event) => {
            clearCreate("password");
            setPassword(event.target.value);
          }}
        />
        <Field
          label="Confirm password"
          type="password"
          value={confirm}
          autoComplete="new-password"
          error={createErrors.confirm}
          onChange={(event) => {
            clearCreate("confirm");
            setConfirm(event.target.value);
          }}
        />
        <PrimaryButton disabled={busy} onClick={create}>
          Create user
        </PrimaryButton>
      </div>
      <div className="mt-4 space-y-4">
        {rows.map((row) => {
          const problems = rowErrors[row.id] ?? {};
          const draftPassword = rowPassword[row.id] ?? "";
          const chosen = rowRole[row.id] ?? row.role;
          const unchanged = chosen === row.role && draftPassword === "";
          return (
            <article key={row.id} className="space-y-4 rounded-3xl border border-line bg-white p-5">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <div>
                  <h2 className="font-semibold">{row.full_name}</h2>
                  <p className="text-sm text-charcoal/60">{row.email}</p>
                </div>
                <p className="text-xs text-charcoal/50">Last login {when(row.last_login_at)}</p>
              </div>
              <label className="block text-sm font-medium text-charcoal">
                Role
                <Select
                  className="mt-1.5"
                  aria-label={`Role for ${row.full_name}`}
                  value={chosen}
                  onChange={(value) => {
                    setRowRole((current) => ({ ...current, [row.id]: value as OperatorRole }));
                    setRowErrors((current) => ({ ...current, [row.id]: { ...current[row.id], role: undefined } }));
                  }}
                  options={ROLES}
                />
                {problems.role ? (
                  <span className="mt-1.5 block text-xs font-normal text-danger">{problems.role}</span>
                ) : null}
              </label>
              <Field
                label="New password"
                type="password"
                value={draftPassword}
                autoComplete="new-password"
                placeholder="Leave blank to keep the current password"
                error={problems.password}
                onChange={(event) => {
                  setRowPassword((current) => ({ ...current, [row.id]: event.target.value }));
                  setRowErrors((current) => ({ ...current, [row.id]: { ...current[row.id], password: undefined } }));
                }}
              />
              <Field
                label="Confirm new password"
                type="password"
                value={rowConfirm[row.id] ?? ""}
                autoComplete="new-password"
                error={problems.confirm}
                onChange={(event) => {
                  setRowConfirm((current) => ({ ...current, [row.id]: event.target.value }));
                  setRowErrors((current) => ({ ...current, [row.id]: { ...current[row.id], confirm: undefined } }));
                }}
              />
              <PrimaryButton disabled={busy || unchanged} onClick={() => saveRow(row)}>
                Save
              </PrimaryButton>
            </article>
          );
        })}
      </div>
      <ErrorNote message={error} />
    </section>
  );
}
