import { ChevronDown, ChevronUp } from "lucide-react";
import { useState, type ReactNode } from "react";
import { DrawerFooter, drawerShell } from "../../components/shell/Drawer";

interface CheckoutSidebarProps {
  /** Below lg the sidebar is a sheet the cashier opens over the catalog. */
  open: boolean;
  onDismiss: () => void;
  header: ReactNode;
  customer: ReactNode;
  cart: ReactNode;
  /** Receives the fold toggle to place on the subtotal line. */
  summary: (foldToggle: ReactNode) => ReactNode;
  payment: ReactNode;
  /** The chosen payment method, shown while the payment sheet is folded away. */
  paymentLabel: string;
  notices?: ReactNode;
  footer: ReactNode;
}

/**
 * Current-sale layout: the cart list takes all free height; the payment sheet is capped at 35% (it scrolls
 * inside when a tender needs more) and folds down to the total so long carts get almost the whole panel.
 */
export function CheckoutSidebar({ open, onDismiss, header, customer, cart, summary, payment, paymentLabel, notices, footer }: CheckoutSidebarProps) {
  const [folded, setFolded] = useState(false);

  return (
    <>
      {open ? (
        <div aria-hidden="true" onClick={onDismiss} className="fixed inset-0 z-40 hidden bg-black/60 backdrop-blur-sm md:block lg:hidden" />
      ) : null}
      <aside
        id="current-sale"
        aria-label="Current sale"
        className={`${open ? "cart-sheet flex" : "hidden"} fixed inset-0 z-40 ${drawerShell} md:left-auto md:w-[420px] md:border-l md:shadow-2xl lg:static lg:z-auto lg:flex lg:w-[400px] lg:shadow-none xl:w-[440px]`}
      >
        {header}

        <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto lg:flex lg:flex-col lg:overflow-hidden">
          <div className="px-4 pt-3">{customer}</div>
          {cart}

          <section
            aria-label="Payment"
            className="custom-scrollbar space-y-2 border-t border-zinc-200 px-4 py-2.5 lg:max-h-[35%] lg:min-h-0 lg:shrink-0 lg:overflow-y-auto dark:border-white/[0.08]"
          >
            {summary(
              <button
                type="button"
                aria-expanded={!folded}
                aria-controls="payment-controls"
                title={folded ? "Show payment options" : "Fold payment options away to see more of the cart"}
                onClick={() => setFolded((value) => !value)}
                className="inline-flex h-5 items-center gap-0.5 rounded-full bg-zinc-100 px-2 text-[10px] font-semibold text-zinc-600 transition-colors hover:text-zinc-900 dark:bg-white/[0.08] dark:text-white/70 dark:hover:text-white"
              >
                {folded ? paymentLabel : "Fold"}
                {folded ? <ChevronUp size={12} aria-hidden="true" /> : <ChevronDown size={12} aria-hidden="true" />}
              </button>,
            )}
            {folded ? null : <div id="payment-controls">{payment}</div>}
            {notices}
          </section>
        </div>

        <DrawerFooter>{footer}</DrawerFooter>
      </aside>
    </>
  );
}
