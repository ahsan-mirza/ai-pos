import { SIGNUP_BUSINESS_CARDS, type SignupBusinessCard, type SignupState } from "@ai-pos/shared-types";
import { Check, Coffee, MailCheck, Sandwich, Shirt, ShoppingCart, Smartphone, Store, UtensilsCrossed, type LucideIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { ErrorNote } from "../../components/ui/Field";
import { ApiRequestError } from "../../lib/api";
import { signupApi, type SignupSession } from "./signupApi";

const ICONS: Record<string, LucideIcon> = {
  electronics_wholesale: Smartphone,
  wholesale_retail: Store,
  retail_fashion: Shirt,
  grocery: ShoppingCart,
  restaurant: UtensilsCrossed,
  cafe: Coffee,
  quick_service: Sandwich,
};

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
  const [card, setCard] = useState<SignupBusinessCard | null>(
    () => SIGNUP_BUSINESS_CARDS.find((option) => option.profile === initialProfile) ?? null,
  );
  const [subType, setSubType] = useState<string | null>(initialSubType);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const choose = async (profile: string, sub: string | null) => {
    setBusy(true);
    setError(null);
    try {
      onChosen(await signupApi.business(session, { profile, sub_type: sub }));
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Could not save your choice.");
    } finally {
      setBusy(false);
    }
  };

  const pick = (next: SignupBusinessCard) => {
    setCard(next);
    setSubType(next.subTypes[0]?.id ?? null);
    setError(null);
  };

  useEffect(() => {
    if (initialProfile === null) return;
    setCard(SIGNUP_BUSINESS_CARDS.find((option) => option.profile === initialProfile) ?? null);
    setSubType(initialSubType);
  }, [initialProfile, initialSubType]);

  const comingSoon = card !== null && card.subTypes.length === 0;

  return (
    <div>
      <h2 className="text-2xl font-semibold">What do you sell?</h2>
      <p className="mt-1 text-sm text-charcoal/60">We switch on the right modules. You can change them later in Settings.</p>
      <div className="mt-6 grid gap-3 sm:grid-cols-2" role="radiogroup" aria-label="Business type">
        {SIGNUP_BUSINESS_CARDS.map((option) => {
          const Icon = ICONS[option.profile] ?? Smartphone;
          const selected = card?.profile === option.profile;
          const soon = option.subTypes.length === 0;
          return (
            <button
              key={option.profile}
              type="button"
              role="radio"
              aria-checked={selected}
              onClick={() => pick(option)}
              className={`relative flex min-h-[132px] flex-col items-start rounded-3xl border-2 p-5 text-left transition-colors ${
                selected ? "border-accent bg-accent/5" : "border-line bg-white hover:border-charcoal/20"
              }`}
            >
              <span
                className={`flex h-11 w-11 items-center justify-center rounded-2xl ${
                  soon ? "bg-surface text-charcoal/40" : "bg-accent/10 text-accent"
                }`}
              >
                <Icon size={22} aria-hidden="true" />
              </span>
              <span className="mt-3 font-semibold">{option.label}</span>
              <span className="mt-0.5 text-sm text-charcoal/60">{option.description}</span>
              {soon ? (
                <span className="absolute right-4 top-4 rounded-full bg-surface px-2.5 py-1 text-[11px] font-semibold text-charcoal/60">
                  Coming soon
                </span>
              ) : null}
              {selected && !soon ? (
                <span className="absolute right-4 top-4 flex h-6 w-6 items-center justify-center rounded-full bg-accent text-white">
                  <Check size={14} aria-hidden="true" />
                </span>
              ) : null}
            </button>
          );
        })}
      </div>

      {card !== null && !comingSoon ? (
        <section className="mt-5 rounded-3xl border border-line bg-surface/60 p-5" aria-label="Kind of business">
          <p className="text-sm font-semibold">Which fits best?</p>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {card.subTypes.map((option, index) => (
              <label
                key={option.id}
                className={`flex cursor-pointer gap-3 rounded-2xl border-2 bg-white p-4 ${
                  card.subTypes.length % 2 === 1 && index === card.subTypes.length - 1 ? "sm:col-span-2" : ""
                } ${subType === option.id ? "border-accent" : "border-transparent"}`}
              >
                <input
                  type="radio"
                  name="sub-type"
                  value={option.id}
                  checked={subType === option.id}
                  onChange={() => setSubType(option.id)}
                  className="mt-1 accent-accent"
                />
                <span>
                  <span className="block text-sm font-semibold">{option.label}</span>
                  <span className="block text-xs text-charcoal/60">{option.description}</span>
                </span>
              </label>
            ))}
          </div>
        </section>
      ) : null}

      {comingSoon && card ? (
        <section className="mt-5 rounded-3xl border border-line bg-surface/60 p-5">
          <p className="text-sm font-semibold">{card.label} is on its way</p>
          <p className="mt-1 text-sm text-charcoal/60">
            Join the waitlist and we will email you the day it opens. Nothing is charged.
          </p>
        </section>
      ) : null}

      <ErrorNote message={error} />
      <div className="mt-6 flex justify-end">
        <button
          type="button"
          disabled={card === null || busy || (!comingSoon && subType === null)}
          onClick={() => card && void choose(card.profile, comingSoon ? null : subType)}
          className="h-12 rounded-2xl bg-accent px-8 font-semibold text-white transition-colors hover:bg-accent-hover disabled:opacity-40"
        >
          {busy ? "Saving…" : comingSoon ? "Join the waitlist" : "Continue"}
        </button>
      </div>
    </div>
  );
}

export function WaitlistStep({ state, onBack }: { state: SignupState; onBack: () => void }) {
  const card = SIGNUP_BUSINESS_CARDS.find((option) => option.profile === state.profile);
  return (
    <div className="mx-auto flex max-w-md flex-col items-center py-10 text-center">
      <span className="flex h-14 w-14 items-center justify-center rounded-full bg-accent/10 text-accent">
        <MailCheck size={26} aria-hidden="true" />
      </span>
      <h2 className="mt-5 text-2xl font-semibold">You are on the list</h2>
      <p className="mt-2 text-sm text-charcoal/60">
        We will email <strong>{state.email}</strong> as soon as {card?.label ?? "your business type"} is ready.
      </p>
      <button
        type="button"
        onClick={onBack}
        className="mt-8 rounded-full border border-gray-200 px-6 py-2.5 text-sm font-medium hover:bg-gray-50"
      >
        Choose another business type
      </button>
    </div>
  );
}
