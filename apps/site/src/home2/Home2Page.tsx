import { Coffee, Monitor, Package, ShoppingBag, ShoppingCart, Utensils } from "lucide-react";
import { AnimatePresence, motion, useMotionValue, useReducedMotion, useScroll, useSpring, useTransform } from "framer-motion";
import { createPortal } from "react-dom";
import { lazy, memo, Suspense, useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type PointerEvent as ReactPointerEvent, type ReactNode } from "react";
import { track } from "../track";
import { SiteHeader } from "./SiteHeader";
import { ResponsiveImage } from "../responsiveImage";
import { WhatsAppButton } from "../components/WhatsAppButton";
import { apiBaseUrl } from "../env";
import { EMPTY_WHATSAPP, parsePublicWhatsApp, type PublicWhatsApp } from "../whatsapp";

const Home2Below = lazy(() => import("./Home2Below").then((mod) => ({ default: mod.Home2Below })));
const QuoteDialog = lazy(() => import("../components/QuoteDialog").then((mod) => ({ default: mod.QuoteDialog })));

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

  const book = () => {
    track("click_book_demo", { page_path: "/" });
    ask("Book a demo. This page does not create an invoice.");
  };
  const below = (
    <Suspense fallback={null}>
      <Home2Below onAsk={ask} />
    </Suspense>
  );
  const dialog = quote !== null ? (
    <Suspense fallback={null}>
      <QuoteDialog contact={contact} contactStatus={contactStatus} draft={quote} onClose={() => setQuote(null)} />
    </Suspense>
  ) : null;
  const headerSlot = typeof document !== "undefined" ? document.getElementById("h2-header-slot") : null;
  if (headerSlot && headerSlot.dataset.ready !== "1") {
    headerSlot.replaceChildren();
    headerSlot.dataset.ready = "1";
    const rotator = document.getElementById("h2-rotator-slot");
    if (rotator) rotator.replaceChildren();
  }
  if (headerSlot) {
    const portal = (id: string, node: ReactNode) => {
      const target = document.getElementById(id);
      return target ? createPortal(node, target) : null;
    };
    return (
      <>
        {portal("h2-header-slot", <SiteHeader atHome onDemo={book} />)}
        {portal("h2-rotator-slot", <IndustryRotator />)}
        {portal("h2-pins-slot", <Pins />)}
        {portal("h2-devices-slot", <Devices />)}
        {portal("h2-below-slot", below)}
        {dialog}
        <WhatsAppButton contact={contact} />
      </>
    );
  }

  return (
    <>
    <div className="home2">
      <a className="h2-skip" href="#h2-main">
        Skip to content
      </a>
      <SiteHeader atHome onDemo={book} />
      <main id="h2-main">
        <Hero />
        {below}
      </main>
      {dialog}
    </div>
    <WhatsAppButton contact={contact} />
    </>
  );
}

const CityArt = memo(function CityArt() {
  const slotRef = useRef<HTMLDivElement>(null);
  const useStatic = useRef(typeof document !== "undefined" && document.getElementById("h2-city-picture") !== null).current;

  useLayoutEffect(() => {
    const slot = slotRef.current;
    const picture = document.getElementById("h2-city-picture");
    if (useStatic && slot && picture && picture.parentElement !== slot) slot.prepend(picture);
    document.getElementById("h2-static-hero")?.remove();
    return () => {
      const park = document.getElementById("h2-picture-park");
      if (picture && park && picture.parentElement !== park) park.appendChild(picture);
    };
  }, [useStatic]);

  return (
    <div className="h2-city">
      {useStatic ? <div ref={slotRef} /> : <CityPicture />}
      <Pins />
    </div>
  );
});

function Pins() {
  return (
    <>
      <Pin className="pin-cafe" label="Cafe"><Coffee size={14} /></Pin>
      <Pin className="pin-restaurant" label="Restaurant"><Utensils size={14} /></Pin>
      <Pin className="pin-retail" label="Retail"><ShoppingBag size={14} /></Pin>
      <Pin className="pin-market" label="Supermarket"><ShoppingCart size={14} /></Pin>
      <Pin className="pin-electronics" label="Electronics"><Monitor size={14} /></Pin>
      <Pin className="pin-wholesale" label="Wholesale"><Package size={14} /></Pin>
    </>
  );
}

function CityPicture() {
  return (
    <ResponsiveImage
      src="/images/home-2/isometric-city.png"
      alt="Cafe, restaurant, retail, supermarket, electronics and wholesale storefronts"
      width={1691}
      height={691}
      sizes="(max-width: 860px) calc(100vw - 48px), min(1400px, calc(100vw - 48px))"
      loading="eager"
      fetchPriority="high"
    />
  );
}

function Hero() {
  const reduce = useReducedMotion();
  const painted = useRef(typeof document !== "undefined" && document.getElementById("h2-static-hero") !== null).current;
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
        <motion.p className="h2-eyebrow" initial={reduce || painted ? false : { opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45 }}>
          <span />
          Smart POS for every business
          <span />
        </motion.p>
        <motion.h1 initial={reduce || painted ? false : { y: 16 }} animate={{ y: 0 }} transition={{ duration: 0.55, delay: 0.08 }}>
          <span className="h2-h1-lines">
            Run <span className="h2-h1-your">your</span>
            <br />
            business <span className="h2-h1-break">better</span>
          </span>
          <span className="h2-h1-brand">with AxizPOS</span>
        </motion.h1>
        <IndustryRotator />
        <motion.a className="h2-btn" href="/explore" initial={reduce || painted ? false : { opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, delay: 0.24 }}>
          Explore AxizPOS <span aria-hidden="true">→</span>
        </motion.a>
      </div>
      <motion.div className="h2-stage" ref={stage} style={{ y: lift }}>
        <motion.div style={reduce ? undefined : { x: cityX, y: cityY }}>
          <CityArt />
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
      <ResponsiveImage
        src="/images/home-2/checkout-suite.png"
        alt="AxizPOS checkout on a terminal, receipt printer and phone"
        width={1752}
        height={897}
        sizes="(max-width: 860px) min(100%, 420px), min(680px, 50vw)"
        loading="lazy"
        fetchPriority="low"
      />
    </motion.div>
  );
}
