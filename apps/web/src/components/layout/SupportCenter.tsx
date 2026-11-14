import { whatsappChatUrl, useLocale } from "@ai-pos/ui";
import { type FocusEvent, type MouseEvent, type ReactNode } from "react";
import { SUPPORT_WHATSAPP_MESSAGE } from "./supportWhatsapp";

export interface SupportTip {
  label: ReactNode;
  top: number;
}

/** Brand mark. The fill stays WhatsApp green and does not inherit the row text color. */
function WhatsAppMark() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="h-[18px] w-[18px] shrink-0">
      <path
        fill="#25D366"
        d="M20.5 3.5A11 11 0 0 0 2.1 17.2L1 23l5.9-1.1A11 11 0 0 0 12 22a11 11 0 0 0 8.5-18.5zM12 20.2a8.2 8.2 0 0 1-4.2-1.1l-.3-.2-3.5.6.7-3.4-.2-.3A8.2 8.2 0 1 1 12 20.2zm4.6-6.1c-.2-.1-1.4-.7-1.6-.8s-.4-.1-.6.1-.6.8-.8.9-.3.2-.5.1a6.7 6.7 0 0 1-2-1.2 7.4 7.4 0 0 1-1.4-1.7c-.1-.3 0-.4.1-.5l.4-.5.2-.3a.5.5 0 0 0 0-.5c-.1-.1-.6-1.3-.8-1.8s-.4-.4-.6-.4h-.5a1 1 0 0 0-.7.3 2.8 2.8 0 0 0-.9 2.1 5 5 0 0 0 1.1 2.7 11.4 11.4 0 0 0 4.6 4 3.7 3.7 0 0 0 1.6.4 2.6 2.6 0 0 0 1.8-1.2 2.2 2.2 0 0 0 .1-1.3c-.1-.2-.3-.2-.5-.3z"
      />
    </svg>
  );
}

/**
 * Pinned sidebar entry. It opens the console WhatsApp contact and never an in-app route.
 * `digits` is that published number; a click reads it again when it was not ready yet.
 */
export function SupportCenter({
  collapsed,
  digits,
  pending = false,
  onTip,
  onNavigate,
  reload,
}: {
  collapsed: boolean;
  digits: string | null;
  /** True while the public contact is still loading. */
  pending?: boolean;
  onTip?: (tip: SupportTip | null) => void;
  onNavigate?: () => void;
  reload?: () => Promise<string | null>;
}) {
  const { t } = useLocale();
  const label = t("Help Center");
  const message = t(SUPPORT_WHATSAPP_MESSAGE);
  const href = pending || digits === null ? null : whatsappChatUrl(digits, message);

  const showTip = (event: MouseEvent<HTMLElement> | FocusEvent<HTMLElement>) => {
    if (!collapsed || !onTip) return;
    const rect = event.currentTarget.getBoundingClientRect();
    onTip({ label, top: rect.top + rect.height / 2 });
  };
  const hideTip = () => onTip?.(null);

  const className =
    "group flex h-10 w-full min-w-0 cursor-pointer items-center gap-3 overflow-hidden rounded-lg px-[18px] text-[13px] font-medium text-charcoal/70 outline-none transition-colors hover:bg-charcoal/[0.04] hover:text-charcoal focus-visible:ring-2 focus-visible:ring-accent/40";
  const body = (
    <>
      <WhatsAppMark />
      <span className={`whitespace-nowrap transition-opacity duration-200 ${collapsed ? "pointer-events-none opacity-0" : "opacity-100"}`}>
        {label}
      </span>
    </>
  );
  const openLatest = () => {
    onNavigate?.();
    void reload?.().then((next) => {
      if (!next) return;
      window.open(whatsappChatUrl(next, message), "_blank", "noopener,noreferrer");
    });
  };

  return (
    <div className="shrink-0 overflow-hidden border-t border-line px-3 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
      {href === null ? (
        <button
          type="button"
          aria-busy={pending ? true : undefined}
          aria-label={collapsed ? label : undefined}
          onClick={openLatest}
          onMouseEnter={showTip}
          onMouseLeave={hideTip}
          onFocus={showTip}
          onBlur={hideTip}
          className={className}
        >
          {body}
        </button>
      ) : (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={collapsed ? label : undefined}
          onClick={onNavigate}
          onMouseEnter={showTip}
          onMouseLeave={hideTip}
          onFocus={showTip}
          onBlur={hideTip}
          className={className}
        >
          {body}
        </a>
      )}
    </div>
  );
}
