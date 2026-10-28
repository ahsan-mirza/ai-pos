import type { AvailabilityResult, SlugCheck } from "@ai-pos/shared-types";
import {
  AvailabilityStatus,
  PhoneField,
  emailError,
  normalizeStoreName,
  phoneError,
  storeNameError,
  toE164,
  useAvailabilityCheck,
  type AvailabilityState,
} from "@ai-pos/ui";
import type { CountryCode } from "libphonenumber-js";
import { TextField } from "../../components/ui/Field";
import { AnimatedAvailabilityCheck } from "./AnimatedAvailabilityCheck";
import { signupApi } from "./signupApi";

export function useEmailAvailability(value: string) {
  return useAvailabilityCheck<AvailabilityResult>({
    value,
    isValid: (next) => emailError(next, true) === undefined,
    normalize: (next) => next.trim().toLowerCase(),
    check: (normalized, signal) => signupApi.emailAvailability(normalized, signal),
  });
}

export function usePhoneAvailability(value: string) {
  return useAvailabilityCheck<AvailabilityResult>({
    value,
    isValid: (next) => phoneError(next, true) === undefined,
    normalize: (next) => toE164(next) || next.trim(),
    check: (normalized, signal) => signupApi.phoneAvailability(normalized, signal),
  });
}

/** Display names are not unique, so this confirms the name locally and does not call the API. */
export function useStoreNameAvailability(value: string) {
  return useAvailabilityCheck<{ available: boolean }>({
    value,
    isValid: (next) => storeNameError(next, true) === undefined,
    normalize: normalizeStoreName,
    check: () => Promise.resolve({ available: true }),
  });
}

export function useSlugAvailability(slug: string) {
  return useAvailabilityCheck<SlugCheck>({
    value: slug,
    isValid: (next) => next.length > 0,
    normalize: (next) => next,
    check: (normalized, signal) => signupApi.slugCheck(normalized, signal),
  });
}

export function EmailAvailabilityField({
  value,
  onChange,
  status,
  onRetry,
}: {
  value: string;
  onChange: (value: string) => void;
  status: AvailabilityState;
  onRetry: () => void;
}) {
  const syntax = value.includes("@") ? emailError(value, false) : undefined;
  const taken = status === "unavailable" ? "This email is already registered." : undefined;
  const shown = syntax || taken ? "idle" : status;
  return (
    <div>
      <TextField
        label="Email"
        type="email"
        autoComplete="email"
        value={value}
        error={syntax || taken}
        onChange={(event) => onChange(event.target.value)}
        endAdornment={<AnimatedAvailabilityCheck show={shown === "available"} />}
        required
      />
      <AvailabilityStatus
        status={shown}
        availableText="This email is available."
        unavailableText="This email is already registered."
        errorText="We couldn't check this email."
        onRetry={onRetry}
      />
    </div>
  );
}

export function PhoneAvailabilityField({
  value,
  onChange,
  country,
  onCountryChange,
  status,
  onRetry,
}: {
  value: string;
  onChange: (value: string) => void;
  country: string;
  onCountryChange: (iso: string) => void;
  status: AvailabilityState;
  onRetry: () => void;
}) {
  const taken = status === "unavailable" ? "This mobile number is already registered." : undefined;
  const shown = taken ? "idle" : status;
  return (
    <div>
      <PhoneField
        label="Mobile number"
        value={value}
        onChange={onChange}
        selectedCountry={country as CountryCode}
        onCountryChange={onCountryChange}
        error={taken}
        hint="Saved on your account. The code is sent by email."
        endAdornment={<AnimatedAvailabilityCheck show={shown === "available"} />}
        required
      />
      <AvailabilityStatus
        status={shown}
        availableText="This number is available. It is not verified yet."
        unavailableText="This mobile number is already registered."
        errorText="We couldn't check this number."
        onRetry={onRetry}
      />
    </div>
  );
}

export function StoreNameAvailabilityField({
  value,
  onChange,
  status,
  onRetry,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  status: AvailabilityState;
  onRetry: () => void;
  placeholder?: string;
}) {
  const syntax = storeNameError(value, false);
  return (
    <div>
      <TextField
        label="Store name"
        value={value}
        error={syntax}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        hint={syntax ? undefined : "Shown on receipts. Other stores can use the same name."}
        required
      />
      <AvailabilityStatus
        status={syntax ? "idle" : status}
        availableText="You can use this name."
        unavailableText="This name cannot be used."
        errorText="We couldn't check this name."
        onRetry={onRetry}
      />
    </div>
  );
}
