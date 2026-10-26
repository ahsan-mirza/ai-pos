import { useCallback, useState } from "react";
import type { FieldErrors } from "./validation";

export function focusFirstInvalid(root: ParentNode | null): void {
  const field = root?.querySelector<HTMLElement>('[aria-invalid="true"]');
  if (!field) return;
  field.scrollIntoView({ block: "nearest" });
  field.focus();
}

/** Field errors shown under inputs, plus one message for failures that are not tied to a field. */
export function useFormValidation() {
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);

  const clearField = useCallback((name: string) => {
    setErrors((current) => {
      if (!current[name]) return current;
      const next = { ...current };
      delete next[name];
      return next;
    });
  }, []);

  const apply = useCallback((next: FieldErrors) => {
    setErrors(next);
    return Object.keys(next).length === 0;
  }, []);

  return { errors, formError, setFormError, setErrors, clearField, apply };
}
