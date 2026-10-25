import { isValidE164, PhoneField } from "@ai-pos/ui";
import { Mail, MessageSquare, Store, User } from "lucide-react";
import { useEffect, useId, useState, type FormEvent, type ReactNode } from "react";
import { signupUrl } from "../env";
import { publishedWhatsapp, whatsappChatUrl, type PublicWhatsApp } from "../whatsapp";

const TYPES = ["Restaurant", "Café", "Retail", "Wholesale", "Fashion", "Electronics"] as const;

interface Fields {
  name: string;
  email: string;
  phone: string;
  type: (typeof TYPES)[number];
  message: string;
}

const EMPTY: Fields = { name: "", email: "", phone: "", type: "Restaurant", message: "" };

const inputClass =
  "w-full rounded-xl border border-slate-200 bg-slate-50/50 py-3 pl-11 pr-4 text-sm text-slate-900 outline-none transition-all placeholder:text-slate-400 focus:border-orange-500 focus:bg-white focus:ring-4 focus:ring-orange-500/10";

const selectClass = `${inputClass} walkthrough-select appearance-none pr-10`;

export function ContactForm({
  contact,
  contactStatus = "ready",
  headingId,
  draft,
}: {
  contact: PublicWhatsApp;
  contactStatus?: "loading" | "ready" | "unavailable";
  headingId?: string;
  /** Fills the note when the pricing estimate is sent to this form. */
  draft?: string | null;
}) {
  const base = useId();
  const [fields, setFields] = useState<Fields>(EMPTY);
  const [errors, setErrors] = useState<Partial<Record<keyof Fields, string>>>({});
  const [sent, setSent] = useState(false);
  const [channelError, setChannelError] = useState<string | null>(null);
  const salesNumber = publishedWhatsapp(contact);

  useEffect(() => {
    if (!draft) return;
    setFields((current) => ({ ...current, message: draft.slice(0, 500) }));
    setSent(false);
  }, [draft]);

  function update<K extends keyof Fields>(key: K, value: Fields[K]) {
    setFields((current) => ({ ...current, [key]: value }));
    setErrors((current) => ({ ...current, [key]: undefined }));
  }

  function validate(value: Fields): Partial<Record<keyof Fields, string>> {
    const next: Partial<Record<keyof Fields, string>> = {};
    if (value.name.trim().length < 2) next.name = "Enter your name.";
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.email.trim())) next.email = "Enter a valid email address.";
    if (!isValidE164(value.phone)) next.phone = "Enter a phone number we can call.";
    if (value.message.trim().length > 500) next.message = "Keep the note under 500 characters.";
    return next;
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSent(false);
    const next = validate(fields);
    setErrors(next);
    if (Object.keys(next).length > 0) return;
    if (!salesNumber) {
      setChannelError(salesChannelMessage(contact, contactStatus));
      return;
    }
    const text = [
      "AxizPOS demo request",
      `Name: ${fields.name.trim()}`,
      `Email: ${fields.email.trim()}`,
      `Phone: ${fields.phone.trim()}`,
      `Business type: ${fields.type}`,
      fields.message.trim() ? `Inquiry: ${fields.message.trim()}` : "",
    ]
      .filter(Boolean)
      .join("\n");
    window.open(whatsappChatUrl(salesNumber, text), "_blank", "noopener,noreferrer");
    setChannelError(null);
    setSent(true);
  }

  return (
    <form onSubmit={onSubmit} noValidate className="grid gap-4">
      <div className="mb-2 pr-10">
        <span className="mb-2 block text-xs font-bold uppercase tracking-widest text-orange-500">Contact</span>
        <h2 id={headingId} className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
          Request a walkthrough
        </h2>
      </div>
      <Field id={`${base}-name`} label="Name" error={errors.name}>
        <IconWrap icon={<User size={16} aria-hidden="true" />}>
          <input
            id={`${base}-name`}
            name="name"
            autoComplete="name"
            value={fields.name}
            onChange={(event) => update("name", event.target.value)}
            className={inputClass}
            aria-invalid={errors.name ? true : undefined}
            aria-describedby={errors.name ? `${base}-name-error` : undefined}
          />
        </IconWrap>
      </Field>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field id={`${base}-email`} label="Email" error={errors.email}>
          <IconWrap icon={<Mail size={16} aria-hidden="true" />}>
            <input
              id={`${base}-email`}
              name="email"
              type="email"
              autoComplete="email"
              value={fields.email}
              onChange={(event) => update("email", event.target.value)}
              className={inputClass}
              aria-invalid={errors.email ? true : undefined}
              aria-describedby={errors.email ? `${base}-email-error` : undefined}
            />
          </IconWrap>
        </Field>
        <PhoneField
          label="Phone"
          tone="marketing"
          value={fields.phone}
          onChange={(phone) => update("phone", phone)}
          error={errors.phone}
          defaultCountry="AE"
        />
      </div>
      <Field id={`${base}-type`} label="Business type">
        <IconWrap icon={<Store size={16} aria-hidden="true" />}>
          <select
            id={`${base}-type`}
            name="type"
            value={fields.type}
            onChange={(event) => update("type", event.target.value as Fields["type"])}
            className={selectClass}
          >
            {TYPES.map((type) => (
              <option key={type}>{type}</option>
            ))}
          </select>
        </IconWrap>
      </Field>
      <Field id={`${base}-message`} label="What should we walk through?" error={errors.message}>
        <IconWrap icon={<MessageSquare size={16} aria-hidden="true" />} align="start">
          <textarea
            id={`${base}-message`}
            name="message"
            rows={4}
            value={fields.message}
            onChange={(event) => update("message", event.target.value)}
            className={`${inputClass} h-28 resize-none`}
            aria-invalid={errors.message ? true : undefined}
            aria-describedby={errors.message ? `${base}-message-error` : undefined}
          />
        </IconWrap>
      </Field>
      {salesNumber ? (
        <div className="flex items-start gap-2.5 rounded-xl border border-emerald-200/60 bg-emerald-50/60 p-3">
          <WhatsAppMark />
          <p className="text-xs leading-snug text-emerald-900/80">
            Send opens WhatsApp with your name, email, phone, business type, and note filled in. Press Send in WhatsApp to deliver the message. Nothing is delivered until you do.
          </p>
        </div>
      ) : (
        <p role="alert" className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs leading-snug text-amber-950">
          {channelError ?? salesChannelMessage(contact, contactStatus)}
          {contactStatus === "ready" ? (
            <>
              {" "}
              A console admin can publish it under Settings, then WhatsApp Sales Contact. You can still{" "}
              <a href={signupUrl} className="font-semibold text-orange-600">
                open a practice store
              </a>
              .
            </>
          ) : null}
        </p>
      )}
      {sent ? (
        <p role="status" className="text-sm font-medium text-slate-800">
          WhatsApp opened with your request. Press Send there to deliver it.
        </p>
      ) : null}
      <button
        type="submit"
        className="w-full cursor-pointer rounded-xl bg-gradient-to-r from-[#F26A21] to-amber-500 px-6 py-3.5 text-sm font-semibold text-white shadow-lg shadow-orange-500/25 transition-all hover:brightness-110 active:scale-[0.99] motion-reduce:transform-none sm:text-base"
      >
        Send demo request
      </button>
    </form>
  );
}

function salesChannelMessage(contact: PublicWhatsApp, contactStatus: "loading" | "ready" | "unavailable"): string {
  if (contactStatus === "loading") return "The sales WhatsApp number is still loading. Try again in a moment.";
  if (contactStatus === "unavailable") return "The sales WhatsApp number could not be loaded. Refresh the page and try again.";
  if (!contact.enabled) return "WhatsApp demo requests are turned off.";
  return "The sales WhatsApp number is missing or not a valid international number.";
}

function WhatsAppMark() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 fill-emerald-600">
      <path d="M20.5 3.5A11 11 0 0 0 2.1 17.2L1 23l5.9-1.1A11 11 0 0 0 12 22a11 11 0 0 0 8.5-18.5zM12 20.2a8.2 8.2 0 0 1-4.2-1.1l-.3-.2-3.5.6.7-3.4-.2-.3A8.2 8.2 0 1 1 12 20.2zm4.6-6.1c-.2-.1-1.4-.7-1.6-.8s-.4-.1-.6.1-.6.8-.8.9-.3.2-.5.1a6.7 6.7 0 0 1-2-1.2 7.4 7.4 0 0 1-1.4-1.7c-.1-.3 0-.4.1-.5l.4-.5.2-.3a.5.5 0 0 0 0-.5c-.1-.1-.6-1.3-.8-1.8s-.4-.4-.6-.4h-.5a1 1 0 0 0-.7.3 2.8 2.8 0 0 0-.9 2.1 5 5 0 0 0 1.1 2.7 11.4 11.4 0 0 0 4.6 4 3.7 3.7 0 0 0 1.6.4 2.6 2.6 0 0 0 1.8-1.2 2.2 2.2 0 0 0 .1-1.3c-.1-.2-.3-.2-.5-.3z" />
    </svg>
  );
}

function IconWrap({ icon, align = "center", children }: { icon: ReactNode; align?: "center" | "start"; children: ReactNode }) {
  return (
    <div className="relative">
      <span className={`pointer-events-none absolute left-3.5 text-slate-400 ${align === "start" ? "top-3.5" : "top-1/2 -translate-y-1/2"}`}>{icon}</span>
      {children}
    </div>
  );
}

function Field({
  id,
  label,
  error,
  children,
}: {
  id: string;
  label: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <label htmlFor={id} className="block">
      <span className="mb-1.5 block text-xs font-semibold text-slate-700">{label}</span>
      {children}
      {error ? (
        <span id={`${id}-error`} className="mt-1.5 block text-xs font-medium text-red-600">
          {error}
        </span>
      ) : null}
    </label>
  );
}
