import { ShoppingCart } from "lucide-react";
import type { CartRow } from "./cart";
import { CartItemCard, type CartItemCardProps } from "./CartItemCard";

type SharedCardProps = Omit<CartItemCardProps, "row" | "floorCents">;

interface CartListProps extends SharedCardProps {
  rows: CartRow[];
  /** Margin floor per product id at this branch. */
  floorFor: (productId: string) => number | null;
}

/** The scrolling item list: it takes every pixel the payment sheet leaves free. */
export function CartList({ rows, floorFor, ...card }: CartListProps) {
  return (
    <ul aria-label="Cart items" className="custom-scrollbar flex flex-col gap-1.5 px-4 py-2.5 lg:min-h-[180px] lg:flex-1 lg:overflow-y-auto">
      {rows.length === 0 ? (
        <li className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-zinc-300 px-6 py-10 text-center lg:flex-1 dark:border-white/10">
          <ShoppingCart size={28} aria-hidden="true" className="text-zinc-300 dark:text-zinc-600" />
          <p className="mt-3 text-sm font-semibold text-zinc-700 dark:text-zinc-300">The cart is empty</p>
          <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">Scan a barcode or tap a product to start a sale.</p>
        </li>
      ) : (
        rows.map((row) => <CartItemCard key={row.key} row={row} floorCents={floorFor(row.product.id)} {...card} />)
      )}
    </ul>
  );
}
