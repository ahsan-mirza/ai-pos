import { motion, useReducedMotion, useScroll, useTransform } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { SectionHeading } from "./SectionHeading";

const BRANCHES = [
  { city: "Dubai", sales: 18_420, tickets: 126, covers: 214, step: 12 },
  { city: "Abu Dhabi", sales: 9_680, tickets: 74, covers: 121, step: 15 },
  { city: "Sharjah", sales: 5_410, tickets: 51, covers: 88, step: 18 },
];

export function Branches() {
  const ref = useRef<HTMLElement>(null);
  const reduce = useReducedMotion();
  const [tick, setTick] = useState(0);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start end", "end start"] });
  const y = useTransform(scrollYProgress, [0, 1], [36, -36]);

  useEffect(() => {
    if (reduce) return undefined;
    const id = window.setInterval(() => setTick((count) => count + 1), 1600);
    return () => window.clearInterval(id);
  }, [reduce]);

  return (
    <section id="branches" ref={ref} className="overflow-hidden bg-white/[0.02] py-24">
      <div className="mx-auto max-w-page px-5 lg:px-8">
        <SectionHeading kicker="Preview" title="Three stores, one catalog." />
        <motion.div style={reduce ? undefined : { y }} className="mt-8 grid gap-3 md:grid-cols-3">
          {BRANCHES.map((branch, index) => (
            <article key={branch.city} className="rounded-2xl border border-white/10 bg-ink/60 p-5">
              <h3 className="text-lg font-semibold">{branch.city}</h3>
              <p className="mt-3 text-3xl font-semibold text-glow">
                AED {(branch.sales + (reduce ? 0 : tick * branch.step)).toLocaleString("en-AE")}
              </p>
              <p className="mt-2 text-sm text-mist">
                {branch.tickets + (reduce ? 0 : tick + index)} tickets · {branch.covers + (reduce ? 0 : tick)} covers
              </p>
            </article>
          ))}
        </motion.div>
        <p className="mt-4 text-xs text-mist">Illustrative preview. Live totals come from each store after go-live.</p>
      </div>
    </section>
  );
}
