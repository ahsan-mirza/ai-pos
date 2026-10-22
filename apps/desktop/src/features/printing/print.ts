import { inTauri, openCashDrawer, printRaster, printerSettings, type PrinterSettings } from "../../lib/tauri";
import { renderReceipt, type ReceiptDoc } from "@ai-pos/receipt";

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

/** Prints a receipt on the configured printer; the drawer kicks only for cash taken in. */
export async function printReceipt(doc: ReceiptDoc, options: { kickDrawer: boolean; manual?: boolean }): Promise<PrintOutcome> {
  const settings = await loadPrinter();
  if (settings.transport === "none") {
    if (!options.manual) return { printed: false, message: null };
    const rendered = await renderReceipt(doc, settings.paper_dots);
    printInBrowser(rendered.canvas);
    return { printed: true, message: null };
  }
  if (!options.manual && !settings.auto_print) {
    if (options.kickDrawer && settings.drawer_kick) await openCashDrawer().catch(() => undefined);
    return { printed: false, message: null };
  }
  try {
    const rendered = await renderReceipt(doc, settings.paper_dots);
    await printRaster({
      width: rendered.width,
      height: rendered.height,
      data: rendered.bits(),
      kick_drawer: options.kickDrawer && settings.drawer_kick,
    });
    return { printed: true, message: null };
  } catch (error) {
    return { printed: false, message: error instanceof Error ? error.message : String(error) };
  }
}
