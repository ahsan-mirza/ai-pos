import { portalUrl } from "../env";

const SOLUTIONS = [
  ["Restaurant", "#solutions"],
  ["Café", "#solutions"],
  ["Retail", "#solutions"],
  ["Wholesale", "#solutions"],
  ["Fashion", "#solutions"],
  ["Electronics", "#solutions"],
] as const;

const PRODUCT = [
  ["Features", "#features"],
  ["How it works", "#how"],
  ["Pricing", "#pricing"],
  ["Contact", "#contact"],
] as const;

export function Footer({ whatsapp }: { whatsapp: string }) {
  const year = new Date().getFullYear();
  const digits = whatsapp.replace(/\D/g, "");

  return (
    <footer className="border-t border-line bg-card">
      <div className="mx-auto grid max-w-page gap-8 px-4 py-12 sm:px-6 md:grid-cols-2 lg:grid-cols-4 lg:px-8">
        <div>
          <img src="/brand/logo.svg" alt="AxizPOS" className="h-8 w-auto dark:hidden" />
          <img src="/brand/logo-white.svg" alt="" className="hidden h-8 w-auto dark:block" />
          <p className="mt-3 max-w-xs text-sm leading-6 text-charcoal/70">
            A point of sale and admin portal for restaurants, cafés, retail, fashion, grocery, and electronics wholesale.
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
                <a href={href} className="text-charcoal/75 hover:text-charcoal">
                  {label}
                </a>
              </li>
            ))}
            <li>
              <a href={portalUrl} className="text-charcoal/75 hover:text-charcoal">
                Sign In
              </a>
            </li>
          </ul>
        </div>
        <div>
          <h2 className="text-sm font-semibold text-charcoal">Contact</h2>
          {digits.length >= 8 ? (
            <a
              href={`https://wa.me/${digits}`}
              className="mt-3 inline-flex text-sm font-medium text-primary"
              target="_blank"
              rel="noopener noreferrer"
            >
              WhatsApp {whatsapp}
            </a>
          ) : (
            <p className="mt-3 text-sm leading-6 text-charcoal/70">Sales contact is the form on this page when WhatsApp is published.</p>
          )}
        </div>
      </div>
      <div className="border-t border-line">
        <p className="mx-auto max-w-page px-4 py-4 text-sm text-charcoal/60 sm:px-6 lg:px-8">© {year} AxizPOS</p>
      </div>
    </footer>
  );
}
