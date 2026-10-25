import { useEffect, useState } from "react";
import { loadCatalog, SEED, type PublicCatalog } from "./catalog";
import { Benefits } from "./components/Benefits";
import { ContactForm } from "./components/ContactForm";
import { DemoModal } from "./components/DemoModal";
import { Faq } from "./components/Faq";
import { Features } from "./components/Features";
import { Footer } from "./components/Footer";
import { Hero } from "./components/Hero";
import { HowItWorks } from "./components/HowItWorks";
import { Industries } from "./components/Industries";
import { Navbar } from "./components/Navbar";
import { Pricing } from "./components/Pricing";
import { SectionHeading } from "./components/SectionHeading";
import { Showcase } from "./components/Showcase";
import { WhatsAppButton } from "./components/WhatsAppButton";
import { apiBaseUrl } from "./env";
import { useSiteTheme } from "./theme";

export function App() {
  const { theme, toggle } = useSiteTheme();
  const [catalog, setCatalog] = useState<PublicCatalog>(SEED);
  const [live, setLive] = useState(false);
  const [demoOpen, setDemoOpen] = useState(false);
  const [whatsapp, setWhatsapp] = useState("");

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
    <div className="min-h-screen bg-canvas text-charcoal">
      <a href="#top" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-2xl focus:bg-card focus:px-4 focus:py-2">
        Skip to content
      </a>
      <Navbar theme={theme} onToggleTheme={toggle} onDemo={() => setDemoOpen(true)} />
      <main>
        <Hero onDemo={() => setDemoOpen(true)} />
        <Industries />
        <Features />
        <HowItWorks />
        <Showcase />
        <Benefits />
        <Pricing catalog={catalog} live={live} />
        <Faq />
        <section id="contact" className="border-t border-line bg-charcoal text-canvas">
          <div className="mx-auto grid max-w-page gap-10 px-4 py-16 sm:px-6 lg:grid-cols-[1fr_1fr] lg:px-8 lg:py-20">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Next step</p>
              <h2 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">Ready to Run Your Business Smarter?</h2>
              <p className="mt-3 max-w-md text-base leading-7 text-canvas/80">
                Discover how AxizPOS can simplify your daily operations and help you manage your business with greater clarity.
              </p>
              <div className="mt-6 flex flex-col gap-3 sm:flex-row">
                <button
                  type="button"
                  onClick={() => setDemoOpen(true)}
                  className="inline-flex h-12 items-center justify-center rounded-2xl bg-primary px-5 text-sm font-semibold text-white hover:bg-primary-hover"
                >
                  Book a Demo
                </button>
                <a href="#demo-form" className="inline-flex h-12 items-center justify-center rounded-2xl border border-canvas/30 px-5 text-sm font-semibold text-canvas">
                  Contact Sales
                </a>
              </div>
            </div>
            <div id="demo-form" className="rounded-card bg-card p-5 text-charcoal">
              <SectionHeading kicker="Contact" title="Request a walkthrough" />
              <div className="mt-4">
                <ContactForm whatsapp={whatsapp} />
              </div>
            </div>
          </div>
        </section>
      </main>
      <Footer whatsapp={whatsapp} />
      {demoOpen ? <DemoModal whatsapp={whatsapp} onClose={() => setDemoOpen(false)} /> : null}
      <WhatsAppButton number={whatsapp} />
    </div>
  );
}
