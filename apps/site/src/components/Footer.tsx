import { portalUrl, signupUrl } from "../env";
import { whatsappChatUrl, whatsappDigits, whatsappReady, type PublicWhatsApp } from "../whatsapp";

const SOLUTIONS = [
  ["Restaurant POS system", "/restaurant-pos"],
  ["Café POS software", "/cafe-pos"],
  ["Retail POS system", "/retail-pos"],
  ["Wholesale POS software", "/wholesale-pos"],
  ["Fashion store POS", "/fashion-pos"],
  ["Electronics store POS", "/electronics-pos"],
  ["POS software UAE", "/pos-software-uae"],
] as const;

const PRODUCT = [
  ["AI", "#intelligence"],
  ["Features", "#features"],
  ["How it works", "#how"],
  ["Pricing", "#pricing"],
  ["Contact", "#contact"],
] as const;

export function Footer({ atHome = true, contact }: { atHome?: boolean; contact: PublicWhatsApp }) {
  const year = new Date().getFullYear();
  const ready = whatsappReady(contact);

  return (
    <footer className="border-t border-line bg-card">
      <div className="mx-auto grid max-w-page gap-8 px-4 py-12 sm:px-6 md:grid-cols-2 lg:grid-cols-4 lg:px-8">
        <div>
          <img src="/brand/logo.svg" alt="AxizPOS" width={137} height={32} className="h-8 w-auto dark:hidden" />
          <img src="/brand/logo-white.svg" alt="" width={137} height={32} className="hidden h-8 w-auto dark:block" />
          <p className="mt-3 max-w-xs text-sm leading-6 text-charcoal/70">
            An AI-powered point of sale and admin portal. Ask the store in English or Arabic, then sell from the same records.
          </p>
        </div>
        <div>
          <h2 className="text-sm font-semibold text-charcoal">Solutions</h2>
          <ul className="mt-3 space-y-2 text-sm">
            {SOLUTIONS.map(([label, href]) => (
              <li key={label}>
                <a href={href} className="text-charcoal/75 hover:text-charcoal">
                  {label}
                </a>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h2 className="text-sm font-semibold text-charcoal">Product</h2>
          <ul className="mt-3 space-y-2 text-sm">
            {PRODUCT.map(([label, href]) => (
              <li key={label}>
                <a href={atHome ? href : `/${href}`} className="text-charcoal/75 hover:text-charcoal">
                  {label}
                </a>
              </li>
            ))}
            <li>
              <a href={portalUrl} className="text-charcoal/75 hover:text-charcoal">
                Sign In
              </a>
            </li>
            <li>
              <a href={signupUrl} className="text-charcoal/75 hover:text-charcoal">
                Sign Up
              </a>
            </li>
          </ul>
        </div>
        <div>
          <h2 className="text-sm font-semibold text-charcoal">Contact</h2>
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
            <p className="mt-3 text-sm leading-6 text-charcoal/70">Sales contact is published from the console.</p>
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
