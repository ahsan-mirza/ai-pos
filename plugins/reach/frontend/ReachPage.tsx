import { formatMoney, type MessageChannel } from "@ai-pos/shared-types";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorNote, PrimaryButton, TextField } from "../../../apps/web/src/components/ui/Field";
import { apiDelete, apiGet, apiPost, apiPut } from "../../../apps/web/src/lib/api";
import { useCurrency } from "../../../apps/web/src/lib/currency";
import { errorMessage } from "../../../apps/web/src/features/users/api";

type Tab = "overview" | "connections" | "campaigns" | "templates" | "history" | "analytics" | "credits" | "settings";

interface ChannelCard {
  channel: MessageChannel;
  enabled: boolean;
  provider: string;
  providers: string[];
  status: string;
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
  credits_available: number | null;
  credits_reserved: number | null;
  connection_status: string | null;
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
  last_webhook_at?: string | null;
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
  { id: "templates", label: "Templates" },
  { id: "history", label: "History" },
  { id: "analytics", label: "Analytics" },
  { id: "credits", label: "Credits" },
  { id: "settings", label: "Settings" },
];

function channelReady(card: ChannelCard | undefined, connectionStatus: string | null): boolean {
  if (!card?.enabled) return false;
  if (card.channel === "whatsapp") return card.provider === "evolution" && connectionStatus === "open";
  if (card.provider === "log" || card.status === "connected") return true;
  return false;
}

export function ReachPage() {
  const { currency } = useCurrency();
  const [tab, setTab] = useState<Tab>("overview");
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
      setConnections(nextConnections);
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
    } catch (caught) {
      setError(errorMessage(caught, fallback));
    } finally {
      setBusy(false);
    }
  };

  const rate = overview?.delivery_rate == null ? "—" : `${Math.round(overview.delivery_rate * 100)}%`;

  return (
    <section className="grid gap-4">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">AxizReach</h1>
        <p className="mt-1 text-sm text-charcoal/60">
          Marketing campaigns for customers who opted in. Receipts stay in{" "}
          <Link to="/settings/messaging" className="font-semibold underline">
            Messaging
          </Link>
          .
        </p>
      </header>
      <div className="flex flex-wrap gap-2">
        {tabs.map((item) => (
          <button
            key={item.id}
            type="button"
            className={`rounded-full px-3 py-1 text-sm ${tab === item.id ? "bg-charcoal text-white" : "border border-line bg-white"}`}
            onClick={() => setTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>
      <ErrorNote message={error} />
      {notice ? <p className="text-sm text-charcoal/70">{notice}</p> : null}

      {tab === "overview" ? (
        <OverviewPanel overview={overview} rate={rate} currency={currency} />
      ) : null}
      {tab === "connections" ? (
        <ConnectionsPanel
          connections={connections}
          busy={busy}
          onCreate={(name) =>
            run(async () => {
              await apiPost("/api/v1/reach/connections", { name });
              setNotice("Connection created. Scan the QR from Connect.");
            }, "The WhatsApp connection was not created.")
          }
          onConnect={(id) =>
            run(async () => {
              const next = await apiPost<Connection>(`/api/v1/reach/connections/${id}/connect`, {});
              setConnections((current) => current.map((row) => (row.id === id ? next : row)));
              setNotice(next.qr_base64 ? "Scan the QR with the authorized WhatsApp number." : "Waiting for a QR from Evolution.");
            }, "The QR could not be loaded.")
          }
          onStatus={(id) =>
            run(async () => {
              await apiPost(`/api/v1/reach/connections/${id}/status`, {});
            }, "Status could not be refreshed.")
          }
          onDisconnect={(id) =>
            run(async () => {
              await apiPost(`/api/v1/reach/connections/${id}/disconnect`, {});
            }, "The connection could not be disconnected.")
          }
        />
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
      {tab === "templates" ? (
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
      ) : null}
      {tab === "history" ? <HistoryPanel rows={history} /> : null}
      {tab === "analytics" ? <OverviewPanel overview={overview} rate={rate} currency={currency} /> : null}
      {tab === "credits" ? <CreditsPanel credits={credits} ledger={ledger} /> : null}
      {tab === "settings" ? (
        <SettingsPanel
          channels={channels}
          busy={busy}
          onSave={(body) =>
            run(async () => {
              await apiPut("/api/v1/reach/channels", body);
              setNotice("Channel saved.");
            }, "The channel was not saved.")
          }
          onPrices={(prices) =>
            run(async () => {
              await apiPut("/api/v1/reach/prices", prices);
              setNotice("Usage prices saved. They do not change prepaid credits.");
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

function ConnectionsPanel({
  connections,
  busy,
  onCreate,
  onConnect,
  onStatus,
  onDisconnect,
}: {
  connections: Connection[];
  busy: boolean;
  onCreate: (name: string) => void;
  onConnect: (id: string) => void;
  onStatus: (id: string) => void;
  onDisconnect: (id: string) => void;
}) {
  const [name, setName] = useState("");
  return (
    <div className="grid gap-3">
      <form
        className="grid gap-3 rounded-card border border-line bg-white p-4 sm:grid-cols-[1fr_auto]"
        onSubmit={(event) => {
          event.preventDefault();
          onCreate(name);
          setName("");
        }}
      >
        <TextField label="Connection name" value={name} onChange={(event) => setName(event.target.value)} />
        <div className="self-end">
          <PrimaryButton disabled={busy || name.trim().length < 1} type="submit">
            Create
          </PrimaryButton>
        </div>
      </form>
      {connections.length === 0 ? (
        <p className="rounded-card border border-line bg-white p-4 text-sm text-charcoal/60">
          No WhatsApp sessions yet. Creating one calls Evolution and returns a QR to scan with an authorized number.
        </p>
      ) : (
        <ul className="grid gap-3">
          {connections.map((row) => (
            <li key={row.id} className="grid gap-2 rounded-card border border-line bg-white p-4 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium">{row.name}</span>
                <span className="text-charcoal/50">{row.status}{row.phone_number ? ` · ${row.phone_number}` : ""}</span>
              </div>
              {row.last_error ? <p className="text-charcoal/70">{row.last_error}</p> : null}
              <p className="text-charcoal/50">
                Delivery updates {row.webhook_status || "pending"}
                {row.last_webhook_at ? ` · last event ${new Date(row.last_webhook_at).toLocaleString()}` : ""}
              </p>
              {row.qr_base64 ? (
                <img alt="WhatsApp QR" className="h-40 w-40 bg-white" src={row.qr_base64.startsWith("data:") ? row.qr_base64 : `data:image/png;base64,${row.qr_base64}`} />
              ) : null}
              <div className="flex flex-wrap gap-2">
                <PrimaryButton disabled={busy} type="button" onClick={() => onConnect(row.id)}>Connect</PrimaryButton>
                <button type="button" className="rounded-xl border border-line px-3 py-2" disabled={busy} onClick={() => onStatus(row.id)}>Refresh</button>
                <button type="button" className="rounded-xl border border-line px-3 py-2" disabled={busy} onClick={() => onDisconnect(row.id)}>Disconnect</button>
              </div>
            </li>
          ))}
        </ul>
      )}
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

function HistoryPanel({ rows }: { rows: Recipient[] }) {
  if (rows.length === 0) {
    return <p className="rounded-card border border-line bg-white p-4 text-sm text-charcoal/60">No recipient history yet.</p>;
  }
  return (
    <ul className="divide-y divide-line rounded-card border border-line bg-white">
      {rows.map((row) => (
        <li key={row.id} className="px-4 py-3 text-sm">
          <span className="font-medium">{row.phone || "no address"}</span>
          <span className="text-charcoal/50"> · {row.status}</span>
          {row.failure_reason ? <span className="block text-charcoal/60">{row.failure_reason}</span> : null}
        </li>
      ))}
    </ul>
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

function SettingsPanel({
  channels,
  busy,
  onSave,
  onPrices,
}: {
  channels: ChannelCard[];
  busy: boolean;
  onSave: (body: { channel: MessageChannel; enabled: boolean; provider: string; public_config: Record<string, string> }) => void;
  onPrices: (prices: { whatsapp: number; sms: number; email: number }) => void;
}) {
  const [whatsapp, setWhatsapp] = useState("0");
  const [sms, setSms] = useState("0");
  const [email, setEmail] = useState("0");
  return (
    <div className="grid gap-3">
      {channels.map((card) => (
        <form
          key={card.channel}
          className="grid gap-2 rounded-card border border-line bg-white p-4 text-sm"
          onSubmit={(event) => {
            event.preventDefault();
            const data = new FormData(event.currentTarget);
            onSave({
              channel: card.channel,
              enabled: data.get("enabled") === "on",
              provider: String(data.get("provider") || card.provider),
              public_config: {},
            });
          }}
        >
          <h3 className="font-medium">{labels[card.channel]}</h3>
          <label className="flex items-center gap-2">
            <input name="enabled" type="checkbox" defaultChecked={card.enabled} />
            Enabled
          </label>
          <label>
            Provider
            <select name="provider" className="mt-1 w-full rounded-xl bg-surface px-3 py-2" defaultValue={card.provider}>
              {card.providers.map((provider) => (
                <option key={provider} value={provider}>{provider}</option>
              ))}
            </select>
          </label>
          <p className="text-charcoal/50">Status {card.status}. Cloud, SMS, and email credentials stay in Messaging.</p>
          <PrimaryButton disabled={busy} type="submit">Save {labels[card.channel]}</PrimaryButton>
        </form>
      ))}
      <form
        className="grid gap-3 rounded-card border border-line bg-white p-4 sm:grid-cols-3"
        onSubmit={(event) => {
          event.preventDefault();
          onPrices({ whatsapp: Number(whatsapp) || 0, sms: Number(sms) || 0, email: Number(email) || 0 });
        }}
      >
        <TextField label="WhatsApp cents" value={whatsapp} onChange={(event) => setWhatsapp(event.target.value)} />
        <TextField label="SMS cents" value={sms} onChange={(event) => setSms(event.target.value)} />
        <TextField label="Email cents" value={email} onChange={(event) => setEmail(event.target.value)} />
        <div className="sm:col-span-3">
          <PrimaryButton disabled={busy} type="submit">Save usage prices</PrimaryButton>
        </div>
      </form>
    </div>
  );
}
