import { PROFILE_PRESETS, capabilitySpec, isCapability, type BusinessProfile, type Capability } from "@ai-pos/shared-types";
import { motion } from "framer-motion";
import { useState, type ReactNode } from "react";
import type { PublicCatalog } from "../catalog";
import { signupUrl } from "../env";
import {
  BUSINESS_TYPE_ORDER,
  priceLabel,
  profileModules,
  profilesFor,
  publicModulePrices,
  requirementLabel,
} from "../modules";
import { IconBadge, type MarkName } from "./icons";
import { lift, rise, stagger, viewport } from "./motion";
import { SectionHeading } from "./SectionHeading";

const BENEFITS: { title: string; icon: MarkName; body: string }[] = [
  {
    title: "Start with the essentials",
    icon: "setup",
    body: "Get the core capabilities appropriate for your business type and subscription.",
  },
  {
    title: "Add specialized features",
    icon: "layers",
    body: "Choose compatible optional modules for your industry and operational needs.",
  },
  {
    title: "Grow without unnecessary complexity",
    icon: "growth",
    body: "Expand your system incrementally instead of automatically paying for capabilities you do not currently need.",
  },
];

const COMPARISON: { consideration: string; approach: string }[] = [
  { consideration: "Starting out", approach: "Begin with the appropriate core capabilities" },
  { consideration: "Feature selection", approach: "Add compatible optional modules when required" },
  { consideration: "Business growth", approach: "Expand the supported functionality incrementally" },
  { consideration: "Cost planning", approach: "Review the applicable plan and add-on prices" },
  { consideration: "Business fit", approach: "Select features appropriate to your business type" },
];

export function Modules({ catalog }: { catalog: PublicCatalog }) {
  const [profile, setProfile] = useState<BusinessProfile>("electronics_wholesale");
  const spec = PROFILE_PRESETS[profile];
  const { included, optional } = profileModules(profile);
  const prices = publicModulePrices(catalog.addons);
  const priced = catalog.addons.filter((addon) => addon.active && priceLabel(addon));

  return (
    <section id="modules" className="border-t border-line bg-surface">
      <div className="mx-auto max-w-page px-4 py-16 sm:px-6 lg:px-8 lg:py-20">
        <SectionHeading kicker="Modules" title="The Right Features for Your Business">
          AxizPOS gives your business the essential tools to get started, with compatible add-on modules available when you need more. Expand your capabilities as your business grows.
        </SectionHeading>
        <p className="mt-4 max-w-2xl text-base font-medium leading-7 text-charcoal">
          Start with the essentials for your business. Add specialized capabilities when you need them.
        </p>

        <motion.div
          className="mt-8 grid gap-4 lg:grid-cols-3"
          initial="hidden"
          whileInView="show"
          viewport={viewport}
          variants={stagger}
        >
          {BENEFITS.map((item) => (
            <motion.article key={item.title} variants={rise} whileHover={lift} className="rounded-card border border-line bg-card p-5">
              <IconBadge name={item.icon} />
              <h3 className="text-lg font-semibold text-charcoal">{item.title}</h3>
              <p className="mt-2 text-sm leading-6 text-charcoal/75">{item.body}</p>
            </motion.article>
          ))}
        </motion.div>

        <div className="mt-10">
          <h3 className="text-lg font-semibold text-charcoal">Included and optional, by business type</h3>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-charcoal/70">
            Included modules are the starter set for that business type. Optional modules are the other capabilities that type is allowed to use. A starter module is never shown as a paid add-on. A price appears only when the public catalog lists one.
          </p>
          <div role="radiogroup" aria-label="Business type" className="mt-4 flex gap-2 overflow-x-auto pb-1">
            {BUSINESS_TYPE_ORDER.map((id) => {
              const selected = id === profile;
              return (
                <button
                  key={id}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  onClick={() => setProfile(id)}
                  className={`inline-flex h-11 shrink-0 items-center rounded-2xl border px-4 text-sm font-semibold ${
                    selected ? "border-primary bg-primary/10 text-primary" : "border-line bg-card text-charcoal"
                  }`}
                >
                  {PROFILE_PRESETS[id].label}
                </button>
              );
            })}
          </div>

          <div className="mt-4 rounded-card border border-line bg-card p-5">
            <h4 className="text-lg font-semibold text-charcoal">{spec.label}</h4>
            <p className="mt-1 text-sm leading-6 text-charcoal/70">{spec.description}</p>
            <div className="mt-5 grid gap-6 lg:grid-cols-2">
              <ModuleColumn title="Included with this business type" empty="This business type has no starter modules.">
                {included.map((id) => (
                  <ModuleRow key={id} capability={id} kind="included" prices={prices[id]} />
                ))}
              </ModuleColumn>
              <ModuleColumn title="Optional for this business type" empty="Every compatible module is already in the starter set.">
                {optional.map((id) => (
                  <ModuleRow key={id} capability={id} kind="optional" prices={prices[id]} />
                ))}
              </ModuleColumn>
            </div>
          </div>
        </div>

        <div className="mt-10">
          <h3 className="text-2xl font-semibold tracking-tight text-charcoal sm:text-3xl">Flexible Features. Smarter Spending.</h3>
          <p className="mt-3 max-w-2xl text-base leading-7 text-charcoal/70">
            The modular approach can help a business avoid paying upfront for optional capabilities it does not currently need. Other point-of-sale products package features differently, and their prices vary by provider.
          </p>
          <div className="mt-6 overflow-x-auto rounded-card border border-line bg-card">
            <table className="w-full min-w-[36rem] text-left text-sm">
              <caption className="sr-only">How AxizPOS plans features as a business grows</caption>
              <thead>
                <tr className="border-b border-line">
                  <th scope="col" className="px-5 py-3 font-semibold text-charcoal">
                    Consideration
                  </th>
                  <th scope="col" className="px-5 py-3 font-semibold text-charcoal">
                    AxizPOS modular approach
                  </th>
                </tr>
              </thead>
              <tbody>
                {COMPARISON.map((row) => (
                  <tr key={row.consideration} className="border-b border-line last:border-b-0">
                    <th scope="row" className="px-5 py-3 font-medium text-charcoal">
                      {row.consideration}
                    </th>
                    <td className="px-5 py-3 text-charcoal/75">{row.approach}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-charcoal/70">
            This is not a savings guarantee. Plan prices and any priced add-on stay on the pricing section, taken from the catalog.
          </p>
        </div>

        <div className="mt-10">
          <h3 id="addon-catalog" className="text-lg font-semibold text-charcoal">
            Available add-ons
          </h3>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-charcoal/70">
            These are the optional add-ons in the public catalog. Each one is available now. A product module is listed only when that add-on is configured to sell it.
          </p>
          <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {priced.map((addon) => {
              const modules = addon.module_keys.filter(isCapability);
              const types = businessTypesFor(modules);
              return (
                <article key={addon.code} className="flex flex-col rounded-card border border-line bg-card p-5">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Optional</p>
                  <h4 className="mt-2 text-lg font-semibold text-charcoal">{addon.name}</h4>
                  <p className="mt-2 flex-1 text-sm leading-6 text-charcoal/75">{addon.description}</p>
                  <p className="mt-3 text-sm font-semibold text-charcoal">{priceLabel(addon)}</p>
                  {modules.length > 0 ? (
                    <p className="mt-2 text-sm leading-6 text-charcoal/70">
                      Includes {modules.map((key) => capabilitySpec(key).label).join(", ")}.
                      {types ? ` Fits ${types}.` : ""}
                    </p>
                  ) : (
                    <p className="mt-2 text-sm leading-6 text-charcoal/70">Does not add a separate product module.</p>
                  )}
                </article>
              );
            })}
          </div>
        </div>

        <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:flex-wrap">
          <a
            href={signupUrl}
            className="inline-flex h-12 items-center justify-center rounded-2xl bg-primary px-5 text-sm font-semibold text-white hover:bg-primary-hover"
          >
            Start your free trial
          </a>
          <a
            href="#features"
            className="inline-flex h-12 items-center justify-center rounded-2xl border border-line bg-card px-5 text-sm font-semibold text-charcoal"
          >
            Explore features
          </a>
          <a
            href="#addon-catalog"
            className="inline-flex h-12 items-center justify-center rounded-2xl border border-line bg-card px-5 text-sm font-semibold text-charcoal"
          >
            View available modules
          </a>
          <a
            href="#contact"
            className="inline-flex h-12 items-center justify-center rounded-2xl border border-line bg-card px-5 text-sm font-semibold text-charcoal"
          >
            Contact us
          </a>
        </div>
      </div>
    </section>
  );
}

function businessTypesFor(keys: Capability[]): string {
  const names = new Set<string>();
  for (const key of keys) {
    for (const profile of profilesFor(key)) names.add(PROFILE_PRESETS[profile].shortLabel);
  }
  return [...names].join(", ");
}

function ModuleColumn({ title, empty, children }: { title: string; empty: string; children: ReactNode }) {
  const items = Array.isArray(children) ? children : [children];
  const filled = items.some((item) => item != null && item !== false);
  return (
    <div>
      <h5 className="text-sm font-semibold text-charcoal">{title}</h5>
      {filled ? <ul className="mt-3 divide-y divide-line rounded-2xl border border-line">{children}</ul> : <p className="mt-3 text-sm text-charcoal/70">{empty}</p>}
    </div>
  );
}

function ModuleRow({
  capability,
  kind,
  prices,
}: {
  capability: Parameters<typeof capabilitySpec>[0];
  kind: "included" | "optional";
  prices: { addonName: string; label: string }[] | undefined;
}) {
  const spec = capabilitySpec(capability);
  const needs = requirementLabel(capability);
  const fits = profilesFor(capability)
    .map((id) => PROFILE_PRESETS[id].shortLabel)
    .join(", ");
  return (
    <li className="p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium text-charcoal">{spec.label}</span>
        {kind === "included" ? (
          <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-primary">
            Included
          </span>
        ) : (
          <span className="rounded-full border border-line px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-charcoal/70">
            Optional
          </span>
        )}
        {spec.available ? (
          <span className="text-[10px] font-semibold uppercase tracking-wider text-charcoal/50">Available</span>
        ) : (
          <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-amber-800">
            Coming soon
          </span>
        )}
      </div>
      <p className="mt-1 text-sm leading-6 text-charcoal/70">{spec.description}</p>
      <p className="mt-1 text-xs leading-5 text-charcoal/55">Fits {fits}.</p>
      {needs ? <p className="mt-1 text-xs text-charcoal/55">{needs}</p> : null}
      {kind === "optional" && prices && prices.length > 0 ? (
        <p className="mt-1 text-xs font-medium text-charcoal/75">
          {prices.map((price) => `${price.addonName}: ${price.label}`).join(" · ")}
        </p>
      ) : null}
      {kind === "optional" && (!prices || prices.length === 0) ? (
        <p className="mt-1 text-xs text-charcoal/55">No separate public price. Confirm it with the plan.</p>
      ) : null}
    </li>
  );
}
