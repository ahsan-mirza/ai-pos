export type ShiftStatus = "OPEN" | "CLOSED";
export type CashMovementKind = "PAY_IN" | "PAY_OUT" | "CASH_DROP" | "NO_SALE";

export interface ShiftReport {
  sales_count: number;
  sales_total_cents: number;
  tax_cents: number;
  tenders: Record<string, number>;
  on_account_cents: number;
  returns_count: number;
  refunds_total_cents: number;
  refund_tenders: Record<string, number>;
  pay_in_cents: number;
  pay_out_cents: number;
  drops_cents: number;
  no_sale_count: number;
  opening_float_cents: number;
  expected_cash_cents: number;
  /** Foreign cash expected per currency, in that currency's minor units, and what was counted at close. */
  foreign_cash?: Record<string, number>;
  foreign_counted?: Record<string, number>;
  /** Restaurant: tips owed to staff (not revenue), the service charge (revenue), and tips per server. */
  tips_cents?: number;
  service_charge_cents?: number;
  tips_by_server?: ServerTips[];
  /** Card and pay-later takings confirmed per provider, keyed "CARD:ngenius" or "BNPL:tabby". */
  provider_totals?: Record<string, number>;
  /** Cash taken as a repair deposit on this shift, and cash deposits refunded on this shift. */
  deposit_cents?: number;
  deposit_refund_cents?: number;
}

export interface ServerTips {
  user_id: string | null;
  name: string;
  sales_count: number;
  tips_cents: number;
}

export interface TipReport {
  start: string;
  end: string;
  store_id: string | null;
  sales_count: number;
  tips_cents: number;
  service_charge_cents: number;
  by_server: ServerTips[];
}

export interface CashMovement {
  id: string;
  kind: CashMovementKind;
  amount_cents: number;
  reason: string;
  user_name: string;
  occurred_at: string;
}

/** GET /shifts: a register shift with its live X report, or its Z report once closed. */
export interface Shift {
  id: string;
  store_id: string;
  store_code: string;
  device_code: string | null;
  opened_by_name: string;
  closed_by_name: string | null;
  opened_at: string;
  closed_at: string | null;
  currency: string;
  status: ShiftStatus;
  opening_float_cents: number;
  counted_cash_cents: number | null;
  expected_cash_cents: number;
  variance_cents: number | null;
  blind_close: boolean;
  z_number: string | null;
  report: ShiftReport;
  movements: CashMovement[];
}
