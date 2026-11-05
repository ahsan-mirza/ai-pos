/** Invoice handed from Shift sales history to the return wizard on the next open. */
let pending: string | null = null;

export function queueReturnLookup(invoice: string): void {
  pending = invoice.trim();
}

export function takeReturnLookup(): string | null {
  const value = pending;
  pending = null;
  return value && value.length > 0 ? value : null;
}
