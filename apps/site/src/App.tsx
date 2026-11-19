import { lazy, Suspense, useEffect, useState } from "react";
import { EMPTY_CATALOG, loadCatalog, type PublicCatalog } from "./catalog";
import { Footer } from "./components/Footer";
import { SiteHeader } from "./home2/SiteHeader";
import "./home2/home2.css";
import { WhatsAppButton } from "./components/WhatsAppButton";
import { apiBaseUrl } from "./env";
import { IndustryPage } from "./pages/IndustryPage";

const MarketingHome = lazy(() => import("./components/MarketingHome").then((mod) => ({ default: mod.MarketingHome })));
const HardwarePage = lazy(() => import("./hardware/HardwarePage").then((mod) => ({ default: mod.HardwarePage })));
const ExplorePage = lazy(() => import("./pages/ExplorePage").then((mod) => ({ default: mod.ExplorePage })));
const BlogIndex = lazy(() => import("./blog/BlogIndex").then((mod) => ({ default: mod.BlogIndex })));
const BlogPost = lazy(() => import("./blog/BlogPost").then((mod) => ({ default: mod.BlogPost })));
const QuoteDialog = lazy(() => import("./components/QuoteDialog").then((mod) => ({ default: mod.QuoteDialog })));
import { seoPage } from "./seo";
import { track } from "./track";
import { EMPTY_WHATSAPP, parsePublicWhatsApp, type PublicWhatsApp } from "./whatsapp";

export function App() {
  const [catalog, setCatalog] = useState<PublicCatalog>(EMPTY_CATALOG);
  const [live, setLive] = useState(false);
  const [catalogStatus, setCatalogStatus] = useState<"loading" | "ready" | "unavailable">("loading");
  const [quoteDraft, setQuoteDraft] = useState<string | null>(null);
  const [contact, setContact] = useState<PublicWhatsApp>(EMPTY_WHATSAPP);
  const [contactStatus, setContactStatus] = useState<"loading" | "ready" | "unavailable">("loading");

  useEffect(() => {
    const page = seoPage(document.documentElement.dataset.page ?? "home");
    track("view_page", {
      page_path: page?.path ?? "/",
      content_group: page?.kind ?? "home",
      locale: page?.locale ?? "en",
    });
  }, []);

  useEffect(() => {
    let cancelled = false;
    loadCatalog(`${apiBaseUrl}/api/v1/billing/public-catalog`).then((result) => {
      if (cancelled) return;
      setCatalog(result.catalog);
      setLive(result.live);
      setCatalogStatus(result.live ? "ready" : "unavailable");
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
      <SiteHeader
        atHome={atHome}
        onDemo={() => {
          track("click_book_demo", { page_path: window.location.pathname });
          setQuoteDraft("Book a demo. This page does not create an invoice.");
        }}
      />
      <main id="content">
        <Suspense fallback={null}>
          {industry?.id === "hardware" ? (
            <HardwarePage contact={contact} />
          ) : industry?.id === "explore" ? (
            <ExplorePage />
          ) : industry?.kind === "blog" ? (
            <BlogIndex page={industry} />
          ) : industry?.kind === "article" ? (
            <BlogPost page={industry} onContact={(note) => setQuoteDraft(note)} />
          ) : industry && industry.id !== "home" ? (
            <IndustryPage
              page={industry}
              catalog={catalog}
              contact={contact}
              onContact={(note) => setQuoteDraft(note)}
            />
          ) : (
            <MarketingHome
              catalog={catalog}
              live={live}
              catalogStatus={catalogStatus}
              onQuote={(note) => setQuoteDraft(note)}
            />
          )}
        </Suspense>
      </main>
      <Footer contact={contact} />
      <WhatsAppButton contact={contact} />
      {quoteDraft ? (
        <Suspense fallback={null}>
          <QuoteDialog
            contact={contact}
            contactStatus={contactStatus}
            draft={quoteDraft}
            onClose={() => setQuoteDraft(null)}
          />
        </Suspense>
      ) : null}
    </div>
  );
}
