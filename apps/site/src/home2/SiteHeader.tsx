import { ChevronDown, Globe, Menu, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { portalUrl } from "../env";

const productLinks = [
  { href: "/#platform", label: "Overview" },
  { href: "/#platform", label: "Features" },
];

const solutionLinks = [
  { href: "/cafe-pos", label: "Café" },
  { href: "/restaurant-pos", label: "Restaurant" },
  { href: "/grocery-pos", label: "Supermarket" },
  { href: "/electronics-pos", label: "Electronics" },
  { href: "/fashion-pos", label: "Fashion" },
  { href: "/wholesale-pos", label: "Retail & Wholesale" },
];

const resourceLinks = [
  { href: "/blog", label: "Blog" },
  { href: "/blog", label: "Guides" },
];

const featurePaths = ["/inventory-management", "/offline-pos", "/multi-branch-pos", "/imei-serial-tracking", "/kitchen-display", "/loyalty-promotions"];

function here(href: string, atHome: boolean): string {
  return atHome && href.startsWith("/#") ? href.slice(1) : href;
}

function pathMatches(href: string): boolean {
  const path = window.location.pathname.replace(/\/+$/, "") || "/";
  const bare = href.split("#")[0] ?? "/";
  if (href.startsWith("/#")) return (path === "/" || path === "/ar") && window.location.hash === href.slice(1);
  return path === bare || path === `/ar${bare}`;
}

export function SiteHeader({ atHome, onDemo }: { atHome: boolean; onDemo: () => void }) {
  const [open, setOpen] = useState(false);
  const [stuck, setStuck] = useState(false);
  const productOn = pathMatches("/#platform") || featurePaths.some((path) => pathMatches(path));
  const solutionsOn = solutionLinks.some((link) => pathMatches(link.href));
  const resourcesOn = window.location.pathname.includes("/blog");
  const pricingOn = pathMatches("/#pricing");

  useEffect(() => {
    const onScroll = () => setStuck(window.scrollY > 4);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    if (!open) return undefined;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <header className={stuck ? "h2-nav is-stuck" : "h2-nav"}>
      <div className="h2-nav-bar">
        <a className="h2-logo" href="/" aria-label="AxizPOS home">
          <img src="/brand/logo.svg" alt="" width="132" height="32" />
        </a>
        <nav className={open ? "h2-links is-open" : "h2-links"} aria-label="Primary" onClick={() => setOpen(false)}>
          <a className={pathMatches("/explore") ? "is-current" : undefined} href="/explore">
            Explore AxizPOS
          </a>
          <a className={window.location.pathname.startsWith("/hardware") ? "is-current" : undefined} href="/hardware">
            Hardware
          </a>
          <Drop label="Product" links={productLinks} atHome={atHome} current={productOn} />
          <Drop label="Solutions" links={solutionLinks} atHome={atHome} current={solutionsOn} />
          <a className={pricingOn ? "is-current" : undefined} href={here("/#pricing", atHome)}>
            Pricing
          </a>
          <Drop label="Resources" links={resourceLinks} atHome={atHome} current={resourcesOn} />
          <div className="h2-nav-tools">
            <Language />
            <a className="h2-login" href={portalUrl}>
              {document.documentElement.lang === "ar" ? "دخول" : "Sign In"}
            </a>
            <button
              className="h2-btn"
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                setOpen(false);
                onDemo();
              }}
            >
              Book a Demo
            </button>
          </div>
        </nav>
        <button className="h2-burger" type="button" aria-expanded={open} aria-label={open ? "Close menu" : "Open menu"} onClick={() => setOpen((value) => !value)}>
          {open ? <X size={22} /> : <Menu size={22} />}
        </button>
      </div>
    </header>
  );
}

function Drop({ label, links, atHome, current }: { label: string; links: { href: string; label: string }[]; atHome: boolean; current: boolean }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const hovered = useRef(false);
  const fine = () => window.matchMedia("(hover: hover) and (pointer: fine)").matches;

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    const onPointer = (event: PointerEvent) => {
      if (!ref.current?.contains(event.target as Node)) setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("pointerdown", onPointer);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pointerdown", onPointer);
    };
  }, [open]);

  return (
    <div
      className={open ? "h2-drop is-open" : current ? "h2-drop is-current" : "h2-drop"}
      ref={ref}
      onMouseEnter={() => {
        if (!fine()) return;
        hovered.current = true;
        setOpen(true);
      }}
      onMouseLeave={() => {
        if (!fine()) return;
        hovered.current = false;
        setOpen(false);
      }}
      onBlur={(event) => {
        if (!ref.current?.contains(event.relatedTarget as Node)) setOpen(false);
      }}
    >
      <button
        type="button"
        aria-expanded={open}
        aria-haspopup="true"
        aria-current={current ? "true" : undefined}
        onClick={(event) => {
          event.stopPropagation();
          if (hovered.current) return;
          setOpen((value) => !value);
        }}
        onKeyDown={(event) => event.key === "Escape" && setOpen(false)}
      >
        {label}
        <ChevronDown size={16} />
      </button>
      <ul hidden={!open}>
        {links.map((link) => (
          <li key={link.label}>
            <a href={here(link.href, atHome)} aria-current={pathMatches(link.href) ? "page" : undefined}>
              {link.label}
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
function alternatePath(): string {
  const arabic = document.documentElement.lang === "ar";
  const link = document.querySelector(`link[rel="alternate"][hreflang="${arabic ? "en" : "ar"}"]`);
  const href = link?.getAttribute("href");
  if (!href) return arabic ? "/" : "/ar";
  try {
    return new URL(href, window.location.origin).pathname || (arabic ? "/" : "/ar");
  } catch {
    return arabic ? "/" : "/ar";
  }
}

function Language() {
  const [open, setOpen] = useState(false);
  const arabic = document.documentElement.lang === "ar";
  const href = alternatePath();
  return (
    <div
      className={open ? "h2-lang is-open" : "h2-lang"}
      onMouseLeave={() => {
        if (window.matchMedia("(hover: hover) and (pointer: fine)").matches) setOpen(false);
      }}
    >
      <button type="button" aria-expanded={open} aria-label="Language" onClick={() => setOpen((value) => !value)}>
        <Globe size={16} />
        {arabic ? "AR" : "EN"}
        <ChevronDown size={14} />
      </button>
      <ul hidden={!open}>
        <li>
          <span>{arabic ? "العربية" : "English"}</span>
        </li>
        <li>
          <a href={href}>{arabic ? "English" : "العربية"}</a>
        </li>
      </ul>
    </div>
  );
}
