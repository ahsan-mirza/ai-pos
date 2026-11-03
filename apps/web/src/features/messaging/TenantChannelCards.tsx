import { PROVIDER_LABELS, type MessageChannel } from "@ai-pos/shared-types";
import { useCallback, useEffect, useState } from "react";
import { ErrorNote, SelectField, TextField } from "../../components/ui/Field";
import { apiGet, apiPost, apiPut } from "../../lib/api";
import { errorMessage } from "../users/api";

interface ChannelCard {
  channel: MessageChannel;
  enabled: boolean;
  provider: string;
  providers: string[];
  public_config: Record<string, string>;
  status: string;
  secret_set: boolean;
  secret_hint: string | null;
  last_error: string | null;
  last_checked_at: string | null;
}

const labels: Record<MessageChannel, string> = { whatsapp: "WhatsApp", sms: "SMS", email: "Email" };

function channelBadge(card: ChannelCard): { label: string; className: string } {
  if (!card.enabled || card.status === "disabled") {
    return { label: "Not configured", className: "bg-surface text-charcoal/60" };
  }
  if (card.status === "error" || (card.last_error && card.status !== "connected")) {
    return { label: "Error", className: "bg-rose-50 text-rose-700" };
  }
  if (card.provider === "log") return { label: "Configured", className: "bg-surface text-charcoal/70" };
  if (card.status === "connected") return { label: "Connected", className: "bg-emerald-50 text-emerald-700" };
  if (card.status === "disconnected" || card.status === "close") {
    return { label: "Disconnected", className: "bg-rose-50 text-rose-700" };
  }
  return { label: "Not configured", className: "bg-surface text-charcoal/60" };
}

const fields: Record<string, { key: string; label: string }[]> = {
  whatsapp_cloud: [
    { key: "waba_id", label: "WhatsApp Business Account ID" },
    { key: "phone_number_id", label: "Phone number ID" },
    { key: "business_phone", label: "Business phone" },
  ],
  http_sms: [
    { key: "url", label: "Gateway URL" },
    { key: "sender_id", label: "Sender ID" },
  ],
  smtp: [
    { key: "host", label: "SMTP host" },
    { key: "port", label: "Port" },
    { key: "username", label: "Username" },
    { key: "sender_email", label: "Sender email" },
    { key: "sender_name", label: "Sender name" },
    { key: "security", label: "Security (starttls, ssl, or none)" },
  ],
};

export function TenantChannelCards() {
  const [cards, setCards] = useState<ChannelCard[]>([]);
  const [drafts, setDrafts] = useState<Record<string, { provider: string; config: Record<string, string>; secret: string }>>({});
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const next = await apiGet<ChannelCard[]>("/api/v1/reach/channels");
    setCards(next);
    setDrafts((current) => {
      const merged = { ...current };
      for (const card of next) {
        if (merged[card.channel]) continue;
        merged[card.channel] = { provider: card.provider, config: { ...card.public_config }, secret: "" };
      }
      return merged;
    });
  }, []);

  useEffect(() => {
    void load().catch((caught) => setError(errorMessage(caught, "Channel settings could not be loaded.")));
  }, [load]);

  const save = async (card: ChannelCard, enabled: boolean) => {
    const draft = drafts[card.channel];
    setBusy(true);
    setError(null);
    try {
      await apiPut("/api/v1/reach/channels", {
        channel: card.channel,
        enabled,
        provider: draft?.provider || card.provider || "log",
        public_config: draft?.config || {},
        secret: draft?.secret || null,
      });
      setDrafts((current) => ({
        ...current,
        [card.channel]: {
          provider: current[card.channel]?.provider ?? card.provider,
          config: current[card.channel]?.config ?? {},
          secret: "",
        },
      }));
      setNotice(enabled ? `${labels[card.channel]} saved.` : `${labels[card.channel]} turned off. History is kept.`);
      await load();
    } catch (caught) {
      setError(errorMessage(caught, "The channel was not saved."));
    } finally {
      setBusy(false);
    }
  };

  const test = async (card: ChannelCard) => {
    setBusy(true);
    setError(null);
    try {
      await apiPost(`/api/v1/reach/channels/${card.channel}/test`, {});
      setNotice(
        card.provider === "smtp"
          ? "Email settings are complete. This does not prove the message will reach the inbox."
          : `${labels[card.channel]} connection accepted.`,
      );
      await load();
    } catch (caught) {
      setError(errorMessage(caught, "The connection test failed."));
      await load().catch(() => undefined);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Transactional channels</h2>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-charcoal/60">
            Receipts, statements, and reminders use these accounts. Leave a credential blank to keep the one already saved.
          </p>
        </div>
        <ul className="flex flex-wrap gap-2">
          {cards.map((card) => {
            const badge = channelBadge(card);
            return (
              <li key={card.channel} className={`rounded-full px-2.5 py-1 text-xs font-medium ${badge.className}`}>
                {labels[card.channel]} · {badge.label}
              </li>
            );
          })}
        </ul>
      </div>
      <ErrorNote message={error} />
      {notice ? <p className="rounded-xl border border-line bg-surface px-3 py-2 text-sm text-charcoal/70">{notice}</p> : null}
      <div className="grid grid-cols-1 items-stretch gap-4 md:grid-cols-2 xl:grid-cols-3">
        {cards.map((card) => {
          const draft = drafts[card.channel] ?? { provider: card.provider, config: {}, secret: "" };
          const extra = fields[draft.provider] ?? [];
          const badge = channelBadge(card);
          const enabled = card.enabled;
          return (
            <article key={card.channel} className="flex h-full flex-col rounded-card border border-line bg-white p-4 shadow-sm">
              <div className="flex items-start justify-between gap-2">
                <h3 className="font-semibold">{labels[card.channel]}</h3>
                <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${badge.className}`}>{badge.label}</span>
              </div>
              <p className="mt-1 text-xs text-charcoal/50">
                {card.secret_set ? `Credential saved ${card.secret_hint ?? ""}` : "No credential stored"}
              </p>
              <div className="mt-3 flex items-center justify-between gap-3">
                <span className="text-sm">Enabled</span>
                <button
                  type="button"
                  role="switch"
                  aria-checked={enabled}
                  aria-label={`${labels[card.channel]} enabled`}
                  disabled={busy}
                  onClick={() => void save(card, !enabled)}
                  className={`relative h-6 w-11 rounded-full transition ${enabled ? "bg-accent" : "bg-charcoal/15"}`}
                >
                  <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow ${enabled ? "left-5" : "left-0.5"}`} />
                </button>
              </div>
              <SelectField
                className="mt-3"
                label="Provider"
                value={draft.provider}
                options={card.providers.map((value) => ({ value, label: PROVIDER_LABELS[value] ?? value }))}
                onChange={(value) =>
                  setDrafts((current) => ({ ...current, [card.channel]: { ...draft, provider: value } }))
                }
              />
              {extra.map((field) => (
                <TextField
                  key={field.key}
                  className="mt-3"
                  label={field.label}
                  value={draft.config[field.key] ?? ""}
                  onChange={(event) =>
                    setDrafts((current) => ({
                      ...current,
                      [card.channel]: {
                        ...draft,
                        config: { ...draft.config, [field.key]: event.target.value },
                      },
                    }))
                  }
                />
              ))}
              {draft.provider !== "log" && draft.provider !== "evolution" ? (
                <label className="mt-3 block text-sm font-medium">
                  Credential
                  <input
                    type="password"
                    autoComplete="new-password"
                    value={draft.secret}
                    onChange={(event) =>
                      setDrafts((current) => ({ ...current, [card.channel]: { ...draft, secret: event.target.value } }))
                    }
                    placeholder={card.secret_set ? "Leave blank to keep it" : "Access token or password"}
                    className="mt-1 h-10 w-full rounded-xl border border-line bg-surface px-3 text-sm font-normal"
                  />
                </label>
              ) : null}
              {draft.provider === "whatsapp_cloud" ? (
                <p className="mt-2 text-xs leading-5 text-charcoal/50">
                  Use the phone number ID and token from your WhatsApp Business account.
                </p>
              ) : null}
              {draft.provider === "evolution" ? (
                <p className="mt-2 text-xs leading-5 text-charcoal/50">
                  The marketing WhatsApp session is paired in AxizReach. This switch uses that same number.
                </p>
              ) : null}
              {draft.provider === "smtp" ? (
                <p className="mt-2 text-xs leading-5 text-charcoal/50">
                  Publish SPF, DKIM, and DMARC for the sender domain. A completed form is not proof of inbox delivery.
                </p>
              ) : null}
              <div className="mt-auto flex flex-wrap items-center gap-3 pt-4">
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void save(card, true)}
                  className="inline-flex rounded-full bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
                >
                  Save
                </button>
                {card.enabled ? (
                  <button type="button" className="text-sm font-semibold text-charcoal" disabled={busy} onClick={() => void test(card)}>
                    Test connection
                  </button>
                ) : null}
              </div>
              {card.last_error ? <p className="mt-2 text-xs text-rose-700">{card.last_error}</p> : null}
            </article>
          );
        })}
      </div>
    </div>
  );
}
