import { paymentCountLabel } from "../lib/paymentBadge";

/** The same badge is used in the desktop rail and the mobile drawer. */
export function PaymentCountBadge({ count, collapsed }: { count: number; collapsed: boolean }) {
  const label = paymentCountLabel(count);
  if (label === null) return null;
  return (
    <span
      className={
        collapsed
          ? "absolute right-1 top-1 inline-flex min-w-4 items-center justify-center rounded-full bg-accent px-1 text-[10px] font-bold leading-4 text-white"
          : "ml-auto inline-flex min-w-5 items-center justify-center rounded-full bg-accent px-1.5 text-[10px] font-bold leading-4 text-white"
      }
    >
      {label}
    </span>
  );
}
