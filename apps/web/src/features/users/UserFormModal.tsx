import {
  PASSWORD_MIN_LENGTH,
  PIN_PATTERN,
  Permission,
  type Role,
  type Store,
  type User,
  type UserCreate,
  type UserUpdate,
} from "@ai-pos/shared-types";
import { useState } from "react";
import { emailError, requiredError } from "@ai-pos/ui";
import { ErrorNote, GhostButton, PrimaryButton, SelectField, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { Toggle } from "../../components/ui/Toggle";
import { useAuth } from "../../lib/auth";
import { fieldErrors, type FieldErrors } from "../inventory/formErrors";
import { errorMessage, usersApi } from "./api";
import { CredentialModal } from "./CredentialModal";

const PIN_REQUIRED = "Set a PIN before enabling POS access.";

interface UserFormModalProps {
  user: User | null;
  roles: Role[];
  stores: Store[];
  onClose: () => void;
  onSaved: (user: User) => void;
  /** Updates the staff list while this dialog stays open, used after a PIN is set. */
  onUpdated?: (user: User) => void;
}

export function UserFormModal({ user, roles, stores, onClose, onSaved, onUpdated }: UserFormModalProps) {
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
  const [openPriceSale, setOpenPriceSale] = useState(user?.can_sell_open_price ?? false);
  const [active, setActive] = useState(user?.is_active ?? true);
  const [error, setError] = useState<string | null>(null);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [busy, setBusy] = useState(false);
  const [hasPin, setHasPin] = useState(user?.has_pin ?? false);
  const [settingPin, setSettingPin] = useState(false);

  const isSelf = editing && actor?.id === user.id;
  const canEnablePortal = editing ? user.has_password : password.length >= PASSWORD_MIN_LENGTH;
  const canEnablePos = editing ? hasPin : PIN_PATTERN.test(pin);
  const actorCanGrantOpenPrice = actor?.permissions.includes(Permission.PosOpenPrice) ?? false;
  const roleAllowsOpenPrice = roles.find((role) => role.id === roleId)?.permissions.includes(Permission.PosOpenPrice) ?? false;

  const validate = (): FieldErrors => {
    const next: FieldErrors = {};
    if (!editing && !/^[a-z0-9][a-z0-9._-]{2,31}$/.test(username.trim().toLowerCase())) {
      next.username = "Username must be 3-32 characters: lowercase letters, digits, dot, dash, underscore.";
    }
    const nameProblem = requiredError(fullName, "the full name");
    if (nameProblem) next.full_name = nameProblem;
    const mailProblem = emailError(email, false);
    if (mailProblem) next.email = mailProblem;
    if (roleId === "") next.role_id = "Choose a role.";
    if (!editing && password !== "" && password.length < PASSWORD_MIN_LENGTH) {
      next.password = `Passwords need at least ${PASSWORD_MIN_LENGTH} characters.`;
    }
    if (!editing && pin !== "" && !PIN_PATTERN.test(pin)) next.pin = "PINs are 4 to 6 digits.";
    if (portalAccess && !canEnablePortal) next.password = "Set a password before enabling web portal access.";
    if (posAccess && !canEnablePos) next.pin = PIN_REQUIRED;
    return next;
  };

  const save = async () => {
    const problem = validate();
    setErrors(problem);
    if (Object.keys(problem).length > 0) {
      setError(problem.pin === PIN_REQUIRED ? PIN_REQUIRED : null);
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
          can_sell_open_price: openPriceSale,
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
      if (openPriceSale !== user.can_sell_open_price) body.can_sell_open_price = openPriceSale;
      if (active !== user.is_active) body.is_active = active;
      onSaved(Object.keys(body).length === 0 ? user : await usersApi.update(user.id, body));
    } catch (caught) {
      const fields = fieldErrors(caught);
      setErrors(fields);
      setError(Object.keys(fields).length > 0 ? null : errorMessage(caught, "Could not save the user."));
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
          required={!editing}
          value={username}
          disabled={editing}
          autoComplete="off"
          error={errors.username}
          onChange={(event) => {
            setUsername(event.target.value);
            setErrors((current) => ({ ...current, username: "" }));
          }}
        />
        <TextField
          label="Full name"
          required
          value={fullName}
          error={errors.full_name}
          onChange={(event) => {
            setFullName(event.target.value);
            setErrors((current) => ({ ...current, full_name: "" }));
          }}
        />
        <TextField
          label="Email"
          type="email"
          value={email}
          error={errors.email}
          onChange={(event) => {
            setEmail(event.target.value);
            setErrors((current) => ({ ...current, email: "" }));
          }}
        />
        <SelectField
          label="Role"
          required
          value={roleId}
          error={errors.role_id}
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
              error={errors.password}
              hint={`Web portal sign-in. At least ${PASSWORD_MIN_LENGTH} characters.`}
              onChange={(event) => {
                setPassword(event.target.value);
                setErrors((current) => ({ ...current, password: "" }));
              }}
            />
            <TextField
              label="POS PIN"
              type="password"
              inputMode="numeric"
              autoComplete="off"
              maxLength={6}
              value={pin}
              error={errors.pin === PIN_REQUIRED ? undefined : errors.pin}
              hint="Register unlock. 4 to 6 digits."
              onChange={(event) => {
                setPin(event.target.value.replace(/\D/g, ""));
                setErrors((current) => ({ ...current, pin: "" }));
              }}
            />
          </>
        ) : null}
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <Toggle label="POS access" description="Unlock registers with a PIN" checked={posAccess} onChange={setPosAccess} />
        <Toggle
          label="Web portal access"
          description="Sign in here with a password"
          checked={portalAccess}
          disabled={isSelf}
          onChange={setPortalAccess}
        />
        <Toggle
          label="Sell open price"
          description={
            roleAllowsOpenPrice
              ? "Included in this role."
              : "Type a price at the till for open-price items."
          }
          checked={roleAllowsOpenPrice || openPriceSale}
          disabled={roleAllowsOpenPrice || !actorCanGrantOpenPrice}
          onChange={setOpenPriceSale}
        />
        <Toggle label="Active" description="Disabled users cannot sign in" checked={active} disabled={isSelf} onChange={setActive} />
      </div>
      {error === PIN_REQUIRED && editing ? (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-warning/10 px-4 py-3 text-sm text-warning">
          <p role="alert">{error}</p>
          <button
            type="button"
            onClick={() => setSettingPin(true)}
            className="h-9 shrink-0 rounded-full bg-accent px-4 text-sm font-semibold text-white hover:bg-accent-hover"
          >
            Set PIN
          </button>
        </div>
      ) : (
        <ErrorNote message={error} />
      )}
      {settingPin && user ? (
        <CredentialModal
          user={user}
          kind="pin"
          elevated
          onClose={() => setSettingPin(false)}
          onSaved={(next) => {
            setHasPin(next.has_pin);
            setSettingPin(false);
            setError(null);
            onUpdated?.(next);
          }}
        />
      ) : null}
    </Modal>
  );
}
