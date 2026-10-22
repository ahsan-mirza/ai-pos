import {
  PASSWORD_MIN_LENGTH,
  PIN_PATTERN,
  type Role,
  type Store,
  type User,
  type UserCreate,
  type UserUpdate,
} from "@ai-pos/shared-types";
import { useState } from "react";
import { ErrorNote, GhostButton, PrimaryButton, SelectField, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { Toggle } from "../../components/ui/Toggle";
import { useAuth } from "../../lib/auth";
import { errorMessage, usersApi } from "./api";

interface UserFormModalProps {
  user: User | null;
  roles: Role[];
  stores: Store[];
  onClose: () => void;
  onSaved: (user: User) => void;
}

export function UserFormModal({ user, roles, stores, onClose, onSaved }: UserFormModalProps) {
  const { user: actor } = useAuth();
  const editing = user !== null;
  const actorStore = actor?.store_id ?? null;
  const grantable = roles.filter((role) => role.permissions.every((item) => actor?.permissions.includes(item)));

  const [username, setUsername] = useState(user?.username ?? "");
  const [email, setEmail] = useState(user?.email ?? "");
  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [roleId, setRoleId] = useState(user?.role.id ?? grantable.find((role) => role.name === "Cashier")?.id ?? "");
  const [storeId, setStoreId] = useState(user?.store_id ?? actorStore ?? "");
  const [password, setPassword] = useState("");
  const [pin, setPin] = useState("");
  const [posAccess, setPosAccess] = useState(user?.has_pos_access ?? true);
  const [portalAccess, setPortalAccess] = useState(user?.has_portal_access ?? false);
  const [active, setActive] = useState(user?.is_active ?? true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const isSelf = editing && actor?.id === user.id;
  const canEnablePortal = editing ? user.has_password : password.length >= PASSWORD_MIN_LENGTH;
  const canEnablePos = editing ? user.has_pin : PIN_PATTERN.test(pin);

  const validate = (): string | null => {
    if (!editing && !/^[a-z0-9][a-z0-9._-]{2,31}$/.test(username.trim().toLowerCase())) {
      return "Username must be 3-32 characters: lowercase letters, digits, dot, dash, underscore.";
    }
    if (fullName.trim() === "") return "Full name is required.";
    if (roleId === "") return "Choose a role.";
    if (!editing && password !== "" && password.length < PASSWORD_MIN_LENGTH) {
      return `Passwords need at least ${PASSWORD_MIN_LENGTH} characters.`;
    }
    if (!editing && pin !== "" && !PIN_PATTERN.test(pin)) return "PINs are 4 to 6 digits.";
    if (portalAccess && !canEnablePortal) return "Set a password before enabling web portal access.";
    if (posAccess && !canEnablePos) return "Set a PIN before enabling POS access.";
    return null;
  };

  const save = async () => {
    const problem = validate();
    if (problem) {
      setError(problem);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (!editing) {
        const body: UserCreate = {
          username: username.trim().toLowerCase(),
          email: email.trim(),
          full_name: fullName.trim(),
          role_id: roleId,
          store_id: storeId === "" ? null : storeId,
          password: password === "" ? null : password,
          pin: pin === "" ? null : pin,
          has_pos_access: posAccess,
          has_portal_access: portalAccess,
          is_active: active,
        };
        onSaved(await usersApi.create(body));
        return;
      }
      const body: UserUpdate = {};
      if (email.trim() !== user.email) body.email = email.trim();
      if (fullName.trim() !== user.full_name) body.full_name = fullName.trim();
      if (roleId !== user.role.id) body.role_id = roleId;
      if ((storeId || null) !== user.store_id) {
        if (storeId === "") body.clear_store = true;
        else body.store_id = storeId;
      }
      if (posAccess !== user.has_pos_access) body.has_pos_access = posAccess;
      if (portalAccess !== user.has_portal_access) body.has_portal_access = portalAccess;
      if (active !== user.is_active) body.is_active = active;
      onSaved(Object.keys(body).length === 0 ? user : await usersApi.update(user.id, body));
    } catch (caught) {
      setError(errorMessage(caught, "Could not save the user."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title={editing ? `Edit ${user.full_name}` : "New user"}
      subtitle={editing ? `@${user.username}` : "Create a staff account and choose where they can sign in."}
      onClose={onClose}
      width="lg"
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy} onClick={() => void save()}>
            {busy ? "Saving…" : editing ? "Save changes" : "Create user"}
          </PrimaryButton>
        </>
      }
    >
      <div className="grid gap-4 md:grid-cols-2">
        <TextField
          label="Username"
          value={username}
          disabled={editing}
          autoComplete="off"
          onChange={(event) => setUsername(event.target.value)}
        />
        <TextField label="Full name" value={fullName} onChange={(event) => setFullName(event.target.value)} />
        <TextField label="Email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
        <SelectField
          label="Role"
          value={roleId}
          disabled={isSelf}
          placeholder="Choose a role"
          options={grantable.map((role) => ({ value: role.id, label: role.name }))}
          onChange={setRoleId}
        />
        <SelectField
          label="Store"
          value={storeId}
          disabled={actorStore !== null}
          options={[
            ...(actorStore === null ? [{ value: "", label: "All stores (global)" }] : []),
            ...stores.map((store) => ({ value: store.id, label: `${store.name} (${store.code})` })),
          ]}
          onChange={setStoreId}
        />
        {!editing ? (
          <>
            <TextField
              label="Password"
              type="password"
              autoComplete="new-password"
              value={password}
              hint={`Web portal sign-in. At least ${PASSWORD_MIN_LENGTH} characters.`}
              onChange={(event) => setPassword(event.target.value)}
            />
            <TextField
              label="POS PIN"
              type="password"
              inputMode="numeric"
              autoComplete="off"
              maxLength={6}
              value={pin}
              hint="Register unlock. 4 to 6 digits."
              onChange={(event) => setPin(event.target.value.replace(/\D/g, ""))}
            />
          </>
        ) : null}
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-3">
        <Toggle label="POS access" description="Unlock registers with a PIN" checked={posAccess} onChange={setPosAccess} />
        <Toggle
          label="Web portal access"
          description="Sign in here with a password"
          checked={portalAccess}
          disabled={isSelf}
          onChange={setPortalAccess}
        />
        <Toggle label="Active" description="Disabled users cannot sign in" checked={active} disabled={isSelf} onChange={setActive} />
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}
