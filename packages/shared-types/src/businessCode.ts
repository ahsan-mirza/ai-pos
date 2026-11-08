/**
 * Display name for the tenant sign-in code.
 * The saved value stays `tenant.slug` (`settings.store_code`). Branch codes are a different field.
 */

export type BusinessCodeLocale = "en" | "ar";

type Kind = "store" | "restaurant" | "cafe";

/** Restaurant and quick service share a label. Café is its own. Every other profile stays "Store code". */
export function businessCodeKind(profile: string | null | undefined): Kind {
  if (profile === "restaurant" || profile === "quick_service") return "restaurant";
  if (profile === "cafe") return "cafe";
  return "store";
}

const LABEL: Record<Kind, Record<BusinessCodeLocale, string>> = {
  store: { en: "Store code", ar: "رمز المتجر" },
  restaurant: { en: "Restaurant code", ar: "رمز المطعم" },
  cafe: { en: "Café code", ar: "رمز المقهى" },
};

const PLURAL: Record<Kind, Record<BusinessCodeLocale, string>> = {
  store: { en: "Store codes", ar: "رموز المتاجر" },
  restaurant: { en: "Restaurant codes", ar: "رموز المطاعم" },
  cafe: { en: "Café codes", ar: "رموز المقاهي" },
};

export function businessCodeLabel(profile: string | null | undefined, locale: BusinessCodeLocale = "en"): string {
  return LABEL[businessCodeKind(profile)][locale];
}

export function businessCodeLabelPlural(profile: string | null | undefined, locale: BusinessCodeLocale = "en"): string {
  return PLURAL[businessCodeKind(profile)][locale];
}

export type BusinessCodePhrase =
  | "enter"
  | "enterExample"
  | "find"
  | "yours"
  | "afterCode"
  | "useWithPassword"
  | "noneLinked"
  | "staff"
  | "copyFailed"
  | "missing"
  | "activateHint"
  | "placeholder"
  | "hintRegister"
  | "signInWith"
  | "ask"
  | "portal"
  | "portalHost"
  | "enterKey"
  | "connects"
  | "typeExample"
  | "expired"
  | "copy"
  | "copied"
  | "keyCopyFailed";

/** English sentence used as the i18n key. Pass it through `t()` on web and the register. */
export function businessCodePhrase(profile: string | null | undefined, phrase: BusinessCodePhrase): string {
  const name = businessCodeLabel(profile).toLowerCase();
  const names = businessCodeLabelPlural(profile);
  switch (phrase) {
    case "enter":
      return `Enter the ${name}.`;
    case "enterExample":
      return `Enter the ${name}. The grey text in that box is only an example.`;
    case "find":
      return `Find your ${name}`;
    case "yours":
      return `Your ${names.toLowerCase()}`;
    case "afterCode":
      return `We email a 6-digit code. ${names} are shown only after that code is accepted.`;
    case "useWithPassword":
      return `Use a ${name} with your email and password. This does not sign you in.`;
    case "noneLinked":
      return `No ${name} is linked to this email.`;
    case "staff":
      return "Your staff sign in with this code.";
    case "copyFailed":
      return `Could not copy the ${name}. Select it and copy it manually.`;
    case "missing":
      return "The business code could not be loaded.";
    case "activateHint":
      return `On the new register, enter this ${name}, then paste the key. The key works once.`;
    case "placeholder":
      return `Enter your ${name}`;
    case "hintRegister":
      return "Same code you enter when activating a register.";
    case "signInWith":
      return `Sign in there with ${name}`;
    case "ask":
      return `Ask your manager for the ${name} and key.`;
    case "portal":
      return `Open the admin portal and sign in with the ${name}.`;
    case "portalHost":
      return `Open the admin portal at http://{host} and sign in with the ${name}.`;
    case "enterKey":
      return `Enter the ${name} and key here. The key works once, for 24 hours.`;
    case "connects":
      return `Connects as ${name}`;
    case "typeExample":
      return `Type the ${name}. The grey text is only an example.`;
    case "expired":
      return "This activation key has expired.";
    case "copy":
      return "Copy";
    case "copied":
      return "Copied";
    case "keyCopyFailed":
      return "Could not copy the activation key. Select it and copy it manually.";
  }
}

/**
 * The code shown and copied in register activation.
 * Only the saved tenant sign-in code is accepted. A branch code, a name, or a host is not a substitute.
 */
export function activationBusinessCode(storeCode: string | null | undefined): string | null {
  const code = storeCode?.trim() ?? "";
  return code.length > 0 ? code : null;
}
