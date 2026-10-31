import { Bell } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { api, reviewSocketUrl } from "./api";
import { money, when } from "./format";
import {
  markNoticeRead,
  paymentCountLabel,
  reconnectDelay,
  reduceReviews,
  REVIEW_POLL_MS,
  type ReviewNotice,
  type ReviewState,
} from "./paymentBadge";

interface PaymentReviews {
  pending: number;
  notices: ReviewNotice[];
  revision: number;
  markRead: (noticeId: string) => Promise<void>;
}

const empty: ReviewState = { pending: 0, notices: [], seen: [] };

export const PaymentReviewContext = createContext<PaymentReviews>({
  pending: 0,
  notices: [],
  revision: 0,
  markRead: async () => undefined,
});

export function usePaymentReviews(): PaymentReviews {
  return useContext(PaymentReviewContext);
}

export function PaymentReviewProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<ReviewState>(empty);
  const [revision, setRevision] = useState(0);

  const refresh = useCallback(async () => {
    try {
      const [summary, notices] = await Promise.all([
        api.get<{ pending: number }>("/billing/review-summary"),
        api.get<ReviewNotice[]>("/billing/review-notices"),
      ]);
      setState((current) => ({ pending: summary.pending, notices, seen: current.seen }));
      setRevision((value) => value + 1);
    } catch {
      // The next poll or reconnect loads the authoritative count.
    }
  }, []);

  useEffect(() => {
    let stopped = false;
    let socket: WebSocket | null = null;
    let reconnect = 0;
    let poll = 0;
    let attempt = 0;

    const startPoll = () => {
      if (poll || stopped) return;
      poll = window.setInterval(() => void refresh(), REVIEW_POLL_MS);
    };
    const stopPoll = () => {
      if (!poll) return;
      window.clearInterval(poll);
      poll = 0;
    };
    const connect = () => {
      const url = reviewSocketUrl();
      if (!url || stopped) {
        startPoll();
        return;
      }
      const current = new WebSocket(url);
      socket = current;
      current.onopen = () => {
        attempt = 0;
        stopPoll();
        void refresh();
      };
      current.onmessage = (event) => {
        let message: Record<string, unknown>;
        try {
          message = JSON.parse(String(event.data)) as Record<string, unknown>;
        } catch {
          return;
        }
        setState((currentState) => reduceReviews(currentState, message));
        if (message.type === "payment.submitted_for_review" || message.type === "payment.review_changed") {
          setRevision((value) => value + 1);
        }
      };
      current.onclose = () => {
        if (stopped || socket !== current) return;
        startPoll();
        reconnect = window.setTimeout(connect, reconnectDelay(attempt));
        attempt += 1;
      };
    };

    void refresh();
    connect();
    return () => {
      stopped = true;
      window.clearTimeout(reconnect);
      stopPoll();
      socket?.close();
    };
  }, [refresh]);

  const markRead = useCallback(async (noticeId: string) => {
    setState((current) => markNoticeRead(current, noticeId));
    try {
      await api.post(`/billing/review-notices/${noticeId}/read`, {});
    } catch {
      void refresh();
    }
  }, [refresh]);

  const value = useMemo(
    () => ({ pending: state.pending, notices: state.notices, revision, markRead }),
    [state.pending, state.notices, revision, markRead],
  );
  return <PaymentReviewContext.Provider value={value}>{children}</PaymentReviewContext.Provider>;
}

export function PaymentNoticeBell() {
  const { notices, markRead } = usePaymentReviews();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const unread = notices.filter((notice) => !notice.read).length;
  const unreadLabel = paymentCountLabel(unread);

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        aria-label={unreadLabel ? `Payment notifications, ${unreadLabel} unread` : "Payment notifications"}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="relative flex h-9 w-9 items-center justify-center rounded-lg text-charcoal/60 outline-none transition-colors hover:bg-charcoal/[0.05] hover:text-charcoal focus-visible:ring-2 focus-visible:ring-accent/40"
      >
        <Bell size={18} strokeWidth={1.75} aria-hidden="true" />
        {unreadLabel ? (
          <span className="absolute right-0.5 top-0.5 inline-flex min-w-4 items-center justify-center rounded-full bg-accent px-1 text-[10px] font-bold leading-4 text-white">
            {unreadLabel}
          </span>
        ) : null}
      </button>
      {open ? (
        <div className="absolute right-0 top-11 z-40 w-[min(360px,calc(100vw-1.5rem))] overflow-hidden rounded-xl border border-line bg-white shadow-xl">
          <div className="border-b border-line px-4 py-3 text-sm font-semibold">Payment reviews</div>
          {notices.length === 0 ? (
            <p className="px-4 py-6 text-center text-xs text-charcoal/55">No payment proofs are waiting.</p>
          ) : (
            <ul className="max-h-80 overflow-y-auto">
              {notices.map((notice) => (
                <li key={notice.id}>
                  <button
                    type="button"
                    onClick={() => {
                      void markRead(notice.id);
                      setOpen(false);
                      navigate(`/payments?transfer=${notice.payment_submission_id}`);
                    }}
                    className={`flex w-full flex-col gap-0.5 px-4 py-3 text-left text-sm hover:bg-[#f8fafc] ${notice.read ? "text-charcoal/70" : "text-charcoal"}`}
                  >
                    <span className="font-semibold">New subscription payment submitted</span>
                    <span>
                      {notice.tenant_name || "Store"} · {notice.invoice_reference}
                    </span>
                    <span className="text-xs text-charcoal/55">
                      {money(notice.amount_fils, notice.currency)} · {when(notice.submitted_at)} ·{" "}
                      {notice.status === "pending_review" ? "Pending review" : notice.status === "approved" ? "Verified" : "Rejected"}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  );
}
