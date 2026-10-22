import { useState } from "react";

/** "Computers & Laptops" -> "COMPUTERS-LAPTOPS". Matches the API's code rule: letters, digits and dashes. */
export function codeFromName(name: string, maxLength = 32): string {
  return name
    .toUpperCase()
    .trim()
    .replace(/[^A-Z0-9\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, maxLength)
    .replace(/-$/, "");
}

/** Sanitises a code as it is typed, keeping a trailing dash so the user can keep typing. */
export function cleanCode(value: string, maxLength = 32): string {
  return value
    .toUpperCase()
    .replace(/[^A-Z0-9\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-/, "")
    .slice(0, maxLength);
}

/**
 * Code that follows the name until the user types their own. Clearing the code hands control back to the name.
 * An existing code counts as manual, so renaming a saved record never silently changes its code.
 */
export function useAutoCode(name: string, initial = "", maxLength = 32) {
  const [typed, setTyped] = useState(initial);
  const [isCodeManuallyEdited, setManual] = useState(initial !== "");
  const code = isCodeManuallyEdited ? typed : codeFromName(name, maxLength);
  const setCode = (value: string) => {
    const next = cleanCode(value, maxLength);
    setTyped(next);
    setManual(next !== "");
  };
  return { code, setCode, isCodeManuallyEdited };
}
