import {
  PROVIDER_LABELS,
  Permission,
  type BackgroundJob,
  type MessageChannel,
  type MessageTemplate,
  type MessagingSettings,
  type OutboundMessage,
} from "@ai-pos/shared-types";
import { Mail, MessageCircle, Play, Send, Smartphone, type LucideIcon } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { ErrorNote, GhostButton, PrimaryButton, SelectField, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { Toast } from "../../components/ui/Toast";
import { Toggle } from "../../components/ui/Toggle";
import { apiGet, apiPost, apiPut } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { formatDate } from "../inventory/shared";
import { errorMessage } from "../users/api";

const channels: { id: MessageChannel; label: string; icon: LucideIcon }[] = [
  { id: "whatsapp", label: "WhatsApp", icon: MessageCircle },
  { id: "sms", label: "SMS", icon: Smartphone },
  { id: "email", label: "Email", icon: Mail },
];

const eventLabels: Record<string, string> = {
  receipt: "Digital receipt after a sale",
  statement: "Statements of account",
  overdue_reminder: "Overdue payment reminders",
  warranty_expiry: "Warranty expiring soon",
  repair_ready: "Repair ready for collection",
  repair_estimate: "Repair estimate to approve",
  layaway_reminder: "Layaway balance reminders",
};

const statusTone: Record<OutboundMessage["status"], string> = {
  SENT: "bg-charcoal text-white",
  QUEUED: "bg-surface text-charcoal ring-1 ring-line",
  FAILED: "bg-accent text-white",
  SKIPPED: "bg-white text-charcoal/60 ring-1 ring-line",
};

export function MessagingPage() {
  const { can } = useAuth();
  const [settings, setSettings] = useState<MessagingSettings | null>(null);
  const [templates, setTemplates] = useState<MessageTemplate[]>([]);
  const [outbox, setOutbox] = useState<OutboundMessage[]>([]);
  const [jobs, setJobs] = useState<BackgroundJob[]>([]);
  const [editing, setEditing] = useState<MessageTemplate | null>(null);
  const [testChannel, setTestChannel] = useState<MessageChannel>("whatsapp");
  const [testTo, setTestTo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);
  const canJobs = can(Permission.SettingsManage);

  const load = useCallback(async () => {
    try {
      const [nextSettings, nextTemplates, nextOutbox] = await Promise.all([
        apiGet<MessagingSettings>("/api/v1/messaging/settings"),
        apiGet<MessageTemplate[]>("/api/v1/messaging/templates"),
        apiGet<OutboundMessage[]>("/api/v1/messaging/outbox?limit=50"),
      ]);
      setSettings(nextSettings);
      setTemplates(nextTemplates);
      setOutbox(nextOutbox);
      if (canJobs) setJobs(await apiGet<BackgroundJob[]>("/api/v1/jobs"));
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "Could not load messaging settings."));
    }
  }, [canJobs]);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async (patch: { providers?: Record<string, string>; events?: Record<string, boolean> }) => {
    try {
      setSettings(await apiPut<MessagingSettings>("/api/v1/messaging/settings", patch));
      setToast("Messaging settings saved.");
    } catch (caught) {
      setError(errorMessage(caught, "Could not save messaging settings."));
    }
  };

  const sendTest = async () => {
    try {
      const result = await apiPost<OutboundMessage>("/api/v1/messaging/test", { channel: testChannel, to: testTo.trim() });
      setToast(result.status === "SENT" ? "Test message sent." : `Test message ${result.status.toLowerCase()}: ${result.last_error ?? ""}`);
      void load();
    } catch (caught) {
      setError(errorMessage(caught, "Could not send the test message."));
    }
  };

  const runJob = async (name: string) => {
    try {
      await apiPost<BackgroundJob>(`/api/v1/jobs/${name}/run`, {});
      setToast("Job finished.");
      void load();
    } catch (caught) {
      setError(errorMessage(caught, "Could not run the job."));
    }
  };

  const sent = outbox.filter((row) => row.status === "SENT").length;
  const failed = outbox.filter((row) => row.status === "FAILED").length;

  return (
    <section className="space-y-4">
      <ErrorNote message={error} />
      <div className="grid gap-4 md:grid-cols-3">
        {channels.map(({ id, label, icon: Icon }) => (
          <article key={id} className="rounded-card border border-line bg-white p-6">
            <div className="flex items-center gap-3">
              <span className="flex h-10 w-10 items-center justify-center rounded-full bg-charcoal text-white">
                <Icon size={18} aria-hidden="true" />
              </span>
              <div>
                <h3 className="font-semibold">{label}</h3>
                <p className="text-xs text-charcoal/50">Credentials come from the server environment.</p>
              </div>
            </div>
            <SelectField
              className="mt-4"
              label="Provider"
              value={settings?.providers[id] ?? "log"}
              options={(settings?.available[id] ?? ["log"]).map((value) => ({ value, label: PROVIDER_LABELS[value] ?? value }))}
              onChange={(value) => void save({ providers: { [id]: value } })}
            />
          </article>
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <article className="rounded-card border border-line bg-white p-6">
          <h2 className="text-xl font-semibold">Automatic messages</h2>
          <p className="text-sm text-charcoal/60">Sent only to customers who opted in on that channel.</p>
          <div className="mt-4 space-y-3">
            {Object.keys(eventLabels).map((key) => {
              const template = templates.find((row) => row.key === key);
              return (
                <div key={key} className="flex items-center gap-3 rounded-2xl bg-surface p-3">
                  <div className="min-w-0 flex-1">
                    <Toggle
                      label={eventLabels[key] ?? key}
                      description={template ? template.body.slice(0, 90) + (template.body.length > 90 ? "…" : "") : ""}
                      checked={settings?.events[key] ?? false}
                      onChange={(value) => void save({ events: { [key]: value } })}
                    />
                  </div>
                  {template ? (
                    <GhostButton onClick={() => setEditing(template)}>Edit text</GhostButton>
                  ) : null}
                </div>
              );
            })}
          </div>
        </article>

        <article className="rounded-card bg-charcoal p-6 text-white">
          <h2 className="text-xl font-semibold">Send a test</h2>
          <p className="text-sm text-white/60">Checks the provider for one channel end to end.</p>
          <div className="mt-4 flex flex-wrap gap-2">
            {channels.map(({ id, label }) => (
              <button
                key={id}
                type="button"
                aria-pressed={testChannel === id}
                onClick={() => setTestChannel(id)}
                className={`rounded-full px-4 py-2 text-sm font-semibold ${testChannel === id ? "bg-accent" : "bg-white/10 hover:bg-white/15"}`}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="mt-4 flex gap-2">
            <input
              value={testTo}
              onChange={(event) => setTestTo(event.target.value)}
              placeholder={testChannel === "email" ? "name@example.com" : "+971 50 123 4567"}
              aria-label="Send the test to"
              className="h-12 flex-1 rounded-xl border border-white/10 bg-white/5 px-4 text-white placeholder:text-white/30 focus:border-accent focus:outline-none"
            />
            <button
              type="button"
              disabled={testTo.trim().length < 3}
              onClick={() => void sendTest()}
              className="inline-flex h-12 items-center gap-2 rounded-xl bg-accent px-5 text-sm font-semibold disabled:opacity-40"
            >
              <Send size={16} aria-hidden="true" /> Send
            </button>
          </div>
          <dl className="mt-6 grid grid-cols-2 gap-3 text-sm">
            <div className="rounded-2xl bg-white/5 p-4">
              <dt className="text-white/60">Sent (recent)</dt>
              <dd className="mt-1 text-2xl font-semibold tabular-nums">{sent}</dd>
            </div>
            <div className="rounded-2xl bg-white/5 p-4">
              <dt className="text-white/60">Failed (recent)</dt>
              <dd className={`mt-1 text-2xl font-semibold tabular-nums ${failed ? "text-accent" : ""}`}>{failed}</dd>
            </div>
          </dl>
        </article>
      </div>

      <article className="rounded-card border border-line bg-white p-6">
        <h2 className="text-xl font-semibold">Outbox</h2>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[820px] text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-charcoal/50">
              <tr>
                <th className="pb-3 font-medium">When</th>
                <th className="pb-3 font-medium">To</th>
                <th className="pb-3 font-medium">Message</th>
                <th className="pb-3 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {outbox.map((row) => (
                <tr key={row.id} className="border-t border-line align-top">
                  <td className="py-3 text-charcoal/70">{formatDate(row.created_at)}</td>
                  <td className="py-3">
                    <span className="block font-medium">{row.customer_name ?? row.to_address}</span>
                    <span className="block text-xs text-charcoal/50">
                      {row.channel} · {row.to_address || "no address"}
                    </span>
                  </td>
                  <td className="max-w-md py-3">
                    <span className="block truncate">{row.body}</span>
                    {row.last_error ? <span className="block text-xs text-accent">{row.last_error}</span> : null}
                  </td>
                  <td className="py-3">
                    <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${statusTone[row.status]}`}>
                      {row.status.toLowerCase()}
                    </span>
                    {row.attempts > 1 ? <span className="ml-2 text-xs text-charcoal/50">{row.attempts} tries</span> : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {outbox.length === 0 ? <p className="py-8 text-sm text-charcoal/60">No messages yet.</p> : null}
        </div>
      </article>

      {canJobs ? (
        <article className="rounded-card border border-line bg-white p-6">
          <h2 className="text-xl font-semibold">Background jobs</h2>
          <p className="text-sm text-charcoal/60">Run inside the API. Only one server runs a job at a time.</p>
          <ul className="mt-4 divide-y divide-line">
            {jobs.map((job) => (
              <li key={job.name} className="flex flex-wrap items-center gap-3 py-3 text-sm">
                <div className="min-w-0 flex-1">
                  <p className="font-semibold">{job.description}</p>
                  <p className="text-xs text-charcoal/50">
                    {job.schedule} · {job.last_finished_at ? `last ran ${formatDate(job.last_finished_at)}` : "not run yet"}
                    {job.last_result ? ` · ${job.last_result}` : ""}
                  </p>
                </div>
                <span
                  className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${
                    job.last_status === "error" ? "bg-accent text-white" : "bg-surface text-charcoal ring-1 ring-line"
                  }`}
                >
                  {job.running ? "running" : (job.last_status ?? "idle")}
                </span>
                <button
                  type="button"
                  aria-label={`Run ${job.description} now`}
                  onClick={() => void runJob(job.name)}
                  className="flex h-9 w-9 items-center justify-center rounded-full border border-line hover:border-accent hover:text-accent"
                >
                  <Play size={14} aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        </article>
      ) : null}

      {editing ? (
        <TemplateModal
          template={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            setToast("Message text saved.");
            void load();
          }}
        />
      ) : null}
      {toast ? <Toast message={toast} onDismiss={dismissToast} /> : null}
    </section>
  );
}

function TemplateModal({ template, onClose, onSaved }: { template: MessageTemplate; onClose: () => void; onSaved: () => void }) {
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
      await apiPut<MessageTemplate>(`/api/v1/messaging/templates/${template.key}`, { subject, body, is_active: active });
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
            className="mt-1.5 w-full rounded-xl border border-transparent bg-surface px-4 py-3 text-sm font-normal focus:border-accent focus:bg-white focus:outline-none"
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
