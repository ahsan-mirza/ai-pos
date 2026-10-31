/** Pending-review count shown beside Payments. Zero stays hidden. */
export function paymentCountLabel(count: number): string | null {
  if (!Number.isFinite(count) || count <= 0) return null;
  if (count > 99) return "99+";
  return String(Math.floor(count));
}

export const REVIEW_POLL_MS = 30_000;

export function reconnectDelay(attempt: number): number {
  const step = Math.max(0, Math.floor(attempt));
  return Math.min(20_000, 1_000 * 2 ** step);
}

export interface ReviewNotice {
  id: string;
  payment_submission_id: string;
  tenant_name: string;
  invoice_reference: string;
  amount_fils: number;
  currency: string;
  submitted_at: string;
  status: "pending_review" | "approved" | "rejected";
  read: boolean;
}

export interface ReviewState {
  pending: number;
  notices: ReviewNotice[];
  seen: string[];
}

const STATUSES = new Set(["pending_review", "approved", "rejected"]);

function asNotice(message: Record<string, unknown>): ReviewNotice | null {
  const id = message.id;
  const submission = message.payment_submission_id;
  const status = message.status;
  if (typeof id !== "string" || typeof submission !== "string" || typeof status !== "string" || !STATUSES.has(status)) {
    return null;
  }
  return {
    id,
    payment_submission_id: submission,
    tenant_name: typeof message.tenant_name === "string" ? message.tenant_name : "",
    invoice_reference: typeof message.invoice_reference === "string" ? message.invoice_reference : "",
    amount_fils: typeof message.amount_fils === "number" ? message.amount_fils : 0,
    currency: typeof message.currency === "string" ? message.currency : "",
    submitted_at: typeof message.submitted_at === "string" ? message.submitted_at : "",
    status: status as ReviewNotice["status"],
    read: false,
  };
}

/** Apply one live message. A repeated event id is ignored. Reading a notice is not this function. */
export function reduceReviews(state: ReviewState, message: Record<string, unknown>): ReviewState {
  const id = typeof message.id === "string" ? message.id : "";
  if (id && state.seen.includes(id)) return state;
  const seen = id ? [...state.seen, id].slice(-200) : state.seen;
  const pending = typeof message.pending === "number" ? message.pending : state.pending;
  if (message.type === "payment.pending_count" || message.type === "payment.review_changed") {
    const submission = typeof message.payment_submission_id === "string" ? message.payment_submission_id : "";
    const status = message.status;
    return {
      pending,
      seen,
      notices: state.notices.map((notice) =>
        submission && notice.payment_submission_id === submission && typeof status === "string" && STATUSES.has(status)
          ? { ...notice, status: status as ReviewNotice["status"] }
          : notice,
      ),
    };
  }
  if (message.type !== "payment.submitted_for_review") return { ...state, pending, seen };
  const notice = asNotice(message);
  if (notice === null || state.notices.some((row) => row.id === notice.id || row.payment_submission_id === notice.payment_submission_id)) {
    return { ...state, pending, seen };
  }
  return { pending, seen, notices: [notice, ...state.notices].slice(0, 30) };
}

/** Marks one alert read. The pending count is the review queue, so it stays as it was. */
export function markNoticeRead(state: ReviewState, noticeId: string): ReviewState {
  return {
    ...state,
    notices: state.notices.map((notice) => (notice.id === noticeId ? { ...notice, read: true } : notice)),
  };
}
