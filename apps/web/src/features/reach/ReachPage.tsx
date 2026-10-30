import { formatMoney, type MessageChannel } from "@ai-pos/shared-types";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorNote, PrimaryButton, TextField } from "../../components/ui/Field";
import { apiGet, apiPost } from "../../lib/api";
import { useCurrency } from "../../lib/currency";
import { errorMessage } from "../users/api";

interface ChannelCard {
  channel: MessageChannel;
  enabled: boolean;
  status: string;
}

interface Overview {
  campaigns: number;
  active: number;
  sent: number;
  failed: number;
  delivery_rate: number | null;
  by_channel: Record<string, number>;
  usage_cents: number;
  recent: { id: string; name: string; status: string; queued_count: number; suppressed_count: number }[];
}

const labels: Record<MessageChannel, string> = { whatsapp: "WhatsApp", sms: "SMS", email: "Email" };

export function ReachPage() {
  const { currency } = useCurrency();
  const [channels, setChannels] = useState<ChannelCard[]>([]);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [name, setName] = useState("");
  const [body, setBody] = useState("Hello {{customer_name}}, {{business_name}} has something for you.");
  const [picked, setPicked] = useState<MessageChannel[]>(["whatsapp"]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [nextChannels, nextOverview] = await Promise.all([
        apiGet<ChannelCard[]>("/api/v1/reach/channels"),
        apiGet<Overview>("/api/v1/reach/overview"),
      ]);
      setChannels(nextChannels);
      setOverview(nextOverview);
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "AxizReach could not be loaded."));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const launch = async () => {
    setBusy(true);
    setError(null);
    const content = Object.fromEntries(picked.map((channel) => [channel, { body, subject: name }]));
    try {
      const preview = await apiPost<{ eligible: number; suppressed: number; unknown_variables: string[] }>(
        "/api/v1/reach/campaigns/preview",
        {
          idempotency_key: crypto.randomUUID(),
          name,
          channels: picked,
          audience: {},
          content,
        },
      );
      if (preview.unknown_variables.length > 0) {
        setError(`Unknown variable: ${preview.unknown_variables.join(", ")}.`);
        return;
      }
      const confirmed = window.confirm(
        `Send to ${preview.eligible} recipients? ${preview.suppressed} are suppressed for missing consent.`,
      );
      if (!confirmed) return;
      await apiPost("/api/v1/reach/campaigns", {
        idempotency_key: crypto.randomUUID(),
        name,
        channels: picked,
        audience: {},
        content,
      });
      setNotice("Campaign queued. Delivery runs in the background.");
      setName("");
      await load();
    } catch (caught) {
      setError(errorMessage(caught, "The campaign was not queued."));
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
          Marketing campaigns for customers who opted in. Provider accounts and receipts stay in{" "}
          <Link to="/settings/messaging" className="font-semibold underline">
            Messaging
          </Link>
          , including when this add-on is off.
        </p>
      </header>
      <ErrorNote message={error} />
      {notice ? <p className="text-sm text-charcoal/70">{notice}</p> : null}

      {overview ? (
        <dl className="grid grid-cols-2 gap-3 rounded-card border border-line bg-white p-4 text-sm sm:grid-cols-4">
          <div>
            <dt className="text-charcoal/50">Campaigns</dt>
            <dd className="text-xl font-semibold tabular-nums">{overview.campaigns}</dd>
          </div>
          <div>
            <dt className="text-charcoal/50">Sent</dt>
            <dd className="text-xl font-semibold tabular-nums">{overview.sent}</dd>
          </div>
          <div>
            <dt className="text-charcoal/50">Failed</dt>
            <dd className="text-xl font-semibold tabular-nums">{overview.failed}</dd>
          </div>
          <div>
            <dt className="text-charcoal/50">Delivery rate</dt>
            <dd className="text-xl font-semibold tabular-nums">{rate}</dd>
          </div>
          <div className="col-span-2 sm:col-span-4 text-charcoal/70">
            Marketing usage {formatMoney(overview.usage_cents, currency)} · WhatsApp {overview.by_channel.whatsapp ?? 0} ·
            SMS {overview.by_channel.sms ?? 0} · Email {overview.by_channel.email ?? 0}
          </div>
        </dl>
      ) : null}

      <form
        className="grid gap-3 rounded-card border border-line bg-white p-4"
        onSubmit={(event) => {
          event.preventDefault();
          void launch();
        }}
      >
        <h2 className="text-lg font-semibold">New campaign</h2>
        <TextField label="Campaign name" value={name} onChange={(event) => setName(event.target.value)} />
        <fieldset className="flex flex-wrap gap-3 text-sm">
          <legend className="sr-only">Channels</legend>
          {(Object.keys(labels) as MessageChannel[]).map((channel) => {
            const card = channels.find((item) => item.channel === channel);
            const ready = card?.status === "connected";
            const hint = ready ? "" : card?.enabled ? " (test the connection in Messaging)" : " (set it up in Messaging)";
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
                {hint}
              </label>
            );
          })}
        </fieldset>
        <label className="block text-sm font-medium">
          Message
          <textarea
            value={body}
            onChange={(event) => setBody(event.target.value)}
            rows={4}
            className="mt-1 w-full rounded-xl bg-surface px-3 py-2 text-sm font-normal"
          />
        </label>
        <p className="text-xs text-charcoal/50">
          Variables: {"{{customer_name}}"}, {"{{business_name}}"}, {"{{store_name}}"}, {"{{loyalty_points}}"}. Customers
          without marketing consent are left out.
        </p>
        <div>
          <PrimaryButton disabled={busy || name.trim().length < 1 || picked.length === 0} type="submit">
            {busy ? "Working…" : "Review and queue"}
          </PrimaryButton>
        </div>
      </form>

      {overview && overview.recent.length > 0 ? (
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
      ) : null}
    </section>
  );
}
