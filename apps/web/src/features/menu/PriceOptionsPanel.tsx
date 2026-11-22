import { formatMoney, type MenuPriceOption, type Product } from "@ai-pos/shared-types";
import { useCallback, useEffect, useState } from "react";
import { apiGet, apiPut } from "../../lib/api";
import { useCurrency } from "../../lib/currency";

interface Draft {
  id?: string;
  name: string;
  price: string;
  active: boolean;
}

/** Portal editor for a menu item's priced serving options. Modifiers stay on their own screen. */
export function PriceOptionsPanel() {
  const { currency } = useCurrency();
  const [products, setProducts] = useState<Product[]>([]);
  const [productId, setProductId] = useState("");
  const [rows, setRows] = useState<Draft[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void apiGet<Product[]>("/api/v1/products?limit=500")
      .then(setProducts)
      .catch(() => setError("Could not load menu items."));
  }, []);

  const loadOptions = useCallback(async (id: string) => {
    setProductId(id);
    setMessage(null);
    setError(null);
    if (!id) {
      setRows([]);
      return;
    }
    try {
      const options = await apiGet<MenuPriceOption[]>(`/api/v1/menu/products/${id}/price-options`);
      setRows(
        options.map((option) => ({
          id: option.id,
          name: option.name,
          price: (option.price_cents / 100).toFixed(2),
          active: option.is_active,
        })),
      );
    } catch {
      setError("Could not load priced options.");
    }
  }, []);

  function addRow() {
    setRows((current) => [...current, { name: "", price: "", active: true }]);
  }

  async function save() {
    if (!productId) return;
    const options = rows.map((row, position) => ({
      id: row.id,
      name: row.name.trim(),
      price_cents: Math.round(Number(row.price) * 100),
      is_active: row.active,
      position,
    }));
    if (options.some((option) => !option.name || !Number.isFinite(option.price_cents) || option.price_cents < 0)) {
      setError("Each option needs a name and a price of zero or more.");
      return;
    }
    try {
      const saved = await apiPut<MenuPriceOption[]>(`/api/v1/menu/products/${productId}/price-options`, { options });
      setRows(
        saved.map((option) => ({
          id: option.id,
          name: option.name,
          price: (option.price_cents / 100).toFixed(2),
          active: option.is_active,
        })),
      );
      setError(null);
      setMessage(saved.filter((option) => option.is_active).length >= 2 ? "Multiple prices saved." : "This item uses its single price.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save priced options.");
    }
  }

  const product = products.find((item) => item.id === productId);

  return (
    <div className="rounded-card border border-line bg-white p-6">
      <h2 className="text-xl font-semibold">Priced options</h2>
      <p className="mt-1 text-sm text-charcoal/60">
        Breakfast, plate size, or any other base price. These are not modifiers. Leave the list empty to keep the item's single price.
      </p>
      <label className="mt-4 block text-sm font-medium">
        Menu item
        <select
          className="mt-1 h-11 w-full rounded-xl border border-line px-3"
          value={productId}
          onChange={(event) => void loadOptions(event.target.value)}
        >
          <option value="">Choose an item</option>
          {products.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
      </label>
      {productId ? (
        <div className="mt-4 space-y-2">
          {rows.map((row, index) => (
            <div key={row.id ?? `new-${index}`} className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_8rem_auto]">
              <input
                aria-label={`Option ${index + 1} name`}
                className="h-11 rounded-xl border border-line px-3"
                value={row.name}
                placeholder="Option name"
                onChange={(event) =>
                  setRows((current) => current.map((item, at) => (at === index ? { ...item, name: event.target.value } : item)))
                }
              />
              <input
                aria-label={`Option ${index + 1} price`}
                className="h-11 rounded-xl border border-line px-3"
                inputMode="decimal"
                value={row.price}
                placeholder={product ? formatMoney(0, product.currency || currency) : "0.00"}
                onChange={(event) =>
                  setRows((current) => current.map((item, at) => (at === index ? { ...item, price: event.target.value } : item)))
                }
              />
              <label className="flex h-11 items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={row.active}
                  onChange={(event) =>
                    setRows((current) => current.map((item, at) => (at === index ? { ...item, active: event.target.checked } : item)))
                  }
                />
                Active
              </label>
            </div>
          ))}
          <div className="flex flex-wrap gap-2 pt-2">
            <button type="button" className="h-11 rounded-xl border border-line px-4 text-sm font-semibold" onClick={addRow}>
              Add option
            </button>
            <button type="button" className="h-11 rounded-xl bg-charcoal px-4 text-sm font-semibold text-white" onClick={() => void save()}>
              Save options
            </button>
          </div>
        </div>
      ) : null}
      {error ? <p className="mt-3 text-sm text-red-600">{error}</p> : null}
      {message ? <p className="mt-3 text-sm text-charcoal/70">{message}</p> : null}
    </div>
  );
}
