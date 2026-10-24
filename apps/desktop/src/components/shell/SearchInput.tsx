import { Search, X, type LucideIcon } from "lucide-react";
import { useEffect, useRef, type Ref } from "react";

interface SearchInputProps {
  id: string;
  label: string;
  /** Show the label above the field; otherwise it is screen-reader only. */
  showLabel?: boolean;
  value: string;
  placeholder: string;
  onChange: (value: string) => void;
  onSubmit: (value: string) => void;
  actionLabel: string;
  actionIcon?: LucideIcon;
  icon?: LucideIcon;
  busy?: boolean;
  disabled?: boolean;
  /** Global key that focuses and selects the field; null turns it off. */
  shortcut?: string | null;
  onShortcut?: () => void;
  autoFocus?: boolean;
  /** "disabled" keeps a barcode-scanner field from opening the touch keyboard. */
  virtualKeyboard?: "text" | "numeric" | "disabled";
  uppercase?: boolean;
  inputRef?: Ref<HTMLInputElement>;
}

/** Barcode / text search used by every register page: prefix icon, shortcut hints, flush action button. */
export function SearchInput({
  id,
  label,
  showLabel = false,
  value,
  placeholder,
  onChange,
  onSubmit,
  actionLabel,
  actionIcon: ActionIcon = Search,
  icon: Icon = Search,
  busy = false,
  disabled = false,
  shortcut = "F2",
  onShortcut,
  autoFocus = false,
  virtualKeyboard,
  uppercase = false,
  inputRef,
}: SearchInputProps) {
  const ownRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (shortcut === null) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== shortcut) return;
      event.preventDefault();
      onShortcut?.();
      ownRef.current?.focus();
      ownRef.current?.select();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [shortcut, onShortcut]);

  const setRef = (node: HTMLInputElement | null) => {
    ownRef.current = node;
    if (typeof inputRef === "function") inputRef(node);
    else if (inputRef) inputRef.current = node;
  };

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit(value);
      }}
    >
      <label htmlFor={id} className={showLabel ? "mb-2 block text-sm font-semibold" : "sr-only"}>
        {label}
      </label>
      <div className="flex h-14 overflow-hidden rounded-xl border border-zinc-200 bg-white shadow-sm transition-colors focus-within:border-primary-500 focus-within:ring-4 focus-within:ring-primary-500/15 dark:border-zinc-800 dark:bg-zinc-900/60">
        <div className="relative min-w-0 flex-1">
          <Icon
            size={20}
            aria-hidden="true"
            className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-zinc-400 dark:text-zinc-500"
          />
          <input
            ref={setRef}
            id={id}
            type="search"
            data-virtual-keyboard={virtualKeyboard}
            autoFocus={autoFocus}
            autoComplete="off"
            spellCheck={false}
            disabled={disabled}
            value={value}
            aria-keyshortcuts={shortcut ?? undefined}
            placeholder={placeholder}
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Escape" && value !== "") {
                event.preventDefault();
                event.stopPropagation();
                onChange("");
              }
            }}
            className={`h-full w-full bg-transparent pl-12 pr-32 text-base tabular-nums text-zinc-900 placeholder:normal-case placeholder:text-zinc-400 focus:outline-none [&::-webkit-search-cancel-button]:hidden dark:text-zinc-100 dark:placeholder:text-zinc-500 ${
              uppercase ? "uppercase" : ""
            }`}
          />
          <span className="pointer-events-none absolute right-3 top-1/2 hidden -translate-y-1/2 items-center gap-1.5 text-[11px] text-zinc-500 sm:flex dark:text-zinc-400">
            {shortcut ? (
              <>
                <kbd className="rounded-md border border-zinc-200 bg-zinc-50 px-1.5 py-0.5 font-mono text-[10px] font-semibold dark:border-zinc-700 dark:bg-zinc-800">
                  {shortcut}
                </kbd>
                focus
              </>
            ) : null}
            <kbd className="rounded-md border border-zinc-200 bg-zinc-50 px-1.5 py-0.5 font-mono text-[10px] font-semibold dark:border-zinc-700 dark:bg-zinc-800">
              ↵
            </kbd>
          </span>
          {value !== "" ? (
            <button
              type="button"
              aria-label="Clear search"
              onClick={() => {
                onChange("");
                ownRef.current?.focus();
              }}
              className="absolute right-24 top-1/2 hidden h-7 w-7 -translate-y-1/2 items-center justify-center rounded-full text-zinc-400 hover:bg-zinc-100 hover:text-zinc-700 sm:flex dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
            >
              <X size={14} aria-hidden="true" />
            </button>
          ) : null}
        </div>
        <button
          type="submit"
          disabled={busy || disabled || value.trim() === ""}
          className="flex shrink-0 items-center gap-2 border-l border-primary-600/20 bg-primary-500 px-5 text-sm font-semibold text-white transition-colors hover:bg-primary-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-white/60 disabled:bg-primary-500/50 disabled:text-white/80"
        >
          <ActionIcon size={17} aria-hidden="true" />
          <span className="hidden sm:inline">{busy ? "Working…" : actionLabel}</span>
        </button>
      </div>
    </form>
  );
}
