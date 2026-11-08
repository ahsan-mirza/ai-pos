import { useSyncExternalStore } from "react";
import { localize, readLocale, setLocale, subscribeLocale, type Locale } from "./locale";

export function useLocale() {
  const locale = useSyncExternalStore(subscribeLocale, readLocale, (): Locale => "en");
  return {
    locale,
    setLocale,
    t: (text: string, vars?: Record<string, string | number>) => localize(text, locale, vars),
  };
}

/** English and Arabic stay written in their own scripts so the control is recognizable in either layout. */
export function LanguageSwitch({ className = "", compact = false }: { className?: string; compact?: boolean }) {
  const { locale, setLocale: choose, t } = useLocale();
  const item = (id: Locale, label: string) => (
    <button
      type="button"
      aria-pressed={locale === id}
      onClick={() => choose(id)}
      className={`inline-flex items-center rounded-full font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/50 ${
        compact ? "h-8 px-2 text-xs" : "h-8 px-2.5 text-xs"
      } ${locale === id ? "bg-white text-charcoal shadow-sm dark:bg-zinc-700 dark:text-white" : "text-charcoal/60 dark:text-zinc-400"}`}
    >
      {label}
    </button>
  );
  return (
    <div
      role="group"
      aria-label={t("Language")}
      dir="ltr"
      className={`inline-flex items-center gap-0.5 rounded-full bg-charcoal/[0.04] p-0.5 dark:bg-zinc-800 ${compact ? "h-10" : "h-9"} ${className}`}
    >
      {item("en", compact ? "EN" : "English")}
      <span aria-hidden="true" className="text-charcoal/25 dark:text-zinc-600">
        |
      </span>
      {item("ar", compact ? "AR" : "العربية")}
    </div>
  );
}
