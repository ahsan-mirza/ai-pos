export const SerialKind = {
  Imei: "imei",
  Serial: "serial",
} as const;
export type SerialKind = (typeof SerialKind)[keyof typeof SerialKind];

export const SerialStatus = {
  InStock: "in_stock",
  Reserved: "reserved",
  InTransit: "in_transit",
  Sold: "sold",
  Defective: "defective",
  Repair: "repair",
  Quarantine: "quarantine",
  Scrapped: "scrapped",
  Reversed: "reversed",
} as const;
export type SerialStatus = (typeof SerialStatus)[keyof typeof SerialStatus];

export const SaleStatus = {
  Draft: "draft",
  Completed: "completed",
  Voided: "voided",
  PartiallyRefunded: "partially_refunded",
  Refunded: "refunded",
  Quote: "quote",
} as const;
export type SaleStatus = (typeof SaleStatus)[keyof typeof SaleStatus];

export const PaymentMethod = {
  Cash: "cash",
  Card: "card",
  Transfer: "transfer",
  StoreCredit: "store_credit",
  OnAccount: "on_account",
  Cheque: "cheque",
  Deposit: "deposit",
  Qr: "qr",
  Loyalty: "loyalty",
  TradeIn: "trade_in",
  /** Paid through a delivery app, which settles with the business later. */
  Channel: "channel",
  /** Buy now, pay later (Tabby, Tamara): the provider pays the business and collects the instalments. */
  Bnpl: "bnpl",
  /** A gift card spent as payment. */
  GiftCard: "gift_card",
} as const;
export type PaymentMethod = (typeof PaymentMethod)[keyof typeof PaymentMethod];

export const CustomerType = {
  Retail: "RETAIL",
  Wholesale: "WHOLESALE",
} as const;
export type CustomerType = (typeof CustomerType)[keyof typeof CustomerType];

export const PriceTier = {
  Retail: "RETAIL",
  Tier1: "TIER_1",
  Tier2: "TIER_2",
  Distributor: "DISTRIBUTOR",
} as const;
export type PriceTier = (typeof PriceTier)[keyof typeof PriceTier];

export const PRICE_TIERS: readonly PriceTier[] = ["RETAIL", "TIER_1", "TIER_2", "DISTRIBUTOR"];

export const PaymentTerms = {
  DueOnReceipt: "DUE_ON_RECEIPT",
  Net15: "NET_15",
  Net30: "NET_30",
  Net60: "NET_60",
} as const;
export type PaymentTerms = (typeof PaymentTerms)[keyof typeof PaymentTerms];

export const PaymentStatus = {
  Paid: "PAID",
  Partial: "PARTIAL",
  OnAccountUnpaid: "ON_ACCOUNT_UNPAID",
} as const;
export type PaymentStatus = (typeof PaymentStatus)[keyof typeof PaymentStatus];

export const SaleType = {
  Retail: "RETAIL",
  Wholesale: "WHOLESALE",
} as const;
export type SaleType = (typeof SaleType)[keyof typeof SaleType];

export const QuoteStatus = {
  Open: "OPEN",
  Converted: "CONVERTED",
  Expired: "EXPIRED",
  Cancelled: "CANCELLED",
} as const;
export type QuoteStatus = (typeof QuoteStatus)[keyof typeof QuoteStatus];

/** The built-in packs. A business adds its own (GET /api/v1/units), so a unit code is any string. */
export const UnitType = {
  Piece: "PIECE",
  Box10: "BOX_10",
  Carton100: "CARTON_100",
} as const;
export type UnitType = string;

/** Pieces per built-in pack. Use unitFactor(product, code), which also knows a product's custom packs. */
export const UNIT_FACTORS: Readonly<Record<string, number>> = { PIECE: 1, BOX_10: 10, CARTON_100: 100 };

export const RepairStatus = {
  Intake: "intake",
  Diagnosing: "diagnosing",
  AwaitingApproval: "awaiting_approval",
  InRepair: "in_repair",
  WaitingParts: "waiting_parts",
  Ready: "ready",
  Closed: "closed",
  Cancelled: "cancelled",
} as const;
export type RepairStatus = (typeof RepairStatus)[keyof typeof RepairStatus];

export const SyncEntityType = {
  Store: "store",
  Product: "product",
  SerialNumber: "serial_number",
  Sale: "sale",
  RepairTicket: "repair_ticket",
  SaleReturn: "sale_return",
  Customer: "customer",
  OpenOrder: "open_order",
} as const;
export type SyncEntityType = (typeof SyncEntityType)[keyof typeof SyncEntityType];

export const RefundMethod = {
  Cash: "cash",
  OriginalCard: "original_card",
  OriginalBnpl: "original_bnpl",
  StoreCredit: "store_credit",
} as const;
export type RefundMethod = (typeof RefundMethod)[keyof typeof RefundMethod];

/** Built-in condition keys (electronics and fashion presets); a business's returns policy may define its own. */
export const ReturnCondition = {
  UnopenedResealable: "unopened_resealable",
  OpenBox: "open_box",
  DefectiveDoa: "defective_doa",
  TagsAttached: "tags_attached",
  Worn: "worn",
  Damaged: "damaged",
} as const;
/** A condition key from the business's returns policy. */
export type ReturnCondition = string;

export const ReturnReason = {
  Defective: "defective",
  ChangedMind: "changed_mind",
  WrongItem: "wrong_item",
  DamagedInTransit: "damaged_in_transit",
  NotAsDescribed: "not_as_described",
  Other: "other",
  SizeFit: "size_fit",
  Style: "style",
  Quality: "quality",
} as const;
/** A reason key from the business's returns policy. */
export type ReturnReason = string;

export const OverrideReason = {
  NoRefundPermission: "no_refund_permission",
  OutsideWindow: "outside_window",
  FeeWaived: "fee_waived",
  FinalSale: "final_sale",
} as const;
export type OverrideReason = (typeof OverrideReason)[keyof typeof OverrideReason];

export const SyncOperation = {
  Upsert: "upsert",
} as const;
export type SyncOperation = (typeof SyncOperation)[keyof typeof SyncOperation];

export const AnalyticsTimeframe = {
  AllTime: "all_time",
  Weekly: "weekly",
  Monthly: "monthly",
} as const;
export type AnalyticsTimeframe = (typeof AnalyticsTimeframe)[keyof typeof AnalyticsTimeframe];
