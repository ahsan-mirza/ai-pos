/** Priced options saved beside the menu item. One filled row is refused. An empty list keeps the single base price. */
export interface PriceDraft {
  id?: string;
  name: string;
  price: string;
  active?: boolean;
}

export interface PriceOptionPayload {
  id?: string;
  name: string;
  price_cents: number;
  is_active: boolean;
  position: number;
}

export function priceOptionsPayload(
  rows: readonly PriceDraft[],
  cents: (price: string) => number | null,
): { options: PriceOptionPayload[] } | null {
  const filled = rows
    .map((row, index) => ({
      id: row.id,
      name: row.name.trim(),
      price: cents(row.price),
      active: row.active,
      position: index,
    }))
    .filter((row) => row.name !== "" || row.price !== null);
  if (filled.length === 0) return null;
  if (filled.length < 2 || filled.some((row) => row.name === "" || row.price === null)) {
    throw new Error("A menu item with priced options needs at least two named prices. Clear them to keep the single price.");
  }
  if (!filled.some((row) => row.active !== false)) {
    throw new Error("At least one priced option must stay active.");
  }
  const names = new Set<string>();
  for (const row of filled) {
    const key = row.name.toLocaleLowerCase();
    if (names.has(key)) throw new Error("Two priced options on one item cannot share a name.");
    names.add(key);
  }
  return {
    options: filled.map((row) => ({
      ...(row.id ? { id: row.id } : {}),
      name: row.name,
      price_cents: row.price as number,
      is_active: row.active !== false,
      position: row.position,
    })),
  };
}
