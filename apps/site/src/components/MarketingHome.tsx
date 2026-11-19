import { Benefits } from "./Benefits";
import { Faq } from "./Faq";
import { Features } from "./Features";
import { GetStartedSection } from "./GetStartedSection";
import { HardwareShelf } from "./HardwareShelf";
import { Hero } from "./Hero";
import { HowItWorks } from "./HowItWorks";
import { Industries } from "./Industries";
import { Intelligence } from "./Intelligence";
import { Modules } from "./Modules";
import { Pricing } from "./Pricing";
import { Showcase } from "./Showcase";
import type { PublicCatalog } from "../catalog";

export function MarketingHome({
  catalog,
  live,
  catalogStatus,
  onQuote,
}: {
  catalog: PublicCatalog;
  live: boolean;
  catalogStatus: "loading" | "ready" | "unavailable";
  onQuote: (note: string) => void;
}) {
  return (
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
        status={catalogStatus}
        onQuote={(note) => {
          onQuote(note);
          document.getElementById("contact")?.scrollIntoView({ behavior: "smooth" });
        }}
      />
      <HardwareShelf
        items={catalog.hardware}
        live={live}
        onEnquire={(note) => {
          onQuote(note);
          document.getElementById("contact")?.scrollIntoView({ behavior: "smooth" });
        }}
      />
      <Faq />
      <GetStartedSection />
    </>
  );
}
