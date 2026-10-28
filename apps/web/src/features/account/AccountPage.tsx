import { PASSWORD_MIN_LENGTH, type TokenResponse, type User } from "@ai-pos/shared-types";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ErrorNote, PrimaryButton, TextField } from "../../components/ui/Field";
import { ProfileAvatar } from "../../components/ui/ProfileAvatar";
import { apiDelete, apiPatch, apiPost, apiUpload } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useCurrency } from "../../lib/currency";
import { errorMessage } from "../users/api";

const regionNames = new Intl.DisplayNames(["en"], { type: "region" });

function countryName(code: string | null | undefined): string {
  if (!code) return "Not recorded";
  try {
    return regionNames.of(code) ?? code;
  } catch {
    return code;
  }
}

function when(value: string | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function AccountPage() {
  const { user, refreshUser, replaceSession } = useAuth();
  const { settings } = useCurrency();
  const [name, setName] = useState(user?.full_name ?? "");
  const [currentPassword, setCurrentPassword] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState<"name" | "password" | "photo" | null>(null);
  const photoInput = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (user) setName(user.full_name);
  }, [user]);

  const nameDirty = user !== null && name.trim() !== user.full_name;
  const passwordDirty = currentPassword !== "" || password !== "" || confirm !== "";

  useEffect(() => {
    if (!nameDirty && !passwordDirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [nameDirty, passwordDirty]);

  if (user === null) return null;

  const saveName = async (event: FormEvent) => {
    event.preventDefault();
    if (!nameDirty || busy !== null) return;
    setBusy("name");
    setError(null);
    setNotice(null);
    try {
      await apiPatch<User>("/api/v1/auth/me", { full_name: name.trim() });
      await refreshUser();
      setNotice("Your name was saved.");
    } catch (caught) {
      setError(errorMessage(caught, "Could not save your name."));
    } finally {
      setBusy(null);
    }
  };

  const savePhoto = async (file: File) => {
    if (busy !== null) return;
    setBusy("photo");
    setError(null);
    setNotice(null);
    try {
      const form = new FormData();
      form.append("file", file);
      await apiUpload<User>("/api/v1/auth/me/avatar", form);
      await refreshUser();
      setNotice("Your photo was saved.");
    } catch (caught) {
      setError(errorMessage(caught, "Could not save your photo."));
    } finally {
      setBusy(null);
      if (photoInput.current) photoInput.current.value = "";
    }
  };

  const removePhoto = async () => {
    if (busy !== null || !user.avatar_url) return;
    setBusy("photo");
    setError(null);
    setNotice(null);
    try {
      await apiDelete("/api/v1/auth/me/avatar");
      await refreshUser();
      setNotice("Your photo was removed.");
    } catch (caught) {
      setError(errorMessage(caught, "Could not remove your photo."));
    } finally {
      setBusy(null);
    }
  };

  const savePassword = async (event: FormEvent) => {
    event.preventDefault();
    if (busy !== null) return;
    if (password.length < PASSWORD_MIN_LENGTH) {
      setError(`Use at least ${PASSWORD_MIN_LENGTH} characters.`);
      return;
    }
    if (password !== confirm) {
      setError("The new password and the confirmation do not match.");
      return;
    }
    setBusy("password");
    setError(null);
    setNotice(null);
    try {
      const next = await apiPost<TokenResponse>("/api/v1/auth/me/password", {
        current_password: currentPassword,
        password,
      });
      replaceSession(next);
      setCurrentPassword("");
      setPassword("");
      setConfirm("");
      setNotice("Your password was changed. Other signed-in browsers need to sign in again.");
    } catch (caught) {
      setError(errorMessage(caught, "Could not change the password."));
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="mx-auto grid max-w-3xl gap-4">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">Your account</h1>
        <p className="mt-1 text-sm text-charcoal/60">Your sign-in details. Store settings stay on the business settings page.</p>
      </header>
      {notice ? <p className="rounded-2xl bg-accent/10 px-4 py-3 text-sm font-medium text-charcoal">{notice}</p> : null}
      <ErrorNote message={error} />

      <form onSubmit={(event) => void saveName(event)} className="rounded-card border border-line bg-white p-6">
        <h2 className="text-lg font-semibold">Profile</h2>
        <div className="mt-4 flex items-center gap-4">
          <ProfileAvatar name={user.full_name} url={user.avatar_url} className="h-16 w-16 text-base" />
          <div className="flex flex-wrap gap-2">
            <PrimaryButton type="button" disabled={busy !== null} onClick={() => photoInput.current?.click()}>
              {busy === "photo" ? "Saving…" : "Upload photo"}
            </PrimaryButton>
            {user.avatar_url ? (
              <button
                type="button"
                disabled={busy !== null}
                onClick={() => void removePhoto()}
                className="h-10 rounded-full px-4 text-sm font-medium text-charcoal/70 hover:text-charcoal disabled:opacity-50"
              >
                Remove
              </button>
            ) : null}
          </div>
          <input
            ref={photoInput}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            className="sr-only"
            aria-label="Profile photo"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void savePhoto(file);
            }}
          />
        </div>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <TextField label="Full name" value={name} autoComplete="name" onChange={(event) => setName(event.target.value)} required />
          <TextField label="Email" value={user.email} readOnly disabled hint="Email changes need a verified reset. This address stays as it is." />
          <TextField label="Username" value={user.username} readOnly disabled />
          <TextField label="Role" value={user.role.name} readOnly disabled hint="A manager changes roles from Users. This page cannot." />
          <TextField label="Status" value={user.is_active ? "Active" : "Inactive"} readOnly disabled />
          <TextField label="Branch access" value={user.store_id ? "One branch" : "All branches"} readOnly disabled />
          <TextField label="Created" value={when(user.created_at)} readOnly disabled />
          <TextField label="Last sign-in" value={when(user.last_login_at)} readOnly disabled />
        </div>
        <div className="mt-4 flex justify-end">
          <PrimaryButton type="submit" disabled={!nameDirty || busy !== null}>
            {busy === "name" ? "Saving…" : "Save name"}
          </PrimaryButton>
        </div>
      </form>

      <form onSubmit={(event) => void savePassword(event)} className="rounded-card border border-line bg-white p-6">
        <h2 className="text-lg font-semibold">Password</h2>
        <p className="mt-1 text-sm text-charcoal/60">Enter the current password. This browser stays signed in. Other sessions are signed out.</p>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <TextField
            label="Current password"
            type="password"
            autoComplete="current-password"
            value={currentPassword}
            onChange={(event) => setCurrentPassword(event.target.value)}
          />
          <span className="hidden sm:block" />
          <TextField
            label="New password"
            type="password"
            autoComplete="new-password"
            value={password}
            hint={`At least ${PASSWORD_MIN_LENGTH} characters.`}
            onChange={(event) => setPassword(event.target.value)}
          />
          <TextField
            label="Confirm new password"
            type="password"
            autoComplete="new-password"
            value={confirm}
            onChange={(event) => setConfirm(event.target.value)}
          />
        </div>
        <div className="mt-4 flex justify-end">
          <PrimaryButton type="submit" disabled={busy !== null || currentPassword === "" || password === ""}>
            {busy === "password" ? "Saving…" : "Change password"}
          </PrimaryButton>
        </div>
      </form>

      <section className="rounded-card border border-line bg-white p-6">
        <h2 className="text-lg font-semibold">This business</h2>
        <p className="mt-1 text-sm text-charcoal/60">Read-only here. Store managers change these under business settings.</p>
        <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-charcoal/50">Business</dt>
            <dd className="font-medium">{settings?.legal_name || "—"}</dd>
          </div>
          <div>
            <dt className="text-charcoal/50">Store code</dt>
            <dd className="font-mono font-medium">{settings?.store_code || "—"}</dd>
          </div>
          <div>
            <dt className="text-charcoal/50">Country</dt>
            <dd className="font-medium">{countryName(settings?.country)}</dd>
          </div>
          <div>
            <dt className="text-charcoal/50">Currency</dt>
            <dd className="font-medium">{settings?.currency ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-charcoal/50">Tax registration number</dt>
            <dd className="font-medium">{settings?.trn || "Not registered"}</dd>
          </div>
        </dl>
      </section>
    </section>
  );
}
