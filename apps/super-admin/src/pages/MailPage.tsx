import { useEffect, useState } from "react";
import { Select } from "@ai-pos/ui";
import { ErrorNote, Field, PrimaryButton } from "../components/ui";
import { api, errorText } from "../lib/api";
import { useSession } from "../lib/session";

type Security = "ssl" | "starttls" | "none";

interface MailSettings {
  enabled: boolean;
  host: string;
  port: number;
  security: Security;
  username: string;
  password_set: boolean;
  from_address: string;
  from_name: string;
}

const EMPTY: MailSettings = {
  enabled: false,
  host: "",
  port: 465,
  security: "ssl",
  username: "",
  password_set: false,
  from_address: "",
  from_name: "AI POS",
};

export function MailPage() {
  const { operator } = useSession();
  const admin = operator?.role === "ADMIN";
  const [form, setForm] = useState<MailSettings>(EMPTY);
  const [password, setPassword] = useState("");
  const [reason, setReason] = useState("");
  const [testTo, setTestTo] = useState(operator?.email ?? "");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [tested, setTested] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .get<MailSettings>("/mail")
      .then(setForm)
      .catch((caught: unknown) => setError(errorText(caught, "Could not load the mailbox.")));
  }, []);

  const patch = (partial: Partial<MailSettings>) => setForm((current) => ({ ...current, ...partial }));

  const save = () => {
    setBusy(true);
    setSaved(false);
    api
      .patch<MailSettings>("/mail", { ...form, password, reason: reason.trim() })
      .then((row) => {
        setForm(row);
        setPassword("");
        setReason("");
        setError(null);
        setSaved(true);
      })
      .catch((caught: unknown) => setError(errorText(caught, "Could not save the mailbox.")))
      .finally(() => setBusy(false));
  };

  const sendTest = () => {
    setBusy(true);
    setTested(false);
    api
      .post<{ sent: boolean }>("/mail/test", { to: testTo.trim() })
      .then(() => {
        setError(null);
        setTested(true);
      })
      .catch((caught: unknown) => setError(errorText(caught, "The test email was not sent.")))
      .finally(() => setBusy(false));
  };

  return (
    <section className="max-w-xl">
      <h1 className="text-2xl font-semibold">Email</h1>
      <p className="mt-1 text-sm text-charcoal/60">
        The mailbox that sends password-reset codes to store users. For Spacemail use mail.spacemail.com, port 465, and SSL.
        Port 587 uses STARTTLS.
      </p>
      <div className="mt-6 space-y-4 rounded-3xl border border-line bg-white p-5">
        <label className="flex items-center gap-2 text-sm font-medium">
          <input
            type="checkbox"
            checked={form.enabled}
            disabled={!admin}
            onChange={(event) => patch({ enabled: event.target.checked })}
          />
          Send email
        </label>
        <Field
          label="Outgoing server"
          value={form.host}
          placeholder="mail.spacemail.com"
          disabled={!admin}
          onChange={(event) => patch({ host: event.target.value })}
        />
        <div className="grid grid-cols-2 gap-3">
          <Field
            label="Port"
            type="number"
            value={String(form.port)}
            disabled={!admin}
            onChange={(event) => patch({ port: Number(event.target.value) || 465 })}
          />
          <label className="block text-sm font-medium text-charcoal">
            Security
            <Select
              className="mt-1.5"
              aria-label="Security"
              value={form.security}
              disabled={!admin}
              onChange={(value) => {
                const security = value as Security;
                patch({ security, port: security === "ssl" ? 465 : security === "starttls" ? 587 : form.port });
              }}
              options={[
                { value: "ssl", label: "SSL (465)" },
                { value: "starttls", label: "STARTTLS (587)" },
                { value: "none", label: "None" },
              ]}
            />
          </label>
        </div>
        <Field
          label="Username"
          value={form.username}
          autoComplete="off"
          disabled={!admin}
          onChange={(event) => patch({ username: event.target.value })}
        />
        <Field
          label="Password"
          type="password"
          value={password}
          autoComplete="new-password"
          placeholder={form.password_set ? "Saved — leave blank to keep it" : ""}
          disabled={!admin}
          onChange={(event) => setPassword(event.target.value)}
        />
        <Field
          label="From address"
          type="email"
          value={form.from_address}
          placeholder="pos@yourdomain.com"
          disabled={!admin}
          onChange={(event) => patch({ from_address: event.target.value })}
        />
        <Field
          label="From name"
          value={form.from_name}
          disabled={!admin}
          onChange={(event) => patch({ from_name: event.target.value })}
        />
        {admin ? (
          <>
            <Field label="Reason (kept in the audit log)" value={reason} maxLength={500} onChange={(event) => setReason(event.target.value)} />
            <div className="flex items-center gap-3">
              <PrimaryButton disabled={busy || reason.trim().length < 3} onClick={save}>
                Save
              </PrimaryButton>
              {saved ? <p className="text-sm text-charcoal/60">Saved.</p> : null}
            </div>
            <div className="border-t border-line pt-4">
              <Field label="Send a test to" type="email" value={testTo} onChange={(event) => setTestTo(event.target.value)} />
              <div className="mt-3 flex items-center gap-3">
                <PrimaryButton disabled={busy || testTo.trim() === ""} onClick={sendTest}>
                  Send test
                </PrimaryButton>
                {tested ? <p className="text-sm text-charcoal/60">Test sent.</p> : null}
              </div>
            </div>
          </>
        ) : (
          <p className="text-sm text-charcoal/60">Only a console admin can change the mailbox.</p>
        )}
        <ErrorNote message={error} />
      </div>
    </section>
  );
}
