export type LocalExpenseStatus = "pending_sync" | "pending_review" | "synced" | "failed";

export interface LocalExpenseDecision {
  status: LocalExpenseStatus;
  detail: string;
  reservesPetty: boolean;
}

/**
 * Petty cash is reserved only from a balance this register has already downloaded.
 * Without that balance the row is Pending Review and is not a ledger posting.
 */
export function decideLocalExpense(input: {
  paidFrom: string;
  totalCents: number;
  cachedPettyCents: number | null;
}): LocalExpenseDecision {
  if (input.paidFrom !== "PETTY_CASH") {
    return {
      status: "pending_sync",
      detail: "Pending Sync. This is not posted in the accounting ledger until the server accepts it.",
      reservesPetty: false,
    };
  }
  if (input.cachedPettyCents === null) {
    return {
      status: "pending_review",
      detail: "Pending Review. Petty cash on this register is not known, so this is not a settled petty-cash posting.",
      reservesPetty: false,
    };
  }
  if (input.cachedPettyCents < input.totalCents) {
    return {
      status: "pending_review",
      detail: "Pending Review. The downloaded petty-cash balance does not cover this amount, so it is not posted.",
      reservesPetty: false,
    };
  }
  return {
    status: "pending_sync",
    detail: "Pending Sync. The downloaded petty-cash balance covers this amount. The ledger updates only after the server accepts it.",
    reservesPetty: true,
  };
}

export function localExpenseLabel(status: LocalExpenseStatus): string {
  if (status === "pending_sync") return "Pending Sync";
  if (status === "pending_review") return "Pending Review";
  if (status === "synced") return "Synced";
  return "Failed";
}
