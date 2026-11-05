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
export function LanguageSwitch({ className = "" }: { className?: string }) {
  const { locale, setLocale: choose, t } = useLocale();
  const item = (id: Locale, label: string) => (
    <button
      type="button"
      aria-pressed={locale === id}
      onClick={() => choose(id)}
      className={`inline-flex h-8 items-center rounded-full px-2.5 text-xs font-semibold ${
        locale === id ? "bg-white text-charcoal shadow-sm dark:bg-zinc-700 dark:text-white" : "text-charcoal/60 dark:text-zinc-400"
      }`}
    >
      {label}
    </button>
  );
  return (
    <div
      role="group"
      aria-label={t("Language")}
      className={`inline-flex h-9 items-center gap-0.5 rounded-full bg-charcoal/[0.04] p-0.5 dark:bg-zinc-800 ${className}`}
    >
      {item("en", "English")}
      <span aria-hidden="true" className="text-charcoal/25 dark:text-zinc-600">
        |
      </span>
      {item("ar", "العربية")}
    </div>
  );
}
