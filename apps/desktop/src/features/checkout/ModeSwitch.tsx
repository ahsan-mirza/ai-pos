import type { SaleType } from "@ai-pos/shared-types";
import { Boxes, ShoppingBag } from "lucide-react";

const modes = [
  { value: "RETAIL", label: "Retail", long: "Retail Mode", icon: ShoppingBag },
  { value: "WHOLESALE", label: "Wholesale", long: "Wholesale Mode", icon: Boxes },
] as const;

interface ModeSwitchProps {
  mode: SaleType;
  disabled?: boolean;
  onChange: (mode: SaleType) => void;
}

export function ModeSwitch({ mode, disabled = false, onChange }: ModeSwitchProps) {
  return (
    <div className="inline-flex rounded-full border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900/60 p-1" role="group" aria-label="Sale mode">
      {modes.map((option) => {
        const active = mode === option.value;
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={active}
            disabled={disabled}
            onClick={() => onChange(option.value)}
            className={`inline-flex h-12 items-center gap-2 rounded-full px-4 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60 disabled:opacity-50 sm:px-5 ${
              active ? "bg-primary text-white shadow-lg shadow-primary/25" : "text-zinc-600 dark:text-white/60 hover:text-zinc-900 dark:hover:text-white"
            }`}
          >
            <option.icon size={16} aria-hidden="true" />
            <span className="sm:hidden">{option.label}</span>
            <span className="hidden sm:inline">{option.long}</span>
          </button>
        );
      })}
    </div>
  );
}
