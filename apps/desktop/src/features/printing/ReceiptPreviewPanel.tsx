import { renderReceipt, type ReceiptDoc } from "@ai-pos/receipt";
import { useEffect, useRef, useState } from "react";
import { paperLabel } from "./settingsPreview";

/** Sample slip for Printer & Drawer only. Checkout must not mount this panel. */
export function ReceiptPreviewPanel({ doc, width }: { doc: ReceiptDoc; width: 384 | 576 }) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(true);
  const docRef = useRef(doc);
  docRef.current = doc;
  const signature = [
    width,
    doc.storeName,
    doc.storeAddress,
    doc.trn,
    doc.number,
    doc.branding?.logo_png ?? "",
    doc.branding?.header_text ?? "",
    doc.branding?.footer_text ?? "",
    doc.footer,
    doc.lines.map((line) => `${line.name}|${line.detail}|${line.quantity}|${line.unitCents}`).join(";"),
    doc.subtotalCents,
    doc.taxCents,
    doc.totalCents,
    doc.currency,
  ].join("\n");

  useEffect(() => {
    let cancelled = false;
    const current = docRef.current;
    setBusy(true);
    setError(null);
    void renderReceipt(current, width)
      .then((rendered) => {
        if (cancelled) return;
        if (rendered.width !== width) {
          setError("The receipt preview was drawn at the wrong paper width.");
          setUrl(null);
          setBusy(false);
          return;
        }
        setUrl(rendered.canvas.toDataURL("image/png"));
        setBusy(false);
      })
      .catch((caught: unknown) => {
        if (cancelled) return;
        setUrl(null);
        setError(caught instanceof Error ? caught.message : "The receipt preview could not be rendered.");
        setBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [signature, width]);

  const paper = paperLabel(width);
  return (
    <section aria-label="Receipt Preview" className="rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
      <h3 className="text-lg font-semibold">Receipt Preview</h3>
      <p className="mt-1 text-sm text-zinc-500">
        Sample data at {paper}. This preview does not create a sale, a payment, or a drawer kick, and it is not shown at checkout.
      </p>
      <div className="mt-4 flex justify-center overflow-auto rounded-xl bg-zinc-100 p-4 dark:bg-zinc-950">
        {busy ? <p role="status">Rendering receipt preview…</p> : null}
        {error ? (
          <p role="alert" className="text-sm font-medium text-red-600 dark:text-red-400">
            {error}
          </p>
        ) : null}
        {url ? (
          <img
            src={url}
            alt={`Sample receipt at ${paper}`}
            style={{ width: paper, height: "auto", maxWidth: "100%" }}
          />
        ) : null}
      </div>
    </section>
  );
}
