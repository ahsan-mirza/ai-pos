import { isValidImei } from "@ai-pos/shared-types";
import { X } from "lucide-react";
import { useEffect, useId, useState } from "react";

interface ImeiModalProps {
  productName: string;
  onClose: () => void;
  onConfirm: (value: string, kind: "imei" | "serial") => void;
  title?: string;
  description?: string;
  confirmLabel?: string;
  /** Returns an error message to keep the dialog open. */
  check?: (value: string, kind: "imei" | "serial") => string | null;
}

export function ImeiModal({
  productName,
  onClose,
  onConfirm,
  title = "Validate identifier",
  description = `${productName} requires an IMEI or serial number.`,
  confirmLabel = "Add to sale",
  check,
}: ImeiModalProps) {
  const titleId = useId();
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-backdrop" role="presentation">
      <div role="dialog" aria-modal="true" aria-labelledby={titleId} className="modal-card max-w-md">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id={titleId} className="text-xl font-semibold">
              {title}
            </h2>
            <p className="mt-0.5 text-sm text-charcoal/60 dark:text-zinc-400">{description}</p>
          </div>
          <button type="button" aria-label="Close" onClick={onClose} className="modal-close">
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        <form
          className="mt-5 space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            const cleaned = value.trim();
            let parsed: [string, "imei" | "serial"];
            if (/^\d{15}$/.test(cleaned)) {
              if (!isValidImei(cleaned)) {
                setError("That IMEI failed the Luhn check.");
                return;
              }
              parsed = [cleaned, "imei"];
            } else if (/^[A-Za-z0-9-]{4,64}$/.test(cleaned)) {
              parsed = [cleaned.toUpperCase(), "serial"];
            } else {
              setError("Enter a 15-digit IMEI or a serial of 4 to 64 letters, numbers, or hyphens.");
              return;
            }
            const problem = check?.(...parsed) ?? null;
            if (problem !== null) {
              setError(problem);
              return;
            }
            onConfirm(...parsed);
          }}
        >
          <input
            autoFocus
            data-scan="true"
            value={value}
            onChange={(event) => {
              setValue(event.target.value);
              setError(null);
            }}
            inputMode="text"
            className="modal-input tabular-nums"
            placeholder="IMEI or serial"
          />
          {error ? <p role="alert" className="text-sm font-medium text-red-600 dark:text-red-400">{error}</p> : null}
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="modal-cancel">
              Cancel
            </button>
            <button type="submit" className="modal-save">
              {confirmLabel}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
