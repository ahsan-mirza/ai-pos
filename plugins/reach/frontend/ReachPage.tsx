import { formatMoney, type MessageChannel } from "@ai-pos/shared-types";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { ErrorNote, PrimaryButton, TextField } from "../../../apps/web/src/components/ui/Field";
import {
  AutomationsPanel,
  CountGrid,
  OutboxPanel,
  ServerFallback,
  TransactionalTemplates,
  emptyCounts,
  useOutboxSummary,
} from "../../../apps/web/src/features/messaging/ReachOperations";
import { TenantChannelCards } from "../../../apps/web/src/features/messaging/TenantChannelCards";
import { apiDelete, apiGet, apiPost, apiPut } from "../../../apps/web/src/lib/api";
import { useCurrency } from "../../../apps/web/src/lib/currency";
import { AgentPanel, ActionsPanel, ConversationsPanel } from "./AiCare";
import { errorMessage } from "../../../apps/web/src/features/users/api";

type Tab = "overview" | "connections" | "campaigns" | "agent" | "conversations" | "templates" | "automations" | "actions" | "history" | "analytics" | "credits" | "settings";

interface ChannelCard {
  channel: MessageChannel;
  enabled: boolean;
  provider: string;
  providers: string[];
  public_config?: Record<string, string>;
  status: string;
  last_error?: string | null;
}

interface Campaign {
  id: string;
  name: string;
  description: string;
  objective: string;
  status: string;
  channels: string[];
  eligible_count: number;
  suppressed_count: number;
  queued_count: number;
  scheduled_at: string | null;
  pending_count?: number;
  processing_count?: number;
  accepted_count?: number;
  delivered_count?: number;
  read_count?: number;
  failed_count?: number;
  skipped_count?: number;
  credits_reserved?: number;
  credits_consumed?: number;
  connection_phone?: string | null;
}

interface Overview {
  campaigns: number;
  active: number;
  sent: number;
  failed: number;
  delivered: number;
  read: number;
  delivery_rate: number | null;
  by_channel: Record<string, number>;
  usage_cents: number;
  prices?: Partial<Record<MessageChannel, number>>;
  credits_available: number | null;
  credits_reserved: number | null;
  connection_status: string | null;
  provider_status?: string;
  provider_detail?: string | null;
  campaign_readiness?: string;
  campaign_blockers?: string[];
  connected_phone?: string | null;
  recent: Campaign[];
}

interface Connection {
  id: string;
  name: string;
  instance_name: string;
  phone_number: string | null;
  status: string;
  last_error: string | null;
  qr_base64: string | null;
  webhook_status?: string;
  webhook_registered_at?: string | null;
  last_webhook_at?: string | null;
  updated_at?: string | null;
  session_state?: string;
}

interface Template {
  id: string;
  name: string;
  channel: MessageChannel;
  body: string;
}

interface Recipient {
  id: string;
  campaign_id: string;
  phone: string;
  status: string;
  failure_reason: string | null;
  provider_message_id: string | null;
}

interface Credits {
  balance: number;
  reserved: number;
  available: number;
}

interface CreditTx {
  id: string;
  kind: string;
  units: number;
  note: string;
  created_at: string;
}

interface CustomerHit {
  id: string;
  name: string;
  phone: string | null;
  email: string | null;
  marketing_whatsapp_opt_in: boolean;
  marketing_sms_opt_in: boolean;
  marketing_email_opt_in: boolean;
}

interface Preview {
  recipients: number;
  eligible: number;
  suppressed: number;
  estimated_cents: number;
  estimated_credits: number;
  available_credits: number | null;
  unknown_variables: string[];
  sample?: string;
}

const labels: Record<MessageChannel, string> = { whatsapp: "WhatsApp", sms: "SMS", email: "Email" };
const tabs: { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "connections", label: "Connections" },
  { id: "campaigns", label: "Campaigns" },
  { id: "agent", label: "AI Agent" },
  { id: "conversations", label: "Conversations" },
  { id: "templates", label: "Templates" },
  { id: "automations", label: "Automations" },
  { id: "actions", label: "Action Center" },
  { id: "history", label: "History & Outbox" },
  { id: "analytics", label: "Analytics" },
  { id: "credits", label: "Credits & Usage" },
  { id: "settings", label: "Settings" },
];

function tabFromQuery(value: string | null): Tab {
  return tabs.some((item) => item.id === value) ? (value as Tab) : "overview";
}

function channelReady(card: ChannelCard | undefined, connectionStatus: string | null): boolean {
  if (!card?.enabled) return false;
  if (card.channel === "whatsapp") return card.provider === "evolution" && connectionStatus === "open";
  if (card.provider === "log" || card.status === "connected") return true;
  return false;
}

export function ReachPage() {
  const { currency } = useCurrency();
  const [params, setParams] = useSearchParams();
  const tab = tabFromQuery(params.get("tab"));
  const setTab = (next: Tab) => {
    const following = new URLSearchParams(params);
    if (next === "overview") following.delete("tab");
    else following.set("tab", next);
    setParams(following, { replace: true });
  };
  const summary = useOutboxSummary();
  const [channels, setChannels] = useState<ChannelCard[]>([]);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [connections, setConnections] = useState<Connection[]>([]);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [history, setHistory] = useState<Recipient[]>([]);
  const [credits, setCredits] = useState<Credits | null>(null);
  const [ledger, setLedger] = useState<CreditTx[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [settingsDirty, setSettingsDirty] = useState(false);

  const load = useCallback(async () => {
    try {
      const [nextChannels, nextOverview, nextConnections, nextCampaigns, nextTemplates, nextHistory, nextCredits, nextLedger] =
        await Promise.all([
          apiGet<ChannelCard[]>("/api/v1/reach/channels"),
          apiGet<Overview>("/api/v1/reach/overview"),
          apiGet<Connection[]>("/api/v1/reach/connections"),
          apiGet<Campaign[]>("/api/v1/reach/campaigns"),
          apiGet<Template[]>("/api/v1/reach/templates"),
          apiGet<Recipient[]>("/api/v1/reach/messages"),
          apiGet<Credits>("/api/v1/reach/credits"),
          apiGet<CreditTx[]>("/api/v1/reach/credits/transactions"),
        ]);
      setChannels(nextChannels);
      setOverview(nextOverview);
      setConnections((current) =>
        nextConnections.map((row) => {
          const previous = current.find((item) => item.id === row.id);
          const keepQr = row.status !== "open" && !row.qr_base64 ? previous?.qr_base64 ?? null : row.qr_base64;
          return { ...row, qr_base64: keepQr };
        }),
      );
      setCampaigns(nextCampaigns);
      setTemplates(nextTemplates);
      setHistory(nextHistory);
      setCredits(nextCredits);
      setLedger(nextLedger);
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "AxizReach could not be loaded."));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const live = campaigns.some((item) => item.status === "processing" || item.status === "queued");
    if (!live) return;
    const timer = window.setInterval(() => {
      void load();
    }, 5000);
    return () => window.clearInterval(timer);
  }, [campaigns, load]);

  const run = async (work: () => Promise<void>, fallback: string) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await work();
      await load();
      return true;
    } catch (caught) {
      setError(errorMessage(caught, fallback));
      return false;
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (!settingsDirty) return undefined;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [settingsDirty]);

  const rate = overview?.delivery_rate == null ? "—" : `${Math.round(overview.delivery_rate * 100)}%`;

  return (
    <section className="grid gap-4">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">AxizReach</h1>
        <p className="mt-1 max-w-2xl text-sm text-charcoal/60">
          Receipts, reminders, and marketing campaigns share one connection, one outbox, and one set of provider accounts.
        </p>
      </header>
      <div className="flex flex-wrap gap-2" role="tablist" aria-label="AxizReach">
        {tabs.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            className={`inline-flex h-8 items-center rounded-full px-3 text-sm ${tab === item.id ? "bg-accent text-white" : "border border-line bg-white text-charcoal"}`}
            onClick={() => {
              if (tab === "settings" && item.id !== "settings" && settingsDirty) {
                const leave = window.confirm("You have unsaved settings. Leave without saving?");
                if (!leave) return;
                setSettingsDirty(false);
              }
              setTab(item.id);
            }}
          >
            {item.label}
          </button>
        ))}
      </div>
      <ErrorNote message={error} />
      {notice ? <p className="text-sm text-charcoal/70">{notice}</p> : null}

      {tab === "overview" ? (
        <div className="grid gap-4">
          <div className="grid gap-3 lg:grid-cols-2">
            <CountGrid
              title="Transactional"
              counts={summary?.transactional ?? emptyCounts}
              note="Receipts, statements, and reminders. Accepted means the provider took the message."
            />
            <CountGrid
              title="Marketing outbox"
              counts={summary?.marketing ?? emptyCounts}
              note="Campaign rows in the shared outbox. Delivery and read stay in the campaign totals below."
            />
          </div>
          <OverviewPanel overview={overview} rate={rate} currency={currency} />
        </div>
      ) : null}
      {tab === "connections" ? (
        <div className="grid gap-6">
        <ConnectionsPanel
          connections={connections}
          busy={busy}
          providerStatus={overview?.provider_status ?? "unreachable"}
          providerDetail={overview?.provider_detail ?? null}
          onRetry={() => run(async () => undefined, "The service status could not be checked.")}
          onConnect={(id) =>
            run(async () => {
              const created = id
                ? connections.find((row) => row.id === id) ?? null
                : (await apiPost<Connection>("/api/v1/reach/connections", { name: "Store WhatsApp" }));
              const connectionId = created?.id;
              if (!connectionId) return;
              const next = await apiPost<Connection>(`/api/v1/reach/connections/${connectionId}/connect`, {});
              setConnections((current) => {
                const rest = current.filter((row) => row.id !== next.id);
                return [next, ...rest];
              });
              setNotice(next.qr_base64 ? "Scan the QR from WhatsApp, Linked devices." : "Waiting for a QR from the connection service.");
            }, "The QR could not be loaded.")
          }
          onStatus={async (id) => {
            try {
              const next = await apiPost<Connection>(`/api/v1/reach/connections/${id}/status`, {});
              setConnections((current) => current.map((row) => (row.id === id ? { ...next, qr_base64: next.qr_base64 || row.qr_base64 } : row)));
              if (next.status === "open") setNotice("WhatsApp is connected.");
            } catch (caught) {
              setError(errorMessage(caught, "Status could not be refreshed."));
            }
          }}
          onDisconnect={(id) =>
            run(async () => {
              await apiPost(`/api/v1/reach/connections/${id}/disconnect`, {});
              setNotice("WhatsApp was disconnected for this store.");
            }, "The connection could not be disconnected.")
          }
          onTest={async (to) =>
            apiPost("/api/v1/messaging/test", { channel: "whatsapp", to })
          }
        />
        <TenantChannelCards hidePairing />
        <ServerFallback />
        </div>
      ) : null}
      {tab === "campaigns" ? (
        <CampaignsPanel
          campaigns={campaigns}
          channels={channels}
          templates={templates}
          connectionStatus={overview?.connection_status ?? null}
          history={history}
          currency={currency}
          busy={busy}
          onLaunch={(body) =>
            run(async () => {
              if (body.origin === "ai" && body.mode === "draft") {
                const draft = await apiPost<{ id: string }>("/api/v1/reach/campaigns", body);
                await apiPost(`/api/v1/reach/campaigns/${draft.id}/approve-and-send`, {});
                setNotice("Approved and queued. Messages continue in the background, including if you leave this page.");
              } else {
                await apiPost("/api/v1/reach/campaigns", body);
                setNotice("Campaign started. Messages go out in the background, including if you leave this page.");
              }
              setTab("campaigns");
            }, "The campaign was not queued.")
          }
          onAction={(id, action) =>
            run(async () => {
              await apiPost(`/api/v1/reach/campaigns/${id}/${action}`, {});
            }, "The campaign was not updated.")
          }
        />
      ) : null}
      {tab === "agent" ? <AgentPanel /> : null}
      {tab === "conversations" ? <ConversationsPanel /> : null}
      {tab === "templates" ? (
        <div className="grid gap-4">
          <TransactionalTemplates />
        <TemplatesPanel
          templates={templates}
          busy={busy}
          onSave={(body) =>
            run(async () => {
              await apiPut("/api/v1/reach/templates", body);
              setNotice("Template saved.");
            }, "The template was not saved.")
          }
          onDelete={(id) =>
            run(async () => {
              await apiDelete(`/api/v1/reach/templates/${id}`);
            }, "The template was not deleted.")
          }
        />
        </div>
      ) : null}
      {tab === "automations" ? <AutomationsPanel /> : null}
      {tab === "actions" ? <ActionsPanel /> : null}
      {tab === "history" ? <OutboxPanel campaignRows={history} /> : null}
      {tab === "analytics" ? (
        <div className="grid gap-4">
          <div className="grid gap-3 lg:grid-cols-2">
            <CountGrid
              title="Transactional"
              counts={summary?.transactional ?? emptyCounts}
              note="Provider acceptance. This page does not invent a delivered or read state."
            />
            <CountGrid
              title="Marketing outbox"
              counts={summary?.marketing ?? emptyCounts}
              note="Separate from the campaign delivery rate, which comes from callbacks."
            />
          </div>
          <OverviewPanel overview={overview} rate={rate} currency={currency} />
        </div>
      ) : null}
      {tab === "credits" ? <CreditsPanel credits={credits} ledger={ledger} /> : null}
      {tab === "settings" ? (
        <SettingsPanel
          prices={overview?.prices}
          providerStatus={overview?.provider_status ?? "unreachable"}
          providerDetail={overview?.provider_detail ?? null}
          connectedPhone={overview?.connected_phone ?? null}
          busy={busy}
          onDirty={setSettingsDirty}
          onPrices={(prices) =>
            run(async () => {
              await apiPut("/api/v1/reach/prices", prices);
            }, "Prices were not saved.")
          }
        />
      ) : null}
    </section>
  );
}

function OverviewPanel({ overview, rate, currency }: { overview: Overview | null; rate: string; currency: string }) {
  if (!overview) return <p className="text-sm text-charcoal/60">Overview has not loaded yet.</p>;
  return (
    <div className="grid gap-3">
      <h2 className="text-sm font-semibold">Campaigns</h2>
      <dl className="grid grid-cols-2 gap-3 rounded-card border border-line bg-white p-4 text-sm sm:grid-cols-4">
        <Stat label="Campaigns" value={String(overview.campaigns)} />
        <Stat label="Active" value={String(overview.active)} />
        <Stat label="Sent" value={String(overview.sent)} />
        <Stat label="Failed" value={String(overview.failed)} />
        <Stat label="Delivered" value={String(overview.delivered)} />
        <Stat label="Read" value={String(overview.read)} />
        <Stat label="Delivery rate" value={rate} />
        <Stat label="WhatsApp session" value={overview.connection_status ?? "not_connected"} />
        <div className="col-span-2 text-charcoal/70 sm:col-span-4">
          Usage {formatMoney(overview.usage_cents, currency)} · Credits{" "}
          {overview.credits_available == null ? "not allocated" : overview.credits_available} available
          {overview.credits_reserved ? ` · ${overview.credits_reserved} reserved` : ""}
        </div>
      </dl>
      {overview.recent.length === 0 ? (
        <p className="rounded-card border border-line bg-white p-4 text-sm text-charcoal/60">No campaigns yet.</p>
      ) : (
        <ul className="divide-y divide-line rounded-card border border-line bg-white">
          {overview.recent.map((campaign) => (
            <li key={campaign.id} className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
              <span className="font-medium">{campaign.name}</span>
              <span className="text-charcoal/50">
                {campaign.status} · {campaign.queued_count} queued · {campaign.suppressed_count} suppressed
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-charcoal/50">{label}</dt>
      <dd className="text-xl font-semibold tabular-nums">{value}</dd>
    </div>
  );
}

function sessionBadge(status: string): { label: string; className: string } {
  if (status === "open") return { label: "Connected", className: "bg-emerald-50 text-emerald-700" };
  if (status === "connecting") return { label: "Connecting", className: "bg-sky-50 text-sky-700" };
  if (status === "qr" || status === "qrcode") return { label: "QR waiting for scan", className: "bg-sky-50 text-sky-700" };
  if (status === "close" || status === "closed" || status === "disconnected") {
    return { label: "Disconnected", className: "bg-rose-50 text-rose-700" };
  }
  if (status === "error") return { label: "Connection error", className: "bg-rose-50 text-rose-700" };
  return { label: "Not connected", className: "bg-surface text-charcoal/60" };
}

function testStatusLabel(status: string) {
  if (status === "QUEUED") return "Queued. It is in the outbox and has not been accepted yet.";
  if (status === "SENT") return "Accepted by the provider. Delivered and read are shown only after a webhook.";
  if (status === "FAILED") return "Failed.";
  if (status === "SKIPPED") return "Skipped.";
  return status;
}

function ConnectionsPanel({
  connections,
  busy,
  providerStatus,
  providerDetail,
  onRetry,
  onConnect,
  onStatus,
  onDisconnect,
  onTest,
}: {
  connections: Connection[];
  busy: boolean;
  providerStatus: string;
  providerDetail: string | null;
  onRetry: () => void;
  onConnect: (id: string | null) => void;
  onStatus: (id: string) => Promise<void> | void;
  onDisconnect: (id: string) => void;
  onTest: (to: string) => Promise<{
    to_address: string;
    body: string;
    status: string;
    provider: string | null;
    last_error: string | null;
    created_at: string;
    sent_at: string | null;
  }>;
}) {
  const [testTo, setTestTo] = useState("");
  const [testing, setTesting] = useState(false);
  const [testError, setTestError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<Awaited<ReturnType<typeof onTest>> | null>(null);
  const [qrAge, setQrAge] = useState(0);
  const [timedOut, setTimedOut] = useState(false);
  const row = connections[0] ?? null;
  const open = row?.status === "open";
  const serviceDown = providerStatus !== "healthy";
  const qr = row?.qr_base64 ?? null;

  useEffect(() => {
    setQrAge(0);
    setTimedOut(false);
  }, [qr]);

  useEffect(() => {
    if (!qr || open) return undefined;
    const timer = window.setInterval(() => setQrAge((age) => age + 1), 1000);
    return () => window.clearInterval(timer);
  }, [qr, open]);

  useEffect(() => {
    if (!row || !qr || open || serviceDown) return undefined;
    const timer = window.setInterval(() => {
      void onStatus(row.id);
    }, 4000);
    const stop = window.setTimeout(() => setTimedOut(true), 90000);
    return () => {
      window.clearInterval(timer);
      window.clearTimeout(stop);
    };
  }, [row, qr, open, serviceDown, onStatus]);

  const sendTest = async () => {
    if (testing || testTo.trim().length < 8) return;
    setTesting(true);
    setTestError(null);
    try {
      setTestResult(await onTest(testTo.trim()));
    } catch (caught) {
      setTestError(errorMessage(caught, "The test message was not sent."));
    } finally {
      setTesting(false);
    }
  };

  const badge = sessionBadge(row?.status ?? "created");
  const qrStale = qrAge >= 40;

  return (
    <div className="grid gap-6">
      <section className="grid gap-4 rounded-card border border-line bg-white p-4 shadow-sm sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-accent/10 text-accent">
              <ChannelMark channel="whatsapp" className="h-5 w-5" />
            </span>
            <div>
              <h2 className="text-lg font-semibold">Store WhatsApp</h2>
              <p className="mt-1 max-w-xl text-sm leading-6 text-charcoal/60">
                Connect the number this store uses for marketing. Scan the QR from WhatsApp, then Linked devices.
              </p>
            </div>
          </div>
          <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${badge.className}`}>{badge.label}</span>
        </div>
        {serviceDown ? (
          <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
            <p className="font-medium">WhatsApp connection service is unavailable.</p>
            <p className="mt-1">{providerDetail || "Evolution API could not be reached."} Existing store settings are unchanged.</p>
            <button type="button" disabled={busy} onClick={onRetry} className="mt-3 inline-flex h-[38px] items-center justify-center rounded-full border border-rose-300 px-4 text-sm font-medium disabled:opacity-40">
              Retry
            </button>
          </div>
        ) : null}
        <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs text-charcoal/50">WhatsApp number</dt>
            <dd>{row?.phone_number || "Not connected"}</dd>
          </div>
          <div>
            <dt className="text-xs text-charcoal/50">Last update</dt>
            <dd>{row?.updated_at ? new Date(row.updated_at).toLocaleString() : "Not connected yet"}</dd>
          </div>
          <div>
            <dt className="text-xs text-charcoal/50">Webhook</dt>
            <dd>{row?.webhook_status || "Not registered"}</dd>
          </div>
          <div>
            <dt className="text-xs text-charcoal/50">Service</dt>
            <dd>{providerStatus === "healthy" ? "Available" : providerStatus === "authentication_error" ? "Authentication error" : "Unavailable"}</dd>
          </div>
        </dl>
        {row?.last_error ? <p className="text-sm text-rose-700">{row.last_error}</p> : null}
        {timedOut && !open ? <p className="text-sm text-charcoal/70">The connection check timed out. Refresh the QR and scan again.</p> : null}
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={busy || serviceDown}
            onClick={() => (open && row ? void onStatus(row.id) : onConnect(row?.id ?? null))}
            className="inline-flex h-[38px] items-center justify-center rounded-full bg-accent px-4 text-sm font-medium text-white disabled:opacity-40"
          >
            {busy ? "Working…" : open ? "Check connection" : qr ? "Refresh QR" : "Connect WhatsApp"}
          </button>
          {row ? (
            <button type="button" disabled={busy} onClick={() => void onStatus(row.id)} className="inline-flex h-[38px] items-center justify-center rounded-full border border-line px-4 text-sm font-medium disabled:opacity-40">
              Refresh status
            </button>
          ) : null}
          {row && row.status !== "created" ? (
            <button type="button" disabled={busy || serviceDown} onClick={() => onDisconnect(row.id)} className="inline-flex h-[38px] items-center justify-center rounded-full border border-line px-4 text-sm font-medium disabled:opacity-40">
              Disconnect
            </button>
          ) : null}
        </div>
        {qr && !open ? (
          <div className="grid justify-items-center gap-2 rounded-xl border border-line bg-surface p-4">
            <img
              alt="WhatsApp QR code for this store"
              className={`h-52 w-52 rounded-xl bg-white p-2 ${qrStale ? "opacity-40" : ""}`}
              src={qr.startsWith("data:") ? qr : `data:image/png;base64,${qr}`}
            />
            <p className="text-center text-sm text-charcoal/70">
              {qrStale ? "This QR may have expired. Refresh it, then scan again." : `Scan within ${Math.max(0, 40 - qrAge)} seconds, then keep this page open.`}
            </p>
          </div>
        ) : null}
      </section>
      <section className="rounded-card border border-line bg-white p-4 shadow-sm">
        <h2 className="text-lg font-semibold">Send a test message</h2>
        <p className="mt-1 max-w-2xl text-sm leading-6 text-charcoal/60">
          Uses the same outbox as other WhatsApp messages. The session must be open, and the channel must use Evolution.
        </p>
        <div className="mt-4 flex flex-col gap-2 sm:flex-row">
          <input
            value={testTo}
            onChange={(event) => setTestTo(event.target.value)}
            placeholder="+971501234567"
            aria-label="Test destination"
            className="h-10 w-full max-w-sm rounded-xl border border-line bg-surface px-3 text-sm"
          />
          <button
            type="button"
            disabled={testing || !open || testTo.trim().length < 8}
            onClick={() => void sendTest()}
            className="inline-flex h-[38px] items-center justify-center rounded-full bg-accent px-4 text-sm font-medium text-white disabled:opacity-40"
          >
            {testing ? "Sending…" : "Send test message"}
          </button>
        </div>
        {!open ? <p className="mt-2 text-sm text-charcoal/60">Refresh until the session is open before sending.</p> : null}
        {testError ? <p className="mt-2 text-sm text-rose-700">{testError}</p> : null}
        {testResult ? (
          <dl className="mt-4 grid gap-2 text-sm">
            <div><dt className="text-xs text-charcoal/50">Recipient</dt><dd>{testResult.to_address}</dd></div>
            <div><dt className="text-xs text-charcoal/50">Message</dt><dd>{testResult.body}</dd></div>
            <div><dt className="text-xs text-charcoal/50">Submitted</dt><dd>{new Date(testResult.created_at).toLocaleString()}</dd></div>
            <div><dt className="text-xs text-charcoal/50">Outbox</dt><dd>{testResult.status} — {testStatusLabel(testResult.status)}</dd></div>
            {testResult.provider ? <div><dt className="text-xs text-charcoal/50">Provider</dt><dd>{testResult.provider}</dd></div> : null}
            {testResult.last_error ? <div><dt className="text-xs text-charcoal/50">Error</dt><dd className="text-rose-700">{testResult.last_error}</dd></div> : null}
          </dl>
        ) : null}
      </section>
    </div>
  );
}

function CampaignsPanel({
  campaigns,
  channels,
  templates,
  connectionStatus,
  history,
  currency,
  busy,
  onLaunch,
  onAction,
}: {
  campaigns: Campaign[];
  channels: ChannelCard[];
  templates: Template[];
  connectionStatus: string | null;
  history: Recipient[];
  currency: string;
  busy: boolean;
  onLaunch: (body: Record<string, unknown>) => void;
  onAction: (id: string, action: "pause" | "resume" | "cancel" | "retry") => void;
}) {
  const [step, setStep] = useState(1);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [objective, setObjective] = useState("promotion");
  const [inactiveDays, setInactiveDays] = useState("0");
  const [minPoints, setMinPoints] = useState("0");
  const [query, setQuery] = useState("");
  const [people, setPeople] = useState<CustomerHit[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [optedOnly, setOptedOnly] = useState(true);
  const [picked, setPicked] = useState<MessageChannel[]>([]);
  const [mediaId, setMediaId] = useState<string | null>(null);
  const [mediaKind, setMediaKind] = useState<string | null>(null);
  const [fromAi, setFromAi] = useState(false);
  const [body, setBody] = useState("Hello {{customer_name}}, {{business_name}} has something for you.");
  const [when, setWhen] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);

  const search = async (opted = optedOnly) => {
    setLocalError(null);
    try {
      const params = new URLSearchParams({ q: query, limit: "100" });
      if (opted) params.set("whatsapp_opt_in", "true");
      setPeople(await apiGet<CustomerHit[]>(`/api/v1/reach/customers?${params.toString()}`));
    } catch (caught) {
      setLocalError(errorMessage(caught, "Customers could not be searched."));
    }
  };

  const selectEligible = async () => {
    setLocalError(null);
    try {
      const rows = await apiGet<CustomerHit[]>("/api/v1/reach/customers?whatsapp_opt_in=true&limit=1000");
      setPeople(rows);
      setSelected(rows.filter((person) => person.marketing_whatsapp_opt_in && person.phone).map((person) => person.id));
    } catch (caught) {
      setLocalError(errorMessage(caught, "Eligible customers could not be loaded."));
    }
  };

  const payload = () => ({
    idempotency_key: crypto.randomUUID(),
    name,
    description,
    objective,
    channels: picked,
    audience: {
      inactive_days: Number(inactiveDays) || 0,
      min_loyalty_points: Number(minPoints) || 0,
      customer_ids: selected,
    },
    content: Object.fromEntries(
      picked.map((channel) => [
        channel,
        {
          body,
          subject: name,
          ...(channel === "whatsapp" && mediaId ? { media_id: mediaId, media_kind: mediaKind } : {}),
        },
      ]),
    ),
    scheduled_at: when ? new Date(when).toISOString() : null,
    origin: fromAi ? "ai" : "manual",
    mode: fromAi ? "draft" : "send",
  });

  const review = async () => {
    setLocalError(null);
    if (selected.length === 0) {
      setLocalError("Select at least one customer. Search results are not the audience until you select them.");
      return;
    }
    try {
      const next = await apiPost<Preview>("/api/v1/reach/campaigns/preview", payload());
      if (next.unknown_variables.length > 0) {
        setLocalError(`Unknown variable: ${next.unknown_variables.join(", ")}.`);
        return;
      }
      setPreview(next);
      setStep(5);
    } catch (caught) {
      setLocalError(errorMessage(caught, "The audience could not be previewed."));
    }
  };

  return (
    <div className="grid gap-3">
      <form
        className="grid gap-3 rounded-card border border-line bg-white p-4"
        onSubmit={(event) => {
          event.preventDefault();
          if (step < 4) setStep(step + 1);
          else if (step === 4) void review();
          else {
            const eligible = preview?.eligible ?? 0;
            const credits = preview?.estimated_credits ?? 0;
            const confirmed = window.confirm(
              `You're about to send this campaign to ${eligible} eligible customers. ${credits} credits will be reserved. Messages will be sent individually in the background.`,
            );
            if (confirmed) onLaunch(payload());
          }
        }}
      >
        <h2 className="text-lg font-semibold">New campaign · step {step} of 5</h2>
        <ErrorNote message={localError} />
        {step === 1 ? (
          <>
            <TextField label="Name" value={name} onChange={(event) => setName(event.target.value)} />
            <TextField label="Description" value={description} onChange={(event) => setDescription(event.target.value)} />
            <TextField label="Objective" value={objective} onChange={(event) => setObjective(event.target.value)} />
          </>
        ) : null}
        {step === 2 ? (
          <>
            <TextField label="Inactive days" value={inactiveDays} onChange={(event) => setInactiveDays(event.target.value)} />
            <TextField label="Minimum loyalty points" value={minPoints} onChange={(event) => setMinPoints(event.target.value)} />
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={optedOnly} onChange={(event) => setOptedOnly(event.target.checked)} />
              Only customers who opted in to WhatsApp marketing
            </label>
            <div className="flex flex-wrap items-end gap-2">
              <div className="min-w-48 flex-1">
                <TextField label="Find by name or phone" value={query} onChange={(event) => setQuery(event.target.value)} />
              </div>
              <button type="button" className="rounded-xl border border-line px-3 py-2 text-sm" onClick={() => void search()}>
                Search
              </button>
              <button type="button" className="rounded-xl border border-line px-3 py-2 text-sm" onClick={() => void selectEligible()}>
                Select all eligible
              </button>
              <button type="button" className="rounded-xl border border-line px-3 py-2 text-sm" onClick={() => setSelected([])}>
                Clear
              </button>
            </div>
            <p className="text-sm text-charcoal/70">
              {selected.length} selected. A customer is excluded at send time without a valid phone or WhatsApp marketing consent.
            </p>
            {people.length === 0 ? (
              <p className="text-sm text-charcoal/60">Search, then tick the customers who should receive this message.</p>
            ) : (
              <ul className="divide-y divide-line text-sm">
                {people.map((person) => (
                  <li key={person.id} className="flex items-center gap-2 py-2">
                    <input
                      type="checkbox"
                      checked={selected.includes(person.id)}
                      onChange={() =>
                        setSelected((current) =>
                          current.includes(person.id) ? current.filter((id) => id !== person.id) : [...current, person.id],
                        )
                      }
                    />
                    <span>
                      {person.name} · {person.phone || person.email || "no contact"} · WhatsApp{" "}
                      {person.marketing_whatsapp_opt_in ? "opted in" : "not opted in"}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </>
        ) : null}
        {step === 3 ? (
          <>
            <fieldset className="flex flex-wrap gap-3 text-sm">
              <legend className="mb-1 font-medium">Channels</legend>
              {(Object.keys(labels) as MessageChannel[]).map((channel) => {
                const card = channels.find((item) => item.channel === channel);
                const ready = channelReady(card, connectionStatus);
                return (
                  <label key={channel} className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={picked.includes(channel)}
                      disabled={!ready}
                      onChange={() =>
                        setPicked((current) =>
                          current.includes(channel) ? current.filter((item) => item !== channel) : [...current, channel],
                        )
                      }
                    />
                    {labels[channel]}
                    {ready ? "" : " (not ready)"}
                  </label>
                );
              })}
            </fieldset>
            {templates.length > 0 ? (
              <label className="block text-sm">
                Template
                <select
                  className="mt-1 w-full rounded-xl bg-surface px-3 py-2"
                  defaultValue=""
                  onChange={(event) => {
                    const chosen = templates.find((item) => item.id === event.target.value);
                    if (chosen) setBody(chosen.body);
                  }}
                >
                  <option value="">Write a new message</option>
                  {templates.map((item) => (
                    <option key={item.id} value={item.id}>{item.name}</option>
                  ))}
                </select>
              </label>
            ) : (
              <p className="text-sm text-charcoal/60">No saved templates. The message below is what gets queued.</p>
            )}
            <label className="block text-sm font-medium">
              Message
              <textarea value={body} onChange={(event) => setBody(event.target.value)} rows={4} className="mt-1 w-full rounded-xl bg-surface px-3 py-2 font-normal" />
            </label>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                className="rounded-xl border border-line px-3 py-2 text-sm"
                onClick={() => {
                  void apiPost<{ title: string; body: string }>("/api/v1/reach/ai/generate", { objective: "announcement"                   }).then((draft) => {
                    setName(draft.title);
                    setBody(draft.body);
                    setFromAi(true);
                    setLocalError("AI draft only. Review the wording, then choose Approve and send.");
                  }).catch((caught) => setLocalError(errorMessage(caught, "A draft could not be generated.")));
                }}
              >
                Generate with AI
              </button>
              <label className="rounded-xl border border-line px-3 py-2 text-sm">
                Attach JPG, PNG, WebP, MP4, or PDF
                <input
                  className="mt-1 block text-xs"
                  type="file"
                  accept="image/jpeg,image/png,image/webp,video/mp4,application/pdf"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (!file) return;
                    const reader = new FileReader();
                    reader.onload = () => {
                      const encoded = String(reader.result || "").split(",")[1] || "";
                      void apiPost<{ id: string; kind: string }>("/api/v1/reach/media", {
                        file_name: file.name,
                        mime_type: file.type,
                        content_base64: encoded,
                      }).then((saved) => {
                        setMediaId(saved.id);
                        setMediaKind(saved.kind);
                        setLocalError(null);
                      }).catch((caught) => setLocalError(errorMessage(caught, "The file was not accepted.")));
                    };
                    reader.readAsDataURL(file);
                  }}
                />
              </label>
            </div>
            {mediaId ? <p className="text-sm text-charcoal/70">File attached ({mediaKind}). The same file and caption go to each recipient.</p> : null}
          </>
        ) : null}
        {step === 4 ? (
          <TextField label="Send at (optional)" type="datetime-local" value={when} onChange={(event) => setWhen(event.target.value)} />
        ) : null}
        {step === 5 && preview ? (
          <p className="text-sm text-charcoal/70">
            {preview.eligible} will be queued, {preview.suppressed} excluded, of {preview.recipients} selected.
            Estimated usage {formatMoney(preview.estimated_cents, currency)}. Credits {preview.estimated_credits}
            {preview.available_credits == null ? " (no prepaid account — ask AxizPOS to allocate credits)" : ` of ${preview.available_credits} available`}.
            {preview.sample ? <span className="mt-2 block">Sample: {preview.sample}</span> : null}
          </p>
        ) : null}
        <div className="flex gap-2">
          {step > 1 ? (
            <button type="button" className="rounded-xl border border-line px-3 py-2 text-sm" onClick={() => setStep(step - 1)}>
              Back
            </button>
          ) : null}
          <PrimaryButton
            disabled={busy || (step === 1 && name.trim().length < 1) || (step >= 3 && picked.length === 0) || body.trim().length < 2}
            type="submit"
          >
            {step < 4 ? "Continue" : step === 4 ? "Preview audience" : busy ? "Working…" : fromAi ? "Approve and send" : "Send campaign"}
          </PrimaryButton>
        </div>
      </form>
      {campaigns.length === 0 ? (
        <p className="rounded-card border border-line bg-white p-4 text-sm text-charcoal/60">No campaigns yet.</p>
      ) : (
        <ul className="divide-y divide-line rounded-card border border-line bg-white">
          {campaigns.map((campaign) => (
            <li key={campaign.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 text-sm">
              <button type="button" className="text-left" onClick={() => setOpenId(openId === campaign.id ? null : campaign.id)}>
                <span className="font-medium">{campaign.name}</span>
                <span className="text-charcoal/50">
                  {" "}
                  · {campaign.status} · {campaign.queued_count} eligible · {campaign.suppressed_count} excluded
                  {campaign.connection_phone ? ` · ${campaign.connection_phone}` : ""}
                </span>
              </button>
              {openId === campaign.id ? (
                <div className="basis-full text-charcoal/70">
                  <p>
                    Queued {campaign.pending_count ?? 0} · Accepted {campaign.accepted_count ?? 0} · Delivered{" "}
                    {campaign.delivered_count ?? 0} · Read {campaign.read_count ?? 0} · Failed {campaign.failed_count ?? 0} ·
                    Skipped {campaign.skipped_count ?? 0} · Credits reserved {campaign.credits_reserved ?? 0} · consumed{" "}
                    {campaign.credits_consumed ?? 0}
                  </p>
                  <ul className="mt-2 divide-y divide-line">
                    {history.filter((row) => row.campaign_id === campaign.id).map((row) => (
                      <li key={row.id} className="py-1">
                        {row.phone || "no phone"} · {row.status}
                        {row.failure_reason ? ` · ${row.failure_reason}` : ""}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
              <span className="flex gap-2">
                {campaign.status === "processing" || campaign.status === "scheduled" || campaign.status === "queued" ? (
                  <button type="button" className="underline" disabled={busy} onClick={() => onAction(campaign.id, "pause")}>Pause</button>
                ) : null}
                {campaign.status === "paused" ? (
                  <button type="button" className="underline" disabled={busy} onClick={() => onAction(campaign.id, "resume")}>Resume</button>
                ) : null}
                {campaign.status !== "cancelled" && campaign.status !== "completed" ? (
                  <button type="button" className="underline" disabled={busy} onClick={() => onAction(campaign.id, "cancel")}>Cancel</button>
                ) : null}
                {(campaign.failed_count ?? 0) > 0 ? (
                  <button type="button" className="underline" disabled={busy} onClick={() => onAction(campaign.id, "retry")}>Retry failed</button>
                ) : null}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function TemplatesPanel({
  templates,
  busy,
  onSave,
  onDelete,
}: {
  templates: Template[];
  busy: boolean;
  onSave: (body: { name: string; channel: MessageChannel; body: string }) => void;
  onDelete: (id: string) => void;
}) {
  const [name, setName] = useState("");
  const [channel, setChannel] = useState<MessageChannel>("whatsapp");
  const [body, setBody] = useState("Hello {{customer_name}}");
  return (
    <div className="grid gap-3">
      <div>
        <h2 className="text-lg font-semibold">Marketing templates</h2>
        <p className="mt-1 text-sm text-charcoal/60">Used by campaigns. They are stored separately from receipt and reminder text.</p>
      </div>
      <form
        className="grid gap-3 rounded-card border border-line bg-white p-4"
        onSubmit={(event) => {
          event.preventDefault();
          onSave({ name, channel, body });
        }}
      >
        <TextField label="Template name" value={name} onChange={(event) => setName(event.target.value)} />
        <label className="text-sm">
          Channel
          <select className="mt-1 w-full rounded-xl bg-surface px-3 py-2" value={channel} onChange={(event) => setChannel(event.target.value as MessageChannel)}>
            {(Object.keys(labels) as MessageChannel[]).map((item) => (
              <option key={item} value={item}>{labels[item]}</option>
            ))}
          </select>
        </label>
        <label className="text-sm font-medium">
          Body
          <textarea value={body} onChange={(event) => setBody(event.target.value)} rows={4} className="mt-1 w-full rounded-xl bg-surface px-3 py-2 font-normal" />
        </label>
        <PrimaryButton disabled={busy || name.trim().length < 1 || body.trim().length < 2} type="submit">Save template</PrimaryButton>
      </form>
      {templates.length === 0 ? (
        <p className="rounded-card border border-line bg-white p-4 text-sm text-charcoal/60">No templates saved for this store.</p>
      ) : (
        <ul className="divide-y divide-line rounded-card border border-line bg-white">
          {templates.map((item) => (
            <li key={item.id} className="flex items-start justify-between gap-3 px-4 py-3 text-sm">
              <span>
                <span className="font-medium">{item.name}</span>
                <span className="block text-charcoal/50">{item.channel} · {item.body}</span>
              </span>
              <button type="button" className="underline" disabled={busy} onClick={() => onDelete(item.id)}>Delete</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function CreditsPanel({ credits, ledger }: { credits: Credits | null; ledger: CreditTx[] }) {
  return (
    <div className="grid gap-3">
      <dl className="grid grid-cols-3 gap-3 rounded-card border border-line bg-white p-4 text-sm">
        <Stat label="Balance" value={String(credits?.balance ?? 0)} />
        <Stat label="Reserved" value={String(credits?.reserved ?? 0)} />
        <Stat label="Available" value={String(credits?.available ?? 0)} />
      </dl>
      {ledger.length === 0 ? (
        <p className="rounded-card border border-line bg-white p-4 text-sm text-charcoal/60">
          No credit account yet. AxizPOS allocates credits from the console. Existing usage history is unchanged.
        </p>
      ) : (
        <ul className="divide-y divide-line rounded-card border border-line bg-white">
          {ledger.map((row) => (
            <li key={row.id} className="flex justify-between px-4 py-3 text-sm">
              <span>{row.kind} · {row.note || "—"}</span>
              <span className="tabular-nums">{row.units}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ChannelMark({ channel, className }: { channel: MessageChannel; className?: string }) {
  const props = { className, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2, "aria-hidden": true as const };
  if (channel === "email") {
    return (
      <svg {...props}>
        <rect x="3" y="5" width="18" height="14" rx="2" />
        <path d="m3 7 9 6 9-6" />
      </svg>
    );
  }
  if (channel === "sms") {
    return (
      <svg {...props}>
        <rect x="7" y="2" width="10" height="20" rx="2" />
        <path d="M11 18h2" />
      </svg>
    );
  }
  return (
    <svg {...props}>
      <path d="M21 12a8 8 0 0 1-8 8H7l-4 3V12a8 8 0 1 1 18 0Z" />
    </svg>
  );
}

function wholeCents(value: string): number | null {
  const trimmed = value.trim();
  if (!/^\d+$/.test(trimmed)) return null;
  return Number(trimmed);
}


function SettingsPanel({
  prices,
  providerStatus,
  providerDetail,
  connectedPhone,
  busy,
  onDirty,
  onPrices,
}: {
  prices: Partial<Record<MessageChannel, number>> | undefined;
  providerStatus: string;
  providerDetail: string | null;
  connectedPhone: string | null;
  busy: boolean;
  onDirty: (dirty: boolean) => void;
  onPrices: (prices: { whatsapp: number; sms: number; email: number }) => Promise<boolean>;
}) {
  const [amounts, setAmounts] = useState<Record<MessageChannel, string>>({ whatsapp: "0", sms: "0", email: "0" });
  const [savedAmounts, setSavedAmounts] = useState<Record<MessageChannel, string>>({ whatsapp: "0", sms: "0", email: "0" });
  const [priceError, setPriceError] = useState<string | null>(null);
  const [priceSaved, setPriceSaved] = useState(false);
  const [savingPrices, setSavingPrices] = useState(false);
  const priceDirty = (Object.keys(labels) as MessageChannel[]).some((channel) => amounts[channel] !== savedAmounts[channel]);

  useEffect(() => {
    if (!prices || priceDirty) return;
    const next = {
      whatsapp: String(prices.whatsapp ?? 0),
      sms: String(prices.sms ?? 0),
      email: String(prices.email ?? 0),
    };
    setAmounts(next);
    setSavedAmounts(next);
  }, [prices, priceDirty]);

  useEffect(() => {
    onDirty(priceDirty);
  }, [priceDirty, onDirty]);

  useEffect(() => {
    if (!busy) setSavingPrices(false);
  }, [busy]);

  const savePrices = async (event: FormEvent) => {
    event.preventDefault();
    if (busy) return;
    const parsed = {
      whatsapp: wholeCents(amounts.whatsapp),
      sms: wholeCents(amounts.sms),
      email: wholeCents(amounts.email),
    };
    const whatsapp = parsed.whatsapp;
    const sms = parsed.sms;
    const email = parsed.email;
    if (whatsapp == null || sms == null || email == null) {
      setPriceError("Enter a whole number of cents, 0 or greater, for each channel.");
      setPriceSaved(false);
      return;
    }
    setPriceError(null);
    setSavingPrices(true);
    const ok = await onPrices({ whatsapp, sms, email });
    if (!ok) {
      setSavingPrices(false);
      setPriceSaved(false);
      return;
    }
    const next = {
      whatsapp: String(whatsapp),
      sms: String(sms),
      email: String(email),
    };
    setAmounts(next);
    setSavedAmounts(next);
    setPriceSaved(true);
  };

  return (
    <div className="grid gap-8">
      {providerStatus !== "healthy" ? (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
          <p className="font-medium">WhatsApp connection service is unavailable.</p>
          <p className="mt-1">
            {providerDetail || "Evolution API could not be reached."} Saved channel settings stay as they are. Turning a channel on does not connect a WhatsApp number.
          </p>
        </div>
      ) : null}
      <section className="rounded-card border border-line bg-white p-4 shadow-sm">
        <h2 className="text-lg font-semibold text-charcoal">Connections</h2>
        <p className="mt-1 max-w-2xl text-sm leading-6 text-charcoal/60">
          Provider accounts, credentials, and the WhatsApp session are edited on Connections.
          {connectedPhone ? ` Connected number: ${connectedPhone}.` : " No WhatsApp number is connected yet."}
        </p>
      </section>
      <section className="grid gap-3">
        <div>
          <h2 className="text-lg font-semibold text-charcoal">Marketing usage pricing</h2>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-charcoal/60">
            Configure the internal usage price per message. These values do not modify prepaid credit balances.
          </p>
        </div>
        {priceSaved ? (
          <p className="rounded-xl border border-line bg-surface px-3 py-2 text-sm text-charcoal/70">
            Usage prices saved. They do not change prepaid credits.
          </p>
        ) : null}
        <form onSubmit={(event) => void savePrices(event)} className="grid gap-4">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {(Object.keys(labels) as MessageChannel[]).map((channel) => {
              return (
                <label key={channel} className="rounded-card border border-line bg-white p-4 shadow-sm">
                  <span className="flex items-center gap-2 text-sm font-semibold text-charcoal">
                    <ChannelMark channel={channel} className="h-4 w-4 text-accent" />
                    {labels[channel]}
                  </span>
                  <span className="mt-3 flex items-center gap-2">
                    <input
                      inputMode="numeric"
                      aria-label={`${labels[channel]} cents`}
                      value={amounts[channel]}
                      onChange={(event) => {
                        setPriceSaved(false);
                        setAmounts((current) => ({ ...current, [channel]: event.target.value }));
                      }}
                      className="w-full rounded-xl border border-line bg-surface px-3 py-2 text-sm text-charcoal"
                    />
                    <span className="shrink-0 text-sm text-charcoal/60">cents</span>
                  </span>
                </label>
              );
            })}
          </div>
          {priceError ? <p className="text-sm text-rose-700">{priceError}</p> : null}
          <button
            type="submit"
            disabled={busy}
            className="inline-flex w-fit items-center justify-center rounded-full bg-accent px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-40"
          >
            {savingPrices ? "Saving…" : "Save Usage Prices"}
          </button>
        </form>
      </section>
    </div>
  );
}
