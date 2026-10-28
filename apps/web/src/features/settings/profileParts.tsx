import {
  CAPABILITIES,
  CAPABILITY_DEPENDENCIES,
  CAPABILITY_GROUP_LABELS,
  PROFILE_GROUP_LABELS,
  PROFILE_PRESETS,
  capabilitySpec,
  type BusinessProfile,
  type Capability,
  type CapabilityGroup,
  type CapabilitySpec,
  type OverrideState,
  type ProfileGroup,
} from "@ai-pos/shared-types";
import {
  Check,
  Coffee,
  Lock,
  Sandwich,
  Shirt,
  ShoppingBasket,
  Smartphone,
  Store,
  UtensilsCrossed,
  type LucideIcon,
} from "lucide-react";

export const PROFILE_ICONS: Record<BusinessProfile, LucideIcon> = {
  electronics_wholesale: Smartphone,
  wholesale_retail: Store,
  retail_fashion: Shirt,
  grocery: ShoppingBasket,
  restaurant: UtensilsCrossed,
  cafe: Coffee,
  quick_service: Sandwich,
};

const PROFILE_GROUPS = Object.keys(PROFILE_GROUP_LABELS) as ProfileGroup[];
const CAPABILITY_GROUPS = Object.keys(CAPABILITY_GROUP_LABELS) as CapabilityGroup[];

export function isFoodAndBeverage(profile: BusinessProfile): boolean {
  return PROFILE_PRESETS[profile].group === "food_beverage";
}

export function plannedModules(profile: BusinessProfile): string[] {
  return PROFILE_PRESETS[profile].capabilities
    .map(capabilitySpec)
    .filter((spec) => !spec.available)
    .map((spec) => spec.label.toLowerCase());
}

export function presetSelection(profile: BusinessProfile): Set<Capability> {
  return new Set(PROFILE_PRESETS[profile].capabilities);
}

export function sameSelection(a: ReadonlySet<Capability>, b: ReadonlySet<Capability>): boolean {
  return a.size === b.size && [...a].every((capability) => b.has(capability));
}

/** Turning a module on also turns on what it needs; turning one off also turns off what needs it. */
export function toggleModule(selected: ReadonlySet<Capability>, capability: Capability, on: boolean): Set<Capability> {
  const next = new Set(selected);
  const visit = (id: Capability) => {
    if (on ? next.has(id) : !next.has(id)) return;
    if (on) {
      next.add(id);
      CAPABILITY_DEPENDENCIES[id].forEach(visit);
    } else {
      next.delete(id);
      CAPABILITIES.filter((spec) => spec.requires.includes(id)).forEach((spec) => visit(spec.id));
    }
  };
  visit(capability);
  return next;
}

export function ProfilePicker({
  value,
  onChange,
  current,
}: {
  value: BusinessProfile;
  onChange: (profile: BusinessProfile) => void;
  current?: BusinessProfile;
}) {
  return (
    <div className="space-y-5">
      {PROFILE_GROUPS.map((group) => (
        <fieldset key={group}>
          <legend className="mb-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-charcoal/50">
            {PROFILE_GROUP_LABELS[group]}
          </legend>
          <div className="grid gap-3 sm:grid-cols-3">
            {Object.values(PROFILE_PRESETS)
              .filter((spec) => spec.group === group)
              .map((spec) => {
                const Icon = PROFILE_ICONS[spec.id];
                const selected = value === spec.id;
                return (
                  <label
                    key={spec.id}
                    className={`relative flex cursor-pointer flex-col rounded-2xl border p-4 transition ${
                      selected ? "border-accent bg-accent/5" : "border-line hover:bg-surface"
                    }`}
                  >
                    <input
                      type="radio"
                      name="business-profile"
                      value={spec.id}
                      checked={selected}
                      onChange={() => onChange(spec.id)}
                      className="sr-only"
                    />
                    <span className="flex items-center justify-between">
                      <span
                        className={`flex h-9 w-9 items-center justify-center rounded-xl ${
                          selected ? "bg-accent text-white" : "bg-surface text-charcoal/70"
                        }`}
                      >
                        <Icon size={18} aria-hidden="true" />
                      </span>
                      {spec.id === current ? (
                        <span className="rounded-full bg-charcoal px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-white">
                          Current
                        </span>
                      ) : selected ? (
                        <Check size={16} className="text-accent" aria-hidden="true" />
                      ) : null}
                    </span>
                    <span className="mt-3 text-sm font-semibold">{spec.label}</span>
                    <span className="mt-0.5 text-xs text-charcoal/60">{spec.description}</span>
                  </label>
                );
              })}
          </div>
        </fieldset>
      ))}
    </div>
  );
}

export function ComingSoonBadge() {
  return (
    <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-amber-800">
      Coming soon
    </span>
  );
}

export function ModuleList({
  selected,
  onToggle,
  disabled = false,
  visible,
  managed = {},
  included,
  prices,
}: {
  selected: ReadonlySet<Capability>;
  onToggle: (capability: Capability, on: boolean) => void;
  disabled?: boolean;
  /** Only these modules are listed (after onboarding: the ones that fit the business type). */
  visible?: ReadonlySet<Capability>;
  /** Set by IT support; shown but not switchable. */
  managed?: Partial<Record<Capability, OverrideState>>;
  /** Preset modules. An included module that is on shows an Included badge, never a price. */
  included?: ReadonlySet<Capability>;
  /** A price is shown only when the billing catalogue has an add-on with this module's code. */
  prices?: Partial<Record<Capability, string>>;
}) {
  const shown = (spec: CapabilitySpec) => visible === undefined || visible.has(spec.id);
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      {CAPABILITY_GROUPS.filter((group) => CAPABILITIES.some((spec) => spec.group === group && shown(spec))).map((group) => (
        <fieldset key={group}>
          <legend className="mb-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-charcoal/50">
            {CAPABILITY_GROUP_LABELS[group]}
          </legend>
          <ul className="divide-y divide-line rounded-2xl border border-line">
            {CAPABILITIES.filter((spec) => spec.group === group && shown(spec)).map((spec) => {
              const on = selected.has(spec.id);
              const locked = managed[spec.id] !== undefined;
              return (
                <li key={spec.id} className="flex items-center justify-between gap-4 p-3">
                  <span className="min-w-0">
                    <span className="flex flex-wrap items-center gap-2 text-sm font-medium">
                      {spec.label}
                      {spec.available ? null : <ComingSoonBadge />}
                      {included?.has(spec.id) && on ? (
                        <span className="rounded-full bg-accent/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-accent">
                          Included
                        </span>
                      ) : null}
                      {locked ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-charcoal/5 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-charcoal/60">
                          <Lock size={10} aria-hidden="true" /> Managed by support
                        </span>
                      ) : null}
                    </span>
                    <span className="block text-xs text-charcoal/60">{spec.description}</span>
                    {prices?.[spec.id] ? (
                      <span className="mt-0.5 block text-[11px] font-medium text-charcoal/70">{prices[spec.id]}</span>
                    ) : null}
                    {spec.requires.length > 0 ? (
                      <span className="mt-0.5 block text-[11px] text-charcoal/45">
                        Needs {spec.requires.map((id) => capabilitySpec(id).label).join(", ")}
                      </span>
                    ) : null}
                  </span>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={on}
                    aria-label={spec.available ? spec.label : `${spec.label} (coming soon: plan it now)`}
                    title={spec.available ? undefined : "Coming soon. Turning it on plans it; it switches on when it ships."}
                    disabled={disabled || locked}
                    onClick={() => onToggle(spec.id, !on)}
                    className={`relative h-7 w-12 shrink-0 rounded-full transition disabled:opacity-50 ${
                      on ? (spec.available ? "bg-accent" : "bg-amber-400") : "bg-neutral"
                    }`}
                  >
                    <span
                      className={`absolute top-1 h-5 w-5 rounded-full bg-white transition-all ${on ? "left-6" : "left-1"}`}
                    />
                  </button>
                </li>
              );
            })}
          </ul>
        </fieldset>
      ))}
    </div>
  );
}
