import { PASSWORD_MIN_LENGTH, PIN_PATTERN, type User } from "@ai-pos/shared-types";
import { useState } from "react";
import { ErrorNote, GhostButton, PrimaryButton, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { errorMessage, usersApi } from "./api";

interface CredentialModalProps {
  user: User;
  kind: "password" | "pin";
  onClose: () => void;
  onSaved: (user: User) => void;
  /** Renders above the user form when PIN setup is opened from that dialog. */
  elevated?: boolean;
}

export function CredentialModal({ user, kind, onClose, onSaved, elevated = false }: CredentialModalProps) {
  const [value, setValue] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const isPin = kind === "pin";

  const save = async () => {
    if (isPin && !PIN_PATTERN.test(value)) return setError("PINs are 4 to 6 digits.");
    if (!isPin && value.length < PASSWORD_MIN_LENGTH) {
      return setError(`Passwords need at least ${PASSWORD_MIN_LENGTH} characters.`);
    }
    if (value !== confirm) return setError("The two entries do not match.");
    setBusy(true);
    setError(null);
    try {
      onSaved(isPin ? await usersApi.resetPin(user.id, value) : await usersApi.resetPassword(user.id, value));
    } catch (caught) {
      setError(errorMessage(caught, "Could not update the credential."));
    } finally {
      setBusy(false);
    }
  };

  const sanitize = (raw: string) => (isPin ? raw.replace(/\D/g, "").slice(0, 6) : raw);

  return (
    <Modal
      title={isPin ? "Set POS PIN" : "Reset password"}
      subtitle={`${user.full_name} will be signed out of active sessions.`}
      onClose={onClose}
      elevated={elevated}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy} onClick={() => void save()}>
            {busy ? "Saving…" : isPin ? "Set PIN" : "Reset password"}
          </PrimaryButton>
        </>
      }
    >
      <div className="space-y-4">
        <TextField
          label={isPin ? "New PIN" : "New password"}
          type="password"
          inputMode={isPin ? "numeric" : undefined}
          autoComplete={isPin ? "off" : "new-password"}
          value={value}
          onChange={(event) => setValue(sanitize(event.target.value))}
        />
        <TextField
          label="Confirm"
          type="password"
          inputMode={isPin ? "numeric" : undefined}
          autoComplete={isPin ? "off" : "new-password"}
          value={confirm}
          onChange={(event) => setConfirm(sanitize(event.target.value))}
        />
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}
