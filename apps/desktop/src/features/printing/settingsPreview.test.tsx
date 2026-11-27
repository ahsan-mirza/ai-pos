import { receiptOps } from "@ai-pos/receipt";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ReceiptConfirmationModal } from "../checkout/ReceiptConfirmationModal";
import type { ReceiptPrompt } from "../checkout/receiptConfirmation";
import { ReceiptHardwareCard } from "./ReceiptHardwareCard";
import type { InstalledPrinter, PrinterProbe } from "../../lib/tauri";
import {
  detectionResult,
  layoutWidth,
  livePreviewAllowed,
  paperLabel,
  previewCreatesTransaction,
  previewKicksDrawer,
  settingsPreviewReceipt,
  setupSteps,
} from "./settingsPreview";
import type { ReceiptDoc } from "@ai-pos/receipt";

const identity = {
  storeName: "Harbour Cafe",
  storeAddress: "12 Creek Road",
  storePhone: "0400 000 000",
  legalName: "Harbour Cafe LLC",
  legalNameAr: null,
  trn: "100000000000003",
  taxAuthority: "fta" as const,
  branding: {
    logo_png: null,
    language: "en" as const,
    header_text: "Welcome",
    header_text_ar: null,
    footer_text: "Thank you for visiting",
    footer_text_ar: null,
    email: null,
    website: null,
  },
};

function queue(patch: Partial<InstalledPrinter> & Pick<InstalledPrinter, "name">): InstalledPrinter {
  return {
    driver: "EPSON TM-T20 Receipt",
    port: "USB001",
    status: 0,
    statusLabel: "Ready",
    unavailable: false,
    compatibility: "compatible",
    supportsDrawerKick: true,
    connection: "USB",
    profileId: "epson-tm",
    openable: true,
    availability: "ready",
    ...patch,
  };
}

function probe(patch: Partial<PrinterProbe> = {}): PrinterProbe {
  return {
    configured: true,
    transport: "windows",
    address: "Epson TM-T20",
    reachable: true,
    reachError: null,
    lastOkAt: null,
    lastError: null,
    lastErrorAt: null,
    lastKickOkAt: null,
    lastKickError: null,
    lastKickAttemptAt: null,
    drawerKick: true,
    printing: false,
    printerStatus: "ready",
    driver: "EPSON TM-T20 Receipt",
    port: "USB001",
    discoveredAt: null,
    drawerOpenState: "not_reported",
    compatibility: "compatible",
    supportsDrawerKick: true,
    connection: "USB",
    discoveryOutcome: "kept",
    previousAddress: "",
    autoDiscover: true,
    model: "Epson",
    driverVersion: null,
    printTransport: "escpos",
    ...patch,
  };
}

describe("register settings receipt preview", () => {
  it("builds a sample invoice and does not create a sale or kick the drawer", () => {
    expect(previewCreatesTransaction()).toBe(false);
    expect(previewKicksDrawer()).toBe(false);
    expect(livePreviewAllowed("register-settings")).toBe(true);
    expect(livePreviewAllowed("checkout")).toBe(false);
    expect(livePreviewAllowed("bill-history")).toBe(false);
    const doc = settingsPreviewReceipt(identity, "AED");
    expect(doc.number).toBe("SAMPLE-1001");
    expect(doc.storeName).toBe("Harbour Cafe");
    expect(doc.storeAddress).toBe("12 Creek Road");
    expect(doc.trn).toBe("100000000000003");
    expect(doc.footer).toBe("Thank you for visiting");
    expect(doc.branding?.header_text).toContain("SAMPLE RECEIPT — NOT A SALE");
    expect(doc.number.startsWith("SAMPLE")).toBe(true);
    expect(doc.lines.map((line) => `${line.name} ${line.detail}`).join(" ")).toContain("Regular portion");
    expect(doc.lines.map((line) => line.detail).join(" ")).toContain("Oat milk");
    expect(doc.lines.map((line) => line.detail).join(" ")).toContain("Half portion");
    expect(doc.lines.map((line) => line.detail).join(" ")).toContain("Extra sauce");
    expect(doc.subtotalCents).toBe(5_500);
    expect(doc.taxCents).toBe(275);
    expect(doc.youSavedCents).toBe(200);
    expect(doc.totalCents).toBe(5_575);
    expect(doc.tenders.map((tender) => tender.label)).toEqual(["Cash", "On account"]);
    expect(doc.tenders.reduce((sum, tender) => sum + tender.amountCents, 0)).toBe(doc.totalCents);
    const text = receiptOps(doc)
      .map((op) => ("text" in op ? op.text : "left" in op ? `${op.left} ${op.right}` : ""))
      .join("\n");
    expect(text).toContain("Harbour Cafe");
    expect(text).toContain("Cappuccino");
    expect(text).toContain("Chicken wrap");
    expect(text).toContain("SAMPLE-1001");
    expect(text).toContain("SAMPLE RECEIPT — NOT A SALE");
    expect(text).toContain("100000000000003");
    expect(layoutWidth(384)).toBe(384);
    expect(layoutWidth(576)).toBe(576);
    expect(paperLabel(384)).toBe("58 mm");
    expect(paperLabel(576)).toBe("80 mm");
  });

  it("guides a candidate without activating an unsupported printer", () => {
    const toshiba = queue({
      name: "Toshiba POS Printer (CR)",
      driver: "Toshiba Native Windows Driver",
      port: "Toshiba: 0_USB",
      statusLabel: "Candidate",
      compatibility: "candidate",
      supportsDrawerKick: false,
      printTransport: "windows-gdi",
      profileId: "",
    });
    const pdf = queue({
      name: "Microsoft Print to PDF",
      driver: "Microsoft Print To PDF",
      port: "PORTPROMPT:",
      compatibility: "unsupported",
      supportsDrawerKick: false,
      availability: "virtual",
      statusLabel: "Virtual printer",
      connection: "Virtual",
      profileId: "",
    });
    expect(detectionResult(probe({ address: toshiba.name, driver: toshiba.driver, compatibility: "candidate", printerStatus: "candidate", supportsDrawerKick: false, printTransport: "windows-gdi" }), [toshiba])).toContain("has not yet been verified");
    expect(detectionResult(probe({ address: pdf.name, compatibility: "unsupported", printerStatus: "unavailable", reachable: false }), [pdf])).toContain("not activated");
    expect(detectionResult(probe({ printerStatus: "missing", discoveryOutcome: "missing", address: "Toshiba thermal" }), [])).toContain("not installed");
    expect(detectionResult(probe({ printerStatus: "offline", reachable: false }), [])).toContain("unavailable");
    expect(detectionResult(probe({ address: "", discoveryOutcome: "choose", compatibility: "compatible", reachable: false, printerStatus: "ready" }), [queue({ name: "Front" }), queue({ name: "Bar" })])).toContain("Choose one");
    expect(detectionResult(probe({ discoveryOutcome: "auto", address: "Epson TM-T20" }), [queue({ name: "Epson TM-T20" })])).toContain("Automatically selected");
    const steps = setupSteps({
      queue: toshiba.name,
      driver: toshiba.driver,
      port: toshiba.port,
      compatibility: "candidate",
      transport: "windows-gdi",
      drawerVerified: false,
      paper: "80 mm",
      reachable: true,
    });
    expect(steps).toHaveLength(5);
    expect(steps[0]?.detail).toContain("Toshiba POS Printer (CR)");
    expect(steps[1]?.detail).toContain("Drawer kick is not verified");
    expect(steps[3]?.detail).toContain("does not create a sale");
    expect(steps[3]?.detail).toContain("kick the drawer");
    expect(steps[4]?.detail).toContain("Physical printing is not verified");
  });

  it("shows the live preview on the printer page and not on the checkout question", () => {
    const html = renderToStaticMarkup(
      <ReceiptHardwareCard
        sample={{} as ReceiptDoc}
        onChangePrinter={() => undefined}
        initialPaperDots={576}
        initialProbe={probe()}
        initialQueues={[queue({ name: "Epson TM-T20" })]}
      />,
    );
    expect(html).toContain("Receipt Preview");
    expect(html).toContain("58 mm");
    expect(html).toContain("80 mm");
    expect(html).not.toContain("Step 1");
    expect(html).toContain("does not create a sale");
    expect(html).toContain("Rendering receipt preview");
    const prompt: ReceiptPrompt = {
      id: "pay-1",
      heading: "Payment Successful",
      invoiceNumber: "INV-9",
      customerName: null,
      methodLabel: "Cash",
      receivedLabel: "Payment received",
      receivedText: "AED 10.00",
      remainingLabel: null,
      remainingText: null,
      changeText: null,
      question: "Would you like to print the receipt?",
      paidReceipt: true,
      documentKind: "receipt",
      slips: [],
      pdfAvailable: true,
      saleId: "sale-1",
    };
    const checkout = renderToStaticMarkup(
      <ReceiptConfirmationModal
        prompt={prompt}
        onDismiss={() => undefined}
        onPrinted={() => undefined}
        onPrint={async () => ({ printed: true, message: null })}
        onDownloadPdf={async () => undefined}
      />,
    );
    expect(checkout).toContain("Yes, Print Receipt");
    expect(checkout).toContain("No, Skip");
    expect(checkout).not.toContain("Receipt Preview");
  });
});