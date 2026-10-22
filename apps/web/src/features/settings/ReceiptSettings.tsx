import {
  EMPTY_BRANDING,
  PAPER_DOTS,
  prepareLogo,
  receiptTitle,
  renderReceipt,
  type LogoMode,
  type ReceiptDoc,
} from "@ai-pos/receipt";
import { lineTax, zatcaQr, type ReceiptProfile, type ReceiptSettings } from "@ai-pos/shared-types";
import { ImagePlus, Receipt, Trash2 } from "lucide-react";
import { useEffect, useId, useRef, useState, type TextareaHTMLAttributes } from "react";
import { ErrorNote, GhostButton, PrimaryButton, SelectField, TextField } from "../../components/ui/Field";
import { apiGet, apiPut } from "../../lib/api";
import { useCanManageSettings, useCurrency } from "../../lib/currency";
import { useStoreScope } from "../../lib/storeScope";
import { errorMessage } from "../users/api";

type Paper = keyof typeof PAPER_DOTS;

const PAPER_OPTIONS = [
  { value: "80mm" as const, label: "80 mm (standard)" },
  { value: "58mm" as const, label: "58 mm (compact)" },
];

const SAMPLE_LINES = [
  { name: "iPhone 16 Pro 256GB", detail: "IMEI 356789012345678", quantity: 1, unitCents: 449_900 },
  { name: "USB-C cable 1m", detail: null, quantity: 2, unitCents: 3_500 },
];

function TextArea({
  label,
  hint,
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement> & { label: string; hint?: string }) {
  return (
    <label className="block text-sm font-medium">
      {label}
      <textarea
        rows={3}
        {...props}
        className="mt-1.5 w-full resize-y rounded-xl border border-transparent bg-surface px-4 py-3 text-sm font-normal text-charcoal transition-colors placeholder:text-charcoal/40 focus:border-accent focus:bg-white focus:outline-none disabled:cursor-not-allowed disabled:text-charcoal/50"
      />
      {hint ? <span className="mt-1.5 block text-xs font-normal text-charcoal/50">{hint}</span> : null}
    </label>
  );
}

function tidy(form: ReceiptSettings): ReceiptSettings {
  const clean = (value: string | null) => (value?.trim() ? value.trim() : null);
  return {
    logo_png: form.logo_png,
    header_text: clean(form.header_text),
    header_text_ar: clean(form.header_text_ar),
    footer_text: clean(form.footer_text),
    footer_text_ar: clean(form.footer_text_ar),
    email: clean(form.email),
    website: clean(form.website),
  };
}

function logoBytes(dataUrl: string): number {
  return Math.round(((dataUrl.length - dataUrl.indexOf(",") - 1) * 3) / 4);
}

export function ReceiptSettingsCard() {
  const { currency, settings } = useCurrency();
  const canManage = useCanManageSettings();
  const { stores, storeId } = useStoreScope();
  const [form, setForm] = useState<ReceiptSettings | null>(null);
  const [saved, setSaved] = useState<ReceiptSettings | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [logoFile, setLogoFile] = useState<File | null>(null);
  const [logoMode, setLogoMode] = useState<LogoMode>("dither");
  const [logoBusy, setLogoBusy] = useState(false);
  const [paper, setPaper] = useState<Paper>("80mm");
  const [previewStoreId, setPreviewStoreId] = useState<string>("");
  const fileInput = useRef<HTMLInputElement>(null);
  const fileId = useId();

  useEffect(() => {
    let live = true;
    apiGet<ReceiptProfile>("/api/v1/settings/receipt")
      .then((profile) => {
        if (!live) return;
        setForm(profile.settings);
        setSaved(profile.settings);
      })
      .catch((caught) => live && setLoadError(errorMessage(caught, "Could not load the receipt settings.")));
    return () => {
      live = false;
    };
  }, []);

  const sellingStores = stores.filter((store) => !store.is_warehouse && store.is_active !== false);
  useEffect(() => {
    if (previewStoreId || sellingStores.length === 0) return;
    setPreviewStoreId(storeId ?? sellingStores[0]!.id);
  }, [previewStoreId, sellingStores, storeId]);

  const convertLogo = async (file: File, mode: LogoMode) => {
    setLogoBusy(true);
    setError(null);
    try {
      const logo = await prepareLogo(file, mode);
      setForm((current) => (current ? { ...current, logo_png: logo.dataUrl } : current));
    } catch (caught) {
      setError(errorMessage(caught, "Could not convert the logo."));
    } finally {
      setLogoBusy(false);
    }
  };

  if (form === null) {
    return (
      <div className="rounded-card border border-line bg-white p-6 text-sm text-charcoal/60">
        {loadError ?? "Loading receipt settings…"}
      </div>
    );
  }

  const dirty = JSON.stringify(tidy(form)) !== JSON.stringify(saved && tidy(saved));
  const set = (patch: Partial<ReceiptSettings>) => {
    setForm({ ...form, ...patch });
    setNotice(null);
  };
  const previewStore = sellingStores.find((store) => store.id === previewStoreId) ?? null;

  const save = async () => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const profile = await apiPut<ReceiptProfile>("/api/v1/settings/receipt", tidy(form));
      setSaved(profile.settings);
      setForm(profile.settings);
      setLogoFile(null);
      setNotice("Receipt layout saved. Registers print it after their next sync.");
    } catch (caught) {
      setError(errorMessage(caught, "Could not save the receipt layout."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-card border border-line bg-white p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-accent text-white">
            <Receipt size={20} aria-hidden="true" />
          </span>
          <div>
            <h2 className="text-2xl font-semibold">Receipt layout</h2>
            <p className="text-sm text-charcoal/60">
              Logo, welcome note and return policy printed on every register receipt and refund slip.
            </p>
          </div>
        </div>
        {canManage ? (
          <div className="flex gap-2">
            <GhostButton
              disabled={!dirty || busy}
              onClick={() => {
                setForm(saved);
                setLogoFile(null);
                setError(null);
              }}
            >
              Discard
            </GhostButton>
            <PrimaryButton disabled={!dirty || busy || logoBusy} onClick={() => void save()}>
              {busy ? "Saving…" : "Save receipt"}
            </PrimaryButton>
          </div>
        ) : null}
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <fieldset disabled={!canManage} className="min-w-0 space-y-5">
          <div>
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-charcoal/50">Logo</p>
            <div className="flex flex-wrap items-center gap-4 rounded-2xl border border-line p-4">
              <div className="flex h-24 w-48 items-center justify-center overflow-hidden rounded-xl bg-white ring-1 ring-line">
                {form.logo_png ? (
                  <img src={form.logo_png} alt="Receipt logo" className="max-h-24 max-w-full [image-rendering:pixelated]" />
                ) : (
                  <span className="text-xs text-charcoal/40">No logo</span>
                )}
              </div>
              <div className="space-y-2">
                <div className="flex flex-wrap gap-2">
                  <input
                    ref={fileInput}
                    id={fileId}
                    type="file"
                    accept="image/png,image/jpeg,image/webp,image/svg+xml"
                    className="sr-only"
                    onChange={(event) => {
                      const file = event.target.files?.[0];
                      event.target.value = "";
                      if (!file) return;
                      setLogoFile(file);
                      void convertLogo(file, logoMode);
                    }}
                  />
                  <GhostButton disabled={logoBusy || !canManage} onClick={() => fileInput.current?.click()}>
                    <ImagePlus size={16} className="mr-2" aria-hidden="true" />
                    {logoBusy ? "Converting…" : form.logo_png ? "Replace logo" : "Upload logo"}
                  </GhostButton>
                  {form.logo_png ? (
                    <GhostButton
                      disabled={logoBusy || !canManage}
                      onClick={() => {
                        setLogoFile(null);
                        set({ logo_png: null });
                      }}
                    >
                      <Trash2 size={16} className="mr-2" aria-hidden="true" />
                      Remove
                    </GhostButton>
                  ) : null}
                </div>
                {logoFile ? (
                  <div className="flex gap-1 rounded-full bg-surface p-1 text-xs font-semibold" role="radiogroup" aria-label="Conversion">
                    {(
                      [
                        ["dither", "Photo (dithered)"],
                        ["threshold", "Line art"],
                      ] as const
                    ).map(([mode, label]) => (
                      <button
                        key={mode}
                        type="button"
                        role="radio"
                        aria-checked={logoMode === mode}
                        onClick={() => {
                          setLogoMode(mode);
                          void convertLogo(logoFile, mode);
                        }}
                        className={`rounded-full px-3 py-1.5 transition ${
                          logoMode === mode ? "bg-charcoal text-white" : "text-charcoal/60 hover:text-charcoal"
                        }`}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                ) : null}
                <p className="text-xs text-charcoal/50">
                  {form.logo_png
                    ? `Black and white, ${Math.ceil(logoBytes(form.logo_png) / 1024)} KB. Thermal printers have no grey.`
                    : "PNG or JPEG. It is converted to black and white and sized for 58 and 80 mm paper."}
                </p>
              </div>
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <TextArea
              label="Header note"
              maxLength={200}
              rows={2}
              placeholder="Welcome to our store!"
              value={form.header_text ?? ""}
              onChange={(event) => set({ header_text: event.target.value })}
            />
            <TextArea
              label="Header note (Arabic)"
              dir="rtl"
              maxLength={200}
              rows={2}
              value={form.header_text_ar ?? ""}
              onChange={(event) => set({ header_text_ar: event.target.value })}
            />
            <TextArea
              label="Footer / return policy"
              maxLength={500}
              placeholder="Items can be exchanged within 7 days with this receipt."
              hint="Replaces the default “Thank you. Keep this receipt…” line on sales."
              value={form.footer_text ?? ""}
              onChange={(event) => set({ footer_text: event.target.value })}
            />
            <TextArea
              label="Footer (Arabic)"
              dir="rtl"
              maxLength={500}
              value={form.footer_text_ar ?? ""}
              onChange={(event) => set({ footer_text_ar: event.target.value })}
            />
            <TextField
              label="Email"
              type="email"
              maxLength={120}
              placeholder="support@yourstore.ae"
              value={form.email ?? ""}
              onChange={(event) => set({ email: event.target.value })}
            />
            <TextField
              label="Website"
              maxLength={120}
              placeholder="www.yourstore.ae"
              value={form.website ?? ""}
              onChange={(event) => set({ website: event.target.value })}
            />
          </div>

          <p className="rounded-2xl bg-surface px-4 py-3 text-xs text-charcoal/70">
            The legal name and TRN come from <span className="font-semibold">VAT and tax invoices</span> above, and each
            branch prints its own address and phone from the Stores page, so they always match the tax invoice. The ZATCA
            QR code is added automatically when Saudi invoicing is on.
          </p>
        </fieldset>

        <ReceiptPreview
          branding={form}
          paper={paper}
          onPaper={setPaper}
          storeOptions={sellingStores.map((store) => ({ value: store.id, label: store.name }))}
          storeId={previewStoreId}
          onStore={setPreviewStoreId}
          dirty={dirty}
          doc={{
            storeName: previewStore?.name ?? "Main branch",
            storeAddress: previewStore?.address ?? null,
            storePhone: previewStore?.phone ?? null,
            legalName: settings?.legal_name ?? null,
            legalNameAr: settings?.legal_name_ar ?? null,
            trn: settings?.vat_registered ? (settings.trn ?? null) : null,
            taxAuthority: settings?.tax_authority ?? "fta",
            currency,
            ratePercentBps: settings?.vat_registered ? (settings.standard_rate_bps ?? 500) : 0,
            pricesIncludeVat: Boolean(settings?.prices_include_vat),
          }}
        />
      </div>

      {notice ? <p role="status" className="mt-4 rounded-2xl bg-surface px-4 py-3 text-sm">{notice}</p> : null}
      <ErrorNote message={error} />
    </div>
  );
}

interface PreviewIdentity {
  storeName: string;
  storeAddress: string | null;
  storePhone: string | null;
  legalName: string | null;
  legalNameAr: string | null;
  trn: string | null;
  taxAuthority: "fta" | "zatca";
  currency: string;
  ratePercentBps: number;
  pricesIncludeVat: boolean;
}

function sampleDoc(identity: PreviewIdentity, branding: ReceiptSettings): ReceiptDoc {
  const lines = SAMPLE_LINES.map((line) => {
    const tax = lineTax(line.unitCents, line.quantity, identity.ratePercentBps, identity.pricesIncludeVat);
    return { ...line, net: tax.net_cents, tax: tax.tax_cents, totalCents: tax.line_total_cents };
  });
  const subtotal = lines.reduce((sum, line) => sum + line.net, 0);
  const tax = lines.reduce((sum, line) => sum + line.tax, 0);
  const total = subtotal + tax;
  const issuedAt = new Date();
  const qr =
    identity.taxAuthority === "zatca" && identity.trn
      ? zatcaQr({
          sellerName: identity.legalName ?? identity.storeName,
          vatNumber: identity.trn,
          timestamp: `${issuedAt.toISOString().slice(0, 19)}Z`,
          totalCents: total,
          vatCents: tax,
        })
      : null;
  const hasFooter = Boolean(branding.footer_text || branding.footer_text_ar);
  return {
    ...receiptTitle(identity.trn, null, total, identity.taxAuthority),
    storeName: identity.storeName,
    storeAddress: identity.storeAddress,
    storePhone: identity.storePhone,
    legalName: identity.legalName,
    legalNameAr: identity.legalNameAr,
    trn: identity.trn,
    branding,
    number: "DT-01-R1-000123",
    issuedAt,
    cashier: "Sara",
    customer: null,
    reference: null,
    lines: lines.map(({ name, detail, quantity, unitCents, totalCents }) => ({ name, detail, quantity, unitCents, totalCents })),
    subtotalCents: subtotal,
    taxCents: tax,
    totalCents: total,
    tenders: [{ label: "Cash", amountCents: total + (10_000 - (total % 10_000)) }],
    changeCents: 10_000 - (total % 10_000),
    currency: identity.currency,
    footer: hasFooter ? "" : "Thank you. Keep this receipt for returns and warranty.",
    qr,
  };
}

/** Renders with the register's own drawing code, then thresholds to the 1-bit dots the printer receives. */
function ReceiptPreview({
  branding,
  doc,
  paper,
  onPaper,
  storeOptions,
  storeId,
  onStore,
  dirty,
}: {
  branding: ReceiptSettings;
  doc: PreviewIdentity;
  paper: Paper;
  onPaper: (paper: Paper) => void;
  storeOptions: { value: string; label: string }[];
  storeId: string;
  onStore: (storeId: string) => void;
  dirty: boolean;
}) {
  const [image, setImage] = useState<string | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const key = JSON.stringify([branding, doc, paper]);

  useEffect(() => {
    let live = true;
    const timer = window.setTimeout(() => {
      renderReceipt(sampleDoc(doc, { ...EMPTY_BRANDING, ...branding }), PAPER_DOTS[paper])
        .then((rendered) => {
          const ctx = rendered.canvas.getContext("2d")!;
          const pixels = ctx.getImageData(0, 0, rendered.width, rendered.height);
          const data = pixels.data;
          for (let offset = 0; offset < data.length; offset += 4) {
            const luminance = 0.299 * (data[offset] ?? 255) + 0.587 * (data[offset + 1] ?? 255) + 0.114 * (data[offset + 2] ?? 255);
            const tone = luminance < 160 ? 0 : 255;
            data[offset] = tone;
            data[offset + 1] = tone;
            data[offset + 2] = tone;
            data[offset + 3] = 255;
          }
          ctx.putImageData(pixels, 0, 0);
          if (live) {
            setImage(rendered.canvas.toDataURL("image/png"));
            setFailed(null);
          }
        })
        .catch((caught) => live && setFailed(errorMessage(caught, "The preview could not be drawn.")));
    }, 150);
    return () => {
      live = false;
      window.clearTimeout(timer);
    };
    // `key` captures every input; the objects themselves are rebuilt on each render.
  }, [key]);

  return (
    <aside className="rounded-2xl border border-line bg-[#f4f4f5] p-4" aria-label="Receipt preview">
      <div className="flex items-center justify-between">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-[#6B7280]">Live preview</p>
        <span
          className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${
            dirty ? "bg-amber-100 text-amber-800" : "bg-emerald-50 text-emerald-700"
          }`}
        >
          {dirty ? "Not saved" : "Saved"}
        </span>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2">
        <SelectField label="Paper" value={paper} options={PAPER_OPTIONS} onChange={onPaper} />
        {storeOptions.length > 0 ? (
          <SelectField label="Branch" value={storeId} options={storeOptions} onChange={onStore} />
        ) : null}
      </div>
      <div className="mt-4 flex justify-center">
        {image ? (
          <img
            src={image}
            alt="How the receipt prints"
            className="bg-white shadow-[0_8px_24px_rgba(0,0,0,0.12)] [image-rendering:pixelated]"
            style={{ width: paper === "80mm" ? 288 : 192 }}
          />
        ) : (
          <p className="py-10 text-sm text-charcoal/50">{failed ?? "Drawing…"}</p>
        )}
      </div>
      <p className="mt-3 text-center text-[11px] text-charcoal/50">
        Sample sale, drawn dot for dot as the {paper === "80mm" ? "80" : "58"} mm printer receives it.
      </p>
    </aside>
  );
}
