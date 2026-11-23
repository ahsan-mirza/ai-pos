/** A whole selling quantity from a numeric field. Empty, zero, or text is not a quantity. */
export function parseSellQuantity(raw: string): number | null {
  if (!/^\d+$/.test(raw.trim())) return null;
  const value = Number(raw);
  if (!Number.isSafeInteger(value) || value < 1 || value > 9999) return null;
  return value;
}

/** The first submit claims the dialog. A second call before release is ignored. */
export function claimSubmit(guard: { current: boolean }): boolean {
  if (guard.current) return false;
  guard.current = true;
  return true;
}

/** Lets a later, separate confirmation through after the cart refused the line. */
export function releaseSubmit(guard: { current: boolean }): void {
  guard.current = false;
}

/** Unit price in minor units times a validated quantity. Invalid quantity yields null. */
export function sellLineTotalCents(unitCents: number, rawQuantity: string): number | null {
  const count = parseSellQuantity(rawQuantity);
  if (count === null || !Number.isSafeInteger(unitCents) || unitCents < 0) return null;
  return unitCents * count;
}

export function QuantityField({
  id,
  value,
  onChange,
  autoFocus = false,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  autoFocus?: boolean;
}) {
  const current = parseSellQuantity(value);
  const atMinimum = current === null || current <= 1;

  function step(delta: number) {
    const base = current ?? 1;
    const next = Math.min(9999, Math.max(1, base + delta));
    onChange(String(next));
  }

  return (
    <div>
      <span id={`${id}-label`} className="block text-sm font-semibold">
        Quantity
      </span>
      <div className="mt-2 flex select-none items-center justify-center gap-3" role="group" aria-labelledby={`${id}-label`}>
        <button
          type="button"
          aria-label="Decrease quantity"
          disabled={atMinimum}
          onClick={() => step(-1)}
          className="control-focus flex h-14 w-14 items-center justify-center rounded-2xl border border-zinc-300 text-2xl font-semibold disabled:opacity-40 dark:border-zinc-600"
        >
          −
        </button>
        <input
          id={id}
          inputMode="numeric"
          autoComplete="off"
          autoFocus={autoFocus}
          aria-labelledby={`${id}-label`}
          value={value}
          onChange={(event) => onChange(event.target.value.replace(/\D/g, "").slice(0, 4))}
          className="control-focus h-14 w-20 rounded-2xl border border-zinc-300 bg-white text-center text-2xl font-semibold tabular-nums dark:border-zinc-600 dark:bg-zinc-950"
        />
        <button
          type="button"
          aria-label="Increase quantity"
          onClick={() => step(1)}
          className="control-focus flex h-14 w-14 items-center justify-center rounded-2xl border border-zinc-300 text-2xl font-semibold dark:border-zinc-600"
        >
          +
        </button>
      </div>
    </div>
  );
}
