import { Permission, formatMoney } from "@ai-pos/shared-types";
import { useState } from "react";
import { ManagerApprovalModal } from "../../components/ManagerApprovalModal";
import type { CashierSession } from "../auth/session";
import type { CartRow, PriceOverride } from "./cart";
import { parseCents } from "./tenders";
import { verifyManager } from "./wholesaleClient";

interface PriceOverrideModalProps {
  session: CashierSession;
  row: CartRow;
  currency: string;
  onClose: () => void;
  onApproved: (override: PriceOverride) => void;
}

export function PriceOverrideModal({ session, row, currency, onClose, onApproved }: PriceOverrideModalProps) {
  const line = row.lines[0];
  const listed = line?.listPriceCents ?? row.product.price_cents;
  const [price, setPrice] = useState((listed / 100).toFixed(2));
  const cents = parseCents(price);
  const valid = cents !== null && cents !== listed;
  const pieces = row.lines.reduce((sum, item) => sum + item.quantity, 0);

  return (
    <ManagerApprovalModal
      reasons={[`Change ${row.product.name} from ${formatMoney(listed, currency)} per piece`]}
      subtitle="A manager with price override rights must enter their PIN."
      verify={(username, pin) => verifyManager(session, username, pin, Permission.PosPriceOverride)}
      onClose={onClose}
      ready={valid}
      approveLabel="Approve price"
      remote={{
        kind: "PRICE_OVERRIDE",
        requestedById: session.user.id,
        title: `Price override: ${row.product.name}`,
        details: [
          `${formatMoney(listed, currency)} → ${cents === null ? "?" : formatMoney(cents, currency)} per piece`,
          `${pieces} pcs for ${formatMoney((cents ?? listed) * pieces, currency)} (list ${formatMoney(listed * pieces, currency)})`,
          `Cashier: ${session.user.full_name}`,
        ],
        amountCents: (cents ?? listed) * pieces,
      }}
      onApproved={(approver, note) => {
        if (cents === null) return;
        onApproved({ approvedById: approver.id, approverName: approver.full_name, note, unitPriceCents: cents });
      }}
    >
      <label className="block text-sm font-medium" htmlFor="override-price">
        New price per piece
        <input
          id="override-price"
          autoFocus
          inputMode="decimal"
          value={price}
          onChange={(event) => setPrice(event.target.value)}
          className="modal-input mt-1.5 text-lg font-semibold tabular-nums"
        />
      </label>
      <p className="-mt-2 text-xs text-charcoal/60 dark:text-zinc-400 tabular-nums">
        {cents === null
          ? "Enter a price such as 12.50."
          : `${pieces} pcs → ${formatMoney(cents * pieces, currency)} (list ${formatMoney(listed * pieces, currency)})`}
      </p>
    </ManagerApprovalModal>
  );
}
