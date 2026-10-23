/** A whole selling quantity from a numeric field. Empty or zero is not a quantity. */
export function parseSellQuantity(raw: string): number | null {
  if (!/^\d+$/.test(raw.trim())) return null;
  const value = Number(raw);
  if (value < 1 || value > 9999) return null;
  return value;
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
  return (
    <label className="block text-sm font-medium" htmlFor={id}>
      Quantity
      <input
        id={id}
        inputMode="numeric"
        autoComplete="off"
        autoFocus={autoFocus}
        value={value}
        onChange={(event) => onChange(event.target.value.replace(/\D/g, "").slice(0, 4))}
        className="modal-input mt-1.5 font-semibold tabular-nums"
      />
    </label>
  );
}
