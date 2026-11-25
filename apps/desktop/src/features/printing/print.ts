import { receiptPlainText, renderReceipt, slipDefault, slipLanguage, type ReceiptDoc } from "@ai-pos/receipt";
import { receiptProfile } from "../checkout/currency";
import { inTauri, openCashDrawer, printRaster, printerSettings, type PrinterSettings } from "../../lib/tauri";
import { RENDER_FAILED, SPOOLER_ACCEPTED, inkBytes } from "./printerSelection";

export const BROWSER_PRINTER: PrinterSettings = {
  transport: "none",
  address: "",
  paper_dots: 576,
  drawer_kick: false,
  auto_print: false,
  copies: 1,
};

export async function loadPrinter(): Promise<PrinterSettings> {
  if (!inTauri()) return BROWSER_PRINTER;
  try {
    return await printerSettings();
  } catch {
    return BROWSER_PRINTER;
  }
}

/** Opens the system print dialog with the rendered slip, for registers without a thermal printer. */
function printInBrowser(canvas: HTMLCanvasElement): void {
  const frame = document.createElement("iframe");
  frame.setAttribute("aria-hidden", "true");
  frame.style.cssText = "position:fixed;width:0;height:0;border:0;opacity:0";
  document.body.appendChild(frame);
  const page = frame.contentDocument!;
  page.open();
  page.write(
    `<!doctype html><html><head><style>@page{margin:4mm}body{margin:0}img{width:72mm}</style></head><body><img src="${canvas.toDataURL("image/png")}"></body></html>`,
  );
  page.close();
  const image = page.querySelector("img")!;
  const go = () => {
    frame.contentWindow?.focus();
    frame.contentWindow?.print();
    window.setTimeout(() => frame.remove(), 1000);
  };
  if (image.complete) go();
  else image.onload = go;
}

export interface PrintOutcome {
  printed: boolean;
  message: string | null;
}

/** Reprints and refunds read the saved receipt language, not the language of the register screen. */
function withSavedLanguage(doc: ReceiptDoc): ReceiptDoc {
  const profile = receiptProfile();
  const language = slipLanguage(profile?.settings ?? doc.branding, profile?.country);
  const footer = doc.footer?.trim() ?? "";
  const kind = (["thankYou", "refund", "gift", "test"] as const).find(
    (name) => footer === slipDefault(name, "en") || footer === slipDefault(name, "ar"),
  );
  return {
    ...doc,
    branding: profile?.settings ?? doc.branding,
    language,
    footer: kind ? slipDefault(kind, language) : doc.footer,
  };
}

/** Cash taken in, and the register policy, are both required. Card, failed, and cancelled sales pass kickDrawer false. */
export interface PrintRequest {
  kickDrawer: boolean;
  manual?: boolean;
  /** Opens the Windows print dialog only when no receipt printer is configured. Checkout never sets this. */
  systemDialog?: boolean;
}
export function shouldKickDrawer(
  options: { kickDrawer: boolean },
  settings: Pick<PrinterSettings, "drawer_kick" | "transport">,
): boolean {
  return (
    options.kickDrawer &&
    settings.drawer_kick &&
    (settings.transport === "tcp" || settings.transport === "windows")
  );
}

/**
 * Prints a receipt on the configured printer. The drawer kicks only when the caller passes kickDrawer
 * and the register policy allows it.
 *
 * Checkout asks after each settled payment and passes manual only when the cashier chooses Yes.
 * auto_print does not print or skip that receipt. Refunds and other callers still honor auto_print
 * when manual is omitted.
 */
export async function printReceipt(doc: ReceiptDoc, options: PrintRequest): Promise<PrintOutcome> {
  const slip = withSavedLanguage(doc);
  const settings = await loadPrinter();
  if (settings.transport === "none") {
    if (!options.manual) return { printed: false, message: null };
    if (!options.systemDialog) {
      return { printed: false, message: "No receipt printer is configured. Open Register settings and choose a printer." };
    }
    const rendered = await renderReceipt(slip, settings.paper_dots);
    printInBrowser(rendered.canvas);
    return { printed: true, message: null };
  }
  if (!options.manual && !settings.auto_print) {
    if (shouldKickDrawer(options, settings)) await openCashDrawer().catch(() => undefined);
    return { printed: false, message: null };
  }
  try {
    const rendered = await renderReceipt(slip, settings.paper_dots);
    const data = rendered.bits();
    if (data.length === 0 || inkBytes(data) === 0) {
      return { printed: false, message: RENDER_FAILED };
    }
    await printRaster({
      width: rendered.width,
      height: rendered.height,
      data,
      kick_drawer: shouldKickDrawer(options, settings),
      line_count: slip.lines.length,
      document_number: slip.number,
      subtotal_cents: slip.subtotalCents,
      tax_cents: slip.taxCents,
      discount_cents: slip.youSavedCents ?? 0,
      total_cents: slip.totalCents,
      plain_text: receiptPlainText(slip, settings.paper_dots <= 384 ? 32 : 42),
    });
    return { printed: true, message: slip.number ? `${SPOOLER_ACCEPTED} ${slip.number}.` : SPOOLER_ACCEPTED };
  } catch (error) {
    return { printed: false, message: error instanceof Error ? error.message : String(error) };
  }
}
