import { motion, useReducedMotion } from "framer-motion";
import { useState } from "react";
import { aed } from "../catalog";
import { signupUrl } from "../env";
import { RegisterCanvas } from "./RegisterCanvas";

const UNIT_FILS = 1_850;

export function Hero({ onDemo }: { onDemo: () => void }) {
  const [qty, setQty] = useState(2);
  const reduce = useReducedMotion();
  const total = aed(UNIT_FILS * qty);

  return (
    <section className="relative min-h-[100svh] overflow-hidden">
      <RegisterCanvas totalLabel={total} />
      <div className="pointer-events-none absolute inset-y-0 left-0 z-[1] hidden w-[62%] bg-gradient-to-r from-ink from-35% via-ink/75 to-transparent lg:block" />
      <div className="relative z-10 mx-auto grid min-h-[100svh] max-w-page items-end gap-10 px-5 pb-16 pt-28 lg:grid-cols-[1.15fr_0.85fr] lg:px-8">
        <div>
          <p className="text-xs uppercase tracking-[0.18em] text-glow">axizpos.com</p>
          <h1 className="mt-3 max-w-xl text-5xl font-semibold leading-[0.95] tracking-tight sm:text-7xl">
            The register for every counter in the UAE.
          </h1>
          <p className="mt-5 max-w-md text-lg text-mist">
            Sell, seat a table, and take a store from a practice trial to a paid package. Prices follow the console catalog.
          </p>
          <div className="mt-7 flex flex-wrap gap-3">
            <a href={signupUrl} className="rounded-full bg-cyan-400 px-5 py-3 text-sm font-semibold text-ink">
              Start practice store
            </a>
            <button type="button" onClick={onDemo} className="rounded-full border border-white/20 px-5 py-3 text-sm font-semibold">
              Book a demo
            </button>
          </div>
          <ul className="mt-8 flex flex-wrap gap-x-6 gap-y-2 text-sm text-mist">
            <li>Practice mode before go-live</li>
            <li>UAE e-invoicing on the sale</li>
            <li>Hardware lease on the package</li>
          </ul>
        </div>
        <motion.aside
          drag={reduce ? false : true}
          dragMomentum={false}
          dragConstraints={{ left: -24, right: 24, top: -24, bottom: 24 }}
          className="w-full max-w-sm justify-self-end rounded-2xl border border-cyan-400/35 bg-[#0f1724]/80 p-5 backdrop-blur-xl"
        >
          <p className="text-xs uppercase tracking-[0.16em] text-glow">Open sale</p>
          <div className="mt-4 flex items-baseline justify-between gap-4">
            <span>Arabic coffee</span>
            <span>{aed(UNIT_FILS)}</span>
          </div>
          <div className="mt-4 flex items-center gap-3">
            <button type="button" className="h-10 w-10 rounded-full border border-white/15" aria-label="Fewer" onClick={() => setQty((count) => Math.max(1, count - 1))}>
              −
            </button>
            <strong className="min-w-6 text-center">{qty}</strong>
            <button type="button" className="h-10 w-10 rounded-full border border-white/15" aria-label="More" onClick={() => setQty((count) => count + 1)}>
              +
            </button>
          </div>
          <p className="mt-4 text-glow">{total} on the register</p>
        </motion.aside>
      </div>
    </section>
  );
}
