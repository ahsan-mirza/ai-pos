import { LABEL_LAYOUT_LABELS, type LabelLayout, type Product } from "@ai-pos/shared-types";
import { useState } from "react";
import { GhostButton, PrimaryButton } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { Toggle } from "../../components/ui/Toggle";
import { barcodeModules } from "./barcodeDraft";
import { labelsApi, message } from "./api";

const SIZES: { id: LabelLayout; label: string; mm: [number, number] }[] = [
  { id: "roll_50x25", label: "50 × 25 mm · standard POS", mm: [50, 25] },
  { id: "roll_38x25", label: "38 × 25 mm · compact jewelry", mm: [38, 25] },
  { id: "roll_50x30", label: LABEL_LAYOUT_LABELS.roll_50x30, mm: [50, 30] },
  { id: "a4_3x8", label: "A4 sheet · 3 × 8 matrix", mm: [70, 37] },
];

const PRINTER_KEY = "ai-pos.label-printer";

function bars(code: string): string {
  try {
    return barcodeModules(code);
  } catch {
    return "1010".repeat(20);
  }
}

function LabelPreview({
  product,
  mm,
  copies,
  showName,
  showPrice,
  showVariant,
  showCurrency,
}: {
  product: Product;
  mm: [number, number];
  copies: number;
  showName: boolean;
  showPrice: boolean;
  showVariant: boolean;
  showCurrency: boolean;
}) {
  const [width, height] = mm;
  const scale = 3.4;
  const modules = bars(product.barcode);
  const variant = Object.values(product.variant_attributes ?? {}).filter(Boolean).join(" · ");
  const price = showPrice
    ? `${showCurrency ? `${product.currency} ` : ""}${(product.price_cents / 100).toFixed(2)}`
    : null;
  const shown = Math.min(copies, 3);
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wider text-charcoal/50">Preview</p>
      <div className="mt-2 flex flex-wrap gap-3">
        {Array.from({ length: shown }, (_, index) => (
          <div
            key={index}
            className="flex flex-col justify-between overflow-hidden rounded-md border border-charcoal/20 bg-white px-2 py-1.5 text-charcoal shadow-sm"
            style={{ width: width * scale, height: height * scale }}
          >
            {showName ? <p className="truncate text-[11px] font-semibold leading-tight">{product.name}</p> : <span />}
            <div className="flex items-baseline justify-between gap-1">
              {showVariant && variant ? <p className="truncate text-[10px] text-charcoal/70">{variant}</p> : <span />}
              {price ? <p className="shrink-0 text-[11px] font-semibold tabular-nums">{price}</p> : null}
            </div>
            <svg viewBox={`0 0 ${modules.length} 40`} preserveAspectRatio="none" className="h-8 w-full" aria-hidden="true">
              {(() => {
                const marks: { x: number; width: number }[] = [];
                let run = 0;
                [...modules, "0"].forEach((bit, index) => {
                  if (bit === "1") {
                    run += 1;
                    return;
                  }
                  if (run > 0) marks.push({ x: index - run, width: run });
                  run = 0;
                });
                return marks.map((mark) => <rect key={mark.x} x={mark.x} y="0" width={mark.width} height="40" />);
              })()}
            </svg>
            <p className="text-center font-mono text-[9px] tracking-wider">{product.barcode}</p>
          </div>
        ))}
      </div>
      {copies > shown ? <p className="mt-2 text-xs text-charcoal/50">+ {copies - shown} more in the print queue</p> : null}
    </div>
  );
}

/** Asks whether to print shelf labels, then configures the queue. */
export function BarcodePrintFlow({ product, onDone }: { product: Product; onDone: () => void }) {
  const [stage, setStage] = useState<"ask" | "configure">("ask");
  const [layout, setLayout] = useState<LabelLayout>("roll_50x25");
  const [copies, setCopies] = useState(1);
  const [showName, setShowName] = useState(true);
  const [showPrice, setShowPrice] = useState(true);
  const [showVariant, setShowVariant] = useState(true);
  const [showCurrency, setShowCurrency] = useState(true);
  const [printer, setPrinter] = useState(() => localStorage.getItem(PRINTER_KEY) ?? "browser");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const size = SIZES.find((item) => item.id === layout) ?? SIZES[0]!;

  if (stage === "ask") {
    return (
      <Modal
        elevated
        title="Product created"
        subtitle={product.name}
        onClose={onDone}
        footer={
          <>
            <GhostButton onClick={onDone}>Print later</GhostButton>
            <PrimaryButton onClick={() => setStage("configure")}>Print barcodes now</PrimaryButton>
          </>
        }
      >
        <p className="text-sm text-charcoal/70">
          {product.name} is in the catalog as <span className="font-mono">{product.sku}</span>. Print shelf labels now, or
          leave them for later.
        </p>
      </Modal>
    );
  }

  return (
    <Modal
      elevated
      width="lg"
      title="Print barcode labels"
      subtitle={`${product.name} · ${product.barcode}`}
      onClose={onDone}
      footer={
        <>
          <GhostButton onClick={onDone}>Done</GhostButton>
          <PrimaryButton disabled={busy} onClick={() => void print()}>
            {busy ? "Opening…" : `Print ${copies} ${copies === 1 ? "label" : "labels"}`}
          </PrimaryButton>
        </>
      }
    >
      <div className="grid gap-5 md:grid-cols-[1fr_220px]">
        <div className="space-y-4">
          <label className="block text-sm font-medium">
            Label size
            <select
              value={layout}
              onChange={(event) => setLayout(event.target.value as LabelLayout)}
              className="mt-1.5 h-11 w-full rounded-xl border border-line bg-surface px-3 text-sm"
            >
              {SIZES.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm font-medium">
            Printer
            <select
              value={printer}
              onChange={(event) => {
                setPrinter(event.target.value);
                localStorage.setItem(PRINTER_KEY, event.target.value);
              }}
              className="mt-1.5 h-11 w-full rounded-xl border border-line bg-surface px-3 text-sm"
            >
              <option value="browser">This computer · browser print dialog</option>
            </select>
          </label>
          <label className="block text-sm font-medium">
            Quantity
            <input
              type="number"
              min={1}
              max={500}
              value={copies}
              onChange={(event) => setCopies(Math.min(500, Math.max(1, Number(event.target.value) || 1)))}
              className="mt-1.5 h-11 w-28 rounded-xl border border-line bg-surface px-3 text-sm tabular-nums"
            />
          </label>
          <div className="space-y-2">
            <Toggle label="Product name" checked={showName} onChange={setShowName} />
            <Toggle label="Price" checked={showPrice} onChange={setShowPrice} />
            <Toggle label="Currency" checked={showCurrency} onChange={setShowCurrency} />
            <Toggle label="Variant" checked={showVariant} onChange={setShowVariant} />
          </div>
          {error ? (
            <p role="alert" className="text-sm font-medium text-danger">
              {error}
            </p>
          ) : null}
        </div>
        <LabelPreview
          product={product}
          mm={size.mm}
          copies={copies}
          showName={showName}
          showPrice={showPrice}
          showVariant={showVariant}
          showCurrency={showCurrency}
        />
      </div>
    </Modal>
  );

  async function print() {
    setBusy(true);
    setError(null);
    localStorage.setItem(PRINTER_KEY, printer);
    try {
      await labelsApi.products([{ product_id: product.id, copies }], layout, showPrice, {
        showName,
        showVariant,
        showCurrency,
      });
      onDone();
    } catch (caught) {
      setError(message(caught, "Could not open the labels."));
      setBusy(false);
    }
  }
}
