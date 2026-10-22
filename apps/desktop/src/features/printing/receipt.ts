import { formatWeight, modifierSummary, type TaxPolicy } from "@ai-pos/shared-types";
import type { ReceiptLine } from "@ai-pos/receipt";
import { lineCharge, manualDiscountCents, type CartLine } from "../checkout/cart";

/** Lines priced through the same VAT engine the cart and API use, so the slip matches the invoice exactly. */
export function receiptLines(lines: CartLine[], policy: TaxPolicy): ReceiptLine[] {
  const merged = new Map<string, ReceiptLine>();
  for (const line of lines) {
    const priced = lineCharge(line, policy);
    const name = line.description?.trim() || line.product.name;
    const promo = line.promotion && line.promotion.discountCents > 0 ? line.promotion : null;
    const manual = manualDiscountCents(line);
    const variant = Object.values(line.product.variant_attributes ?? {}).join(" · ");
    if (promo || manual > 0 || variant) {
      const notes = [
        line.serialValue ? `${line.serialKind === "imei" ? "IMEI" : "S/N"} ${line.serialValue}` : null,
        variant || null,
        promo ? `${promo.name} −${(promo.discountCents / 100).toFixed(2)}` : null,
        manual > 0 && line.discount ? `${line.discount.reasonLabel} −${(manual / 100).toFixed(2)}` : null,
      ].filter(Boolean);
      if (promo || manual > 0) {
        merged.set(line.lineId, {
          name,
          detail: notes.join(" · "),
          quantity: line.quantity,
          unitCents: line.unitPriceCents,
          totalCents: priced.line_total_cents,
        });
        continue;
      }
    }
    if (line.product.sold_by_weight) {
      // One weighing per line: "1.234 kg @ 12.99/kg", printed as a single item at its weighed price.
      merged.set(line.lineId, {
        name,
        detail: `${formatWeight(line.quantity)} @ ${(line.unitPriceCents / 100).toFixed(2)}/kg`,
        quantity: 1,
        unitCents: priced.line_total_cents - priced.tax_cents,
        totalCents: priced.line_total_cents,
      });
      continue;
    }
    if (line.components?.length) {
      // A meal is one priced line; its parts print beneath it, one per row.
      const parts = line.components.map(
        (part) => `+ ${part.name ?? ""}${part.surcharge_cents > 0 ? ` (+${(part.surcharge_cents / 100).toFixed(2)})` : ""}`,
      );
      if (line.modifiers?.length) parts.push(modifierSummary(line.modifiers));
      merged.set(line.lineId, {
        name,
        detail: parts.join("\n"),
        quantity: line.quantity,
        unitCents: line.unitPriceCents,
        totalCents: priced.line_total_cents,
      });
      continue;
    }
    if (line.modifiers?.length) {
      merged.set(line.lineId, {
        name,
        detail: modifierSummary(line.modifiers),
        quantity: line.quantity,
        unitCents: line.unitPriceCents,
        totalCents: priced.line_total_cents,
      });
      continue;
    }
    if (line.serialValue === null) {
      const key = `${line.product.id}:${line.unitPriceCents}:${name}`;
      const existing = merged.get(key);
      if (existing) {
        existing.quantity += line.quantity;
        existing.totalCents += priced.line_total_cents;
        continue;
      }
      merged.set(key, {
        name,
        detail: line.giftCardCode ? `Card ${line.giftCardCode}` : variant || null,
        quantity: line.quantity,
        unitCents: line.unitPriceCents,
        totalCents: priced.line_total_cents,
      });
      continue;
    }
    merged.set(line.lineId, {
      name,
      detail: `${line.serialKind === "imei" ? "IMEI" : "S/N"} ${line.serialValue}`,
      quantity: line.quantity,
      unitCents: line.unitPriceCents,
      totalCents: priced.line_total_cents,
    });
  }
  return [...merged.values()];
}
