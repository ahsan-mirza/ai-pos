import {
  PROVIDER_LABELS,
  Permission,
  type BackgroundJob,
  type MessageChannel,
  type MessageTemplate,
  type MessagingSettings,
  type OutboundMessage,
} from "@ai-pos/shared-types";
import { Play, Send } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ErrorNote, GhostButton, PrimaryButton, SelectField, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { Toggle } from "../../components/ui/Toggle";
import { apiGet, apiPost, apiPut } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { formatDate } from "../inventory/shared";
import { errorMessage } from "../users/api";

const action =
  "inline-flex h-[38px] shrink-0 items-center justify-center gap-2 rounded-full px-4 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-40";

const eventLabels: Record<string, string> = {
  receipt: "Digital receipt after a sale",
  statement: "Statements of account",
  overdue_reminder: "Overdue payment reminders",
  warranty_expiry: "Warranty expiring soon",
  repair_ready: "Repair ready for collection",
  repair_estimate: "Repair estimate to approve",
  layaway_reminder: "Layaway balance reminders",
};

const messageJobs = new Set(["dispatch_messages", "warranty_reminders", "layaway_reminders", "overdue_reminders"]);

const channels: { id: MessageChannel; label: string }[] = [
  { id: "whatsapp", label: "WhatsApp" },
  { id: "sms", label: "SMS" },
  { id: "email", label: "Email" },
];

export interface OutboxCounts {
  SENT: number;
  FAILED: number;
  QUEUED: number;
  SKIPPED: number;
}

export interface OutboxSummary {
  transactional: OutboxCounts;
  marketing: OutboxCounts;
}

const emptyCounts: OutboxCounts = { SENT: 0, FAILED: 0, QUEUED: 0, SKIPPED: 0 };

export function useOutboxSummary(): OutboxSummary | null {
  const [summary, setSummary] = useState<OutboxSummary | null>(null);
  useEffect(() => {
    void apiGet<OutboxSummary>("/api/v1/messaging/summary").then(setSummary).catch(() => setSummary(null));
  }, []);
  return summary;
}

export function CountGrid({ title, counts, note }: { title: string; counts: OutboxCounts; note: string }) {
  return (
    <section className="rounded-card border border-line bg-white p-4 shadow-sm">
      <h2 className="text-sm font-semibold">{title}</h2>
      <p className="mt-1 text-xs leading-5 text-charcoal/50">{note}</p>
      <dl className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        {(
          [
            ["Accepted", counts.SENT],
            ["Failed", counts.FAILED],
            ["Pending", counts.QUEUED],
            ["Skipped", counts.SKIPPED],
          ] as const
        ).map(([label, value]) => (
          <div key={label}>
            <dt className="text-xs text-charcoal/50">{label}</dt>
            <dd className="text-xl font-semibold tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

export function ServerFallback() {
  const [settings, setSettings] = useState<MessagingSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    void apiGet<MessagingSettings>("/api/v1/messaging/settings")
      .then(setSettings)
      .catch((caught) => setError(errorMessage(caught, "Fallback providers could not be loaded.")));
  }, []);

  const save = async (channel: MessageChannel, provider: string) => {
    try {
      setSettings(await apiPut<MessagingSettings>("/api/v1/messaging/settings", { providers: { [channel]: provider } }));
      setNotice("Server fallback saved. A saved provider account still takes priority.");
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "The fallback was not saved."));
    }
  };

  return (
    <section className="grid gap-3">
      <div>
        <h2 className="text-lg font-semibold">Server fallback</h2>
        <p className="mt-1 max-w-2xl text-sm leading-6 text-charcoal/60">
          Used only when a channel has no saved account above. Receipts and campaigns share that saved account.
        </p>
      </div>
      <ErrorNote message={error} />
      {notice ? <p className="text-sm text-charcoal/70">{notice}</p> : null}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {channels.map(({ id, label }) => (
          <article key={id} className="rounded-card border border-line bg-white p-4 shadow-sm">
            <h3 className="text-sm font-semibold">{label}</h3>
            <SelectField
              className="mt-3"
              label="Fallback provider"
              value={settings?.providers[id] ?? "log"}
              options={(settings?.available[id] ?? ["log"]).map((value) => ({
                value,
                label: PROVIDER_LABELS[value] ?? value,
              }))}
              onChange={(value) => void save(id, value)}
            />
          </article>
        ))}
      </div>
    </section>
  );
}

export function AutomationsPanel() {
  const { can } = useAuth();
  const canJobs = can(Permission.SettingsManage);
  const [settings, setSettings] = useState<MessagingSettings | null>(null);
  const [templates, setTemplates] = useState<MessageTemplate[]>([]);
  const [jobs, setJobs] = useState<BackgroundJob[]>([]);
  const [editing, setEditing] = useState<MessageTemplate | null>(null);
  const [testChannel, setTestChannel] = useState<MessageChannel>("whatsapp");
  const [testTo, setTestTo] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [nextSettings, nextTemplates] = await Promise.all([
      apiGet<MessagingSettings>("/api/v1/messaging/settings"),
      apiGet<MessageTemplate[]>("/api/v1/messaging/templates"),
    ]);
    setSettings(nextSettings);
    setTemplates(nextTemplates);
    if (canJobs) setJobs(await apiGet<BackgroundJob[]>("/api/v1/jobs"));
  }, [canJobs]);

  useEffect(() => {
    void load().catch((caught) => setError(errorMessage(caught, "Automations could not be loaded.")));
  }, [load]);

  const saveEvent = async (key: string, enabled: boolean) => {
    setSettings(await apiPut<MessagingSettings>("/api/v1/messaging/settings", { events: { [key]: enabled } }));
  };

  const sendTest = async () => {
    if (sending) return;
    setSending(true);
    setError(null);
    try {
      const result = await apiPost<OutboundMessage>("/api/v1/messaging/test", { channel: testChannel, to: testTo.trim() });
      setNotice(
        result.status === "SENT"
          ? "Test message accepted by the provider. Delivery is shown only when a callback arrives."
          : `Test message ${result.status.toLowerCase()}${result.last_error ? `: ${result.last_error}` : ""}`,
      );
    } catch (caught) {
      setError(errorMessage(caught, "Could not send the test message."));
    } finally {
      setSending(false);
    }
  };

  const relevant = jobs.filter((job) => messageJobs.has(job.name));

  return (
    <div className="grid gap-4">
      <ErrorNote message={error} />
      {notice ? <p className="text-sm text-charcoal/70">{notice}</p> : null}
      <section className="rounded-card border border-line bg-white p-4 shadow-sm">
        <h2 className="text-lg font-semibold">Automatic messages</h2>
        <p className="text-sm text-charcoal/60">Sent only to customers who opted in on that channel. The existing jobs still send them.</p>
        <ul className="mt-3 divide-y divide-line">
          {Object.keys(eventLabels).map((key) => {
            const template = templates.find((row) => row.key === key);
            const on = settings?.events[key] ?? false;
            return (
              <li key={key} className="flex flex-wrap items-center gap-3 py-3">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium">{eventLabels[key]}</p>
                  <p className="truncate text-xs text-charcoal/50">{template?.body ?? "No template"}</p>
                </div>
                <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${on ? "bg-emerald-50 text-emerald-700" : "bg-surface text-charcoal/50"}`}>
                  {on ? "On" : "Off"}
                </span>
                <button
                  type="button"
                  role="switch"
                  aria-checked={on}
                  aria-label={eventLabels[key]}
                  onClick={() => void saveEvent(key, !on).catch((caught) => setError(errorMessage(caught, "The automation was not saved.")))}
                  className={`relative h-6 w-11 shrink-0 rounded-full ${on ? "bg-accent" : "bg-charcoal/15"}`}
                >
                  <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow ${on ? "left-5" : "left-0.5"}`} />
                </button>
                {template ? (
                  <GhostButton onClick={() => setEditing(template)}>Edit</GhostButton>
                ) : null}
              </li>
            );
          })}
        </ul>
      </section>
      <section className="rounded-card border border-line bg-white p-4 shadow-sm">
        <h2 className="text-lg font-semibold">Send a test</h2>
        <p className="text-sm text-charcoal/60">Uses the saved provider account and writes a row in the outbox.</p>
        <div className="mt-3 flex flex-wrap gap-2">
          {channels.map(({ id, label }) => (
            <button
              key={id}
              type="button"
              aria-pressed={testChannel === id}
              onClick={() => setTestChannel(id)}
              className={`${action} ${testChannel === id ? "bg-accent text-white" : "border border-line bg-white"}`}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center">
          <input
            value={testTo}
            onChange={(event) => setTestTo(event.target.value)}
            placeholder={testChannel === "email" ? "name@example.com" : "+971501234567"}
            aria-label="Send the test to"
            className="h-10 w-full max-w-sm rounded-xl border border-line bg-surface px-3 text-sm"
          />
          <button type="button" disabled={sending || testTo.trim().length < 3} onClick={() => void sendTest()} className={`${action} bg-accent text-white`}>
            <Send size={16} aria-hidden="true" /> {sending ? "Sending…" : "Send test"}
          </button>
        </div>
      </section>
      {canJobs ? (
        <section className="rounded-card border border-line bg-white p-4 shadow-sm">
          <h2 className="text-lg font-semibold">Message jobs</h2>
          <p className="text-sm text-charcoal/60">These are the existing schedulers. Running one here does not create another job.</p>
          <ul className="mt-3 divide-y divide-line">
            {relevant.map((job) => (
              <li key={job.name} className="flex flex-wrap items-center gap-3 py-3 text-sm">
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{job.description}</p>
                  <p className="text-xs text-charcoal/50">
                    {job.schedule}
                    {job.last_finished_at ? ` · last ran ${formatDate(job.last_finished_at)}` : " · not run yet"}
                    {job.last_result ? ` · ${job.last_result}` : ""}
                  </p>
                </div>
                <span className="rounded-full bg-surface px-2.5 py-0.5 text-[11px] font-semibold ring-1 ring-line">
                  {job.running ? "running" : (job.last_status ?? "idle")}
                </span>
                <button
                  type="button"
                  aria-label={`Run ${job.description} now`}
                  onClick={() =>
                    void apiPost(`/api/v1/jobs/${job.name}/run`, {})
                      .then(() => load())
                      .catch((caught) => setError(errorMessage(caught, "Could not run the job.")))
                  }
                  className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-line"
                >
                  <Play size={14} aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {editing ? (
        <TemplateEditor
          template={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            setNotice("Message text saved.");
            void load();
          }}
        />
      ) : null}
    </div>
  );
}

export function TransactionalTemplates() {
  const [templates, setTemplates] = useState<MessageTemplate[]>([]);
  const [editing, setEditing] = useState<MessageTemplate | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setTemplates(await apiGet<MessageTemplate[]>("/api/v1/messaging/templates"));
  }, []);

  useEffect(() => {
    void load().catch((caught) => setError(errorMessage(caught, "Transactional templates could not be loaded.")));
  }, [load]);

  const known = templates.filter((row) => eventLabels[row.key]);

  return (
    <section className="rounded-card border border-line bg-white p-4 shadow-sm">
      <h2 className="text-lg font-semibold">Transactional templates</h2>
      <p className="mt-1 text-sm text-charcoal/60">Used by receipts, statements, and the scheduled reminders. Placeholders stay the same.</p>
      <ErrorNote message={error} />
      <ul className="mt-3 divide-y divide-line">
        {known.map((template) => (
          <li key={template.key} className="flex flex-wrap items-center gap-3 py-3 text-sm">
            <div className="min-w-0 flex-1">
              <p className="font-medium">{eventLabels[template.key] ?? template.name}</p>
              <p className="truncate text-xs text-charcoal/50">{template.body}</p>
            </div>
            <span className="text-xs text-charcoal/50">{template.is_active ? "Active" : "Inactive"}</span>
            <GhostButton onClick={() => setEditing(template)}>Edit</GhostButton>
          </li>
        ))}
      </ul>
      {editing ? (
        <TemplateEditor
          template={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            void load();
          }}
        />
      ) : null}
    </section>
  );
}

function TemplateEditor({ template, onClose, onSaved }: { template: MessageTemplate; onClose: () => void; onSaved: () => void }) {
  const [subject, setSubject] = useState(template.subject);
  const [body, setBody] = useState(template.body);
  const [active, setActive] = useState(template.is_active);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const placeholders = [...new Set([...template.body.matchAll(/\{\{\s*([a-z_]+)\s*\}\}/g)].map((match) => match[1]))];

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await apiPut(`/api/v1/messaging/templates/${template.key}`, { subject, body, is_active: active });
      onSaved();
    } catch (caught) {
      setError(errorMessage(caught, "Could not save the message."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title={template.name}
      subtitle="Placeholders in double braces are filled in for each customer."
      onClose={onClose}
      width="lg"
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy} onClick={() => void save()}>
            {busy ? "Saving…" : "Save"}
          </PrimaryButton>
        </>
      }
    >
      <div className="space-y-4">
        <TextField label="Email subject" value={subject} maxLength={200} onChange={(event) => setSubject(event.target.value)} />
        <label className="block text-sm font-medium">
          Message
          <textarea
            value={body}
            rows={5}
            maxLength={1000}
            onChange={(event) => setBody(event.target.value)}
            className="mt-1.5 h-32 w-full rounded-xl border border-transparent bg-surface px-4 py-3 text-sm font-normal focus:border-accent focus:bg-white focus:outline-none"
          />
        </label>
        <p className="flex flex-wrap gap-1.5 text-xs">
          {placeholders.map((name) => (
            <code key={name} className="rounded-full bg-surface px-2 py-0.5">{`{{${name}}}`}</code>
          ))}
        </p>
        <Toggle label="Active" description="Inactive messages are never sent" checked={active} onChange={setActive} />
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}

export function OutboxPanel({ campaignRows }: { campaignRows: { id: string; campaign_id: string; phone: string; status: string; failure_reason: string | null }[] }) {
  const [rows, setRows] = useState<OutboundMessage[]>([]);
  const [channel, setChannel] = useState("");
  const [kind, setKind] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void apiGet<OutboundMessage[]>("/api/v1/messaging/outbox?limit=200")
      .then(setRows)
      .catch((caught) => setError(errorMessage(caught, "The outbox could not be loaded.")));
  }, []);

  const visible = useMemo(
    () =>
      rows.filter((row) => {
        if (channel && row.channel !== channel) return false;
        if (status && row.status !== status) return false;
        const marketing = row.template_key === "campaign" || row.template_key === "coupon_issued";
        if (kind === "marketing" && !marketing) return false;
        if (kind === "transactional" && marketing) return false;
        return true;
      }),
    [rows, channel, kind, status],
  );

  return (
    <div className="grid gap-4">
      <ErrorNote message={error} />
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <SelectField
          label="Channel"
          value={channel}
          placeholder="All channels"
          onChange={setChannel}
          options={[{ value: "", label: "All channels" }, ...channels.map((item) => ({ value: item.id, label: item.label }))]}
        />
        <SelectField
          label="Message type"
          value={kind}
          onChange={setKind}
          options={[
            { value: "", label: "All types" },
            { value: "transactional", label: "Transactional" },
            { value: "marketing", label: "Marketing" },
          ]}
        />
        <SelectField
          label="Status"
          value={status}
          onChange={setStatus}
          options={[
            { value: "", label: "All statuses" },
            { value: "QUEUED", label: "Pending" },
            { value: "SENT", label: "Accepted" },
            { value: "FAILED", label: "Failed" },
            { value: "SKIPPED", label: "Skipped" },
          ]}
        />
      </div>
      <section className="overflow-x-auto rounded-card border border-line bg-white p-4 shadow-sm">
        <h2 className="text-lg font-semibold">Outbox</h2>
        <p className="mt-1 text-sm text-charcoal/60">Accepted means the provider took the message. Delivered and read are not shown here.</p>
        <table className="mt-3 w-full min-w-[640px] text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-charcoal/50">
            <tr>
              <th className="pb-2 font-medium">When</th>
              <th className="pb-2 font-medium">Type</th>
              <th className="pb-2 font-medium">To</th>
              <th className="pb-2 font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((row) => {
              const marketing = row.template_key === "campaign" || row.template_key === "coupon_issued";
              return (
                <tr key={row.id} className="border-t border-line align-top">
                  <td className="py-2 text-charcoal/70">{formatDate(row.created_at)}</td>
                  <td className="py-2">{marketing ? "Marketing" : "Transactional"} · {row.channel}</td>
                  <td className="max-w-xs py-2">
                    <span className="block truncate">{row.customer_name ?? row.to_address}</span>
                    {row.last_error ? <span className="block text-xs text-rose-700">{row.last_error}</span> : null}
                  </td>
                  <td className="py-2">{row.status.toLowerCase()}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {visible.length === 0 ? <p className="py-6 text-sm text-charcoal/60">No messages match these filters.</p> : null}
      </section>
      <section className="overflow-x-auto rounded-card border border-line bg-white p-4 shadow-sm">
        <h2 className="text-lg font-semibold">Campaign delivery</h2>
        <p className="mt-1 text-sm text-charcoal/60">Delivered and read appear only after a provider callback.</p>
        <table className="mt-3 w-full min-w-[640px] text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-charcoal/50">
            <tr>
              <th className="pb-2 font-medium">Phone</th>
              <th className="pb-2 font-medium">Status</th>
              <th className="pb-2 font-medium">Failure</th>
            </tr>
          </thead>
          <tbody>
            {campaignRows.map((row) => (
              <tr key={row.id} className="border-t border-line">
                <td className="py-2">{row.phone || "—"}</td>
                <td className="py-2">{row.status}</td>
                <td className="py-2 text-charcoal/60">{row.failure_reason ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {campaignRows.length === 0 ? <p className="py-6 text-sm text-charcoal/60">No campaign recipients yet.</p> : null}
      </section>
    </div>
  );
}

export { emptyCounts };
