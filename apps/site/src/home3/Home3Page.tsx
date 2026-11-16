import { isValidE164, PhoneField } from "@ai-pos/ui";
import { motion, useReducedMotion } from "framer-motion";
import {
  ArrowRight,
  BarChart3,
  Boxes,
  Check,
  ChevronDown,
  Coffee,
  Globe,
  Menu,
  Monitor,
  Package,
  Play,
  Printer,
  Puzzle,
  Receipt,
  Scale,
  Shield,
  Shirt,
  ShoppingCart,
  Smartphone,
  Store,
  Users,
  UtensilsCrossed,
  Wallet,
  Wifi,
  X,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import {
  defaultCountry,
  loadCatalog,
  money,
  publishedPrice,
  showcasePlans,
  EMPTY_CATALOG,
  type Plan,
  type PublicCatalog,
} from "../catalog";
import { apiBaseUrl, portalUrl, signupUrl } from "../env";
import { track } from "../track";
import { WhatsAppButton } from "../components/WhatsAppButton";
import { EMPTY_WHATSAPP, parsePublicWhatsApp, publishedWhatsapp, whatsappChatUrl, whatsappDigits, whatsappReady, type PublicWhatsApp } from "../whatsapp";

const PRODUCT = [
  { href: "#features", label: "Overview" },
  { href: "/retail-pos", label: "Sales & billing" },
  { href: "/offline-pos", label: "Offline POS" },
  { href: "/inventory-management", label: "Inventory" },
  { href: "#hardware", label: "Hardware" },
];

const SOLUTIONS = [
  { href: "/cafe-pos", label: "Cafe" },
  { href: "/restaurant-pos", label: "Restaurant" },
  { href: "/grocery-pos", label: "Grocery & Supermarket" },
  { href: "/electronics-pos", label: "Electronics & Wholesale" },
  { href: "/fashion-pos", label: "Fashion & Retail" },
  { href: "/quick-service-pos", label: "Quick Service" },
  { href: "/wholesale-pos", label: "Wholesale" },
];

const FEATURES = [
  { href: "/retail-pos", label: "Sales & billing" },
  { href: "/inventory-management", label: "Inventory" },
  { href: "/multi-branch-pos", label: "Multi-branch" },
  { href: "/loyalty-promotions", label: "Customers & loyalty" },
  { href: "/kitchen-display", label: "Kitchen display" },
  { href: "/imei-serial-tracking", label: "IMEI & serial" },
  { href: "/offline-pos", label: "Offline checkout" },
];

const RESOURCES = [
  { href: "/blog", label: "Blog" },
  { href: "/blog", label: "Guides" },
  { href: "/pos-software-uae", label: "POS software UAE" },
  { href: "#demo", label: "Contact" },
];

const INDUSTRIES: {
  id: string;
  label: string;
  eyebrow: string;
  title: string;
  body: string;
  href: string;
  image: string;
  alt: string;
  icon: LucideIcon;
}[] = [
  {
    id: "cafe",
    label: "Cafe",
    eyebrow: "Cafe POS system",
    title: "Run Your Cafe More Efficiently",
    body: "Fast billing, modifiers, recipes, inventory and smooth counter or table service.",
    href: "/cafe-pos",
    image: "/images/home-3/cafe.jpg",
    alt: "Cafe counter with a barista working the espresso bar",
    icon: Coffee,
  },
  {
    id: "restaurant",
    label: "Restaurant",
    eyebrow: "Restaurant POS system",
    title: "Complete Restaurant Management",
    body: "Dine-in, takeaway, delivery, kitchen display (KDS) and table management.",
    href: "/restaurant-pos",
    image: "/images/home-3/restaurant.jpg",
    alt: "Plated dishes being served at a restaurant table",
    icon: UtensilsCrossed,
  },
  {
    id: "grocery",
    label: "Grocery & Supermarket",
    eyebrow: "Grocery & supermarket POS",
    title: "Streamline Your Retail Operations",
    body: "Barcode billing, weighed items, PLU, stock control and expiry (FEFO) management.",
    href: "/grocery-pos",
    image: "/images/home-3/grocery.jpg",
    alt: "Supermarket aisle stocked with grocery products",
    icon: ShoppingCart,
  },
  {
    id: "electronics",
    label: "Electronics & Wholesale",
    eyebrow: "Electronics & wholesale POS",
    title: "Track Every Item with Confidence",
    body: "IMEI / serial tracking, warranties, quotations, tier pricing and B2B credit accounts.",
    href: "/electronics-pos",
    image: "/images/home-3/electronics.jpg",
    alt: "Phones, a watch, and a laptop laid out for electronics retail",
    icon: Smartphone,
  },
  {
    id: "fashion",
    label: "Fashion & Retail",
    eyebrow: "Fashion & retail POS",
    title: "Smarter Retail for Fashion Stores",
    body: "Manage products by size, color and style, with branch stock and promotions.",
    href: "/fashion-pos",
    image: "/images/home-3/fashion.jpg",
    alt: "Clothing store with shirts, jackets, and folded apparel",
    icon: Shirt,
  },
  {
    id: "quick",
    label: "Quick Service",
    eyebrow: "Quick service POS",
    title: "Fast, Simple and High-Volume",
    body: "A speedy and reliable POS for takeaways, food courts and high-volume counters.",
    href: "/quick-service-pos",
    image: "/images/home-3/quick-service.jpg",
    alt: "Burger and fries prepared for a quick-service counter",
    icon: Store,
  },
];

const FEATURE_CARDS: { title: string; body: string; href?: string; icon: LucideIcon }[] = [
  { title: "Sales & Billing", body: "Fast, flexible and reliable checkout.", href: "/retail-pos", icon: Receipt },
  { title: "Inventory Management", body: "Real-time stock, transfers and expiry (FEFO).", href: "/inventory-management", icon: Boxes },
  { title: "Multi-Branch", body: "Manage all your branches in one place.", href: "/multi-branch-pos", icon: Store },
  { title: "Customers & Loyalty", body: "Customer profiles, offers and rewards.", href: "/loyalty-promotions", icon: Users },
  { title: "Reports & Analytics", body: "Clear insights to make better decisions.", href: "/pos-software-uae", icon: BarChart3 },
  { title: "Staff & Access Control", body: "Role-based access and activity tracking.", icon: Shield },
];

const PLAN_RANK = ["FREE", "GROWTH", "PRO_AI", "ENTERPRISE"] as const;

const PLAN_COPY: Record<(typeof PLAN_RANK)[number], { points: string[]; cta: string }> = {
  FREE: { points: ["Core POS & billing", "Basic inventory", "Reports"], cta: "Get Started" },
  GROWTH: { points: ["Full inventory management", "Customers & loyalty", "Multi-branch (limited)"], cta: "Choose Growth" },
  PRO_AI: { points: ["All Growth features", "AI insights & recommendations", "Multi-branch & advanced reports"], cta: "Choose Pro AI" },
  ENTERPRISE: { points: ["All features, fully customized", "Priority support", "Integration & on-boarding"], cta: "Contact Us" },
};

const PLAN_NAMES: Record<(typeof PLAN_RANK)[number], string> = {
  FREE: "Free",
  GROWTH: "Growth",
  PRO_AI: "Pro AI",
  ENTERPRISE: "Enterprise",
};

const FAQS = [
  {
    q: "What is AxizPOS?",
    a: "AxizPOS is a point of sale register and an admin portal. Staff sell at the till. Managers look after products, stock, customers, users, and the reports the store has recorded.",
  },
  {
    q: "Which businesses can use AxizPOS?",
    a: "The product ships with profiles for restaurants, cafés, quick service, grocery, fashion, wholesale and retail, and electronics. Each profile turns on the modules that fit that work.",
  },
  {
    q: "Does it work offline?",
    a: "The desktop register can keep selling after it has connected to the store once. Those sales sync when the connection returns. The admin portal in the browser needs a connection. Add-on modules on a till that stays offline for more than a day wait until that till syncs.",
  },
  {
    q: "Can I migrate my existing data?",
    a: "This page does not start an import. Tell us which products, customers, or stock you need to move, and the team will say what can be brought into the portal. Creating a store does not copy another system's database on its own.",
  },
  {
    q: "Can I manage multiple branches?",
    a: "Yes. The portal has a stores list and stock transfers. How many registers and branches are included depends on the published plan.",
  },
  {
    q: "Is support available in the UAE and internationally?",
    a: "Sales questions on this page go through the WhatsApp number published in the console, in English or Arabic. AxizPOS is set up for businesses selling in the UAE and the wider GCC. This page does not list an office address. If that number is not published, the form says so and does not pretend a message was sent.",
  },
];

const TYPES = ["Restaurant", "Café", "Quick Service", "Grocery", "Retail", "Wholesale", "Fashion", "Electronics"] as const;

export function Home3Page() {
  const [catalog, setCatalog] = useState<PublicCatalog>(EMPTY_CATALOG);
  const [catalogStatus, setCatalogStatus] = useState<"loading" | "ready" | "unavailable">("loading");
  const [contact, setContact] = useState<PublicWhatsApp>(EMPTY_WHATSAPP);
  const [contactStatus, setContactStatus] = useState<"loading" | "ready" | "unavailable">("loading");
  const [draft, setDraft] = useState<string | null>(null);

  useEffect(() => {
    track("view_page", { page_path: "/home-3", content_group: "home-3", locale: "en" });
  }, []);

  useEffect(() => {
    let cancelled = false;
    loadCatalog(`${apiBaseUrl}/api/v1/billing/public-catalog`).then((result) => {
      if (cancelled) return;
      setCatalog(result.catalog);
      setCatalogStatus(result.live ? "ready" : "unavailable");
    });
    fetch(`${apiBaseUrl}/api/v1/site/contact`)
      .then(async (response) => {
        if (!response.ok) throw new Error("contact");
        return parsePublicWhatsApp(await response.json());
      })
      .then((next) => {
        if (cancelled) return;
        setContact(next);
        setContactStatus("ready");
      })
      .catch(() => {
        if (cancelled) return;
        setContact(EMPTY_WHATSAPP);
        setContactStatus("unavailable");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function ask(note: string) {
    setDraft(note);
    document.getElementById("demo")?.scrollIntoView({ behavior: "smooth" });
  }

  return (
    <div className="home3">
      <a className="h3-skip" href="#h3-main">
        Skip to content
      </a>
      <Header />
      <main id="h3-main">
        <Hero />
        <Industries />
        <Features />
        <Panels />
        <Hardware onAsk={ask} />
        <Pricing catalog={catalog} status={catalogStatus} onAsk={ask} />
        <Faq />
        <Demo contact={contact} contactStatus={contactStatus} draft={draft} />
      </main>
      <SiteFooter contact={contact} />
      <WhatsAppButton contact={contact} />
    </div>
  );
}

function Header() {
  const [open, setOpen] = useState(false);
  const [stuck, setStuck] = useState(false);

  useEffect(() => {
    const onScroll = () => setStuck(window.scrollY > 4);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
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
    <header className={stuck ? "h3-nav is-stuck" : "h3-nav"} id="top">
      <a className="h3-logo" href="/home-3" aria-label="AxizPOS home">
        <img src="/brand/logo.svg" alt="" width={137} height={32} />
      </a>
      <nav id="h3-primary" className={open ? "h3-links is-open" : "h3-links"} aria-label="Primary">
        <Drop label="Product" links={PRODUCT} />
        <Drop label="Solutions" links={SOLUTIONS} />
        <Drop label="Features" links={FEATURES} />
        <a href="#pricing" onClick={() => setOpen(false)}>
          Pricing
        </a>
        <Drop label="Resources" links={RESOURCES} />
        <a className="h3-btn h3-mobile-demo" href="#demo" onClick={() => setOpen(false)}>
          Get a Demo
        </a>
      </nav>
      <div className="h3-tools">
        <Language />
        <a className="h3-btn" href="#demo">
          Get a Demo
        </a>
        <button className="h3-burger" type="button" aria-expanded={open} aria-controls="h3-primary" aria-label={open ? "Close menu" : "Open menu"} onClick={() => setOpen((value) => !value)}>
          {open ? <X size={22} /> : <Menu size={22} />}
        </button>
      </div>
    </header>
  );
}

function Drop({ label, links }: { label: string; links: { href: string; label: string }[] }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const hovered = useRef(false);
  const fine = () => window.matchMedia("(hover: hover) and (pointer: fine)").matches;

  return (
    <div
      className={open ? "h3-drop is-open" : "h3-drop"}
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
        onClick={() => {
          if (hovered.current) return;
          setOpen((value) => !value);
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape") setOpen(false);
        }}
      >
        {label}
        <ChevronDown size={16} aria-hidden="true" />
      </button>
      <ul className="h3-menu" inert={open ? undefined : true} aria-hidden={open ? undefined : true}>
        {links.map((link) => (
          <li key={link.label}>
            <a href={link.href}>{link.label}</a>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Language() {
  const [open, setOpen] = useState(false);
  return (
    <div
      className={open ? "h3-lang is-open" : "h3-lang"}
      onMouseLeave={() => {
        if (window.matchMedia("(hover: hover) and (pointer: fine)").matches) setOpen(false);
      }}
    >
      <button type="button" aria-expanded={open} aria-haspopup="true" aria-label="Language" onClick={() => setOpen((value) => !value)} onKeyDown={(event) => event.key === "Escape" && setOpen(false)}>
        <Globe size={16} aria-hidden="true" />
        EN
        <ChevronDown size={14} aria-hidden="true" />
      </button>
      <ul className="h3-menu" inert={open ? undefined : true} aria-hidden={open ? undefined : true}>
        <li>
          <span aria-current="true">English</span>
        </li>
        <li>
          <a href="/ar" hrefLang="ar">
            العربية
          </a>
        </li>
      </ul>
    </div>
  );
}

function Hero() {
  const reduce = useReducedMotion();
  return (
    <section className="h3-hero" aria-labelledby="h3-hero-title">
      <div className="h3-glow" aria-hidden="true" />
      <div className="h3-wrap h3-hero-grid">
        <div>
          <motion.p className="h3-kicker" initial={reduce ? false : { opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
            All-in-one POS solution
          </motion.p>
          <motion.h1 id="h3-hero-title" initial={reduce ? false : { opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.05 }}>
            Smart POS Software for <span>Every Business</span>
          </motion.h1>
          <motion.p className="h3-lead" initial={reduce ? false : { opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.12 }}>
            A modern, reliable and easy-to-use POS system to manage sales, inventory, customers and your entire business — for cafes, restaurants, retail, grocery, electronics and more.
          </motion.p>
          <motion.div className="h3-cta-row" initial={reduce ? false : { opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.18 }}>
            <a className="h3-btn" href="#demo">
              Get a Demo <ArrowRight size={16} aria-hidden="true" />
            </a>
            <a className="h3-btn-ghost" href="#product">
              <Play size={15} aria-hidden="true" /> Watch Overview
            </a>
          </motion.div>
          <motion.ul className="h3-caps" initial={reduce ? false : { opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.5, delay: 0.28 }}>
            <li className="h3-cap">
              <Wifi size={16} aria-hidden="true" /> Works Online & Offline
            </li>
            <li className="h3-cap">
              <Package size={16} aria-hidden="true" /> Inventory & Stock
            </li>
            <li className="h3-cap">
              <Store size={16} aria-hidden="true" /> Multi-Branch
            </li>
            <li className="h3-cap">
              <BarChart3 size={16} aria-hidden="true" /> Reports & Analytics
            </li>
          </motion.ul>
        </div>
        <motion.div className="h3-hero-visual" initial={reduce ? false : { opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, delay: 0.15 }}>
          <img
            src="/pos/terminal.png"
            alt="AxizPOS on a register with a customer display, receipt printer, phone, and barcode scanner."
            width={819}
            height={782}
            fetchPriority="high"
          />
        </motion.div>
      </div>
    </section>
  );
}

function Industries() {
  const [active, setActive] = useState("cafe");
  return (
    <section className="h3-section h3-industries" id="industries" aria-labelledby="h3-industries-title">
      <div className="h3-wrap">
        <div className="h3-center">
          <h2 id="h3-industries-title">POS Built for Your Business</h2>
          <p className="h3-sub">Specialized workflows and features for different industries — all in one powerful platform.</p>
        </div>
        <div className="h3-picks" role="tablist" aria-label="Industries">
          {INDUSTRIES.map((item) => {
            const Icon = item.icon;
            const on = active === item.id;
            return (
              <button
                key={item.id}
                type="button"
                role="tab"
                aria-selected={on}
                className={on ? "h3-pick is-on" : "h3-pick"}
                onClick={() => {
                  setActive(item.id);
                  document.getElementById(item.id)?.scrollIntoView({ behavior: "smooth", block: "center" });
                }}
              >
                <Icon size={22} aria-hidden="true" />
                <span>{item.label}</span>
              </button>
            );
          })}
        </div>
        <div className="h3-industry-grid">
          {INDUSTRIES.map((item) => (
            <article key={item.id} id={item.id} className={active === item.id ? "h3-industry is-on" : "h3-industry"}>
              <img src={item.image} alt={item.alt} width={720} height={480} loading="lazy" />
              <div className="h3-industry-copy">
                <p className="h3-kicker">{item.eyebrow}</p>
                <h3>{item.title}</h3>
                <p>{item.body}</p>
                <a className="h3-more" href={item.href}>
                  Learn More <ArrowRight size={15} aria-hidden="true" />
                </a>
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

function Features() {
  return (
    <section className="h3-section h3-features" id="features" aria-labelledby="h3-features-title">
      <div className="h3-wrap h3-feature-layout">
        <div>
          <p className="h3-kicker">Powerful features</p>
          <h2 id="h3-features-title">Everything You Need in a Modern POS</h2>
          <p className="h3-sub">A complete set of tools to run, grow and scale your business.</p>
        </div>
        <div className="h3-feature-grid">
          {FEATURE_CARDS.map((item) => {
            const Icon = item.icon;
            return (
              <article key={item.title} className="h3-feature">
                <div className="h3-feature-icon">
                  <Icon size={18} aria-hidden="true" />
                </div>
                <h3>{item.title}</h3>
                <p>{item.body}</p>
                {item.href ? (
                  <a className="h3-more" href={item.href}>
                    Learn More <ArrowRight size={14} aria-hidden="true" />
                  </a>
                ) : null}
              </article>
            );
          })}
        </div>
      </div>
    </section>
  );
}

function Panels() {
  return (
    <section className="h3-section h3-panels" id="product" aria-labelledby="h3-offline-title">
      <div className="h3-wrap h3-panel-grid">
        <article className="h3-panel">
          <div>
            <p className="h3-kicker">Offline-first POS</p>
            <h3 id="h3-offline-title">Keep Your Business Running, Always</h3>
            <p>Continue selling, even when the internet is down. AxizPOS syncs your data automatically when you're back online.</p>
            <ul className="h3-ticks">
              <li>
                <Check size={16} aria-hidden="true" /> Work fully offline
              </li>
              <li>
                <Check size={16} aria-hidden="true" /> Auto sync when online
              </li>
              <li>
                <Check size={16} aria-hidden="true" /> No data loss
              </li>
            </ul>
          </div>
          <div>
            <figure className="h3-shot">
              <img src="/pos/register.jpg" alt="AxizPOS checkout on the register, with dine-in, takeaway, and delivery." width={960} height={600} loading="lazy" />
            </figure>
            <p className="h3-shot-note">Sells offline after activation</p>
          </div>
        </article>
        <article className="h3-panel">
          <figure className="h3-shot">
            <img src="/portal/macbook.png" alt="AxizPOS dashboard on a laptop, showing revenue, units sold, and category mix." width={1200} height={750} loading="lazy" />
          </figure>
          <div>
            <p className="h3-kicker">Inventory & analytics</p>
            <h3>Real-Time Control and Insights</h3>
            <p>Track sales, stock and performance with powerful, easy-to-understand reports.</p>
            <ul className="h3-ticks">
              <li>
                <Check size={16} aria-hidden="true" /> Live sales and stock
              </li>
              <li>
                <Check size={16} aria-hidden="true" /> Product and category insights
              </li>
              <li>
                <Check size={16} aria-hidden="true" /> Export and scheduled reports
              </li>
            </ul>
          </div>
        </article>
      </div>
    </section>
  );
}

function Hardware({ onAsk }: { onAsk: (note: string) => void }) {
  const tiles: { name: string; note: string; photo?: string; icon?: LucideIcon }[] = [
    { name: "POS Terminal", note: "POS terminal", photo: "h3-hw-terminal" },
    { name: "Receipt Printer", note: "Receipt printer", photo: "h3-hw-printer" },
    { name: "Barcode Scanner", note: "Barcode scanner", photo: "h3-hw-scanner" },
    { name: "Cash Drawer", note: "Cash drawer", icon: Wallet },
    { name: "Weighing Scale", note: "Weighing scale", icon: Scale },
    { name: "Integrations", note: "Integrations", icon: Puzzle },
  ];
  return (
    <section className="h3-section h3-hardware" id="hardware" aria-labelledby="h3-hardware-title">
      <div className="h3-wrap">
        <div className="h3-center">
          <h2 id="h3-hardware-title">A Complete POS Ecosystem</h2>
          <p className="h3-sub">Works with the hardware and business tools you already use.</p>
        </div>
        <div className="h3-hw-grid">
          {tiles.map((tile) => {
            const Icon = tile.icon ?? Monitor;
            return (
              <button key={tile.name} type="button" className="h3-hw" onClick={() => onAsk(`Hardware enquiry: ${tile.note}. This page does not confirm a device model.`)}>
                {tile.photo ? <span className={`h3-hw-photo ${tile.photo}`} role="img" aria-label={tile.name} /> : (
                  <span className="h3-hw-photo h3-hw-icon" aria-hidden="true">
                    <Icon size={32} />
                  </span>
                )}
                <strong>{tile.name}</strong>
              </button>
            );
          })}
        </div>
        <p className="h3-note">
          The desktop register prints receipts, scans barcodes, and can price weighed items on the grocery profile. Ask which models are available before you buy hardware.{" "}
          <a className="h3-more" href="#demo">
            Talk to us <ArrowRight size={14} aria-hidden="true" />
          </a>
        </p>
      </div>
    </section>
  );
}

function Pricing({
  catalog,
  status,
  onAsk,
}: {
  catalog: PublicCatalog;
  status: "loading" | "ready" | "unavailable";
  onAsk: (note: string) => void;
}) {
  const live = showcasePlans(catalog);
  const country = defaultCountry(catalog);
  const cycle = catalog.cycles.find((item) => item.code === "MONTHLY") ?? catalog.cycles[0];
  return (
    <section className="h3-section h3-pricing" id="pricing" aria-labelledby="h3-pricing-title">
      <div className="h3-wrap">
        <div className="h3-center">
          <p className="h3-kicker">Simple & flexible plans</p>
          <h2 id="h3-pricing-title">Choose the Right Plan for Your Business</h2>
          <p className="h3-sub">Scalable plans designed for businesses of all sizes.</p>
        </div>
        {status === "unavailable" ? <p className="h3-price-msg">Published subscription prices are unavailable right now. Amounts stay hidden until the catalog can be loaded.</p> : null}
        <div className="h3-plans">
          {PLAN_RANK.map((code) => {
            const plan = live.find((item) => item.code === code);
            return (
              <PlanCard
                key={code}
                code={code}
                plan={plan}
                catalog={catalog}
                country={country}
                cycle={cycle}
                status={status}
                onAsk={onAsk}
              />
            );
          })}
        </div>
        <p className="h3-center">
          <a className="h3-catalog-link" href="/#pricing">
            Compare the full published catalog
          </a>
        </p>
      </div>
    </section>
  );
}

function PlanCard({
  code,
  plan,
  catalog,
  country,
  cycle,
  status,
  onAsk,
}: {
  code: (typeof PLAN_RANK)[number];
  plan: Plan | undefined;
  catalog: PublicCatalog;
  country: string | null;
  cycle: PublicCatalog["cycles"][number] | undefined;
  status: "loading" | "ready" | "unavailable";
  onAsk: (note: string) => void;
}) {
  const copy = PLAN_COPY[code];
  const popular = code === "PRO_AI";
  const name = plan?.name ?? PLAN_NAMES[code];
  let amount = "—";
  let period = "";
  if (status === "loading") {
    amount = "…";
    period = "Loading the published price";
  } else if (!plan || !cycle || status !== "ready") {
    amount = "Unavailable";
    period = "Published price unavailable";
  } else {
    const price = publishedPrice(plan, cycle, catalog, country);
    if (price.kind === "free") {
      amount = "AED 0";
      period = "No subscription charge";
    } else if (price.kind === "custom") {
      amount = "Custom";
      period = "Priced on a contract";
    } else if (price.kind === "priced" && price.amountFils !== null) {
      amount = money(price.amountFils, price.currency || "AED");
      period = `/ ${cycle.name.toLowerCase()}`;
    } else {
      amount = "Unavailable";
      period = "Published price unavailable";
    }
  }
  const enquire = code === "ENTERPRISE" || (status === "ready" && !plan);
  return (
    <article className={popular ? "h3-plan is-popular" : "h3-plan"}>
      {popular ? <span className="h3-popular">Most Popular</span> : null}
      <h3>{name}</h3>
      <p className="h3-price">{amount}</p>
      <p className="h3-period">{period}</p>
      <ul className="h3-ticks">
        {copy.points.map((point) => (
          <li key={point}>
            <Check size={16} aria-hidden="true" /> {point}
          </li>
        ))}
      </ul>
      {enquire ? (
        <button type="button" className={popular ? "h3-btn h3-btn-block" : "h3-btn-line"} onClick={() => onAsk(`${name}: custom pricing. Contact sales. This page does not create an invoice.`)}>
          {copy.cta}
        </button>
      ) : (
        <a className={popular ? "h3-btn h3-btn-block" : "h3-btn-line"} href={signupUrl} onClick={() => track("click_get_started", { page_path: "/home-3" })}>
          {copy.cta}
        </a>
      )}
    </article>
  );
}

function Faq() {
  const base = useId();
  const [open, setOpen] = useState<number | null>(null);
  return (
    <section className="h3-section h3-faq" id="faq" aria-labelledby="h3-faq-title">
      <div className="h3-wrap">
        <div className="h3-center">
          <p className="h3-kicker">FAQ</p>
          <h2 id="h3-faq-title">Frequently Asked Questions</h2>
        </div>
        <div className="h3-faq-grid">
          {FAQS.map((item, index) => {
            const expanded = open === index;
            const panelId = `${base}-panel-${index}`;
            const buttonId = `${base}-button-${index}`;
            return (
              <div key={item.q} className={expanded ? "h3-acc is-open" : "h3-acc"}>
                <h3>
                  <button id={buttonId} type="button" aria-expanded={expanded} aria-controls={panelId} onClick={() => setOpen(expanded ? null : index)}>
                    {item.q}
                    <ChevronDown className="chev" size={18} aria-hidden="true" />
                  </button>
                </h3>
                <div className="h3-acc-panel" id={panelId} role="region" aria-labelledby={buttonId}>
                  <div>
                    <p>{item.a}</p>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

function Demo({
  contact,
  contactStatus,
  draft,
}: {
  contact: PublicWhatsApp;
  contactStatus: "loading" | "ready" | "unavailable";
  draft: string | null;
}) {
  const base = useId();
  const lock = useRef(false);
  const [fields, setFields] = useState({ name: "", email: "", phone: "", type: TYPES[0] as (typeof TYPES)[number], message: "" });
  const [errors, setErrors] = useState<Partial<Record<"name" | "email" | "phone" | "message", string>>>({});
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [channelError, setChannelError] = useState<string | null>(null);
  const salesNumber = publishedWhatsapp(contact);

  useEffect(() => {
    if (!draft) return;
    setFields((current) => ({ ...current, message: draft.slice(0, 500) }));
    setSent(false);
  }, [draft]);

  function update<K extends keyof typeof fields>(key: K, value: (typeof fields)[K]) {
    setFields((current) => ({ ...current, [key]: value }));
    setErrors((current) => ({ ...current, [key]: undefined }));
    setSent(false);
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (lock.current || busy) return;
    const next: typeof errors = {};
    if (fields.name.trim().length < 2) next.name = "Enter your name.";
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(fields.email.trim())) next.email = "Enter a valid email address.";
    if (!isValidE164(fields.phone)) next.phone = "Enter a phone number we can call.";
    if (fields.message.trim().length > 500) next.message = "Keep the note under 500 characters.";
    setErrors(next);
    if (Object.keys(next).length > 0) return;
    if (!salesNumber) {
      setChannelError(salesChannelMessage(contact, contactStatus));
      return;
    }
    const text = [
      "AxizPOS — demo request",
      `Name: ${fields.name.trim()}`,
      `Email: ${fields.email.trim()}`,
      `Phone: ${fields.phone.trim()}`,
      `Business type: ${fields.type}`,
      fields.message.trim() ? `Inquiry: ${fields.message.trim()}` : "",
    ]
      .filter(Boolean)
      .join("\n");
    lock.current = true;
    setBusy(true);
    window.open(whatsappChatUrl(salesNumber, text), "_blank", "noopener,noreferrer");
    track("contact_form_submit", { business_type: fields.type });
    setChannelError(null);
    setSent(true);
    setBusy(false);
    lock.current = false;
  }

  return (
    <section className="h3-demo" id="demo" aria-labelledby="h3-demo-title">
      <div className="h3-wrap h3-demo-grid">
        <div>
          <p className="h3-kicker">Get a demo</p>
          <h2 id="h3-demo-title">See AxizPOS in Action</h2>
          <p className="h3-sub">Book a free demo and discover how AxizPOS can simplify your operations and grow your business.</p>
          <div className="h3-demo-points">
            <span>
              <Users size={16} aria-hidden="true" /> Personal Demo
            </span>
            <span>
              <Monitor size={16} aria-hidden="true" /> Explore Features
            </span>
            <span>
              <Printer size={16} aria-hidden="true" /> Talk to an Expert
            </span>
          </div>
        </div>
        <form className="h3-form" onSubmit={onSubmit} noValidate>
          <div className="h3-fields">
            <label className="h3-field" htmlFor={`${base}-name`}>
              <span>Your Name *</span>
              <input id={`${base}-name`} name="name" autoComplete="name" value={fields.name} onChange={(event) => update("name", event.target.value)} aria-invalid={errors.name ? true : undefined} />
              {errors.name ? <span className="err">{errors.name}</span> : null}
            </label>
            <label className="h3-field" htmlFor={`${base}-email`}>
              <span>Business Email *</span>
              <input id={`${base}-email`} name="email" type="email" autoComplete="email" value={fields.email} onChange={(event) => update("email", event.target.value)} aria-invalid={errors.email ? true : undefined} />
              {errors.email ? <span className="err">{errors.email}</span> : null}
            </label>
            <div className="h3-field">
              <PhoneField label="Phone Number" tone="marketing" required value={fields.phone} onChange={(phone) => update("phone", phone)} error={errors.phone} defaultCountry="AE" />
            </div>
            <label className="h3-field" htmlFor={`${base}-type`}>
              <span>Business Type *</span>
              <select id={`${base}-type`} name="type" value={fields.type} onChange={(event) => update("type", event.target.value as (typeof TYPES)[number])}>
                {TYPES.map((type) => (
                  <option key={type}>{type}</option>
                ))}
              </select>
            </label>
            <label className="h3-field h3-field-wide" htmlFor={`${base}-message`}>
              <span>Tell us about your business</span>
              <textarea id={`${base}-message`} name="message" rows={3} value={fields.message} onChange={(event) => update("message", event.target.value)} aria-invalid={errors.message ? true : undefined} />
              {errors.message ? <span className="err">{errors.message}</span> : null}
            </label>
          </div>
          {salesNumber ? (
            <p className="h3-form-note">Request a Demo opens WhatsApp with these details. Nothing is delivered until you press Send there.</p>
          ) : (
            <p className="h3-form-alert" role="alert">
              {channelError ?? salesChannelMessage(contact, contactStatus)}
            </p>
          )}
          {sent ? (
            <p className="h3-form-status" role="status">
              WhatsApp opened with your details. Press Send there so the team receives the request. Nothing is delivered until you do.
            </p>
          ) : null}
          <button className="h3-btn h3-btn-block" type="submit" disabled={busy || sent}>
            {busy ? "Opening WhatsApp…" : sent ? "WhatsApp opened" : "Request a Demo"}
          </button>
        </form>
      </div>
    </section>
  );
}

function salesChannelMessage(contact: PublicWhatsApp, contactStatus: "loading" | "ready" | "unavailable"): string {
  if (contactStatus === "loading") return "The sales WhatsApp number is still loading. Try again in a moment.";
  if (contactStatus === "unavailable") return "The sales WhatsApp number could not be loaded. Refresh the page and try again.";
  if (!contact.enabled) return "WhatsApp enquiries are turned off.";
  return "The sales WhatsApp number is missing or not a valid international number.";
}

function SiteFooter({ contact }: { contact: PublicWhatsApp }) {
  const ready = whatsappReady(contact);
  const year = new Date().getFullYear();
  return (
    <footer className="h3-footer">
      <div className="h3-wrap">
        <div className="h3-footer-grid">
          <div>
            <img src="/brand/logo-white.svg" alt="AxizPOS" width={137} height={32} />
            <p>Smart POS software for cafes, restaurants, grocery, electronics, fashion, and quick service.</p>
          </div>
          <div>
            <h2>Product</h2>
            {PRODUCT.map((link) => (
              <a key={link.label} href={link.href}>
                {link.label}
              </a>
            ))}
            <a href={portalUrl}>Sign in</a>
            <a href={signupUrl}>Get Started Free</a>
          </div>
          <div>
            <h2>Solutions</h2>
            {SOLUTIONS.map((link) => (
              <a key={link.href} href={link.href}>
                {link.label}
              </a>
            ))}
          </div>
          <div>
            <h2>Resources</h2>
            <a href="/blog">Blog</a>
            <a href="/blog">Guides</a>
            <a href="/pos-software-uae">POS software UAE</a>
            <a href="/offline-pos">Offline POS</a>
          </div>
          <div>
            <h2>Company</h2>
            <a href="#demo">Contact</a>
            <a href="/#pricing">Pricing</a>
            {ready ? (
              <a href={whatsappChatUrl(contact.number, contact.message)} target="_blank" rel="noopener noreferrer">
                WhatsApp +{whatsappDigits(contact.number)}
              </a>
            ) : (
              <p>Sales contact is published from the console.</p>
            )}
            {contact.email ? <a href={`mailto:${contact.email}`}>{contact.email}</a> : null}
          </div>
        </div>
        <div className="h3-footer-base">
          <span>© {year} AxizPOS</span>
          <div className="h3-footer-lang">
            <a href="/home-3" hrefLang="en" aria-current="page">
              EN
            </a>
            <a href="/ar" hrefLang="ar">
              AR
            </a>
          </div>
        </div>
      </div>
    </footer>
  );
}
