import { useEffect, useState } from "react";
import { portalUrl } from "../env";
import type { SiteTheme } from "../theme";

const LINKS = [
  { href: "#top", label: "Home", id: "top" },
  { href: "#solutions", label: "Solutions", id: "solutions" },
  { href: "#features", label: "Features", id: "features" },
  { href: "#industries", label: "Industries", id: "industries" },
  { href: "#how", label: "How It Works", id: "how" },
  { href: "#pricing", label: "Pricing", id: "pricing" },
  { href: "#contact", label: "Contact", id: "contact" },
] as const;

export function Navbar({ theme, onToggleTheme, onDemo }: { theme: SiteTheme; onToggleTheme: () => void; onDemo: () => void }) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState("top");

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

  return (
    <header className="sticky top-0 z-20 border-b border-line bg-card/95 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-page items-center justify-between gap-2 px-3 sm:gap-3 sm:px-6 lg:px-8">
        <a href="#top" className="inline-flex min-w-0 items-center" aria-label="AxizPOS home">
          <img src="/brand/logo.svg" alt="" className="h-7 w-auto sm:h-8 dark:hidden" />
          <img src="/brand/logo-white.svg" alt="" className="hidden h-7 w-auto sm:h-8 dark:block" />
        </a>
        <nav aria-label="Page" className="hidden items-center gap-4 xl:flex">
          {LINKS.map((link) => (
            <a
              key={link.href}
              href={link.href}
              aria-current={active === link.id ? "true" : undefined}
              className={`text-sm font-medium ${active === link.id ? "text-primary" : "text-charcoal/75 hover:text-charcoal"}`}
            >
              {link.label}
            </a>
          ))}
        </nav>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onToggleTheme}
            className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-line text-sm font-medium text-charcoal sm:w-auto sm:px-3"
            aria-pressed={theme === "dark"}
            aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          >
            <span className="sm:hidden" aria-hidden="true">
              {theme === "dark" ? "L" : "D"}
            </span>
            <span className="hidden sm:inline">{theme === "dark" ? "Light" : "Dark"}</span>
          </button>
          <a href={portalUrl} className="hidden h-11 items-center rounded-2xl border border-line px-4 text-sm font-semibold text-charcoal sm:inline-flex">
            Sign In
          </a>
          <button
            type="button"
            onClick={onDemo}
            className="inline-flex h-11 shrink-0 items-center whitespace-nowrap rounded-2xl bg-primary px-3 text-sm font-semibold text-white hover:bg-primary-hover sm:px-4"
          >
            <span className="sm:hidden">Demo</span>
            <span className="hidden sm:inline">Book a Demo</span>
          </button>
          <button
            type="button"
            className="inline-flex h-11 w-11 items-center justify-center rounded-2xl border border-line xl:hidden"
            aria-expanded={open}
            aria-controls="mobile-nav"
            onClick={() => setOpen((value) => !value)}
          >
            <span className="sr-only">{open ? "Close menu" : "Open menu"}</span>
            <span aria-hidden="true" className="flex w-4 flex-col gap-1">
              <span className="h-0.5 bg-charcoal" />
              <span className="h-0.5 bg-charcoal" />
              <span className="h-0.5 bg-charcoal" />
            </span>
          </button>
        </div>
      </div>
      {open ? (
        <nav id="mobile-nav" aria-label="Page" className="border-t border-line bg-card px-4 py-3 xl:hidden">
          <ul className="grid gap-1">
            {LINKS.map((link) => (
              <li key={link.href}>
                <a
                  href={link.href}
                  onClick={() => setOpen(false)}
                  className="flex h-11 items-center rounded-xl px-3 text-sm font-medium text-charcoal hover:bg-surface"
                >
                  {link.label}
                </a>
              </li>
            ))}
            <li>
              <a href={portalUrl} className="flex h-11 items-center rounded-xl px-3 text-sm font-semibold text-charcoal hover:bg-surface">
                Sign In
              </a>
            </li>
          </ul>
        </nav>
      ) : null}
    </header>
  );
}
