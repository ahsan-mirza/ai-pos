import { useEffect, useState } from "react";
import { loadCatalog, SEED, type PublicCatalog } from "./catalog";
import { Benefits } from "./components/Benefits";
import { Faq } from "./components/Faq";
import { Features } from "./components/Features";
import { Footer } from "./components/Footer";
import { Hero } from "./components/Hero";
import { HowItWorks } from "./components/HowItWorks";
import { Industries } from "./components/Industries";
import { Modules } from "./components/Modules";
import { Intelligence } from "./components/Intelligence";
import { Navbar } from "./components/Navbar";
import { HardwareShelf } from "./components/HardwareShelf";
import { Pricing } from "./components/Pricing";
import { Showcase } from "./components/Showcase";
import { WhatsAppButton } from "./components/WhatsAppButton";
import { apiBaseUrl } from "./env";
import { GetStartedSection } from "./components/GetStartedSection";
import { QuoteDialog } from "./components/QuoteDialog";
import { useSiteTheme } from "./theme";
import { IndustryPage } from "./pages/IndustryPage";
import { seoPage } from "./seo";
import { EMPTY_WHATSAPP, parsePublicWhatsApp, type PublicWhatsApp } from "./whatsapp";

export function App() {
  const { theme, toggle } = useSiteTheme();
  const [catalog, setCatalog] = useState<PublicCatalog>(SEED);
  const [live, setLive] = useState(false);
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
      <Navbar
        atHome={atHome}
        theme={theme}
        onToggleTheme={toggle}
        showHardware={live && catalog.hardware.length > 0}
      />
      <main id="content">
        {industry && industry.id !== "home" ? (
          <IndustryPage page={industry} catalog={catalog} />
        ) : (
          <>
        <Hero />
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
          onQuote={(note) => {
            setQuoteDraft(note);
            document.getElementById("contact")?.scrollIntoView({ behavior: "smooth" });
          }}
        />
        <HardwareShelf
          items={catalog.hardware}
          live={live}
          onEnquire={(note) => {
            setQuoteDraft(note);
            document.getElementById("contact")?.scrollIntoView({ behavior: "smooth" });
          }}
        />
        <Faq />
        <GetStartedSection />
          </>
        )}
      </main>
      <Footer atHome={atHome} contact={contact} />
      <WhatsAppButton contact={contact} />
      {quoteDraft ? (
        <QuoteDialog
          contact={contact}
          contactStatus={contactStatus}
          draft={quoteDraft}
          onClose={() => setQuoteDraft(null)}
        />
      ) : null}
    </div>
  );
}
