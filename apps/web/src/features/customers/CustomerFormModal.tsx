import {
  PAYMENT_TERMS_LABELS,
  PRICE_TIER_LABELS,
  PRICE_TIERS,
  TAX_TREATMENT_LABELS,
  type Customer,
  type CustomerGroup,
  type CustomerType,
  type PaymentTerms,
  type PriceTier,
  type TaxTreatment,
} from "@ai-pos/shared-types";
import { useEffect, useState } from "react";
import { ErrorNote, GhostButton, PrimaryButton, SelectField, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { Toggle } from "../../components/ui/Toggle";
import { priceListsApi } from "../inventory/priceListsApi";
import { centsText, customersApi, message, toCents } from "./api";

const typeOptions = [
  { value: "WHOLESALE", label: "Wholesale (B2B)" },
  { value: "RETAIL", label: "Retail / walk-in" },
] as const;

const termOptions = (Object.keys(PAYMENT_TERMS_LABELS) as PaymentTerms[]).map((value) => ({
  value,
  label: PAYMENT_TERMS_LABELS[value],
}));

interface CustomerFormModalProps {
  customer: Customer | null;
  currency: string;
  onClose: () => void;
  onSaved: (customer: Customer) => void;
  /** Text searched for before choosing to add a customer: a phone number or a name. */
  prefill?: string;
}

const PHONE_LIKE = /^[+\d][\d\s()-]{5,}$/;

export function CustomerFormModal({ customer, currency, onClose, onSaved, prefill = "" }: CustomerFormModalProps) {
  const editing = customer !== null;
  const prefillPhone = PHONE_LIKE.test(prefill.trim());
  const [customerType, setCustomerType] = useState<CustomerType>(customer?.customer_type ?? (prefill ? "RETAIL" : "WHOLESALE"));
  const [name, setName] = useState(customer?.name ?? (prefillPhone ? "" : prefill.trim()));
  const [company, setCompany] = useState(customer?.company_name ?? "");
  const [trn, setTrn] = useState(customer?.trn_vat_number ?? "");
  const [phone, setPhone] = useState(customer?.phone ?? (prefillPhone ? prefill.trim() : ""));
  const [email, setEmail] = useState(customer?.email ?? "");
  const [address, setAddress] = useState(customer?.address ?? "");
  const [birthday, setBirthday] = useState(customer?.birthday ?? "");
  const [gender, setGender] = useState(customer?.gender ?? "");
  const [tops, setTops] = useState(customer?.preferred_sizes?.tops ?? "");
  const [bottoms, setBottoms] = useState(customer?.preferred_sizes?.bottoms ?? "");
  const [notes, setNotes] = useState(customer?.notes ?? "");
  const [tags, setTags] = useState((customer?.tags ?? []).join(", "));
  const [tier, setTier] = useState<PriceTier>(customer?.price_tier ?? "TIER_1");
  const [terms, setTerms] = useState<PaymentTerms>(customer?.payment_terms ?? "NET_30");
  const [limit, setLimit] = useState(customer ? centsText(customer.credit_limit_cents) : "0.00");
  const [active, setActive] = useState(customer?.is_active ?? true);
  const [consent, setConsent] = useState({
    whatsapp_opt_in: customer?.whatsapp_opt_in ?? false,
    sms_opt_in: customer?.sms_opt_in ?? false,
    email_opt_in: customer?.email_opt_in ?? false,
  });
  const [groups, setGroups] = useState<CustomerGroup[]>([]);
  const [groupId, setGroupId] = useState(customer?.group_id ?? "");
  const [treatment, setTreatment] = useState<TaxTreatment>(customer?.tax_treatment ?? "STANDARD");
  const [certificate, setCertificate] = useState(customer?.tax_certificate_ref ?? "");
  const [certificateExpiry, setCertificateExpiry] = useState(customer?.tax_certificate_expiry ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const wholesale = customerType === "WHOLESALE";

  useEffect(() => {
    void priceListsApi.groups().then(setGroups).catch(() => undefined);
  }, []);

  const save = async () => {
    const limitCents = wholesale ? toCents(limit) : 0;
    if (name.trim() === "") {
      setError("Enter the contact name.");
      return;
    }
    if (limitCents === null) {
      setError("Enter the credit limit as an amount such as 5000.00.");
      return;
    }
    const body = {
      name: name.trim(),
      customer_type: customerType,
      company_name: company.trim() || null,
      trn_vat_number: trn.trim() || null,
      phone: phone.trim() || null,
      email: email.trim() || null,
      address: address.trim() || null,
      price_tier: wholesale ? tier : ("RETAIL" as PriceTier),
      payment_terms: wholesale ? terms : ("DUE_ON_RECEIPT" as PaymentTerms),
      credit_limit_cents: limitCents,
      is_active: active,
      ...consent,
      group_id: groupId || null,
      tax_treatment: treatment,
      tax_certificate_ref: treatment === "STANDARD" ? null : certificate.trim() || null,
      tax_certificate_expiry: treatment === "STANDARD" ? null : certificateExpiry || null,
      birthday: birthday || null,
      gender: (gender || null) as Customer["gender"],
      preferred_sizes: { ...(tops.trim() ? { tops: tops.trim() } : {}), ...(bottoms.trim() ? { bottoms: bottoms.trim() } : {}) },
      notes: notes.trim() || null,
      tags: tags.split(",").map((tag) => tag.trim()).filter(Boolean),
    };
    setBusy(true);
    setError(null);
    try {
      onSaved(editing ? await customersApi.update(customer.id, body) : await customersApi.create(body));
    } catch (caught) {
      setError(message(caught, "Could not save the customer."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title={editing ? `Edit ${customer.company_name ?? customer.name}` : "New customer"}
      subtitle={editing ? customer.code : "Wholesale accounts get a price tier, credit limit, and payment terms."}
      onClose={onClose}
      width="lg"
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy} onClick={() => void save()}>
            {busy ? "Saving…" : editing ? "Save changes" : "Create customer"}
          </PrimaryButton>
        </>
      }
    >
      <SegmentedControl label="Customer type" value={customerType} options={typeOptions} onChange={setCustomerType} />
      <div className="mt-5 grid gap-4 md:grid-cols-2">
        <TextField label="Contact name" value={name} onChange={(event) => setName(event.target.value)} />
        <TextField
          label="Company name"
          value={company}
          placeholder={wholesale ? "Registered trading name" : "Optional"}
          onChange={(event) => setCompany(event.target.value)}
        />
        <TextField label="Phone" value={phone} onChange={(event) => setPhone(event.target.value)} />
        <TextField label="Email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
        <TextField
          label="TRN / VAT number"
          value={trn}
          hint="Printed on quotations and statements."
          onChange={(event) => setTrn(event.target.value)}
        />
        <TextField label="Address" value={address} onChange={(event) => setAddress(event.target.value)} />
        <TextField label="Birthday" type="date" value={birthday} onChange={(event) => setBirthday(event.target.value)} />
        <SelectField
          label="Gender"
          value={gender}
          placeholder="Not set"
          options={[
            { value: "women", label: "Women" },
            { value: "men", label: "Men" },
            { value: "kids", label: "Kids" },
            { value: "unisex", label: "Unisex" },
          ]}
          onChange={setGender}
        />
        <TextField label="Tops size" value={tops} onChange={(event) => setTops(event.target.value)} />
        <TextField label="Bottoms size" value={bottoms} onChange={(event) => setBottoms(event.target.value)} />
        <TextField label="Tags" value={tags} placeholder="vip, denim" onChange={(event) => setTags(event.target.value)} />
        <TextField label="Notes" value={notes} onChange={(event) => setNotes(event.target.value)} />
      </div>
      {wholesale ? (
        <div className="mt-5 grid gap-4 rounded-2xl bg-surface p-4 md:grid-cols-3">
          <SelectField
            label="Price tier"
            value={tier}
            options={PRICE_TIERS.map((value) => ({ value, label: PRICE_TIER_LABELS[value] }))}
            onChange={setTier}
          />
          <SelectField label="Payment terms" value={terms} options={termOptions} onChange={setTerms} />
          <TextField
            label={`Credit limit (${currency})`}
            inputMode="decimal"
            value={limit}
            className="bg-white tabular-nums"
            onChange={(event) => setLimit(event.target.value)}
          />
        </div>
      ) : null}
      <div className="mt-5 grid gap-4 md:grid-cols-2">
        <SelectField
          label="Customer group"
          hint="Shares the group's tier, discount and price lists."
          value={groupId}
          options={[{ value: "", label: "No group" }, ...groups.map((group) => ({ value: group.id, label: group.name }))]}
          onChange={setGroupId}
        />
        <SelectField
          label="VAT treatment"
          hint="Zero-rated and exempt customers pay no VAT on standard-rated items."
          value={treatment}
          options={(Object.keys(TAX_TREATMENT_LABELS) as TaxTreatment[]).map((value) => ({ value, label: TAX_TREATMENT_LABELS[value] }))}
          onChange={setTreatment}
        />
        {treatment === "STANDARD" ? null : (
          <>
            <TextField
              label="Certificate / evidence ref"
              value={certificate}
              maxLength={64}
              placeholder="Export declaration or exemption certificate"
              onChange={(event) => setCertificate(event.target.value)}
            />
            <TextField
              label="Certificate expires"
              type="date"
              value={certificateExpiry}
              hint="After this date sales fall back to standard VAT."
              onChange={(event) => setCertificateExpiry(event.target.value)}
            />
          </>
        )}
      </div>
      <div className="mt-5">
        <p className="text-sm font-semibold">Message consent</p>
        <p className="text-xs text-charcoal/60">Receipts, statements and reminders go only to channels the customer agreed to.</p>
        <div className="mt-3 grid gap-3 md:grid-cols-3">
          <Toggle
            label="WhatsApp"
            description={phone.trim() ? phone.trim() : "Needs a phone number"}
            checked={consent.whatsapp_opt_in}
            onChange={(value) => setConsent((current) => ({ ...current, whatsapp_opt_in: value }))}
          />
          <Toggle
            label="SMS"
            description={phone.trim() ? phone.trim() : "Needs a phone number"}
            checked={consent.sms_opt_in}
            onChange={(value) => setConsent((current) => ({ ...current, sms_opt_in: value }))}
          />
          <Toggle
            label="Email"
            description={email.trim() ? email.trim() : "Needs an email address"}
            checked={consent.email_opt_in}
            onChange={(value) => setConsent((current) => ({ ...current, email_opt_in: value }))}
          />
        </div>
      </div>
      {editing ? (
        <div className="mt-4">
          <Toggle label="Active" description="Inactive accounts disappear from registers" checked={active} onChange={setActive} />
        </div>
      ) : null}
      <ErrorNote message={error} />
    </Modal>
  );
}
