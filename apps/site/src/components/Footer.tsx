import { portalUrl, signupUrl } from "../env";
import { SEO_PAGES } from "../seo";
import { whatsappChatUrl, whatsappDigits, whatsappReady, type PublicWhatsApp } from "../whatsapp";

const SOLUTIONS = [
  ["Restaurant POS system", "/restaurant-pos"],
  ["Café POS software", "/cafe-pos"],
  ["Quick service POS", "/quick-service-pos"],
  ["Retail POS system", "/retail-pos"],
  ["Supermarket and grocery POS", "/grocery-pos"],
  ["Wholesale POS software", "/wholesale-pos"],
  ["Fashion store POS", "/fashion-pos"],
  ["Electronics store POS", "/electronics-pos"],
  ["POS software UAE", "/pos-software-uae"],
] as const;

const PRODUCT = [
  ["Overview", "/#platform"],
  ["Pricing", "/#pricing"],
] as const;

export function Footer({ contact }: { contact: PublicWhatsApp }) {
  const year = new Date().getFullYear();
  const ready = whatsappReady(contact);
  const arabic = document.documentElement.lang === "ar";
  const solutions = arabic
    ? SEO_PAGES.filter((page) => page.locale === "ar" && page.kind === "industry").map((page) => [page.crumb, page.path] as const)
    : SOLUTIONS;
  const features = SEO_PAGES.filter((page) => page.locale === (arabic ? "ar" : "en") && page.kind === "feature").map(
    (page) => [page.crumb, page.path] as const,
  );
  const guides = arabic ? "/ar/blog" : "/blog";

  return (
    <footer className="border-t border-line bg-card">
      <div className="mx-auto grid max-w-page gap-8 px-4 py-12 sm:px-6 md:grid-cols-2 lg:grid-cols-4 lg:px-8">
        <div>
          <img src="/brand/logo.svg" alt="AxizPOS" width={137} height={32} className="h-8 w-auto dark:hidden" />
          <img src="/brand/logo-white.svg" alt="" width={137} height={32} className="hidden h-8 w-auto dark:block" />
          <p className="mt-3 max-w-xs text-sm leading-6 text-charcoal/70">
            {arabic
              ? "برنامج نقاط بيع للمطاعم والتجزئة والجملة في الإمارات والخليج. اسأل المتجر بالعربية أو الإنجليزية، ثم بيع من السجلات نفسها."
              : "POS software for restaurants, retail, and wholesale businesses in the UAE and GCC. Ask the store in English or Arabic, then sell from the same records."}
          </p>
        </div>
        <div>
          <h2 className="text-sm font-semibold text-charcoal">{arabic ? "الحلول" : "Solutions"}</h2>
          <ul className="mt-3 space-y-2 text-sm">
            {solutions.map(([label, href]) => (
              <li key={label}>
                <a href={href} className="text-charcoal/75 hover:text-charcoal">
                  {label}
                </a>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h2 className="text-sm font-semibold text-charcoal">{arabic ? "المنتج" : "Product"}</h2>
          <ul className="mt-3 space-y-2 text-sm">
            {features.map(([label, href]) => (
              <li key={label}>
                <a href={href} className="text-charcoal/75 hover:text-charcoal">
                  {label}
                </a>
              </li>
            ))}
            <li>
              <a href={guides} className="text-charcoal/75 hover:text-charcoal">
                {arabic ? "الأدلة" : "Guides"}
              </a>
            </li>
            {arabic ? (
              <li>
                <a href="/#pricing" className="text-charcoal/75 hover:text-charcoal">
                  الأسعار
                </a>
              </li>
            ) : (
              PRODUCT.map(([label, href]) => (
                <li key={label}>
                  <a href={href} className="text-charcoal/75 hover:text-charcoal">
                    {label}
                  </a>
                </li>
              ))
            )}
            <li>
              <a href={portalUrl} className="text-charcoal/75 hover:text-charcoal">
                {arabic ? "دخول" : "Sign In"}
              </a>
            </li>
            <li>
              <a href={signupUrl} className="text-charcoal/75 hover:text-charcoal">
                {arabic ? "ابدأ مجاناً" : "Get Started Free"}
              </a>
            </li>
          </ul>
        </div>
        <div>
          <h2 className="text-sm font-semibold text-charcoal">{arabic ? "التواصل" : "Contact"}</h2>
          {ready || contact.email ? (
            <ul className="mt-3 space-y-2 text-sm">
              {ready ? (
                <li>
                  <a
                    href={whatsappChatUrl(contact.number, contact.message)}
                    className="text-charcoal/75 hover:text-charcoal"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    WhatsApp +{whatsappDigits(contact.number)}
                  </a>
                </li>
              ) : null}
              {contact.email ? (
                <li>
                  <a href={`mailto:${contact.email}`} className="text-charcoal/75 hover:text-charcoal">
                    {contact.email}
                  </a>
                </li>
              ) : null}
            </ul>
          ) : (
            <p className="mt-3 text-sm leading-6 text-charcoal/70">
              {arabic ? "بيانات المبيعات تُنشر من لوحة التحكم." : "Sales contact is published from the console."}
            </p>
          )}
        </div>
      </div>
      <div className="border-t border-line">
        <p className="mx-auto max-w-page px-4 py-4 text-sm text-charcoal/60 sm:px-6 lg:px-8">© {year} AxizPOS</p>
      </div>
      {ready ? (
        <div aria-hidden="true" style={{ height: "max(6rem, calc(env(safe-area-inset-bottom) + 5rem))" }} />
      ) : null}
    </footer>
  );
}
