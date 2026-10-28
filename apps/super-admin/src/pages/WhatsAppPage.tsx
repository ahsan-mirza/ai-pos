import { isValidE164, PhoneField } from "@ai-pos/ui";
import { useEffect, useState } from "react";
import { PageHeader } from "../components/PageHeader";
import { ErrorNote, Field, GhostButton, PrimaryButton } from "../components/ui";
import { ConsoleError, api, errorText } from "../lib/api";
import { useSession } from "../lib/session";

interface SiteContact {
  enabled: boolean;
  whatsapp: string;
  message: string;
  tooltip: string;
  email: string;
}

interface FormState {
  enabled: boolean;
  phone: string;
  message: string;
  tooltip: string;
  email: string;
}

const EMPTY_FORM: FormState = {
  enabled: true,
  phone: "",
  message: "",
  tooltip: "Chat with Sales",
  email: "",
};

function toForm(row: SiteContact): FormState {
  const digits = row.whatsapp.replace(/\D/g, "");
  return {
    enabled: row.enabled,
    phone: digits ? `+${digits}` : "",
    message: row.message,
    tooltip: row.tooltip || "Chat with Sales",
    email: row.email ?? "",
  };
}

function previewUrl(phone: string, message: string): string | null {
  if (!isValidE164(phone)) return null;
  const digits = phone.replace(/\D/g, "");
  const text = message.trim();
  const base = `https://wa.me/${digits}`;
  return text ? `${base}?text=${encodeURIComponent(text)}` : base;
}

function fieldErrors(form: FormState): { phone?: string; message?: string; tooltip?: string; email?: string } {
  const next: { phone?: string; message?: string; tooltip?: string; email?: string } = {};
  if (form.phone && !isValidE164(form.phone)) {
    next.phone = "Enter a valid WhatsApp number, including the country code.";
  } else if (form.enabled && !form.phone) {
    next.phone = "Enter the WhatsApp number before showing the button.";
  }
  if (form.message.trim().length > 500) next.message = "Keep the welcome message under 500 characters.";
  if (form.tooltip.trim().length > 40) next.tooltip = "Keep the label under 40 characters.";
  const email = form.email.trim();
  if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    next.email = "Enter a valid sales email, or leave it blank.";
  }
  return next;
}

export function WhatsAppPage() {
  const { operator } = useSession();
  const admin = operator?.role === "ADMIN";
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [savedForm, setSavedForm] = useState<FormState>(EMPTY_FORM);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [phoneError, setPhoneError] = useState<string | null>(null);
  const [messageError, setMessageError] = useState<string | null>(null);
  const [tooltipError, setTooltipError] = useState<string | null>(null);
  const [emailError, setEmailError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [ready, setReady] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .get<SiteContact>("/site/contact")
      .then((row) => {
        const next = toForm(row);
        setForm(next);
        setSavedForm(next);
        setLoaded(true);
        setError(null);
      })
      .catch((caught: unknown) => setError(errorText(caught, "Could not load the WhatsApp contact.")))
      .finally(() => setReady(true));
  }, []);

  const dirty =
    form.enabled !== savedForm.enabled ||
    form.phone !== savedForm.phone ||
    form.message !== savedForm.message ||
    form.tooltip !== savedForm.tooltip ||
    form.email !== savedForm.email ||
    reason !== "";

  const applyErrors = (next: { phone?: string; message?: string; tooltip?: string; email?: string }) => {
    setPhoneError(next.phone ?? null);
    setMessageError(next.message ?? null);
    setTooltipError(next.tooltip ?? null);
    setEmailError(next.email ?? null);
    return Object.keys(next).length > 0;
  };

  const cancel = () => {
    setForm(savedForm);
    setReason("");
    setSaved(false);
    setError(null);
    setPhoneError(null);
    setMessageError(null);
    setTooltipError(null);
    setEmailError(null);
  };

  const save = () => {
    if (applyErrors(fieldErrors(form))) return;
    setBusy(true);
    setSaved(false);
    api
      .patch<SiteContact>("/site/contact", {
        enabled: form.enabled,
        whatsapp: form.phone,
        message: form.message,
        tooltip: form.tooltip,
        email: form.email.trim(),
        reason: reason.trim(),
      })
      .then((row) => {
        const next = toForm(row);
        setForm(next);
        setSavedForm(next);
        setReason("");
        setError(null);
        setSaved(true);
      })
      .catch((caught: unknown) => {
        const message = errorText(caught, "Could not save the WhatsApp contact.");
        if (caught instanceof ConsoleError && caught.code === "invalid_sales_email") {
          setEmailError(message);
          setError(null);
        } else if (
          caught instanceof ConsoleError &&
          (caught.code === "invalid_whatsapp" || caught.code === "whatsapp_required")
        ) {
          setPhoneError(message);
          setError(null);
        } else {
          setError(message);
        }
      })
      .finally(() => setBusy(false));
  };

  const preview = form.enabled ? previewUrl(form.phone, form.message) : null;

  return (
    <section className="max-w-xl" aria-busy={busy}>
      <PageHeader
        title="WhatsApp Sales Contact"
        description="The landing-page demo form, the floating button, and the site footer use this WhatsApp number. The footer also shows the sales email. The visitor still has to press Send in WhatsApp."
      />
      {!ready ? (
        <p className="mt-6 text-sm text-charcoal/60">Loading…</p>
      ) : !loaded ? (
        <ErrorNote message={error ?? "Could not load the WhatsApp contact."} />
      ) : (
        <div className="mt-6 space-y-4 rounded-3xl border border-line bg-white p-5">
          <label className="flex items-center gap-2 text-sm font-medium">
            <input
              type="checkbox"
              checked={form.enabled}
              disabled={!admin || busy}
              onChange={(event) => {
                setForm((current) => ({ ...current, enabled: event.target.checked }));
                setSaved(false);
              }}
            />
            Show the WhatsApp button
          </label>
          <PhoneField
            label="WhatsApp business number"
            value={form.phone}
            disabled={!admin || busy}
            error={phoneError ?? undefined}
            hint="Include the country code. The link uses digits only, without a leading +."
            onChange={(phone) => {
              setForm((current) => ({ ...current, phone }));
              setPhoneError(null);
              setSaved(false);
            }}
          />
          <Field
            label="Sales email"
            type="email"
            autoComplete="email"
            value={form.email}
            maxLength={254}
            disabled={!admin || busy}
            error={emailError ?? undefined}
            hint="Shown in the site footer. Leave blank to hide it. This is not the mailbox that sends password resets."
            onChange={(event) => {
              setForm((current) => ({ ...current, email: event.target.value }));
              setEmailError(null);
              setSaved(false);
            }}
          />
          <Field
            label="Default welcome message"
            multiline
            rows={4}
            value={form.message}
            maxLength={500}
            disabled={!admin || busy}
            error={messageError ?? undefined}
            hint={`${form.message.trim().length}/500. This text is prefilled. It is not sent until the visitor sends it.`}
            onChange={(event) => {
              setForm((current) => ({ ...current, message: event.target.value }));
              setMessageError(null);
              setSaved(false);
            }}
          />
          <Field
            label="Button label"
            value={form.tooltip}
            maxLength={40}
            disabled={!admin || busy}
            error={tooltipError ?? undefined}
            hint="Shown beside the button on desktop. Leave blank to use Chat with Sales."
            onChange={(event) => {
              setForm((current) => ({ ...current, tooltip: event.target.value }));
              setTooltipError(null);
              setSaved(false);
            }}
          />
          {preview ? (
            <p className="text-xs leading-5 text-charcoal/60">
              <a href={preview} target="_blank" rel="noopener noreferrer" className="font-medium text-accent">
                Preview the chat
              </a>
              <span className="mt-1 block break-all font-mono text-[11px]">{preview}</span>
            </p>
          ) : (
            <p className="text-xs leading-5 text-charcoal/50">
              {form.enabled
                ? "Add a valid number to preview the WhatsApp link."
                : "The button stays hidden while this is turned off."}
            </p>
          )}
          {admin ? (
            <>
              <Field
                label="Reason (kept in the audit log)"
                value={reason}
                maxLength={500}
                disabled={busy}
                onChange={(event) => {
                  setReason(event.target.value);
                  setSaved(false);
                }}
              />
              <div className="flex flex-wrap items-center gap-3">
                <PrimaryButton disabled={busy || reason.trim().length < 3} onClick={save}>
                  {busy ? "Saving…" : "Save"}
                </PrimaryButton>
                <GhostButton disabled={busy || !dirty} onClick={cancel}>
                  Cancel
                </GhostButton>
                {saved ? (
                  <p role="status" className="text-sm text-charcoal/60">
                    Saved. The landing page uses this contact.
                  </p>
                ) : null}
              </div>
            </>
          ) : (
            <p className="text-sm text-charcoal/60">Only a console admin can change the WhatsApp contact.</p>
          )}
          <ErrorNote message={error} />
        </div>
      )}
    </section>
  );
}
