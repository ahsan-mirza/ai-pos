import { BarChart3, BookOpen, Boxes, Globe, Layers, Monitor, Notebook, Percent, Receipt, ScanBarcode, ShieldCheck, Shirt, ShoppingBag, ShoppingCart, Tag, Truck, Users, Utensils, Warehouse, type LucideIcon } from "lucide-react";
import { motion, useInView, useReducedMotion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { track } from "../track";
import { ResponsiveImage } from "../responsiveImage";
import { IndustryBanner } from "./IndustryBanner";
import { Home2Pricing } from "./Home2Pricing";

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
                  <motion.div
                    className={phone.className}
                    initial={reduce ? false : hidden}
                    animate={shown ? { opacity: 1, x: 0, y: 0, scale: 1 } : hidden}
                    transition={{ duration: 0.85, delay: shown && !reduce ? phone.delay : 0, ease: phoneEase }}
                  >
                    <ResponsiveImage
                      src={phone.src}
                      alt={phone.alt}
                      width={phone.width}
                      height={phone.height}
                      sizes="(max-width: 767px) min(420px, 78vw), 280px"
                      loading="lazy"
                    />
                  </motion.div>
                </div>
                <div className="h2-phone-copy">
                  <div className="h2-phone-title">
                    <Icon size={26} strokeWidth={1.75} aria-hidden="true" />
                    <h3>{phone.title}</h3>
                  </div>
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
        <ResponsiveImage
          src={item.image}
          alt={item.imageAlt}
          width={1280}
          height={720}
          sizes="(max-width: 860px) 100vw, 50vw"
          loading="lazy"
          style={item.imagePosition ? { objectPosition: item.imagePosition } : undefined}
        />
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

export function Home2Below({ onAsk }: { onAsk: (note: string) => void }) {
  return (
    <>
      <Showcase />
      <Solutions />
      <Home2Pricing onContact={onAsk} />
      <IndustryBanner />
      <FinalCta onDemo={() => { track("click_book_demo", { page_path: "/" }); onAsk("Book a demo. This page does not create an invoice."); }} />
      <Footer onDemo={onAsk} />
    </>
  );
}
