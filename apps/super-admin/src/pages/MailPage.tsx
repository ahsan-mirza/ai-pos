import { useEffect, useState } from "react";
import { Select } from "@ai-pos/ui";
import { ErrorNote, Field, PrimaryButton } from "../components/ui";
import { ConsoleError, api, errorText } from "../lib/api";
import { useSession } from "../lib/session";

type Security = "ssl" | "starttls" | "none";
type FieldName = "host" | "port" | "username" | "password" | "from_address" | "from_name" | "reason" | "to";

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

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function isEmail(value: string): boolean {
  return EMAIL.test(value.trim());
}

function fieldName(loc: unknown): FieldName | null {
  const parts = Array.isArray(loc) ? loc.map(String) : [];
  const name = parts.filter((part) => part !== "body" && !/^\d+$/.test(part)).at(-1);
  if (
    name === "host" ||
    name === "port" ||
    name === "username" ||
    name === "password" ||
    name === "from_address" ||
    name === "from_name" ||
    name === "reason" ||
    name === "to"
  ) {
    return name;
  }
  return null;
}

function fieldSentence(name: FieldName, raw: string): string {
  const text = raw.replace(/^Value error,\s*/i, "").trim();
  if (name === "reason" && /at least 3/i.test(text)) return "Enter a reason of at least 3 characters.";
  if (name === "to") return "Enter an email address to send the test to.";
  if (name === "from_address" && /email/i.test(text)) return "Enter a valid From address.";
  if (name === "host") return "Enter the outgoing server.";
  if (name === "password") return "Enter the mailbox password.";
  return text.endsWith(".") ? text : `${text}.`;
}

function apiFieldErrors(caught: ConsoleError): Partial<Record<FieldName, string>> {
  const next: Partial<Record<FieldName, string>> = {};
  if (Array.isArray(caught.details)) {
    for (const item of caught.details) {
      if (item === null || typeof item !== "object") continue;
      const record = item as { loc?: unknown; msg?: unknown };
      const name = fieldName(record.loc);
      if (name === null) continue;
      next[name] = fieldSentence(name, String(record.msg ?? caught.message));
    }
  }
  if (Object.keys(next).length > 0) return next;
  if (caught.code === "invalid_email" && /test/i.test(caught.message)) {
    next.to = "Enter an email address to send the test to.";
  } else if (caught.code === "invalid_email") {
    next.from_address = "Enter a valid From address.";
  } else if (caught.code === "mail_incomplete" && /password/i.test(caught.message)) {
    next.password = "Enter the mailbox password.";
  } else if (caught.code === "mail_incomplete") {
    next.host = "Enter the outgoing server.";
    next.from_address = "Enter the From address.";
  }
  return next;
}

export function MailPage() {
  const { operator } = useSession();
  const admin = operator?.role === "ADMIN";
  const [form, setForm] = useState<MailSettings>(EMPTY);
  const [password, setPassword] = useState("");
  const [reason, setReason] = useState("");
  const [testTo, setTestTo] = useState(operator?.email ?? "");
  const [error, setError] = useState<string | null>(null);
  const [fields, setFields] = useState<Partial<Record<FieldName, string>>>({});
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
  const clearField = (name: FieldName) => setFields((current) => ({ ...current, [name]: undefined }));

  const saveErrors = (): Partial<Record<FieldName, string>> => {
    const next: Partial<Record<FieldName, string>> = {};
    if (form.enabled && form.host.trim() === "") next.host = "Enter the outgoing server.";
    if (form.enabled && form.from_address.trim() === "") next.from_address = "Enter the From address.";
    else if (form.from_address.trim() !== "" && !isEmail(form.from_address)) {
      next.from_address = "Enter a valid From address.";
    }
    if (form.enabled && password === "" && !form.password_set) next.password = "Enter the mailbox password.";
    if (reason.trim().length > 0 && reason.trim().length < 3) next.reason = "Enter a reason of at least 3 characters.";
    return next;
  };

  const save = () => {
    const local = saveErrors();
    setFields(local);
    setSaved(false);
    if (Object.keys(local).length > 0) {
      setError(null);
      return;
    }
    setBusy(true);
    api
      .patch<MailSettings>("/mail", {
        enabled: form.enabled,
        host: form.host,
        port: form.port,
        security: form.security,
        username: form.username,
        password,
        from_address: form.from_address,
        from_name: form.from_name,
        reason: reason.trim(),
      })
      .then((row) => {
        setForm(row);
        setPassword("");
        setReason("");
        setError(null);
        setFields({});
        setSaved(true);
      })
      .catch((caught: unknown) => {
        const mapped = caught instanceof ConsoleError ? apiFieldErrors(caught) : {};
        if (Object.keys(mapped).length > 0) {
          setFields(mapped);
          setError(null);
        } else {
          setError(errorText(caught, "Could not save the mailbox."));
        }
      })
      .finally(() => setBusy(false));
  };

  const sendTest = () => {
    setTested(false);
    if (testTo.trim() === "" || !isEmail(testTo)) {
      setFields((current) => ({ ...current, to: "Enter an email address to send the test to." }));
      setError(null);
      return;
    }
    setBusy(true);
    api
      .post<{ sent: boolean }>("/mail/test", { to: testTo.trim() })
      .then(() => {
        setError(null);
        clearField("to");
        setTested(true);
      })
      .catch((caught: unknown) => {
        const mapped = caught instanceof ConsoleError ? apiFieldErrors(caught) : {};
        if (mapped.to) {
          setFields((current) => ({ ...current, to: mapped.to }));
          setError(null);
        } else {
          setError(errorText(caught, "The test email was not sent."));
        }
      })
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
          error={fields.host}
          onChange={(event) => {
            clearField("host");
            patch({ host: event.target.value });
          }}
        />
        <div className="grid grid-cols-2 gap-3">
          <Field
            label="Port"
            type="number"
            value={String(form.port)}
            disabled={!admin}
            error={fields.port}
            onChange={(event) => {
              clearField("port");
              patch({ port: Number(event.target.value) || 465 });
            }}
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
          error={fields.username}
          onChange={(event) => {
            clearField("username");
            patch({ username: event.target.value });
          }}
        />
        <Field
          label="Password"
          type="password"
          value={password}
          autoComplete="new-password"
          placeholder={form.password_set ? "Saved — leave blank to keep it" : ""}
          disabled={!admin}
          error={fields.password}
          onChange={(event) => {
            clearField("password");
            setPassword(event.target.value);
          }}
        />
        <Field
          label="From address"
          type="email"
          value={form.from_address}
          placeholder="pos@yourdomain.com"
          disabled={!admin}
          error={fields.from_address}
          onChange={(event) => {
            clearField("from_address");
            patch({ from_address: event.target.value });
          }}
        />
        <Field
          label="From name"
          value={form.from_name}
          disabled={!admin}
          error={fields.from_name}
          onChange={(event) => {
            clearField("from_name");
            patch({ from_name: event.target.value });
          }}
        />
        {admin ? (
          <>
            <Field
              label="Reason (kept in the audit log)"
              value={reason}
              maxLength={500}
              error={fields.reason}
              onChange={(event) => {
                clearField("reason");
                setReason(event.target.value);
              }}
            />
            <div className="flex items-center gap-3">
              <PrimaryButton disabled={busy || reason.trim().length < 3} onClick={save}>
                Save
              </PrimaryButton>
              {saved ? <p className="text-sm text-charcoal/60">Saved.</p> : null}
            </div>
            <div className="border-t border-line pt-4">
              <Field
                label="Send a test to"
                type="email"
                value={testTo}
                error={fields.to}
                onChange={(event) => {
                  clearField("to");
                  setTestTo(event.target.value);
                }}
              />
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
