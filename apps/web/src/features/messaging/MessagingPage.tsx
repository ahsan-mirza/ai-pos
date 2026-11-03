import {
  Capability,
  PROVIDER_LABELS,
  Permission,
  type BackgroundJob,
  type MessageChannel,
  type MessageTemplate,
  type MessagingSettings,
  type OutboundMessage,
} from "@ai-pos/shared-types";
import { actionHoverClass } from "@ai-pos/ui";
import { Mail, MessageCircle, Play, Send, Smartphone, type LucideIcon } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorNote, GhostButton, PrimaryButton, SelectField, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { Toast } from "../../components/ui/Toast";
import { Toggle } from "../../components/ui/Toggle";
import { apiGet, apiPost, apiPut } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useCapability } from "../../lib/capabilities";
import { formatDate } from "../inventory/shared";
import { errorMessage } from "../users/api";
import { TenantChannelCards } from "./TenantChannelCards";

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
  const reachOn = useCapability(Capability.AxizReach);
  const [settings, setSettings] = useState<MessagingSettings | null>(null);
  const [templates, setTemplates] = useState<MessageTemplate[]>([]);
  const [outbox, setOutbox] = useState<OutboundMessage[]>([]);
  const [jobs, setJobs] = useState<BackgroundJob[]>([]);
  const [editing, setEditing] = useState<MessageTemplate | null>(null);
  const [testChannel, setTestChannel] = useState<MessageChannel>("whatsapp");
  const [testTo, setTestTo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
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
    if (sending) return;
    setSending(true);
    try {
      const result = await apiPost<OutboundMessage>("/api/v1/messaging/test", { channel: testChannel, to: testTo.trim() });
      setToast(result.status === "SENT" ? "Test message accepted by the provider." : `Test message ${result.status.toLowerCase()}${result.last_error ? `: ${result.last_error}` : ""}`);
      void load();
    } catch (caught) {
      setError(errorMessage(caught, "Could not send the test message."));
    } finally {
      setSending(false);
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
    <section className="space-y-6">
      <ErrorNote message={error} />
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">Messaging</h1>
        <p className="mt-1 max-w-2xl text-sm leading-6 text-charcoal/60">
          Manage customer notifications and automated business communications.
        </p>
        {reachOn ? (
          <p className="mt-2 text-sm text-charcoal/70">
            <Link to="/settings/reach" className="font-semibold text-accent">
              Manage marketing campaigns in AxizReach.
            </Link>
          </p>
        ) : null}
      </header>
      <TenantChannelCards />
      <section className="grid gap-3">
        <div>
          <h2 className="text-lg font-semibold">Server fallback</h2>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-charcoal/60">
            Used only when a channel has no saved account above. A saved account always wins.
          </p>
        </div>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {channels.map(({ id, label, icon: Icon }) => (
            <article key={id} className="rounded-card border border-line bg-white p-4 shadow-sm">
              <div className="flex items-center gap-3">
                <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent/10 text-accent">
                  <Icon size={16} aria-hidden="true" />
                </span>
                <h3 className="text-sm font-semibold">{label}</h3>
              </div>
              <SelectField
                className="mt-3"
                label="Fallback provider"
                value={settings?.providers[id] ?? "log"}
                options={(settings?.available[id] ?? ["log"]).map((value) => ({ value, label: PROVIDER_LABELS[value] ?? value }))}
                onChange={(value) => void save({ providers: { [id]: value } })}
              />
            </article>
          ))}
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-2">
        <article className="rounded-card border border-line bg-white p-4 shadow-sm">
          <h2 className="text-lg font-semibold">Automatic messages</h2>
          <p className="text-sm text-charcoal/60">Sent only to customers who opted in on that channel.</p>
          <ul className="mt-4 divide-y divide-line">
            {Object.keys(eventLabels).map((key) => {
              const template = templates.find((row) => row.key === key);
              const on = settings?.events[key] ?? false;
              return (
                <li key={key} className="flex items-center gap-3 py-3">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium">{eventLabels[key] ?? key}</p>
                    <p className="truncate text-xs text-charcoal/50">
                      {template ? template.body.slice(0, 110) + (template.body.length > 110 ? "…" : "") : "No template"}
                    </p>
                  </div>
                  <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${on ? "bg-emerald-50 text-emerald-700" : "bg-surface text-charcoal/50"}`}>
                    {on ? "On" : "Off"}
                  </span>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={on}
                    aria-label={eventLabels[key] ?? key}
                    onClick={() => void save({ events: { [key]: !on } })}
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
        </article>

        <article className="rounded-card border border-line bg-white p-4 shadow-sm">
          <h2 className="text-lg font-semibold">Test a transactional message</h2>
          <p className="text-sm text-charcoal/60">Sends through the saved provider and records the outbox result.</p>
          <div className="mt-4 flex flex-wrap gap-2">
            {channels.map(({ id, label }) => (
              <button
                key={id}
                type="button"
                aria-pressed={testChannel === id}
                onClick={() => setTestChannel(id)}
                className={`rounded-full px-3 py-1.5 text-sm font-medium ${testChannel === id ? "bg-accent text-white" : "border border-line bg-white"}`}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="mt-4 flex flex-col gap-2 sm:flex-row">
            <input
              value={testTo}
              onChange={(event) => setTestTo(event.target.value)}
              placeholder={testChannel === "email" ? "name@example.com" : "+971501234567"}
              aria-label="Send the test to"
              className="h-11 flex-1 rounded-xl border border-line bg-surface px-3 text-sm focus:border-accent focus:outline-none"
            />
            <button
              type="button"
              disabled={sending || testTo.trim().length < 3}
              onClick={() => void sendTest()}
              className="inline-flex h-11 items-center justify-center gap-2 rounded-full bg-accent px-4 text-sm font-medium text-white disabled:opacity-40"
            >
              <Send size={16} aria-hidden="true" /> {sending ? "Sending…" : "Send test"}
            </button>
          </div>
          <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
            <div className="rounded-xl bg-surface p-3">
              <dt className="text-charcoal/60">Sent recently</dt>
              <dd className="mt-1 text-2xl font-semibold tabular-nums">{sent}</dd>
            </div>
            <div className="rounded-xl bg-surface p-3">
              <dt className="text-charcoal/60">Failed recently</dt>
              <dd className="mt-1 text-2xl font-semibold tabular-nums">{failed}</dd>
            </div>
          </dl>
        </article>
      </div>

      <article className="rounded-card border border-line bg-white p-6">
        <h2 className="text-xl font-semibold">Outbox</h2>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-left text-sm">
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
                  className={`flex h-9 w-9 items-center justify-center rounded-full border border-line ${actionHoverClass("primary")}`}
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
