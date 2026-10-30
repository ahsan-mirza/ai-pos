import { formatMoney } from "@ai-pos/shared-types";
import { ArrowRight, Building2, CreditCard, LogOut, UserRound } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { apiGet } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useCanManageSettings } from "../../lib/currency";
import { ProfileAvatar } from "../ui/ProfileAvatar";

interface PaymentAttention {
  kind: "awaiting_proof" | "pending_review" | "rejected" | "revoked";
}

interface AccountSubscription {
  id: string;
  plan_code: string;
  plan_name: string;
  cycle_name: string;
  status: string;
  price_fils: number;
  currency: string;
  trial_ends_at: string | null;
  current_period_end: string | null;
  grace_ends_at: string | null;
}

interface AccountAccess {
  state: string;
  attention: PaymentAttention | null;
  subscription: AccountSubscription | null;
}

const listeners = new Set<() => void>();

/** Drops the cached subscription so the menu reads billing again after a payment change. */
export function invalidateAccountSubscription(): void {
  listeners.forEach((listen) => listen());
}

function day(value: string | null): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" });
}

function statusOf(access: AccountAccess): { label: string; tone: string; when: string | null } {
  const kind = access.attention?.kind;
  const subscription = access.subscription;
  if (kind === "pending_review") return { label: "Payment verification pending", tone: "bg-amber-100 text-amber-900", when: null };
  if (kind === "awaiting_proof" || kind === "rejected") {
    return { label: "Pending payment", tone: "bg-amber-100 text-amber-900", when: null };
  }
  if (kind === "revoked") return { label: "Access updated", tone: "bg-red-100 text-red-800", when: null };
  if (access.state === "trial") {
    return { label: "Trial", tone: "bg-amber-100 text-amber-900", when: day(subscription?.trial_ends_at ?? null) };
  }
  if (access.state === "active") {
    return { label: "Active", tone: "bg-emerald-100 text-emerald-800", when: day(subscription?.current_period_end ?? null) };
  }
  if (access.state === "grace") {
    return { label: "Grace period", tone: "bg-amber-100 text-amber-900", when: day(subscription?.grace_ends_at ?? null) };
  }
  if (access.state === "restricted" && subscription?.status === "canceled") {
    return { label: "Cancelled", tone: "bg-red-100 text-red-800", when: day(subscription.current_period_end) };
  }
  if (access.state === "restricted" && subscription?.status === "past_due") {
    return { label: "Payment overdue", tone: "bg-red-100 text-red-800", when: day(subscription.current_period_end) };
  }
  if (access.state === "restricted") {
    return { label: "Expired", tone: "bg-red-100 text-red-800", when: day(subscription?.current_period_end ?? null) };
  }
  return { label: "No active subscription", tone: "bg-charcoal/5 text-charcoal/70", when: null };
}

const itemClass =
  "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13px] font-medium text-charcoal outline-none transition-colors hover:bg-charcoal/[0.04] focus-visible:ring-2 focus-visible:ring-accent/40";

export function AccountMenu() {
  const { user, logout } = useAuth();
  const canBill = useCanManageSettings();
  const [open, setOpen] = useState(false);
  const [access, setAccess] = useState<AccountAccess | null>(null);
  const [phase, setPhase] = useState<"loading" | "ready" | "unavailable">("loading");
  const panel = useRef<HTMLDivElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!canBill) return;
    let cancelled = false;
    const load = () => {
      apiGet<AccountAccess>("/api/v1/billing/access")
        .then((found) => {
          if (cancelled) return;
          setAccess(found);
          setPhase("ready");
        })
        .catch(() => {
          if (!cancelled) setPhase("unavailable");
        });
    };
    load();
    listeners.add(load);
    return () => {
      cancelled = true;
      listeners.delete(load);
    };
  }, [canBill]);

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      if (panel.current && !panel.current.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointer);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (user === null) return null;
  const status = access ? statusOf(access) : null;
  const subscription = access?.subscription ?? null;
  const showPlan = canBill && subscription !== null && access?.state !== "unbilled";

  return (
    <div ref={panel} className="relative">
      <button
        type="button"
        aria-label={`Account menu for ${user.full_name}`}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={() => setOpen((value) => !value)}
        className="flex h-9 w-9 items-center justify-center rounded-full outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
      >
        <ProfileAvatar name={user.full_name} url={user.avatar_url} className="h-8 w-8" />
      </button>
      {open ? (
        <div
          id={menuId}
          role="menu"
          aria-label="Account"
          className="absolute right-0 top-11 z-40 max-h-[min(32rem,calc(100dvh-5rem))] w-[min(340px,calc(100vw-1.5rem))] overflow-y-auto rounded-2xl border border-line bg-white p-2 shadow-xl"
        >
          <div className="flex items-center gap-3 rounded-xl bg-[#f8fafc] px-3 py-3">
            <ProfileAvatar name={user.full_name} url={user.avatar_url} className="h-11 w-11" />
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold">{user.full_name}</p>
              <p className="truncate text-xs text-charcoal/60">{user.role.name}</p>
              <p className="truncate text-xs text-charcoal/45">{user.email}</p>
            </div>
          </div>

          {canBill ? (
            <div className="mt-2 rounded-xl border border-line px-3 py-3">
              <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-charcoal/45">Your subscription</p>
              {phase === "loading" ? (
                <div className="mt-3 space-y-2" aria-hidden="true">
                  <div className="h-4 w-2/3 animate-pulse rounded bg-charcoal/10" />
                  <div className="h-3 w-1/2 animate-pulse rounded bg-charcoal/10" />
                  <div className="h-3 w-3/4 animate-pulse rounded bg-charcoal/10" />
                </div>
              ) : null}
              {phase === "unavailable" ? (
                <p className="mt-2 text-sm text-charcoal/70">Subscription details are unavailable.</p>
              ) : null}
              {phase === "ready" && !showPlan ? (
                <>
                  <p className="mt-2 text-sm font-semibold">No active subscription</p>
                  <p className="mt-1 text-xs text-charcoal/60">Choose a plan to unlock the available AxizPOS features.</p>
                  <Link
                    to="/subscription"
                    role="menuitem"
                    onClick={() => setOpen(false)}
                    className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-accent hover:underline"
                  >
                    View plans <ArrowRight size={14} aria-hidden="true" />
                  </Link>
                </>
              ) : null}
              {phase === "ready" && showPlan && subscription && status ? (
                <>
                  <div className="mt-2 flex items-start justify-between gap-2">
                    <p className="text-sm font-semibold">{subscription.plan_name}</p>
                    <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${status.tone}`}>
                      {status.label}
                    </span>
                  </div>
                  <p className="mt-1 text-sm text-charcoal/80">
                    {formatMoney(subscription.price_fils, subscription.currency)}
                    <span className="text-charcoal/50"> · {subscription.cycle_name}</span>
                  </p>
                  <dl className="mt-2 space-y-1 text-xs text-charcoal/70">
                    <div className="flex justify-between gap-3">
                      <dt>Status</dt>
                      <dd className="font-medium text-charcoal">{status.label}</dd>
                    </div>
                    <div className="flex justify-between gap-3">
                      <dt>Billing cycle</dt>
                      <dd>{subscription.cycle_name}</dd>
                    </div>
                    {access?.state === "trial" && status.when ? (
                      <div className="flex justify-between gap-3">
                        <dt>Trial ends</dt>
                        <dd>{status.when}</dd>
                      </div>
                    ) : null}
                    {access?.state === "active" && status.when ? (
                      <div className="flex justify-between gap-3">
                        <dt>Next renewal</dt>
                        <dd>{status.when}</dd>
                      </div>
                    ) : null}
                    {access?.state === "grace" && status.when ? (
                      <div className="flex justify-between gap-3">
                        <dt>Grace ends</dt>
                        <dd>{status.when}</dd>
                      </div>
                    ) : null}
                    {access?.state === "restricted" && status.when ? (
                      <div className="flex justify-between gap-3">
                        <dt>Access ended</dt>
                        <dd>{status.when}</dd>
                      </div>
                    ) : null}
                  </dl>
                  <Link
                    to="/subscription"
                    role="menuitem"
                    onClick={() => setOpen(false)}
                    className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-accent hover:underline"
                  >
                    Manage subscription <ArrowRight size={14} aria-hidden="true" />
                  </Link>
                </>
              ) : null}
            </div>
          ) : null}

          <div className="mt-2 space-y-0.5">
            <Link to="/account" role="menuitem" onClick={() => setOpen(false)} className={itemClass}>
              <UserRound size={16} strokeWidth={1.75} aria-hidden="true" />
              My account
            </Link>
            {canBill ? (
              <Link to="/settings" role="menuitem" onClick={() => setOpen(false)} className={itemClass}>
                <Building2 size={16} strokeWidth={1.75} aria-hidden="true" />
                Business settings
              </Link>
            ) : null}
            {canBill ? (
              <Link to="/subscription" role="menuitem" onClick={() => setOpen(false)} className={itemClass}>
                <CreditCard size={16} strokeWidth={1.75} aria-hidden="true" />
                Subscription & billing
              </Link>
            ) : null}
          </div>
          <div className="mt-1 border-t border-line pt-1">
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                logout();
              }}
              className={`${itemClass} text-charcoal/80`}
            >
              <LogOut size={16} strokeWidth={1.75} aria-hidden="true" />
              Sign out
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
