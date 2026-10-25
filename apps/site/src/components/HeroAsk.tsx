import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useEffect, useState } from "react";
import { Mark, type MarkName } from "./icons";

type Tab = "sales" | "stock" | "kitchen";

const ORDER: Tab[] = ["sales", "stock", "kitchen"];

const PROMPTS: Record<Tab, { label: string; icon: MarkName; question: string; answer: string; tool: string }> = {
  sales: {
    label: "Sales Summary",
    icon: "chart",
    question: "How much did we sell today?",
    answer: "Net sales, number of sales, refunds, and the average basket for the stores you can open.",
    tool: "Sales summary",
  },
  stock: {
    label: "Low Stock Alert",
    icon: "package",
    question: "Which ingredients are running low?",
    answer: "Items below minimum threshold, supplier lead times, and suggested reorder quantities based on sales velocity.",
    tool: "Inventory status",
  },
  kitchen: {
    label: "Kitchen Brief",
    icon: "utensils",
    question: "What should the kitchen prep for dinner shift?",
    answer: "What to order, use first, move, prep, or take off the menu. Figures come from stock, recipes, and batch expiry.",
    tool: "Kitchen prep brief",
  },
};

function useTypedQuestion(question: string, reduce: boolean) {
  const [count, setCount] = useState(reduce ? question.length : 0);

  useEffect(() => {
    if (reduce) {
      setCount(question.length);
      return undefined;
    }
    setCount(0);
    let next = 0;
    const timer = window.setInterval(() => {
      next += 1;
      setCount(next);
      if (next >= question.length) window.clearInterval(timer);
    }, 28);
    return () => window.clearInterval(timer);
  }, [question, reduce]);

  return question.slice(0, count);
}

export function HeroAsk() {
  const reduce = useReducedMotion() ?? false;
  const [activeTab, setActiveTab] = useState<Tab>("sales");
  const [paused, setPaused] = useState(false);
  const prompt = PROMPTS[activeTab];
  const typed = useTypedQuestion(prompt.question, reduce);

  useEffect(() => {
    if (reduce || paused) return undefined;
    const timer = window.setInterval(() => {
      setActiveTab((current) => ORDER[(ORDER.indexOf(current) + 1) % ORDER.length] ?? "sales");
    }, 5000);
    return () => window.clearInterval(timer);
  }, [paused, reduce]);

  return (
    <div
      className="relative z-10 w-full rounded-2xl border border-slate-800 bg-slate-900/90 p-5 shadow-2xl backdrop-blur-xl"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={(event) => {
        const next = event.relatedTarget;
        if (next instanceof Node && event.currentTarget.contains(next)) return;
        setPaused(false);
      }}
    >
      <div className="flex items-center gap-2">
        <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-primary text-white">
          <AnimatePresence mode="wait">
            <motion.span
              key={prompt.icon}
              initial={reduce ? false : { opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={reduce ? undefined : { opacity: 0, y: -4 }}
              transition={{ duration: 0.2 }}
              className="flex"
            >
              <Mark name={prompt.icon} className="h-4 w-4" />
            </motion.span>
          </AnimatePresence>
        </span>
        <p className="text-sm font-semibold text-white">Ask your business</p>
      </div>
      <p className="mt-3 flex min-h-11 items-center rounded-xl border border-slate-700 bg-slate-950/80 px-3 py-2 text-sm text-slate-100" aria-live="polite">
        <AnimatePresence mode="wait">
          <motion.span
            key={activeTab}
            initial={reduce ? false : { opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduce ? undefined : { opacity: 0, y: -4 }}
            transition={{ duration: 0.25 }}
          >
            {typed}
            <span className="hero-caret ml-0.5 inline-block h-4 w-px bg-amber-300 align-middle" aria-hidden="true" />
          </motion.span>
        </AnimatePresence>
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        {ORDER.map((tab) => {
          const item = PROMPTS[tab];
          const selected = tab === activeTab;
          return (
            <button
              key={tab}
              type="button"
              aria-pressed={selected}
              onClick={() => setActiveTab(tab)}
              className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-semibold transition-colors ${
                selected
                  ? "border-orange-400/40 bg-orange-500/15 text-orange-200"
                  : "border-slate-700 bg-slate-950/60 text-slate-300 hover:border-slate-500 hover:text-white"
              }`}
            >
              <Mark name={item.icon} className="h-3.5 w-3.5" />
              {item.label}
            </button>
          );
        })}
      </div>
      <div className="mt-3 min-h-28 rounded-xl border border-slate-800 bg-slate-950/70 px-3 py-2.5 text-sm leading-6 text-slate-300">
        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={reduce ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduce ? undefined : { opacity: 0, y: -6 }}
            transition={{ duration: 0.28 }}
          >
            <p>{prompt.answer}</p>
            <p className="mt-2 text-xs font-semibold text-orange-300">{prompt.tool}</p>
          </motion.div>
        </AnimatePresence>
      </div>
      <p className="mt-2 text-[11px] leading-4 text-slate-500">In the portal, every figure comes from that store.</p>
    </div>
  );
}
