import { receiptTitle, slipLanguage, type ReceiptDoc, type ReceiptIdentity } from "@ai-pos/receipt";
import type { InstalledPrinter, PrinterProbe } from "../../lib/tauri";
import { CANDIDATE, MISSING, OFFLINE, UNSUPPORTED_METHOD, candidateMessage } from "./printerSelection";

/** The live sample slip is drawn only on Printer & Drawer. Checkout and Bill History do not use it. */
export const LIVE_PREVIEW_SURFACE = "register-settings";

export function livePreviewAllowed(surface: string): boolean {
  return surface === LIVE_PREVIEW_SURFACE;
}

/** Sample data only. Building this slip does not create a sale, a payment, or a stock movement. */
export function previewCreatesTransaction(): false {
  return false;
}

/** Discovery, preview, and the test receipt do not kick the drawer. */
export function previewKicksDrawer(): false {
  return false;
}

/** Dots passed to the shared receipt renderer. 58 mm and 80 mm are different layouts, not one image scaled. */
export function layoutWidth(dots: number): 384 | 576 {
  return dots <= 384 ? 384 : 576;
}

export function paperLabel(dots: number): "58 mm" | "80 mm" {
  return layoutWidth(dots) === 384 ? "58 mm" : "80 mm";
}

/**
 * Sample invoice for the Register Settings preview and the matching test print.
 * Amounts are fixed sample figures. They are not a second tax calculation.
 * Business name, address, tax number, logo, header, and footer come from the register identity.
 */
export function settingsPreviewReceipt(identity: ReceiptIdentity, currency: string): ReceiptDoc {
  const title = receiptTitle(identity.trn, null, 5_575, identity.taxAuthority);
  const language = slipLanguage(identity.branding, null);
  const footer = identity.branding?.footer_text?.trim() || "Sample receipt. Not a sale.";
  return {
    storeName: identity.storeName,
    storeAddress: identity.storeAddress,
    storePhone: identity.storePhone,
    legalName: identity.legalName,
    legalNameAr: identity.legalNameAr,
    trn: identity.trn,
    branding: identity.branding ?? null,
    taxAuthority: identity.taxAuthority,
    ...title,
    number: "SAMPLE-1001",
    issuedAt: new Date(2026, 10, 25, 12, 0, 0),
    cashier: "Sample",
    customer: "Sample customer",
    reference: null,
    lines: [
      { name: "Cappuccino", detail: "Regular portion · Oat milk", quantity: 2, unitCents: 1_500, totalCents: 3_000 },
      { name: "Chicken wrap", detail: "Half portion · Extra sauce", quantity: 1, unitCents: 2_500, totalCents: 2_500 },
    ],
    subtotalCents: 5_500,
    taxCents: 275,
    youSavedCents: 200,
    totalCents: 5_575,
    tenders: [
      { label: "Cash", amountCents: 4_000 },
      { label: "On account", amountCents: 1_575 },
    ],
    changeCents: null,
    currency,
    language,
    footer,
    vatIncluded: false,
  };
}

export interface SetupStep {
  step: number;
  title: string;
  detail: string;
}

export function setupSteps(input: {
  queue: string;
  driver: string;
  port: string;
  compatibility: string;
  transport: string;
  drawerVerified: boolean;
  paper: string;
  reachable: boolean;
}): SetupStep[] {
  const detected = input.queue.trim() !== "";
  const unsupported = input.compatibility === "unsupported";
  const candidate = input.compatibility === "candidate";
  const verified = input.compatibility === "compatible" && input.reachable;
  return [
    {
      step: 1,
      title: "Printer detected",
      detail: detected
        ? `${input.queue}. Driver ${input.driver || "not reported"}. Port ${input.port || "not reported"}.`
        : "No Windows printer is selected.",
    },
    {
      step: 2,
      title: "Compatibility",
      detail: unsupported
        ? `${UNSUPPORTED_METHOD} Drawer kick is not available.`
        : candidate
          ? `${CANDIDATE} Transport ${input.transport || "not selected"}. Drawer kick is not verified.`
          : verified
            ? `Receipt printing is available through ${input.transport || "the saved transport"}. ${input.drawerVerified ? "Drawer kick is verified separately." : "Drawer kick is not verified."} Open/closed state: Not reported.`
            : "Compatibility has not been checked.",
    },
    {
      step: 3,
      title: "Receipt preview",
      detail: `Sample invoice at ${input.paper}. Changing the paper width redraws the slip. Nothing is printed.`,
    },
    {
      step: 4,
      title: "Test receipt",
      detail: "Print test receipt sends one sample slip. It does not create a sale or kick the drawer.",
    },
    {
      step: 5,
      title: "Setup result",
      detail: input.reachable
        ? "The queue can be opened. Physical printing is not verified until the paper shows this slip."
        : "Queue connectivity is not confirmed. Physical printing is not verified.",
    },
  ];
}

export function detectionResult(probe: Pick<PrinterProbe, "address" | "compatibility" | "printerStatus" | "reachable" | "driver" | "discoveryOutcome" | "supportsDrawerKick"> | null, queues: readonly InstalledPrinter[]): string {
  if (!probe || probe.printerStatus === "not_configured") return "No receipt printer is configured.";
  const verified = queues.filter((queue) => queue.compatibility === "compatible" && queue.availability === "ready" && queue.openable !== false);
  if (probe.printerStatus === "missing" || probe.discoveryOutcome === "missing") return MISSING;
  if (probe.printerStatus === "offline") return OFFLINE;
  if (probe.compatibility === "unsupported") return `${UNSUPPORTED_METHOD} Receipt printing is not activated.`;
  if (probe.compatibility === "candidate" || probe.printerStatus === "candidate") {
    return candidateMessage({ name: probe.address, driver: probe.driver ?? "" });
  }
  if (probe.discoveryOutcome === "choose" || (!probe.address.trim() && verified.length > 1)) {
    return "More than one verified printer is installed. Choose one.";
  }
  if (probe.discoveryOutcome === "auto" && verified.length === 1) {
    return `Automatically selected ${verified[0]?.name ?? probe.address}. One verified printer was found.`;
  }
  if (probe.compatibility === "compatible" && probe.reachable) {
    return probe.supportsDrawerKick
      ? "Verified receipt printer. Drawer kick is available through this printer. Open/closed state: Not reported."
      : "Verified receipt printer. Drawer kick is not verified for this printer.";
  }
  return probe.reachable ? "Printer discovered." : "The printer connection is not confirmed.";
}
