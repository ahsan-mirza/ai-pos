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
import { Modules } from "./components/Modules";
import { Intelligence } from "./components/Intelligence";
import { Navbar } from "./components/Navbar";
import { Pricing } from "./components/Pricing";
import { Showcase } from "./components/Showcase";
import { WhatsAppButton } from "./components/WhatsAppButton";
import { apiBaseUrl, signupUrl } from "./env";
import { useSiteTheme } from "./theme";
import { IndustryPage } from "./pages/IndustryPage";
import { seoPage } from "./seo";
import { EMPTY_WHATSAPP, parsePublicWhatsApp, type PublicWhatsApp } from "./whatsapp";

export function App() {
  const { theme, toggle } = useSiteTheme();
  const [catalog, setCatalog] = useState<PublicCatalog>(SEED);
  const [live, setLive] = useState(false);
  const [demoOpen, setDemoOpen] = useState(false);
  const [quoteDraft, setQuoteDraft] = useState<string | null>(null);
  const [contact, setContact] = useState<PublicWhatsApp>(EMPTY_WHATSAPP);
  const [contactStatus, setContactStatus] = useState<"loading" | "ready" | "unavailable">("loading");

  useEffect(() => {
    let cancelled = false;
    loadCatalog(`${apiBaseUrl}/api/v1/billing/public-catalog`).then((result) => {
      if (cancelled) return;
      setCatalog(result.catalog);
      setLive(result.live);
    });
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

  const industry = seoPage(document.documentElement.dataset.page ?? "home");
  const atHome = industry === undefined || industry.id === "home";

  return (
    <div className="min-h-screen bg-canvas text-charcoal">
      <a href="#content" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-2xl focus:bg-card focus:px-4 focus:py-2">
        Skip to content
      </a>
      <Navbar atHome={atHome} theme={theme} onToggleTheme={toggle} onDemo={() => setDemoOpen(true)} />
      <main id="content">
        {industry && industry.id !== "home" ? (
          <IndustryPage page={industry} contact={contact} contactStatus={contactStatus} onDemo={() => setDemoOpen(true)} />
        ) : (
          <>
        <Hero onDemo={() => setDemoOpen(true)} />
        <Intelligence />
        <Industries />
        <Modules catalog={catalog} />
        <Features />
        <HowItWorks />
        <Showcase />
        <Benefits />
        <Pricing
          catalog={catalog}
          live={live}
          onDemo={(note) => {
            setQuoteDraft(note);
            setDemoOpen(true);
          }}
          onQuote={(note) => {
            setQuoteDraft(note);
            document.getElementById("contact")?.scrollIntoView({ behavior: "smooth" });
          }}
        />
        <Faq />
        <section id="contact" className="border-t border-line bg-charcoal text-canvas">
          <div className="mx-auto grid max-w-page gap-10 px-4 py-16 sm:px-6 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)] lg:items-start lg:gap-12 lg:px-8 lg:py-20">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Next step</p>
              <h2 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">Ready to ask the store?</h2>
              <p className="mt-3 max-w-md text-base leading-7 text-canvas/80">
                Book a walkthrough of the register, the assistant, and the insights that read the sales you already record.
              </p>
              <div className="mt-6 flex flex-wrap gap-3">
                <button
                  type="button"
                  onClick={() => setDemoOpen(true)}
                  className="inline-flex h-12 shrink-0 items-center justify-center whitespace-nowrap rounded-2xl bg-primary px-5 text-sm font-semibold text-white hover:bg-primary-hover"
                >
                  Book a Demo
                </button>
                <a href={signupUrl} className="inline-flex h-12 shrink-0 items-center justify-center whitespace-nowrap rounded-2xl border border-canvas/30 px-5 text-sm font-semibold text-canvas">
                  Create a store
                </a>
              </div>
            </div>
            <div id="demo-form" className="walkthrough-card w-full rounded-3xl border border-slate-100 bg-white p-6 text-slate-900 shadow-2xl shadow-slate-900/10 sm:p-8">
              <ContactForm contact={contact} contactStatus={contactStatus} draft={quoteDraft} />
            </div>
          </div>
        </section>
          </>
        )}
      </main>
      <Footer atHome={atHome} contact={contact} />
      {demoOpen ? (
        <DemoModal contact={contact} contactStatus={contactStatus} draft={quoteDraft} onClose={() => setDemoOpen(false)} />
      ) : null}
      {demoOpen ? null : <WhatsAppButton contact={contact} />}
    </div>
  );
}
