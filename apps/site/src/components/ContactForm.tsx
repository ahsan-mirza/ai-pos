import { useId, useState, type FormEvent, type ReactNode } from "react";
import { signupUrl } from "../env";

const TYPES = ["Restaurant", "Café", "Retail", "Wholesale", "Fashion", "Electronics"] as const;

interface Fields {
  name: string;
  email: string;
  phone: string;
  type: (typeof TYPES)[number];
  message: string;
}

const EMPTY: Fields = { name: "", email: "", phone: "", type: "Restaurant", message: "" };

function whatsappDigits(number: string): string {
  return number.replace(/\D/g, "");
}

export function ContactForm({ whatsapp, compact = false }: { whatsapp: string; compact?: boolean }) {
  const base = useId();
  const [fields, setFields] = useState<Fields>(EMPTY);
  const [errors, setErrors] = useState<Partial<Record<keyof Fields, string>>>({});
  const [sent, setSent] = useState(false);
  const digits = whatsappDigits(whatsapp);
  const channelReady = digits.length >= 8;

  function update<K extends keyof Fields>(key: K, value: Fields[K]) {
    setFields((current) => ({ ...current, [key]: value }));
    setErrors((current) => ({ ...current, [key]: undefined }));
  }

  function validate(value: Fields): Partial<Record<keyof Fields, string>> {
    const next: Partial<Record<keyof Fields, string>> = {};
    if (value.name.trim().length < 2) next.name = "Enter your name.";
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.email.trim())) next.email = "Enter a valid email address.";
    if (value.phone.replace(/\D/g, "").length < 8) next.phone = "Enter a phone number we can call.";
    if (value.message.trim().length > 500) next.message = "Keep the note under 500 characters.";
    return next;
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const next = validate(fields);
    setErrors(next);
    if (Object.keys(next).length > 0) return;
    if (!channelReady) return;
    const text = [
      "AxizPOS demo request",
      `Name: ${fields.name.trim()}`,
      `Business: ${fields.type}`,
      `Email: ${fields.email.trim()}`,
      `Phone: ${fields.phone.trim()}`,
      fields.message.trim() ? `Note: ${fields.message.trim()}` : "",
    ]
      .filter(Boolean)
      .join("\n");
    window.open(`https://wa.me/${digits}?text=${encodeURIComponent(text)}`, "_blank", "noopener,noreferrer");
    setSent(true);
  }

  return (
    <form onSubmit={onSubmit} noValidate className={compact ? "grid gap-3" : "grid gap-4"}>
      <Field id={`${base}-name`} label="Name" error={errors.name}>
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
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field id={`${base}-email`} label="Email" error={errors.email}>
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
        </Field>
        <Field id={`${base}-phone`} label="Phone" error={errors.phone}>
          <input
            id={`${base}-phone`}
            name="phone"
            type="tel"
            autoComplete="tel"
            value={fields.phone}
            onChange={(event) => update("phone", event.target.value)}
            className={inputClass}
            aria-invalid={errors.phone ? true : undefined}
            aria-describedby={errors.phone ? `${base}-phone-error` : undefined}
          />
        </Field>
      </div>
      <Field id={`${base}-type`} label="Business type">
        <select
          id={`${base}-type`}
          name="type"
          value={fields.type}
          onChange={(event) => update("type", event.target.value as Fields["type"])}
          className={inputClass}
        >
          {TYPES.map((type) => (
            <option key={type}>{type}</option>
          ))}
        </select>
      </Field>
      <Field id={`${base}-message`} label="What should we walk through?" error={errors.message}>
        <textarea
          id={`${base}-message`}
          name="message"
          rows={compact ? 3 : 4}
          value={fields.message}
          onChange={(event) => update("message", event.target.value)}
          className={inputClass}
          aria-invalid={errors.message ? true : undefined}
          aria-describedby={errors.message ? `${base}-message-error` : undefined}
        />
      </Field>
      {channelReady ? (
        <p className="text-sm leading-6 text-charcoal/70">
          Sending opens WhatsApp with this request so the sales number published for this site can reply.
        </p>
      ) : (
        <p className="text-sm leading-6 text-charcoal/70">
          The sales WhatsApp number is not published yet, so this form cannot send a request. You can still{" "}
          <a href={signupUrl} className="font-semibold text-primary">
            open a practice store
          </a>
          .
        </p>
      )}
      {sent ? <p className="text-sm font-medium text-charcoal">WhatsApp opened with your request. Send the message there to finish.</p> : null}
      <button
        type="submit"
        className="inline-flex h-12 items-center justify-center rounded-2xl bg-primary px-5 text-sm font-semibold text-white hover:bg-primary-hover"
      >
        Send demo request
      </button>
    </form>
  );
}

const inputClass =
  "mt-1 w-full rounded-2xl border border-line bg-surface px-4 py-3 text-base text-charcoal outline-none transition focus:border-primary focus:bg-card";

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
    <label htmlFor={id} className="block text-sm font-medium text-charcoal">
      {label}
      {children}
      {error ? (
        <span id={`${id}-error`} className="mt-1 block text-sm font-medium text-danger">
          {error}
        </span>
      ) : null}
    </label>
  );
}
