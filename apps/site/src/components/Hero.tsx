import { AnimatePresence, motion, useReducedMotion, type Variants } from "framer-motion";
import { useEffect, useState } from "react";
import { portalUrl, signupUrl } from "../env";
import { AIAnimatedBackground } from "./AIAnimatedBackground";
import { HeroAsk } from "./HeroAsk";
import { Mark } from "./icons";

const POINTS = ["Ask in English or Arabic", "Verified store data", "Real-time sync"];

const BUSINESSES = ["Restaurants", "Cafés", "Retail", "Wholesale", "Fashion", "Electronics"] as const;

const TAGLINES = [
  { lead: "Ask the store.", accent: "Sell from the same till." },
  { lead: "Real-time inventory.", accent: "Zero guesswork. Absolute control." },
  { lead: "Your entire business,", accent: "Answered in seconds." },
  { lead: "From register to report,", accent: "Powered by enterprise AI." },
] as const;

const containerVariants: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.15 } },
};

const itemVariants: Variants = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.6, ease: [0.22, 1, 0.36, 1] } },
};

function RotatingBusiness({ reduce }: { reduce: boolean }) {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    if (reduce) return undefined;
    const timer = window.setInterval(() => {
      setIndex((current) => (current + 1) % BUSINESSES.length);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [reduce]);

  const word = BUSINESSES[index] ?? BUSINESSES[0];

  return (
    <span className="mt-1 block min-h-[1.15em]">
      <AnimatePresence mode="wait">
        <motion.span
          key={reduce ? "all" : word}
          initial={reduce ? false : { opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          exit={reduce ? undefined : { opacity: 0, y: -14 }}
          transition={{ duration: reduce ? 0 : 0.35 }}
          className="hero-accent inline-block"
        >
          {reduce ? "Restaurants, Cafés, Retail, Wholesale, Fashion & Electronics" : word}
        </motion.span>
      </AnimatePresence>
    </span>
  );
}

function RotatingTagline({ reduce }: { reduce: boolean }) {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    if (reduce) return undefined;
    const timer = window.setInterval(() => {
      setIndex((current) => (current + 1) % TAGLINES.length);
    }, 5000);
    return () => window.clearInterval(timer);
  }, [reduce]);

  const line = TAGLINES[index] ?? TAGLINES[0];

  return (
    <div className="mb-4 min-h-[4.5rem]">
      <AnimatePresence mode="wait">
        <motion.p
          key={line.lead}
          initial={reduce ? false : { opacity: 0, y: 15, filter: "blur(6px)" }}
          animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
          exit={reduce ? undefined : { opacity: 0, y: -15, filter: "blur(6px)" }}
          transition={{ duration: reduce ? 0 : 0.6 }}
          className="text-xl font-semibold leading-snug text-slate-200 sm:text-2xl"
        >
          {line.lead}{" "}
          <span className="hero-accent">{line.accent}</span>
        </motion.p>
      </AnimatePresence>
    </div>
  );
}

export function Hero({ onDemo }: { onDemo: () => void }) {
  const reduce = useReducedMotion() ?? false;
  const reveal = (delay: number) =>
    reduce
      ? { initial: false as const, animate: { opacity: 1, y: 0 }, transition: { duration: 0 } }
      : {
          variants: itemVariants,
          initial: "hidden" as const,
          animate: "visible" as const,
          transition: { delay, duration: 0.6, ease: [0.22, 1, 0.36, 1] as const },
        };

  return (
    <section id="top" className="hero-showcase relative overflow-hidden bg-[#0A0E17] text-white">
      <AIAnimatedBackground />
      <div className="relative z-10 mx-auto grid max-w-7xl grid-cols-1 items-center gap-10 px-6 py-16 lg:grid-cols-12 lg:px-12">
        <motion.div className="lg:col-span-6" variants={containerVariants} initial="hidden" animate="visible">
          <motion.p
            {...reveal(0)}
            className="mb-6 inline-flex items-center gap-2 rounded-full border border-orange-500/20 bg-orange-500/10 px-3.5 py-1.5 text-xs font-semibold uppercase tracking-wider text-orange-400"
          >
            <Mark name="spark" className="h-3.5 w-3.5" />
            AI-powered POS
          </motion.p>
          <h1 className="text-4xl font-bold leading-tight tracking-tight text-white sm:text-5xl">
            <span className="sr-only">
              Smart POS Software for restaurants, cafés, retail, wholesale, fashion, and electronics.
            </span>
            <span aria-hidden="true">
              Smart POS Software for
              <RotatingBusiness reduce={reduce} />
            </span>
          </h1>
          <div className="mt-4">
            <RotatingTagline reduce={reduce} />
          </div>
          <motion.p {...reveal(0.3)} className="mb-6 max-w-xl text-base leading-relaxed text-slate-300 sm:text-lg">
            AxizPOS is point of sale software for restaurants, cafés, retailers, wholesalers, fashion stores, and
            electronics shops. Staff take the sale on the register. Managers ask about that store&apos;s sales, stock, and
            customers in the portal.
          </motion.p>
          <motion.ul {...reveal(0.45)} className="mb-8 flex flex-wrap gap-2.5">
            {POINTS.map((point) => (
              <li
                key={point}
                className="inline-flex items-center gap-2 rounded-xl border border-slate-800 bg-slate-900/90 px-3.5 py-2 text-xs font-medium text-slate-300"
              >
                <Mark name="check" className="h-3.5 w-3.5 text-orange-400" />
                {point}
              </li>
            ))}
          </motion.ul>
          <motion.div {...reveal(0.6)} className="flex w-full flex-col gap-3 sm:w-auto sm:flex-row">
            <button
              type="button"
              onClick={onDemo}
              className="inline-flex w-full items-center justify-center rounded-xl bg-gradient-to-r from-[#F26A21] to-amber-500 px-6 py-3.5 text-sm font-semibold text-white shadow-lg shadow-orange-500/20 transition-all hover:brightness-110 motion-safe:hover:scale-[1.02] motion-safe:active:scale-[0.98] sm:w-auto"
            >
              Book a Demo
            </button>
            <a
              href={signupUrl}
              className="inline-flex w-full items-center justify-center rounded-xl border border-slate-700 bg-slate-900 px-6 py-3.5 text-sm font-semibold text-white transition-all hover:bg-slate-800 motion-safe:hover:scale-[1.02] motion-safe:active:scale-[0.98] sm:w-auto"
            >
              Create a store
            </a>
          </motion.div>
          <motion.p {...reveal(0.75)} className="mt-4 flex flex-wrap items-center gap-3 text-xs text-slate-400">
            <a href="#intelligence" className="font-semibold text-slate-200 hover:text-orange-300">
              See the assistant
            </a>
            <span aria-hidden="true"> · </span>
            <a href={portalUrl} className="font-semibold text-slate-200 hover:text-orange-300">
              Sign in
            </a>
            <span aria-hidden="true"> · </span>
            <a href="#solutions" className="font-semibold text-slate-200 hover:text-orange-300">
              Explore solutions
            </a>
          </motion.p>
        </motion.div>

        <motion.div
          className="lg:col-span-6"
          initial={reduce ? false : { opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: reduce ? 0 : 0.2, ease: "easeOut" }}
        >
          <div className="flex flex-col gap-8">
            <HeroAsk />
            <figure className="relative mx-auto w-full max-w-xl px-6 py-6">
              <div className="pointer-events-none absolute inset-10 rounded-full bg-orange-500/15 blur-3xl" aria-hidden="true" />
              <motion.div
                animate={reduce ? undefined : { y: [0, -8, 0] }}
                transition={reduce ? undefined : { duration: 5.5, repeat: Infinity, ease: "easeInOut" }}
              >
                <img
                  src="/pos/surface.png"
                  alt="The restaurant register on a Surface tablet, with dine-in tables and checkout."
                  width={949}
                  height={706}
                  fetchPriority="high"
                  decoding="async"
                  className="hero-device relative h-auto w-full drop-shadow-2xl"
                />
              </motion.div>
            </figure>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
