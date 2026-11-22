import { useLocale } from "@ai-pos/ui";
import { Inbox } from "lucide-react";
import { useEffect, useState } from "react";
import { useBusinessCurrency } from "../checkout/currency";
import { CashDrawerModal } from "./CashDrawerModal";

/**
 * Opens the cash drawer from any register screen. The reason is still recorded;
 * the button itself is the same on every business type.
 */
export function OpenDrawerButton({
  className,
  disabled = false,
  iconOnly = false,
  onLogged,
}: {
  className: string;
  disabled?: boolean;
  /** Icon with an accessible name, and no visible label. */
  iconOnly?: boolean;
  /** When omitted, the confirmation is shown beside the register. */
  onLogged?: (message: string) => void;
}) {
  const { t } = useLocale();
  const currency = useBusinessCurrency();
  const [open, setOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 4000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  return (
    <>
      <button
        type="button"
        className={className}
        disabled={disabled}
        aria-label={t("Open drawer")}
        title={t("Open the cash drawer")}
        onClick={() => setOpen(true)}
      >
        <Inbox size={iconOnly ? 18 : 16} aria-hidden="true" />
        {iconOnly ? null : t("Open drawer")}
      </button>
      {open ? (
        <CashDrawerModal
          currency={currency}
          onClose={() => setOpen(false)}
          onLogged={(message) => {
            if (onLogged) onLogged(message);
            else setNotice(message);
          }}
        />
      ) : null}
      {notice ? (
        <p
          role="status"
          className="fixed bottom-12 start-4 z-50 max-w-sm rounded-xl bg-zinc-900 px-3 py-2 text-sm text-white shadow-lg dark:bg-white dark:text-zinc-900"
        >
          {notice}
        </p>
      ) : null}
    </>
  );
}
