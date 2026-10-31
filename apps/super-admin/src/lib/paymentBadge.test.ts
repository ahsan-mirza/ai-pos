import { describe, expect, it } from "vitest";
import {
  markNoticeRead,
  paymentCountLabel,
  reconnectDelay,
  reduceReviews,
  REVIEW_POLL_MS,
  type ReviewNotice,
  type ReviewState,
} from "./paymentBadge";

const notice = (id: string, status: ReviewNotice["status"] = "pending_review"): ReviewNotice => ({
  id,
  payment_submission_id: `transfer-${id}`,
  tenant_name: "Alpha Mobiles",
  invoice_reference: "LITE-ABCDEF",
  amount_fils: 14900,
  currency: "AED",
  submitted_at: "2026-10-30T12:00:00+00:00",
  status,
  read: false,
});

const empty: ReviewState = { pending: 0, notices: [], seen: [] };

describe("payment count badge", () => {
  it("hides a zero count", () => {
    expect(paymentCountLabel(0)).toBeNull();
    expect(paymentCountLabel(-1)).toBeNull();
  });

  it("shows one and several pending receipts", () => {
    expect(paymentCountLabel(1)).toBe("1");
    expect(paymentCountLabel(5)).toBe("5");
  });

  it("caps a large queue at 99+", () => {
    expect(paymentCountLabel(99)).toBe("99");
    expect(paymentCountLabel(125)).toBe("99+");
  });
});

describe("live payment reviews", () => {
  it("adds one submission and ignores the same event twice", () => {
    const first = reduceReviews(empty, {
      type: "payment.submitted_for_review",
      id: "notice-1",
      payment_submission_id: "transfer-notice-1",
      tenant_name: "Alpha Mobiles",
      invoice_reference: "LITE-ABCDEF",
      amount_fils: 14900,
      currency: "AED",
      submitted_at: "2026-10-30T12:00:00+00:00",
      status: "pending_review",
      pending: 1,
    });
    expect(first.pending).toBe(1);
    expect(first.notices).toHaveLength(1);
    const again = reduceReviews(first, {
      type: "payment.submitted_for_review",
      id: "notice-1",
      payment_submission_id: "transfer-notice-1",
      pending: 1,
      status: "pending_review",
    });
    expect(again.notices).toHaveLength(1);
    expect(again.pending).toBe(1);
  });

  it("counts several submissions and drops the count when a review finishes", () => {
    const queued = { ...empty, pending: 2, notices: [notice("a"), notice("b")] };
    const decided = reduceReviews(queued, {
      type: "payment.review_changed",
      id: "event-1",
      payment_submission_id: "transfer-a",
      status: "approved",
      pending: 1,
    });
    expect(decided.pending).toBe(1);
    expect(decided.notices.find((row) => row.id === "a")?.status).toBe("approved");
  });

  it("restores the authoritative count after a reconnect", () => {
    const stale = { pending: 0, notices: [], seen: [] };
    const restored = reduceReviews(stale, { type: "payment.pending_count", pending: 4 });
    expect(restored.pending).toBe(4);
  });

  it("keeps the payment pending when the alert is marked read", () => {
    const state = { pending: 1, notices: [notice("a")], seen: [] };
    const read = markNoticeRead(state, "a");
    expect(read.pending).toBe(1);
    expect(read.notices[0]?.read).toBe(true);
    expect(read.notices[0]?.status).toBe("pending_review");
  });

  it("polls slowly only as a fallback and backs off reconnects", () => {
    expect(REVIEW_POLL_MS).toBeGreaterThanOrEqual(15_000);
    expect(reconnectDelay(0)).toBe(1_000);
    expect(reconnectDelay(3)).toBe(8_000);
    expect(reconnectDelay(10)).toBe(20_000);
  });
});
