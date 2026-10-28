import type { PublicHardware } from "../catalog";
import { aed } from "../catalog";
import { SectionHeading } from "./SectionHeading";

/** Published hardware from the console catalogue. Hidden when the live list is empty. */
export function HardwareShelf({
  items,
  live,
  onEnquire,
}: {
  items: PublicHardware[];
  live: boolean;
  onEnquire: (note: string) => void;
}) {
  if (!live || items.length === 0) return null;
  return (
    <section id="hardware" className="border-t border-line bg-canvas">
      <div className="mx-auto max-w-page px-4 py-16 sm:px-6 lg:px-8 lg:py-20">
        <SectionHeading kicker="Hardware" title="Registers and equipment you can lease or buy.">
          Only products an administrator has published. A deposit is paid once and is refundable. Lease rent is separate.
        </SectionHeading>
        <ul className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((item) => (
            <li key={item.id} className="flex flex-col overflow-hidden rounded-card border border-line bg-card">
              {item.image_url ? (
                <img src={item.image_url} alt="" className="h-40 w-full object-cover" />
              ) : (
                <div className="flex h-40 items-center justify-center bg-surface text-sm text-charcoal/40">No photo</div>
              )}
              <div className="flex flex-1 flex-col p-5">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">{item.category_name || item.sku}</p>
                <h3 className="mt-2 text-xl font-semibold text-charcoal">{item.name}</h3>
                {item.description ? <p className="mt-2 text-sm leading-6 text-charcoal/70">{item.description}</p> : null}
                <ul className="mt-4 space-y-1 text-sm text-charcoal/80">
                  {item.lease_available ? <li>Lease {aed(item.monthly_fils)} / month</li> : null}
                  {item.purchase_available && item.purchase_fils != null ? <li>Buy {aed(item.purchase_fils)}</li> : null}
                  {item.deposit_fils > 0 ? <li>Refundable deposit {aed(item.deposit_fils)}, charged once</li> : null}
                  {item.fee_fils > 0 ? <li>One-time fee {aed(item.fee_fils)}</li> : null}
                  {item.delivery_fils > 0 ? <li>Delivery {aed(item.delivery_fils)}</li> : null}
                </ul>
                <button
                  type="button"
                  onClick={() => onEnquire(`Hardware enquiry: ${item.name} (${item.sku})`)}
                  className="mt-auto inline-flex h-11 items-center justify-center rounded-2xl bg-primary px-4 text-sm font-semibold text-white"
                >
                  Enquire
                </button>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
