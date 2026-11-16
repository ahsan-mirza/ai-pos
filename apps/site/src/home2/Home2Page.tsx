import { BarChart3, BookOpen, Boxes, Coffee, Globe, Layers, Monitor, Notebook, Package, Percent, Receipt, ScanBarcode, ShieldCheck, Shirt, ShoppingBag, ShoppingCart, Tag, Truck, Users, Utensils, Warehouse, type LucideIcon } from "lucide-react";
import { AnimatePresence, motion, useInView, useMotionValue, useReducedMotion, useScroll, useSpring, useTransform } from "framer-motion";
import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type PointerEvent as ReactPointerEvent, type ReactNode } from "react";
import { track } from "../track";
import { IndustryBanner } from "./IndustryBanner";
import { SiteHeader } from "./SiteHeader";
import { Home2Pricing } from "./Home2Pricing";
import { QuoteDialog } from "../components/QuoteDialog";
import { WhatsAppButton } from "../components/WhatsAppButton";
import { apiBaseUrl } from "../env";
import { EMPTY_WHATSAPP, parsePublicWhatsApp, type PublicWhatsApp } from "../whatsapp";

const industries = [
  {
    id: "cafe",
    label: "Cafe",
    headline: "Cafe POS Software",
    description:
      "Manage cafe billing, menu items, recipes, ingredients, inventory and daily cafe operations with one intelligent POS platform.",
    keywords: ["Cafe POS UAE", "Coffee Shop POS", "Cafe Billing Software", "Cafe Inventory Management"],
  },
  {
    id: "restaurant",
    label: "Restaurant",
    headline: "Restaurant POS Software",
    description:
      "Manage restaurant orders, tables, kitchen workflows, menu modifiers, billing and inventory from one connected platform.",
    keywords: ["Restaurant POS UAE", "Restaurant Billing System", "Table Management POS", "Kitchen Display System"],
  },
  {
    id: "grocery",
    label: "Supermarket",
    headline: "Supermarket POS Software",
    description:
      "Manage grocery sales, barcode billing, weighed products, stock, expiry-first inventory and supermarket operations.",
    keywords: ["Supermarket POS UAE", "Grocery POS Software", "Barcode Billing System", "Grocery Inventory Management"],
  },
  {
    id: "electronics",
    label: "Electronics",
    headline: "Electronics & Wholesale POS",
    description:
      "Manage electronics sales, IMEI and serial tracking, warranties, quotations, tier pricing and B2B customer accounts.",
    keywords: ["Electronics POS UAE", "Wholesale POS Software", "IMEI Tracking POS", "B2B Billing Software"],
  },
  {
    id: "fashion",
    label: "Fashion",
    headline: "Fashion & Retail POS",
    description:
      "Manage retail sales, product variants, size and colour matrices, inventory, customers and store operations.",
    keywords: ["Retail POS UAE", "Fashion POS Software", "Clothing Store POS", "Retail Inventory Management"],
  },
  {
    id: "quick-service",
    label: "Quick Service",
    headline: "Quick Service POS Software",
    description:
      "Streamline fast billing, order processing, menu management and inventory for quick-service businesses.",
    keywords: ["Quick Service POS", "Fast Food POS", "Food Billing Software", "QSR POS System"],
  },
] as const;

const INDUSTRY_MS = 4000;

export function Home2Page() {
  const [quote, setQuote] = useState<string | null>(null);
  const [contact, setContact] = useState<PublicWhatsApp>(EMPTY_WHATSAPP);
  const [contactStatus, setContactStatus] = useState<"loading" | "ready" | "unavailable">("loading");
  const ask = (note: string) => setQuote(note);

  useEffect(() => {
    track("view_page", { page_path: "/", content_group: "home", locale: "en" });
  }, []);

  useEffect(() => {
    let cancelled = false;
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

  return (
    <>
    <div className="home2">
      <a className="h2-skip" href="#h2-main">
        Skip to content
      </a>
      <SiteHeader atHome onDemo={() => { track("click_book_demo", { page_path: "/" }); ask("Book a demo. This page does not create an invoice."); }} />
      <main id="h2-main">
        <Hero />
        <Showcase />
        <Solutions />
        <Home2Pricing onContact={(note) => ask(note)} />
        <IndustryBanner />
        <FinalCta onDemo={() => { track("click_book_demo", { page_path: "/" }); ask("Book a demo. This page does not create an invoice."); }} />
      </main>
      <Footer onDemo={(note) => ask(note)} />
      {quote !== null ? <QuoteDialog contact={contact} contactStatus={contactStatus} draft={quote} onClose={() => setQuote(null)} /> : null}
    </div>
    <WhatsAppButton contact={contact} />
    </>
  );
}

function Hero() {
  const reduce = useReducedMotion();
  const stage = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: stage, offset: ["start start", "end start"] });
  const lift = useTransform(scrollYProgress, [0, 1], [0, reduce ? 0 : 36]);
  const mx = useMotionValue(0);
  const my = useMotionValue(0);
  const px = useSpring(mx, { stiffness: 80, damping: 20 });
  const py = useSpring(my, { stiffness: 80, damping: 20 });
  const cityX = useTransform(px, [-0.5, 0.5], [8, -8]);
  const cityY = useTransform(py, [-0.5, 0.5], [5, -5]);

  function onPointer(event: ReactPointerEvent<HTMLElement>) {
    if (reduce || window.innerWidth < 1024) return;
    const box = event.currentTarget.getBoundingClientRect();
    mx.set((event.clientX - box.left) / box.width - 0.5);
    my.set((event.clientY - box.top) / box.height - 0.5);
  }

  return (
    <section className="h2-hero" onPointerMove={onPointer}>
      <div className="h2-hero-copy">
        <motion.p className="h2-eyebrow" initial={reduce ? false : { opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45 }}>
          <span />
          Smart POS for every business
          <span />
        </motion.p>
        <motion.h1 initial={reduce ? false : { y: 16 }} animate={{ y: 0 }} transition={{ duration: 0.55, delay: 0.08 }}>
          <span className="h2-h1-lines">
            Run your
            <br />
            business better
          </span>
          <span className="h2-h1-brand">with AxizPOS</span>
        </motion.h1>
        <IndustryRotator />
        <motion.a className="h2-btn" href="#platform" initial={reduce ? false : { opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, delay: 0.24 }}>
          Explore AxizPOS <span aria-hidden="true">→</span>
        </motion.a>
      </div>
      <motion.div className="h2-stage" ref={stage} style={{ y: lift }}>
        <motion.div className="h2-city" style={reduce ? undefined : { x: cityX, y: cityY }} initial={reduce ? false : { opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.7 }}>
          <img src="/images/home-2/isometric-city.png" alt="Cafe, restaurant, retail, supermarket, electronics and wholesale storefronts" width="1691" height="691" />
          <Pin className="pin-cafe" label="Cafe"><Coffee size={14} /></Pin>
          <Pin className="pin-restaurant" label="Restaurant"><Utensils size={14} /></Pin>
          <Pin className="pin-retail" label="Retail"><ShoppingBag size={14} /></Pin>
          <Pin className="pin-market" label="Supermarket"><ShoppingCart size={14} /></Pin>
          <Pin className="pin-electronics" label="Electronics"><Monitor size={14} /></Pin>
          <Pin className="pin-wholesale" label="Wholesale"><Package size={14} /></Pin>
        </motion.div>
        <Devices />
      </motion.div>
    </section>
  );
}

function IndustryRotator() {
  const reduce = useReducedMotion();
  const [active, setActive] = useState(0);
  const [paused, setPaused] = useState(false);
  const [height, setHeight] = useState<number | "auto">("auto");
  const [smoothHeight, setSmoothHeight] = useState(false);
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  const viewRef = useRef<HTMLDivElement>(null);
  const heightRef = useRef(height);
  const measured = useRef(false);
  const holdResize = useRef(0);
  heightRef.current = height;
  const item = industries[active] as (typeof industries)[number];

  useLayoutEffect(() => {
    const node = document.getElementById(`h2-industry-${item.id}`);
    if (!node) return;
    const next = Math.ceil(node.offsetHeight);
    holdResize.current = performance.now() + 500;
    if (!measured.current) {
      measured.current = true;
      setSmoothHeight(false);
      setHeight(next);
      return;
    }
    setSmoothHeight(!reduce);
    setHeight(next);
  }, [item.id, reduce]);

  useEffect(() => {
    const node = document.getElementById(`h2-industry-${item.id}`);
    if (!node) return;
    const observer = new ResizeObserver(() => {
      if (performance.now() < holdResize.current) return;
      const next = Math.ceil(node.offsetHeight);
      if (next === heightRef.current) return;
      setSmoothHeight(false);
      setHeight(next);
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [item.id]);

  useEffect(() => {
    if (reduce || paused) return;
    const id = window.setInterval(() => {
      setActive((current) => (current + 1) % industries.length);
    }, INDUSTRY_MS);
    return () => window.clearInterval(id);
  }, [reduce, paused, active]);

  function choose(index: number, focus: boolean) {
    setActive(index);
    if (focus) tabs.current[index]?.focus();
  }

  function onTabsKey(event: ReactKeyboardEvent<HTMLDivElement>) {
    const last = industries.length - 1;
    if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      event.preventDefault();
      choose((active + 1) % industries.length, true);
    } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      event.preventDefault();
      choose((active - 1 + industries.length) % industries.length, true);
    } else if (event.key === "Home") {
      event.preventDefault();
      choose(0, true);
    } else if (event.key === "End") {
      event.preventDefault();
      choose(last, true);
    }
  }

  return (
    <div
      className="h2-rotator"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node)) setPaused(false);
      }}
    >
      <p className="h2-sr">
        {reduce
          ? "Choose a business type to read its description."
          : "Business examples change every few seconds. Hover or choose a type to pause."}
      </p>
      <motion.div
        ref={viewRef}
        className="h2-rotator-view"
        initial={false}
        animate={{ height }}
        transition={{ height: { duration: reduce || !smoothHeight ? 0 : 0.45, ease: "easeInOut" } }}
      >
        <AnimatePresence initial={false} mode="popLayout">
          <motion.article
            key={item.id}
            id={`h2-industry-${item.id}`}
            className="h2-slide"
            role="tabpanel"
            aria-labelledby={`h2-tab-${item.id}`}
            layout
            initial={reduce ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduce ? undefined : { opacity: 0, y: -8 }}
            transition={{ duration: reduce ? 0 : 0.45, ease: "easeInOut" }}
          >
            <h2>{item.headline}</h2>
            <p>{item.description}</p>
            <ul>
              {item.keywords.map((keyword) => (
                <li key={keyword}>{keyword}</li>
              ))}
            </ul>
          </motion.article>
        </AnimatePresence>
      </motion.div>
      <div className="h2-tabs" role="tablist" aria-label="Business types" onKeyDown={onTabsKey}>
        {industries.map((item, index) => (
          <button
            key={item.id}
            id={`h2-tab-${item.id}`}
            ref={(node) => {
              tabs.current[index] = node;
            }}
            type="button"
            role="tab"
            aria-selected={index === active}
            aria-controls={`h2-industry-${item.id}`}
            tabIndex={index === active ? 0 : -1}
            onClick={() => choose(index, false)}
          >
            {item.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function Pin({ className, label, children }: { className: string; label: string; children: ReactNode }) {
  return (
    <span className={`h2-pin ${className}`}>
      <span className="h2-pin-mark" aria-hidden="true">{children}</span>
      <span className="h2-sr">{label}</span>
    </span>
  );
}

function Devices() {
  const reduce = useReducedMotion();
  return (
    <motion.div className="h2-devices" initial={reduce ? false : { opacity: 0, y: 36 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, delay: 0.2 }}>
      <img src="/images/home-2/checkout-suite.png" alt="AxizPOS checkout on a terminal, receipt printer and phone" width="1752" height="897" />
    </motion.div>
  );
}

const showcasePhones = [
  {
    key: "sell",
    className: "sell-mobile",
    src: "/images/home-2/phones/new-sale.png",
    width: 873,
    height: 1448,
    alt: "New Sale screen with product photos, quantities and a payment button",
    title: "Sell",
    text: "Fast and reliable billing at the counter.",
    icon: ShoppingCart,
    fromX: -100,
    fromY: 0,
    delay: 0,
  },
  {
    key: "manage",
    className: "inventory-mobile",
    src: "/images/home-2/phones/inventory.png",
    width: 825,
    height: 1527,
    alt: "Inventory screen with product search, names, SKUs and stock quantities",
    title: "Manage",
    text: "Control products, inventory and customers.",
    icon: Layers,
    fromX: 0,
    fromY: 35,
    delay: 0.15,
  },
  {
    key: "grow",
    className: "analytics-mobile",
    src: "/images/home-2/phones/analytics.png",
    width: 1006,
    height: 1527,
    alt: "Analytics screen with total sales, an orange chart and sales by category",
    title: "Grow",
    text: "Understand performance and make better decisions.",
    icon: BarChart3,
    fromX: 100,
    fromY: 0,
    delay: 0.3,
  },
] as const;

const phoneEase = [0.22, 1, 0.36, 1] as const;

function useMaxWidth(px: number) {
  const query = `(max-width: ${px}px)`;
  const [matches, setMatches] = useState(() => typeof window !== "undefined" && window.matchMedia(query).matches);
  useEffect(() => {
    const media = window.matchMedia(query);
    const apply = () => setMatches(media.matches);
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [query]);
  return matches;
}

function Showcase() {
  const reduce = useReducedMotion();
  const narrow = useMaxWidth(767);
  const stageRef = useRef<HTMLElement>(null);
  const inView = useInView(stageRef, { once: true, amount: 0.22 });
  const shown = Boolean(reduce) || inView;
  return (
    <section className="h2-showcase" id="platform" ref={stageRef}>
      <motion.h2 initial={reduce ? false : { opacity: 0, y: 16 }} animate={shown ? { opacity: 1, y: 0 } : undefined} transition={{ duration: 0.5, ease: phoneEase }}>
        One platform. Every part of your business.
      </motion.h2>
      <motion.p className="h2-showcase-lead" initial={reduce ? false : { opacity: 0, y: 12 }} animate={shown ? { opacity: 1, y: 0 } : undefined} transition={{ duration: 0.5, delay: shown && !reduce ? 0.08 : 0, ease: phoneEase }}>
        Sell, manage and grow your business from the counter, office or anywhere on the go.
      </motion.p>
      <div className="h2-phone-row">
        {showcasePhones.map((phone, index) => {
          const Icon = phone.icon;
          const fromX = narrow ? phone.fromX * 0.4 : phone.fromX;
          const fromY = narrow ? Math.round(phone.fromY * 0.5) : phone.fromY;
          const hidden = { opacity: 0, x: fromX, y: fromY, scale: 0.96 };
          return (
            <span key={phone.key} className="h2-phone-slot">
              {index > 0 ? <span className="h2-phone-rule" aria-hidden="true" /> : null}
              <article className="h2-phone-card">
                <div className="h2-phone-frame">
                  <motion.img
                    className={phone.className}
                    src={phone.src}
                    alt={phone.alt}
                    width={phone.width}
                    height={phone.height}
                    loading="lazy"
                    initial={reduce ? false : hidden}
                    animate={shown ? { opacity: 1, x: 0, y: 0, scale: 1 } : hidden}
                    transition={{ duration: 0.85, delay: shown && !reduce ? phone.delay : 0, ease: phoneEase }}
                  />
                </div>
                <div className="h2-phone-copy">
                  <Icon size={26} strokeWidth={1.75} aria-hidden="true" />
                  <h3>{phone.title}</h3>
                  <p>{phone.text}</p>
                </div>
              </article>
            </span>
          );
        })}
      </div>
    </section>
  );
}

type SolutionFeature = { icon: LucideIcon; label: string };
type Solution = {
  id: string;
  eyebrow: string;
  title: string;
  text: string;
  href: string;
  image: string;
  imageAlt: string;
  imageFit: "cover" | "contain";
  imagePosition?: string;
  imageOnLeft: boolean;
  features: SolutionFeature[];
};

const solutions: Solution[] = [
  {
    id: "cafe",
    eyebrow: "Café POS",
    title: "A Better Way to Run Your Café",
    text: "Manage counter sales, modifiers, recipes, ingredients and daily cafe operations.",
    href: "/cafe-pos",
    image: "/images/home-2/cafe.png",
    imageAlt: "Cafe counter with a coffee grinder, AxizPOS receipt printer, sales terminal and branded cup",
    imageFit: "cover",
    imagePosition: "center",
    imageOnLeft: false,
    features: [
      { icon: Receipt, label: "Fast Billing" },
      { icon: BookOpen, label: "Recipes & Ingredients" },
      { icon: Utensils, label: "Table Service" },
    ],
  },
  {
    id: "restaurant",
    eyebrow: "Restaurant POS",
    title: "Streamline Your Restaurant Operations",
    text: "Manage dine-in, takeaway, delivery, kitchen orders and inventory in one place.",
    href: "/restaurant-pos",
    image: "/images/home-2/restaurant.png",
    imageAlt: "Restaurant counter with an AxizPOS terminal, receipt printer and table marker",
    imageFit: "cover",
    imagePosition: "center",
    imageOnLeft: true,
    features: [
      { icon: ShoppingBag, label: "Dine-in & Takeaway" },
      { icon: Monitor, label: "Kitchen Display (KDS)" },
      { icon: Truck, label: "Delivery Management" },
    ],
  },
  {
    id: "supermarket",
    eyebrow: "Supermarket POS",
    title: "Run Your Supermarket More Efficiently",
    text: "Manage sales, inventory, barcodes, promotions and expiry (FEFO) with ease.",
    href: "/grocery-pos",
    image: "/images/home-2/supermarket.png",
    imageAlt: "Supermarket checkout with an AxizPOS terminal, barcode scanner, receipt printer and grocery basket",
    imageFit: "cover",
    imagePosition: "center",
    imageOnLeft: false,
    features: [
      { icon: ScanBarcode, label: "Barcode Scanning" },
      { icon: Boxes, label: "Inventory & Stock" },
      { icon: Percent, label: "Promotions & Discounts" },
    ],
  },
  {
    id: "electronics",
    eyebrow: "Electronics POS",
    title: "Track Every Product and Transaction",
    text: "IMEI and serial tracking, warranties, quotations, tier pricing and B2B credit accounts.",
    href: "/electronics-pos",
    image: "/images/home-2/electronics.png",
    imageAlt: "Electronics counter with an AxizPOS terminal, barcode scanner, receipt printer and boxed devices",
    imageFit: "cover",
    imagePosition: "center",
    imageOnLeft: true,
    features: [
      { icon: ScanBarcode, label: "IMEI / Serial Tracking" },
      { icon: ShieldCheck, label: "Warranties" },
      { icon: Layers, label: "B2B Pricing" },
    ],
  },
  {
    id: "fashion",
    eyebrow: "Fashion POS",
    title: "Simplify Your Fashion Retail Business",
    text: "Manage products by size, color and variant, track inventory and run promotions effortlessly.",
    href: "/fashion-pos",
    image: "/images/home-2/fashion.png",
    imageAlt: "Fashion counter with an AxizPOS terminal, barcode scanner, receipt printer and shopping bags",
    imageFit: "cover",
    imagePosition: "center",
    imageOnLeft: false,
    features: [
      { icon: Shirt, label: "Variants (Size/Color)" },
      { icon: Tag, label: "Promotions & Offers" },
      { icon: Boxes, label: "Inventory Management" },
    ],
  },
  {
    id: "wholesale",
    eyebrow: "Wholesale POS",
    title: "Power Your Wholesale Distribution",
    text: "Manage bulk sales, credit accounts, price lists and inventory across multiple locations.",
    href: "/wholesale-pos",
    image: "/images/home-2/wholesale.png",
    imageAlt: "Wholesale counter with an AxizPOS terminal, barcode scanner, receipt printer and warehouse stock",
    imageFit: "cover",
    imagePosition: "center",
    imageOnLeft: true,
    features: [
      { icon: Users, label: "B2B Customers" },
      { icon: Notebook, label: "Credit Ledger" },
      { icon: Warehouse, label: "Bulk Pricing" },
    ],
  },
];

function Solutions() {
  return (
    <section className="h2-solutions" id="solutions" aria-label="Business solutions">
      {solutions.map((item) => (
        <SolutionRow key={item.id} item={item} />
      ))}
    </section>
  );
}

function SolutionRow({ item }: { item: Solution }) {
  const reduce = useReducedMotion();
  const contentFrom = item.imageOnLeft ? 40 : -40;
  const imageFrom = item.imageOnLeft ? -40 : 40;
  const enter = { duration: 0.75, ease: "easeOut" as const };
  return (
    <article id={item.id === "wholesale" ? "retail-wholesale-pos" : `${item.id}-pos`} className={item.imageOnLeft ? "h2-solution is-flip" : "h2-solution"}>
      <motion.div
        className="h2-solution-copy"
        initial={reduce ? false : { opacity: 0, x: contentFrom }}
        whileInView={{ opacity: 1, x: 0 }}
        viewport={{ once: true, amount: 0.18 }}
        transition={enter}
      >
        <p className="h2-solution-kicker">{item.eyebrow}</p>
        <h2>{item.title}</h2>
        <p>{item.text}</p>
        <ul>
          {item.features.map((feature, index) => {
            const Icon = feature.icon;
            return (
              <motion.li
                key={feature.label}
                initial={reduce ? false : { opacity: 0, y: 12 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, amount: 0.18 }}
                transition={{ duration: 0.7, ease: "easeOut", delay: 0.16 + index * 0.08 }}
              >
                <Icon size={20} strokeWidth={1.75} aria-hidden="true" />
                {feature.label}
              </motion.li>
            );
          })}
        </ul>
        <motion.a
          className="h2-solution-link"
          href={item.href}
          aria-label={`Learn more about ${item.eyebrow}`}
          onClick={() => track("click_solution", { solution: item.id })}
          initial={reduce ? false : { opacity: 0, y: 10 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.18 }}
          transition={{ duration: 0.7, ease: "easeOut", delay: 0.44 }}
        >
          Learn More <span aria-hidden="true">→</span>
        </motion.a>
      </motion.div>
      <motion.div
        className={`h2-solution-media is-${item.imageFit}`}
        initial={reduce ? false : { opacity: 0, x: imageFrom, scale: 0.97 }}
        whileInView={{ opacity: 1, x: 0, scale: 1 }}
        viewport={{ once: true, amount: 0.18 }}
        transition={enter}
      >
        <img src={item.image} alt={item.imageAlt} width={1280} height={720} loading="lazy" style={item.imagePosition ? { objectPosition: item.imagePosition } : undefined} />
      </motion.div>
    </article>
  );
}

function FinalCta({ onDemo }: { onDemo: () => void }) {
  const reduce = useReducedMotion();
  const viewport = { once: true, amount: 0.6 } as const;
  const rise = { duration: 0.7, ease: "easeOut" as const };
  return (
    <section className="h2-cta" aria-labelledby="h2-cta-title">
      <motion.svg
        className="h2-cta-flare"
        viewBox="0 0 720 125"
        preserveAspectRatio="xMinYMid meet"
        aria-hidden="true"
        initial={reduce ? false : { opacity: 0 }}
        whileInView={{ opacity: 1 }}
        viewport={viewport}
        transition={{ duration: 0.8, ease: "easeOut" }}
      >
        <defs>
          <linearGradient id="h2CtaFlare" x1="0" y1="1" x2="1" y2="0">
            <stop offset="0%" stopColor="#ff9a4a" stopOpacity="0.95" />
            <stop offset="46%" stopColor="#f26a21" stopOpacity="0.5" />
            <stop offset="100%" stopColor="#f26a21" stopOpacity="0" />
          </linearGradient>
          <filter id="h2CtaBlur" x="-15%" y="-90%" width="140%" height="280%">
            <feGaussianBlur stdDeviation="4.5" />
          </filter>
        </defs>
        <path d="M-30 132 C 36 128, 92 86, 176 52 C 268 14, 372 2, 560 28" fill="none" stroke="url(#h2CtaFlare)" strokeWidth="34" strokeLinecap="round" filter="url(#h2CtaBlur)" />
        <path d="M-30 128 C 36 124, 92 82, 176 48 C 268 10, 372 -2, 560 24" fill="none" stroke="#ffe3c8" strokeWidth="1.75" strokeLinecap="round" opacity="0.9" />
      </motion.svg>
      <motion.div className="h2-cta-ambient" aria-hidden="true" initial={reduce ? false : { opacity: 0 }} whileInView={{ opacity: 1 }} viewport={viewport} transition={{ duration: 0.9, ease: "easeOut" }} />
      <div className="h2-cta-row">
        <motion.div className="h2-cta-copy" initial={reduce ? false : { opacity: 0, y: 12 }} whileInView={{ opacity: 1, y: 0 }} viewport={viewport} transition={rise}>
          <h2 id="h2-cta-title">Ready to Simplify Your Business?</h2>
          <p>Book a free demo and discover how AxizPOS can help you run, manage and grow your business.</p>
        </motion.div>
        <motion.div className="h2-cta-actions" initial={reduce ? false : { opacity: 0, y: 12 }} whileInView={{ opacity: 1, y: 0 }} viewport={viewport} transition={{ ...rise, delay: reduce ? 0 : 0.14 }}>
          <button className="h2-btn" type="button" onClick={onDemo}>
            Book a Demo <span aria-hidden="true">→</span>
          </button>
          <a className="h2-btn h2-btn-ghost" href="#pricing" onClick={() => track("click_explore_plans", { page_path: "/" })}>
            Explore Plans
          </a>
        </motion.div>
      </div>
    </section>
  );
}

function Footer({ onDemo }: { onDemo: (note: string) => void }) {
  return (
    <footer className="h2-foot">
      <div>
        <img src="/brand/logo.svg" alt="AxizPOS" width="120" height="28" />
        <p>All-in-one POS software for cafes, restaurants, retail, grocery, electronics and wholesale.</p>
      </div>
      <nav aria-label="Product">
        <strong>Product</strong>
        <a href="#platform">Overview</a>
        <a href="#platform">Features</a>
        <a href="#pricing">Pricing</a>
      </nav>
      <nav aria-label="Solutions">
        <strong>Solutions</strong>
        <a href="/cafe-pos">Café</a>
        <a href="/restaurant-pos">Restaurant</a>
        <a href="/grocery-pos">Supermarket</a>
        <a href="/electronics-pos">Electronics</a>
        <a href="/fashion-pos">Fashion</a>
        <a href="/wholesale-pos">Retail & Wholesale</a>
      </nav>
      <nav aria-label="Resources">
        <strong>Resources</strong>
        <a href="/blog">Blog</a>
        <a href="/blog">Guides</a>
        <button type="button" onClick={() => onDemo("Help Center. This page does not create an invoice.")}>Help Center</button>
      </nav>
      <nav aria-label="Company">
        <strong>Company</strong>
        <a href="/pos-software-uae">About Us</a>
        <button type="button" onClick={() => onDemo("Contact. This page does not create an invoice.")}>Contact</button>
        <button type="button" onClick={() => onDemo("Careers. This page does not create an invoice.")}>Careers</button>
      </nav>
      <div className="h2-foot-end">
        <button type="button" onClick={() => onDemo("Contact. This page does not create an invoice.")}>
          <BookOpen size={16} /> Contact
        </button>
        <a href="/ar">
          <Globe size={16} /> العربية
        </a>
        <small>© {new Date().getFullYear()} AxizPOS</small>
      </div>
    </footer>
  );
}
