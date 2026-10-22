/**
 * A size exchange handed from Returns to Checkout: the return has issued a store-credit voucher, and checkout opens
 * with that voucher applied and the variant picker on the returned product's model. Two documents (credit note,
 * then a new invoice), as VAT requires, but one flow for the cashier.
 */
export interface ExchangeIntent {
  voucherCode: string;
  balanceCents: number;
  productId: string;
  productName: string;
}

let pending: ExchangeIntent | null = null;

export function startExchange(intent: ExchangeIntent): void {
  pending = intent;
}

/** Checkout takes the intent once; navigating away and back does not apply it twice. */
export function takeExchange(): ExchangeIntent | null {
  const intent = pending;
  pending = null;
  return intent;
}
