import { motion, useReducedMotion, useScroll, useSpring } from "framer-motion";
import { useEffect, useState } from "react";
import { loadCatalog, SEED, type PublicCatalog } from "./catalog";
import { Branches } from "./components/Branches";
import { DemoModal } from "./components/DemoModal";
import { Floor } from "./components/Floor";
import { Hardware } from "./components/Hardware";
import { Hero } from "./components/Hero";
import { Pricing } from "./components/Pricing";
import { WhatsAppButton } from "./components/WhatsAppButton";
import { apiBaseUrl, installerUrl, signupUrl } from "./env";

export function App() {
  const reduce = useReducedMotion();
  const [catalog, setCatalog] = useState<PublicCatalog>(SEED);
  const [live, setLive] = useState(false);
  const [demoOpen, setDemoOpen] = useState(false);
  const [whatsapp, setWhatsapp] = useState("");
  const { scrollYProgress } = useScroll();
  const bar = useSpring(scrollYProgress, { stiffness: 120, damping: 24, restDelta: 0.001 });

  useEffect(() => {
    let cancelled = false;
    loadCatalog(`${apiBaseUrl}/api/v1/billing/public-catalog`).then((result) => {
      if (cancelled) return;
      setCatalog(result.catalog);
      setLive(result.live);
    });
    fetch(`${apiBaseUrl}/api/v1/site/contact`)
      .then(async (response) => {
        if (!response.ok) return "";
        const body = (await response.json()) as { whatsapp?: unknown };
        return typeof body.whatsapp === "string" ? body.whatsapp : "";
      })
      .then((number) => {
        if (!cancelled) setWhatsapp(number);
      })
      .catch(() => {
        if (!cancelled) setWhatsapp("");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div>
      {!reduce && (
        <motion.div style={{ scaleX: bar }} className="fixed left-0 right-0 top-0 z-30 h-0.5 origin-left bg-emerald-400" />
      )}
      <header className="sticky top-0 z-20 flex items-center justify-between gap-4 border-b border-white/10 bg-ink/80 px-5 py-3 backdrop-blur-xl lg:px-8">
        <a href="#top" className="font-semibold tracking-tight">
          AxizPOS
        </a>
        <nav className="hidden items-center gap-5 text-sm text-mist md:flex">
          <a href="#floor">Floor</a>
          <a href="#branches">Branches</a>
          <a href="#hardware">Hardware</a>
          <a href="#pricing">Packages</a>
          <a href={installerUrl()}>Download POS</a>
        </nav>
        <div className="flex items-center gap-2">
          <a href={signupUrl} className="hidden rounded-full border border-white/15 px-3 py-2 text-sm sm:inline">
            Practice store
          </a>
          <button type="button" onClick={() => setDemoOpen(true)} className="rounded-full bg-cyan-400 px-3 py-2 text-sm font-semibold text-ink">
            Book a demo
          </button>
        </div>
      </header>
      <main id="top">
        <Hero onDemo={() => setDemoOpen(true)} />
        <Floor />
        <Branches />
        <Hardware />
        <Pricing catalog={catalog} live={live} />
      </main>
      <footer className="px-5 py-10 text-sm text-mist lg:px-8">AxizPOS · axizpos.com</footer>
      {demoOpen && <DemoModal onClose={() => setDemoOpen(false)} />}
      <WhatsAppButton number={whatsapp} />
    </div>
  );
}
