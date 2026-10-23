import { motion, useReducedMotion, useScroll, useTransform } from "framer-motion";
import { useRef } from "react";
import { SectionHeading } from "./SectionHeading";

export function Hardware() {
  const ref = useRef<HTMLElement>(null);
  const reduce = useReducedMotion();
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start end", "end start"] });
  const y = useTransform(scrollYProgress, [0, 1], [28, -28]);

  return (
    <section id="hardware" ref={ref} className="overflow-hidden py-24">
      <div className="mx-auto max-w-page px-5 lg:px-8">
        <SectionHeading kicker="Hardware" title="The counter around the software." />
        <motion.div style={reduce ? undefined : { y }} className="mt-8 grid gap-3 lg:grid-cols-12">
          <article className="rounded-2xl border border-cyan-400/30 bg-white/[0.03] p-6 lg:col-span-7">
            <p className="text-xs uppercase tracking-[0.16em] text-glow">At the till</p>
            <h3 className="mt-3 text-2xl font-semibold">Receipt printers</h3>
            <p className="mt-3 max-w-md text-mist">Slip and invoice print on the tender the register just closed.</p>
          </article>
          <article className="rounded-2xl border border-white/10 bg-white/[0.03] p-6 lg:col-span-5">
            <h3 className="text-xl font-semibold">Cash drawers</h3>
            <p className="mt-3 text-sm text-mist">Kick the drawer on cash, and keep a counted session for each till.</p>
          </article>
          <article className="rounded-2xl border border-emerald-400/30 bg-white/[0.03] p-6 lg:col-span-5">
            <h3 className="text-xl font-semibold">Kitchen displays</h3>
            <p className="mt-3 text-sm text-mist">Pro routes tickets to kitchen and bar screens by station.</p>
          </article>
          <article className="rounded-2xl border border-white/10 bg-white/[0.03] p-6 lg:col-span-7">
            <p className="text-xs uppercase tracking-[0.16em] text-emerald-300">On the counter</p>
            <h3 className="mt-3 text-2xl font-semibold">Barcode scanners</h3>
            <p className="mt-3 max-w-md text-mist">
              Scan into the open sale. Weighed and price-embedded barcodes stay on grocery profiles.
            </p>
          </article>
        </motion.div>
      </div>
    </section>
  );
}
