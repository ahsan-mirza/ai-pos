import { SIGNUP_BUSINESS_CARDS, type SignupBusinessCard, type SignupState, type SignupSubType } from "@ai-pos/shared-types";
import { useLocale } from "@ai-pos/ui";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
  Check,
  Coffee,
  Croissant,
  Laptop,
  MailCheck,
  Sandwich,
  Shirt,
  ShoppingBag,
  ShoppingCart,
  Smartphone,
  Store,
  Truck,
  UtensilsCrossed,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useState } from "react";
import { ErrorNote } from "../../components/ui/Field";
import { ApiRequestError } from "../../lib/api";
import {
  businessMotion,
  operatingModels,
  orderedCategories,
  selectionReady,
  setupPreview,
  subTypeAfterCategoryChange,
} from "./businessSelection";
import { signupApi, type SignupSession } from "./signupApi";
import { WizardFooter } from "./WizardFooter";

const ICONS: Record<string, LucideIcon> = {
  electronics_wholesale: Smartphone,
  wholesale_retail: Store,
  retail_fashion: Shirt,
  grocery: ShoppingCart,
  restaurant: UtensilsCrossed,
  cafe: Coffee,
  quick_service: Sandwich,
};

const MODEL_ICONS: Record<string, LucideIcon> = {
  electronics_mobile: Smartphone,
  electronics_computer: Laptop,
  electronics_b2b: Store,
  bakery_cafe: Croissant,
  cafe_delivery: Truck,
  cloud_kitchen: Truck,
  qsr_truck: Truck,
  wholesale_distribution: Truck,
  fashion_clothing: Shirt,
  fashion_footwear: ShoppingBag,
  grocery_shop: ShoppingCart,
};

function modelIcon(id: string, fallback: LucideIcon): LucideIcon {
  return MODEL_ICONS[id] ?? fallback;
}

export function BusinessStep({
  session,
  initialProfile,
  initialSubType,
  onChosen,
}: {
  session: SignupSession;
  initialProfile: string | null;
  initialSubType: string | null;
  onChosen: (state: SignupState) => void;
}) {
  const reduced = useReducedMotion() === true;
  const motionProps = businessMotion(reduced);
  const [card, setCard] = useState<SignupBusinessCard | null>(
    () => SIGNUP_BUSINESS_CARDS.find((option) => option.profile === initialProfile) ?? null,
  );
  const [subType, setSubType] = useState<string | null>(initialSubType);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { t } = useLocale();
  const compact = card !== null;
  const models = card ? operatingModels(card.profile) : [];
  const selectedModel = models.find((model) => model.id === subType) ?? null;
  const comingSoon = card !== null && models.length === 0;
  const ready = selectionReady(card?.profile ?? null, subType) && !busy;

  const choose = async (profile: string, sub: string | null) => {
    setBusy(true);
    setError(null);
    try {
      onChosen(await signupApi.business(session, { profile, sub_type: sub }));
    } catch (caught) {
      setError(t(caught instanceof ApiRequestError ? caught.message : "Could not save your choice."));
    } finally {
      setBusy(false);
    }
  };

  const pick = (next: SignupBusinessCard) => {
    setCard(next);
    setSubType((current) => subTypeAfterCategoryChange(next.profile, current));
    setError(null);
  };

  useEffect(() => {
    if (initialProfile === null) return;
    setCard(SIGNUP_BUSINESS_CARDS.find((option) => option.profile === initialProfile) ?? null);
    setSubType(initialSubType);
  }, [initialProfile, initialSubType]);

  return (
    <div className="flex min-h-0 flex-auto flex-col overflow-hidden">
      <div className="min-h-0 flex-auto overflow-y-auto overscroll-contain pr-0.5">
        <h2 className="text-lg font-semibold text-charcoal">{t("Choose your business type")}</h2>
        <p className="signup-step-help mt-0.5 text-xs leading-4 text-charcoal/60">
          {t("Pick the category closest to what you sell. You can change modules later in Settings.")}
        </p>
        <div className="mt-3 grid grid-cols-1 gap-2 min-[480px]:grid-cols-2" role="radiogroup" aria-label={t("Business type")}>
          {orderedCategories(card?.profile ?? null).map((option) => {
            const Icon = ICONS[option.profile] ?? Smartphone;
            const selected = card?.profile === option.profile;
            return (
              <motion.button
                key={option.profile}
                type="button"
                role="radio"
                aria-checked={selected}
                layout
                transition={motionProps}
                onClick={() => pick(option)}
                className={`relative flex items-center gap-2.5 rounded-xl border-2 text-left ${
                  compact ? "px-2.5 py-1.5" : "min-h-[68px] p-2.5"
                } ${selected ? "border-accent bg-accent/5" : "border-line bg-white hover:border-charcoal/20"}`}
              >
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent/10 text-accent">
                  <Icon size={18} aria-hidden="true" />
                </span>
                <span className="min-w-0 pr-5">
                  <span className="block text-sm font-semibold leading-4 text-charcoal">{t(option.label)}</span>
                  {compact ? null : (
                    <span className="mt-0.5 line-clamp-2 text-xs leading-4 text-charcoal/60">{t(option.description)}</span>
                  )}
                </span>
                {selected ? (
                  <span className="absolute right-2 top-2 flex h-5 w-5 items-center justify-center rounded-full bg-accent text-white">
                    <Check size={12} aria-hidden="true" />
                  </span>
                ) : null}
              </motion.button>
            );
          })}
        </div>

        <AnimatePresence initial={false}>
          {card !== null && !comingSoon ? (
            <motion.section
              key={card.profile}
              initial={reduced ? false : { opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={reduced ? undefined : { opacity: 0, y: 4 }}
              transition={motionProps}
              className="mt-3"
              aria-label={t("Operating model")}
            >
              <h3 className="text-sm font-semibold text-charcoal">{t("Which best describes how your business operates?")}</h3>
              <p className="signup-model-help mt-0.5 text-xs leading-4 text-charcoal/60">
                {t("Choose the setup that most closely matches your day-to-day operations.")}
              </p>
              <div className="mt-2 grid grid-cols-1 gap-2 min-[480px]:grid-cols-2" role="radiogroup" aria-label={t("Operating model")}>
                {models.map((option, index) => (
                  <ModelCard
                    key={option.id}
                    option={option}
                    selected={subType === option.id}
                    reduced={reduced}
                    delay={reduced ? 0 : Math.min(index, 4) * 0.03}
                    fallback={ICONS[card.profile] ?? Smartphone}
                    onSelect={() => setSubType(option.id)}
                  />
                ))}
              </div>
              {selectedModel ? <SetupPreview model={selectedModel} /> : null}
            </motion.section>
          ) : null}
        </AnimatePresence>

        {comingSoon && card ? (
          <section className="mt-3 rounded-xl border border-line bg-surface/60 p-3">
            <p className="text-sm font-semibold">{t("{label} is on its way", { label: t(card.label) })}</p>
            <p className="mt-1 text-xs text-charcoal/60">{t("Join the waitlist and we will email you the day it opens. Nothing is charged.")}</p>
          </section>
        ) : null}
        <ErrorNote message={error} />
      </div>
      <WizardFooter
        continueLabel={comingSoon ? "Join the waitlist" : "Continue"}
        busyLabel="Saving…"
        busy={busy}
        disabled={!ready}
        onContinue={() => card && void choose(card.profile, comingSoon ? null : subType)}
      />
    </div>
  );
}

function ModelCard({
  option,
  selected,
  reduced,
  delay,
  fallback,
  onSelect,
}: {
  option: SignupSubType;
  selected: boolean;
  reduced: boolean;
  delay: number;
  fallback: LucideIcon;
  onSelect: () => void;
}) {
  const { t } = useLocale();
  const Icon = modelIcon(option.id, fallback);
  return (
    <motion.label
      layout
      initial={reduced ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: reduced ? 0 : 0.28, delay, ease: [0.4, 0, 0.2, 1] }}
      className={`flex cursor-pointer items-start gap-2 rounded-xl border-2 bg-white p-2 ${selected ? "border-accent" : "border-line"}`}
    >
      <input
        type="radio"
        name="sub-type"
        value={option.id}
        checked={selected}
        onChange={onSelect}
        className="mt-1 accent-accent"
      />
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-accent/10 text-accent">
        <Icon size={16} aria-hidden="true" />
      </span>
      <span className="min-w-0">
        <span className="block text-sm font-semibold text-charcoal">
          {t(option.label)}
          {selected ? <span className="sr-only">{t(", selected")}</span> : null}
        </span>
        <span className="signup-model-copy mt-0.5 block text-xs leading-4 text-charcoal/60">{t(option.description)}</span>
      </span>
    </motion.label>
  );
}

function SetupPreview({ model }: { model: SignupSubType }) {
  const { t } = useLocale();
  const preview = setupPreview(model);
  const paid = t("Paid add-ons stay off until they are on your plan.");
  return (
    <div className="mt-2 rounded-xl border border-line bg-surface/70 p-2.5">
      <p className="text-sm font-semibold text-charcoal">{t("Your AxizPOS setup will include")}</p>
      <ul className="mt-2 flex flex-wrap gap-1.5">
        {preview.included.map((chip) => (
          <li key={chip} className="rounded-full bg-white px-2.5 py-1 text-xs font-medium text-charcoal ring-1 ring-line">
            {t(chip)}
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs leading-4 text-charcoal/60">{model.note ? `${t(model.note)} ${paid}` : paid}</p>
    </div>
  );
}

export function WaitlistStep({ state, onBack }: { state: SignupState; onBack: () => void }) {
  const { t } = useLocale();
  const card = SIGNUP_BUSINESS_CARDS.find((option) => option.profile === state.profile);
  return (
    <div className="flex min-h-0 flex-auto flex-col overflow-hidden">
      <div className="flex min-h-0 flex-auto flex-col items-center justify-center px-4 text-center">
        <span className="flex h-14 w-14 items-center justify-center rounded-full bg-accent/10 text-accent">
          <MailCheck size={26} aria-hidden="true" />
        </span>
        <h2 className="mt-5 text-xl font-semibold">{t("You are on the list")}</h2>
        <p className="mt-2 max-w-md text-sm text-charcoal/60">
          {t("We will email {email} as soon as {type} is ready.", {
            email: state.email,
            type: t(card?.label ?? "your business type"),
          })}
        </p>
      </div>
      <WizardFooter onBack={onBack} backLabel="Choose another type" />
    </div>
  );
}
