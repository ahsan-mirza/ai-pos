import { Calendar, LogIn, Menu, Moon, Sparkles, Sun, UserPlus, X } from "lucide-react";
import { useEffect, useState } from "react";
import { portalUrl, signupUrl } from "../env";
import type { SiteTheme } from "../theme";

const LINKS = [
  { href: "#top", label: "Home", id: "top" },
  { href: "#intelligence", label: "AI", id: "intelligence" },
  { href: "#solutions", label: "Solutions", id: "solutions" },
  { href: "#features", label: "Features", id: "features" },
  { href: "#industries", label: "Industries", id: "industries" },
  { href: "#how", label: "How it Works", id: "how" },
  { href: "#pricing", label: "Pricing", id: "pricing" },
  { href: "#contact", label: "Contact", id: "contact" },
] as const;

const linkClass = (current: boolean) =>
  `whitespace-nowrap transition-colors hover:text-orange-500 dark:hover:text-orange-400 ${
    current ? "text-orange-500 dark:text-orange-400" : "text-slate-600 dark:text-slate-300"
  }`;

export function Navbar({
  atHome = true,
  theme,
  onToggleTheme,
  onDemo,
}: {
  atHome?: boolean;
  theme: SiteTheme;
  onToggleTheme: () => void;
  onDemo: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState("top");
  const dark = theme === "dark";

  useEffect(() => {
    const nodes = LINKS.map((link) => document.getElementById(link.id)).filter((node) => node !== null);
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (visible?.target.id) setActive(visible.target.id);
      },
      { rootMargin: "-30% 0px -55% 0px", threshold: [0.15, 0.4] },
    );
    for (const node of nodes) observer.observe(node);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  useEffect(() => {
    const media = window.matchMedia("(min-width: 1024px)");
    const close = () => {
      if (media.matches) setOpen(false);
    };
    media.addEventListener("change", close);
    return () => media.removeEventListener("change", close);
  }, []);

  return (
    <header className="sticky top-0 z-50 w-full border-b border-slate-200/80 bg-white/80 px-4 py-3 text-slate-900 backdrop-blur-md transition-all dark:border-slate-800/80 dark:bg-slate-900/80 dark:text-white sm:px-8">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4">
        <a href={atHome ? "#top" : "/"} className="flex cursor-pointer items-center gap-2" aria-label="AxizPOS home">
          <img src="/brand/logo.svg" alt="" width={137} height={32} className="h-8 w-auto dark:hidden" />
          <img src="/brand/logo-white.svg" alt="" width={137} height={32} className="hidden h-8 w-auto dark:block" />
        </a>

        <nav aria-label="Page" className="hidden items-center gap-6 text-sm font-medium lg:flex xl:gap-8">
          {LINKS.map((link) =>
            link.id === "intelligence" ? (
              <a key={link.href} href={atHome ? link.href : `/${link.href}`} aria-current={atHome && active === link.id ? "true" : undefined} className="whitespace-nowrap">
                <AiBadge current={atHome && active === link.id} />
              </a>
            ) : (
              <a key={link.href} href={atHome ? link.href : `/${link.href}`} aria-current={atHome && active === link.id ? "true" : undefined} className={linkClass(atHome && active === link.id)}>
                {link.label}
              </a>
            ),
          )}
        </nav>

        <div className="flex items-center gap-1 sm:gap-2">
          <button
            type="button"
            onClick={onToggleTheme}
            className="hidden rounded-xl p-2 text-slate-500 transition-all hover:bg-slate-100 hover:text-slate-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-orange-500 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white lg:inline-flex"
            aria-pressed={dark}
            aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
          >
            {dark ? <Sun className="h-5 w-5" aria-hidden="true" /> : <Moon className="h-5 w-5" aria-hidden="true" />}
          </button>
          <a
            href={portalUrl}
            className="hidden px-3 py-2 text-sm font-medium text-slate-600 transition-colors hover:text-slate-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-orange-500 dark:text-slate-300 dark:hover:text-white lg:inline-flex"
          >
            Sign In
          </a>
          <button
            type="button"
            onClick={onDemo}
            className="inline-flex cursor-pointer items-center gap-2 whitespace-nowrap rounded-xl bg-gradient-to-r from-orange-500 to-amber-500 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-orange-500/20 transition-all hover:from-orange-600 hover:to-amber-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-orange-500 motion-safe:hover:scale-[1.02] motion-safe:active:scale-[0.98] sm:px-5"
          >
            <Calendar className="h-4 w-4" aria-hidden="true" />
            Book a Demo
          </button>
          <button
            type="button"
            className="rounded-xl p-2 text-slate-500 transition-all hover:bg-slate-100 hover:text-slate-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-orange-500 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white lg:hidden"
            aria-expanded={open}
            aria-controls="mobile-nav"
            onClick={() => setOpen((value) => !value)}
          >
            <span className="sr-only">{open ? "Close menu" : "Open menu"}</span>
            {open ? <X className="h-5 w-5" aria-hidden="true" /> : <Menu className="h-5 w-5" aria-hidden="true" />}
          </button>
        </div>
      </div>

      {open ? (
        <nav id="mobile-nav" aria-label="Page" className="mx-auto mt-3 max-w-7xl border-t border-slate-200 pt-3 dark:border-slate-800 lg:hidden">
          <ul className="grid gap-1">
            {LINKS.map((link) => (
              <li key={link.href}>
                <a
                  href={atHome ? link.href : `/${link.href}`}
                  onClick={() => setOpen(false)}
                  aria-current={atHome && active === link.id ? "true" : undefined}
                  className="flex h-11 items-center rounded-xl px-3 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800"
                >
                  {link.id === "intelligence" ? <AiBadge current={active === link.id} /> : link.label}
                </a>
              </li>
            ))}
            <li>
              <a href={portalUrl} className="flex h-11 items-center gap-2 rounded-xl px-3 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800">
                <LogIn className="h-4 w-4" aria-hidden="true" />
                Sign In
              </a>
            </li>
            <li>
              <a href={signupUrl} className="flex h-11 items-center gap-2 rounded-xl px-3 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800">
                <UserPlus className="h-4 w-4" aria-hidden="true" />
                Sign Up
              </a>
            </li>
            <li>
              <button
                type="button"
                onClick={onToggleTheme}
                className="flex h-11 w-full items-center gap-2 rounded-xl px-3 text-left text-sm font-medium text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800"
                aria-pressed={dark}
              >
                {dark ? <Sun className="h-4 w-4" aria-hidden="true" /> : <Moon className="h-4 w-4" aria-hidden="true" />}
                {dark ? "Light theme" : "Dark theme"}
              </button>
            </li>
          </ul>
        </nav>
      ) : null}
    </header>
  );
}

function AiBadge({ current }: { current: boolean }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border bg-gradient-to-r from-orange-500/10 to-amber-500/10 px-2.5 py-0.5 text-xs font-semibold text-orange-500 dark:text-orange-400 ${
        current ? "border-orange-500" : "border-orange-500/30"
      }`}
    >
      <Sparkles className="h-3 w-3" aria-hidden="true" />
      AI
    </span>
  );
}
