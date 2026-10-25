import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useEffect, useState } from "react";
import { Mark } from "./icons";

export const EXCHANGES = [
  {
    question: "How much did we sell today?",
    tool: "Sales summary",
    answer: "Net sales, number of sales, refunds, and the average basket for the stores you can open.",
  },
  {
    question: "What should I reorder?",
    tool: "Reorder forecast",
    answer: "Items the latest replenishment run flagged, with the forecast model and the quantity to order.",
  },
  {
    question: "Any unusual voids or refunds this month?",
    tool: "Unusual activity",
    answer: "Cashiers whose voids, refunds, drawer opens, or price overrides stand out from the rest of the team, and why.",
  },
  {
    question: "Which prices should I change?",
    tool: "Price suggestions",
    answer: "Prices under the margin floor, stock that demand is outrunning, and batches to mark down.",
  },
  {
    question: "كم بعنا اليوم؟",
    tool: "Sales summary",
    answer: "صافي المبيعات وعدد الفواتير والمرتجعات ومتوسط السلة للمتاجر التي يمكنك فتحها.",
  },
] as const;

export function AskDemo({ compact = false }: { compact?: boolean }) {
  const reduce = useReducedMotion();
  const [index, setIndex] = useState(0);
  const [phase, setPhase] = useState<"read" | "answer">("answer");
  const [hold, setHold] = useState(false);
  const item = EXCHANGES[index] ?? EXCHANGES[0];

  useEffect(() => {
    if (reduce) return undefined;
    setPhase("read");
    const answerTimer = window.setTimeout(() => setPhase("answer"), 800);
    const advance = window.setTimeout(() => {
      if (!hold) setIndex((current) => (current + 1) % EXCHANGES.length);
    }, 4600);
    return () => {
      window.clearTimeout(answerTimer);
      window.clearTimeout(advance);
    };
  }, [hold, index, reduce]);

  const choose = (next: number) => {
    setHold(true);
    setIndex(next);
  };

  return (
    <div className="rounded-card border border-primary/30 bg-card p-4 shadow-lg shadow-primary/10">
      <div className="flex items-center gap-3">
        <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-primary text-white">
          <Mark name="spark" className="h-5 w-5" />
        </span>
        <div>
          <p className="text-sm font-semibold text-charcoal">Ask your business</p>
          <p className="text-xs text-charcoal/60">English or العربية · answers come only from your reports</p>
        </div>
      </div>

      <div className="mt-4 space-y-3" aria-live="polite">
        <p
          dir={item.question.startsWith("ك") ? "rtl" : "ltr"}
          className="ml-auto max-w-[90%] rounded-2xl rounded-br-md bg-charcoal px-3 py-2 text-sm text-canvas"
        >
          {item.question}
        </p>
        <div className="max-w-[92%] rounded-2xl rounded-bl-md border border-line bg-surface px-3 py-2.5 text-sm text-charcoal">
          <AnimatePresence mode="wait">
            {phase === "read" && !reduce ? (
              <motion.p key="read" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="text-charcoal/60">
                Reading {item.tool.toLowerCase()}
                <span className="inline-flex w-6 justify-between px-1" aria-hidden="true">
                  <motion.span animate={{ opacity: [0.2, 1, 0.2] }} transition={{ duration: 1, repeat: Infinity }}>
                    .
                  </motion.span>
                  <motion.span animate={{ opacity: [0.2, 1, 0.2] }} transition={{ duration: 1, repeat: Infinity, delay: 0.15 }}>
                    .
                  </motion.span>
                  <motion.span animate={{ opacity: [0.2, 1, 0.2] }} transition={{ duration: 1, repeat: Infinity, delay: 0.3 }}>
                    .
                  </motion.span>
                </span>
              </motion.p>
            ) : (
              <motion.div key={item.question} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}>
                <p dir={item.question.startsWith("ك") ? "rtl" : "ltr"} className="leading-6">
                  {item.answer}
                </p>
                <p className="mt-2 inline-flex rounded-full bg-primary/10 px-2 py-0.5 text-xs font-semibold text-primary">{item.tool}</p>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {compact ? (
        <a href="#intelligence" className="mt-4 inline-flex text-sm font-semibold text-primary">
          See what you can ask
        </a>
      ) : (
        <div className="mt-4 flex flex-wrap gap-2">
          {EXCHANGES.map((exchange, exchangeIndex) => (
            <button
              key={exchange.question}
              type="button"
              dir={exchange.question.startsWith("ك") ? "rtl" : "ltr"}
              onClick={() => choose(exchangeIndex)}
              aria-pressed={exchangeIndex === index}
              className={`rounded-full px-3 py-1.5 text-left text-xs font-semibold ${
                exchangeIndex === index ? "bg-primary text-white" : "bg-surface text-charcoal hover:text-primary"
              }`}
            >
              {exchange.question}
            </button>
          ))}
        </div>
      )}
      <p className="mt-3 text-xs leading-5 text-charcoal/55">
        Layout sample. In the portal, every figure comes from that store. The assistant does not invent a number.
      </p>
    </div>
  );
}
