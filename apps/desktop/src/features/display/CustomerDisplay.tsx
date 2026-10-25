import { formatMoney } from "@ai-pos/shared-types";
import { BrandLogo } from "@ai-pos/ui";
import { CheckCircle2, ScanLine } from "lucide-react";
import QRCode from "qrcode";
import { useEffect, useState } from "react";
import { subscribeDisplay, type DisplayState } from "./displayChannel";

/** Customer-facing second screen: running cart and total, the QR to pay, and a thank-you after the sale. */
export function CustomerDisplay() {
  const [state, setState] = useState<DisplayState | null>(null);
  const [qrImage, setQrImage] = useState<string | null>(null);

  useEffect(() => subscribeDisplay(setState), []);

  const payload = state?.qr?.payload ?? null;
  useEffect(() => {
    if (!payload) {
      setQrImage(null);
      return;
    }
    void QRCode.toDataURL(payload, { margin: 1, width: 420, color: { dark: "#222026", light: "#FFFFFF" } }).then(setQrImage);
  }, [payload]);

  if (state === null || (state.lines.length === 0 && !state.thanks)) {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center bg-charcoal p-10 font-sans text-white">
        <BrandLogo tone="dark" className="h-16 w-auto" />
        <h1 className="mt-8 text-5xl font-semibold tracking-tight">{state?.storeName ?? "Welcome"}</h1>
        <p className="mt-3 text-xl text-white/60">مرحبا · Your items will appear here</p>
      </main>
    );
  }

  if (state.thanks) {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center bg-charcoal p-10 font-sans text-white">
        <CheckCircle2 size={96} className="text-primary" aria-hidden="true" />
        <h1 className="mt-8 text-5xl font-semibold tracking-tight">Thank you!</h1>
        <p className="mt-3 text-2xl text-white/70">{state.thanks}</p>
        <p className="mt-2 text-xl text-white/50">شكراً لتسوقكم معنا</p>
      </main>
    );
  }

  return (
    <main className="grid min-h-screen grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)] gap-6 bg-charcoal p-8 font-sans text-white">
      <section className="flex min-h-0 flex-col rounded-[28px] bg-white/5 p-8">
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-white/50">{state.storeName}</p>
        <ul className="mt-6 flex-1 space-y-4 overflow-y-auto">
          {state.lines.map((line, index) => (
            <li key={`${line.name}-${index}`} className="flex items-baseline justify-between gap-6 text-2xl">
              <span className="min-w-0 truncate">
                <span className="tabular-nums text-white/50">{line.quantity} × </span>
                {line.name}
              </span>
              <span className="shrink-0 font-semibold tabular-nums">{formatMoney(line.totalCents, state.currency)}</span>
            </li>
          ))}
        </ul>
        <dl className="mt-6 space-y-2 border-t border-white/10 pt-6 text-xl">
          <div className="flex justify-between text-white/60">
            <dt>Subtotal</dt>
            <dd className="tabular-nums">{formatMoney(state.subtotalCents, state.currency)}</dd>
          </div>
          <div className="flex justify-between text-white/60">
            <dt>VAT</dt>
            <dd className="tabular-nums">{formatMoney(state.taxCents, state.currency)}</dd>
          </div>
        </dl>
      </section>
      <section className="flex flex-col items-center justify-center rounded-[28px] bg-white p-8 text-charcoal">
        {state.qr && qrImage ? (
          <>
            {state.qr.status === "PAID" ? (
              <CheckCircle2 size={120} className="text-primary" aria-hidden="true" />
            ) : (
              <img src={qrImage} alt="Scan to pay" className="h-80 w-80 rounded-2xl" />
            )}
            <p className="mt-6 flex items-center gap-2 text-2xl font-semibold">
              {state.qr.status === "PAID" ? (
                "Payment received"
              ) : (
                <>
                  <ScanLine size={26} aria-hidden="true" className="text-primary" /> Scan to pay
                </>
              )}
            </p>
            <p className="mt-2 text-lg text-charcoal/60">امسح الرمز للدفع</p>
          </>
        ) : (
          <>
            <p className="text-xl font-medium text-charcoal/60">Total to pay</p>
            <p className="mt-2 text-sm text-charcoal/50">المبلغ الإجمالي</p>
          </>
        )}
        <p className="mt-8 text-7xl font-bold tracking-tight tabular-nums text-primary">
          {formatMoney(state.qr?.amountCents ?? state.totalCents, state.currency)}
        </p>
      </section>
    </main>
  );
}
