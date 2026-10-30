import { type MessageChannel } from "@ai-pos/shared-types";
import { useCallback, useEffect, useState } from "react";
import { ErrorNote, PrimaryButton, SelectField, TextField } from "../../components/ui/Field";
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
      setDrafts((current) => ({ ...current, [card.channel]: { ...current[card.channel], secret: "" } }));
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
      <div>
        <h2 className="text-xl font-semibold">Your provider accounts</h2>
        <p className="mt-1 text-sm text-charcoal/60">
          Each channel is yours to turn on. This is included with the starter kit. AxizReach is only required for
          marketing campaigns. Leave a credential blank to keep the one already saved.
        </p>
      </div>
      <ErrorNote message={error} />
      {notice ? <p className="text-sm text-charcoal/70">{notice}</p> : null}
      <div className="grid gap-3 lg:grid-cols-3">
        {cards.map((card) => {
          const draft = drafts[card.channel] ?? { provider: card.provider, config: {}, secret: "" };
          const extra = fields[draft.provider] ?? [];
          return (
            <article key={card.channel} className="rounded-card border border-line bg-white p-4">
              <div className="flex items-center justify-between gap-2">
                <h3 className="font-semibold">{labels[card.channel]}</h3>
                <span className="text-xs capitalize text-charcoal/50">{card.status.replaceAll("_", " ")}</span>
              </div>
              <p className="mt-1 text-xs text-charcoal/50">
                {card.secret_set ? `Credential saved ${card.secret_hint ?? ""}` : "No credential stored"}
              </p>
              <SelectField
                className="mt-3"
                label="Provider"
                value={draft.provider}
                options={card.providers.map((value) => ({ value, label: value }))}
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
              {draft.provider !== "log" ? (
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
                    className="mt-1 h-10 w-full rounded-xl bg-surface px-3 text-sm font-normal"
                  />
                </label>
              ) : null}
              {draft.provider === "whatsapp_cloud" ? (
                <p className="mt-2 text-xs text-charcoal/50">
                  Use the phone number ID and token from your own WhatsApp Business account. Paste a new token here to
                  rotate it.
                </p>
              ) : null}
              {draft.provider === "smtp" ? (
                <p className="mt-2 text-xs text-charcoal/50">
                  Publish SPF, DKIM, and DMARC for the sender domain. A completed form is not proof of inbox delivery.
                </p>
              ) : null}
              <div className="mt-3 flex flex-wrap gap-2">
                <PrimaryButton disabled={busy} onClick={() => void save(card, true)}>
                  {card.enabled ? "Save" : "Turn on"}
                </PrimaryButton>
                {card.enabled ? (
                  <button type="button" className="text-sm font-semibold" disabled={busy} onClick={() => void test(card)}>
                    Test
                  </button>
                ) : null}
                {card.enabled ? (
                  <button
                    type="button"
                    className="text-sm font-semibold text-charcoal/60"
                    disabled={busy}
                    onClick={() => void save(card, false)}
                  >
                    Turn off
                  </button>
                ) : null}
              </div>
              {card.last_error ? <p className="mt-2 text-xs text-accent">{card.last_error}</p> : null}
            </article>
          );
        })}
      </div>
    </div>
  );
}
