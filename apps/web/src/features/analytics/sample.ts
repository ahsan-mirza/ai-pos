import { AnalyticsTimeframe, PaymentMethod, type AnalyticsSummary } from "@ai-pos/shared-types";

const categories = [
  { category: "Phones", units: 570, revenue_cents: 12_000_000 },
  { category: "Accessories", units: 347, revenue_cents: 2_800_000 },
  { category: "Repairs", units: 198, revenue_cents: 2_100_000 },
  { category: "Tablets", units: 125, revenue_cents: 1_700_000 },
];

const paymentSplit = [
  { method: PaymentMethod.Card, revenue_cents: 13_000_000 },
  { method: PaymentMethod.Cash, revenue_cents: 5_600_000 },
];

export const sampleAnalytics: Record<AnalyticsTimeframe, AnalyticsSummary> = {
  [AnalyticsTimeframe.AllTime]: {
    timeframe: AnalyticsTimeframe.AllTime,
    currency: "USD",
    net_revenue_cents: 18_600_000,
    units_sold: 1240,
    average_ticket_cents: 15_000,
    units_growth_bps: null,
    revenue_series: [1_800_000, 2_100_000, 2_400_000, 2_200_000, 3_100_000, 3_400_000, 3_600_000],
    categories,
    payment_split: paymentSplit,
  },
  [AnalyticsTimeframe.Weekly]: {
    timeframe: AnalyticsTimeframe.Weekly,
    currency: "USD",
    net_revenue_cents: 428_500,
    units_sold: 86,
    average_ticket_cents: 4_983,
    units_growth_bps: 860,
    revenue_series: [48_000, 52_000, 61_000, 58_000, 72_000, 69_000, 68_500],
    categories: categories.map((item) => ({
      ...item,
      units: Math.max(1, Math.round(item.units / 14)),
      revenue_cents: Math.round(item.revenue_cents / 40),
    })),
    payment_split: [
      { method: PaymentMethod.Card, revenue_cents: 300_000 },
      { method: PaymentMethod.Cash, revenue_cents: 128_500 },
    ],
  },
  [AnalyticsTimeframe.Monthly]: {
    timeframe: AnalyticsTimeframe.Monthly,
    currency: "USD",
    net_revenue_cents: 1_842_000,
    units_sold: 312,
    average_ticket_cents: 5_904,
    units_growth_bps: 420,
    revenue_series: [240_000, 280_000, 310_000, 295_000, 350_000, 367_000],
    categories: categories.map((item) => ({
      ...item,
      units: Math.max(1, Math.round(item.units / 4)),
      revenue_cents: Math.round(item.revenue_cents / 10),
    })),
    payment_split: [
      { method: PaymentMethod.Card, revenue_cents: 1_280_000 },
      { method: PaymentMethod.Cash, revenue_cents: 562_000 },
    ],
  },
};
