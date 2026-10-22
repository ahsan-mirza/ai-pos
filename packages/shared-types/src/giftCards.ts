/** Gift cards (GIFT_CARD store credits). Mirrors apps/api/app/schemas/store_credit.py. */

export interface GiftCardIssue {
  store_id: string;
  amount_cents: number;
  count: number;
  customer_id: string | null;
  note: string;
}

/** The service product a register adds to sell a gift card, and the business's gift-card rules. */
export interface GiftCardProduct {
  product_id: string;
  sku: string;
  name: string;
  min_cents: number;
  max_cents: number;
  expiry_months: number | null;
}
