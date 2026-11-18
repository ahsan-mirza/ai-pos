import { PhoneField } from "@ai-pos/ui";
import { useState } from "react";
import { apiBaseUrl } from "../env";
import { publishedWhatsapp, whatsappChatUrl, type PublicWhatsApp } from "../whatsapp";
import { BUSINESS_TYPES, enquiryErrors, type EnquiryDraft, type HardwarePackageCard, type HardwareProduct } from "./model";

const EMPTY: EnquiryDraft = {
  customer_name: "",
  business_name: "",
  email: "",
  phone: "",
  country: "United Arab Emirates",
  business_type: "restaurant",
  product_slug: "",
  package_slug: "",
  quantity: "1",
  message: "",
};

export function EnquiryForm({
  contact,
  products,
  packages,
  productSlug = "",
  packageSlug = "",
}: {
  contact: PublicWhatsApp;
  products: HardwareProduct[];
  packages: HardwarePackageCard[];
  productSlug?: string;
  packageSlug?: string;
}) {
  const [draft, setDraft] = useState<EnquiryDraft>({ ...EMPTY, product_slug: productSlug, package_slug: packageSlug });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [website, setWebsite] = useState("");
  const [sending, setSending] = useState(false);
  const [reference, setReference] = useState("");
  const [failure, setFailure] = useState("");

  function patch(partial: Partial<EnquiryDraft>) {
    setDraft((current) => ({ ...current, ...partial }));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (sending || reference) return;
    const next = enquiryErrors(draft);
    setErrors(next);
    if (Object.keys(next).length) return;
    setSending(true);
    setFailure("");
    const interest = draft.package_slug ? "package" : draft.product_slug ? "product" : "custom";
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/public/hardware/enquiries`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          customer_name: draft.customer_name.trim(),
          business_name: draft.business_name.trim(),
          email: draft.email.trim(),
          phone: draft.phone.trim(),
          country: draft.country.trim(),
          business_type: draft.business_type,
          enquiry_type: interest,
          product_slug: draft.product_slug,
          package_slug: draft.package_slug,
          quantity: Number(draft.quantity),
          message: draft.message.trim(),
          source: window.location.pathname.startsWith("/hardware") ? window.location.pathname : "/hardware",
          website,
        }),
      });
      const body = (await response.json().catch(() => null)) as {
        reference?: string;
        error?: { message?: string; code?: string; details?: { reference?: string } };
      } | null;
      if (response.status === 409 && body?.error?.details?.reference) {
        setReference(body.error.details.reference);
        return;
      }
      if (!response.ok || !body?.reference) {
        setFailure(body?.error?.message || "The enquiry was not saved. Please try again.");
        return;
      }
      setReference(body.reference);
    } catch {
      setFailure("The enquiry was not saved. Check the connection and try again.");
    } finally {
      setSending(false);
    }
  }

  if (reference) {
    const digits = publishedWhatsapp(contact);
    const followUp = digits
      ? whatsappChatUrl(digits, `AxizPOS hardware enquiry ${reference}`)
      : null;
    return (
      <div className="rounded-3xl border border-line bg-card p-6" role="status">
        <h3 className="text-xl font-semibold">Enquiry received</h3>
        <p className="mt-2 text-sm leading-6 text-charcoal/70">Your reference is {reference}. Keep it for the reply from AxizPOS.</p>
        {followUp ? (
          <a className="mt-4 inline-flex rounded-full bg-primary px-5 py-2 text-sm font-medium text-white" href={followUp}>
            Continue on WhatsApp
          </a>
        ) : null}
      </div>
    );
  }

  return (
    <form className="grid gap-3 rounded-3xl border border-line bg-card p-6" onSubmit={submit} noValidate>
      <h3 className="text-xl font-semibold">Request a quotation</h3>
      <label className="text-sm">
        Name
        <input className="mt-1 h-11 w-full rounded-xl border border-line px-3" value={draft.customer_name} onChange={(event) => patch({ customer_name: event.target.value })} required />
        {errors.customer_name ? <span className="text-red-700">{errors.customer_name}</span> : null}
      </label>
      <label className="text-sm">
        Business name
        <input className="mt-1 h-11 w-full rounded-xl border border-line px-3" value={draft.business_name} onChange={(event) => patch({ business_name: event.target.value })} required />
        {errors.business_name ? <span className="text-red-700">{errors.business_name}</span> : null}
      </label>
      <label className="text-sm">
        Email
        <input className="mt-1 h-11 w-full rounded-xl border border-line px-3" type="email" value={draft.email} onChange={(event) => patch({ email: event.target.value })} required />
        {errors.email ? <span className="text-red-700">{errors.email}</span> : null}
      </label>
      <div className="text-sm">
        <PhoneField label="WhatsApp / phone" value={draft.phone} onChange={(phone) => patch({ phone })} />
        {errors.phone ? <span className="text-red-700">{errors.phone}</span> : null}
      </div>
      <label className="text-sm">
        Country
        <input className="mt-1 h-11 w-full rounded-xl border border-line px-3" value={draft.country} onChange={(event) => patch({ country: event.target.value })} />
      </label>
      <label className="text-sm">
        Business type
        <select className="mt-1 h-11 w-full rounded-xl border border-line px-3" value={draft.business_type} onChange={(event) => patch({ business_type: event.target.value })}>
          {BUSINESS_TYPES.map(([id, label]) => (
            <option key={id} value={id}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label className="text-sm">
        Product or package
        <select
          className="mt-1 h-11 w-full rounded-xl border border-line px-3"
          value={draft.package_slug ? `package:${draft.package_slug}` : draft.product_slug ? `product:${draft.product_slug}` : ""}
          onChange={(event) => {
            const [kind, slug] = event.target.value.split(":");
            patch({ product_slug: kind === "product" ? slug ?? "" : "", package_slug: kind === "package" ? slug ?? "" : "" });
          }}
        >
          <option value="">General enquiry</option>
          {products.map((product) => (
            <option key={product.slug} value={`product:${product.slug}`}>
              {product.name}
            </option>
          ))}
          {packages.map((item) => (
            <option key={item.slug} value={`package:${item.slug}`}>
              {item.name}
            </option>
          ))}
        </select>
      </label>
      <label className="text-sm">
        Quantity
        <input className="mt-1 h-11 w-full rounded-xl border border-line px-3" inputMode="numeric" value={draft.quantity} onChange={(event) => patch({ quantity: event.target.value })} />
        {errors.quantity ? <span className="text-red-700">{errors.quantity}</span> : null}
      </label>
      <label className="text-sm">
        Message
        <textarea className="mt-1 min-h-28 w-full rounded-xl border border-line px-3 py-2" value={draft.message} onChange={(event) => patch({ message: event.target.value })} required />
        {errors.message ? <span className="text-red-700">{errors.message}</span> : null}
      </label>
      <label className="absolute left-[-9999px]" aria-hidden="true">
        Website
        <input tabIndex={-1} autoComplete="off" value={website} onChange={(event) => setWebsite(event.target.value)} />
      </label>
      {failure ? (
        <p role="alert" className="rounded-xl bg-red-50 px-3 py-2 text-sm text-red-800">
          {failure}
        </p>
      ) : null}
      <button className="h-11 rounded-full bg-primary text-sm font-medium text-white disabled:opacity-60" type="submit" disabled={sending}>
        {sending ? "Sending…" : "Request quotation"}
      </button>
    </form>
  );
}
