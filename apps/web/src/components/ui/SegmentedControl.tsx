interface Option<T extends string> {
  value: T;
  label: string;
}

interface SegmentedControlProps<T extends string> {
  value: T;
  options: readonly Option<T>[];
  onChange: (value: T) => void;
  label: string;
}

export function SegmentedControl<T extends string>({
  value,
  options,
  onChange,
  label,
}: SegmentedControlProps<T>) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap items-center gap-2">
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(option.value)}
            className={`h-10 rounded-full border px-5 text-sm font-semibold transition-colors ${
              active
                ? "border-accent bg-accent text-white"
                : "border-line bg-white text-charcoal/70 hover:text-charcoal"
            }`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
