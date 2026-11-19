import { Select, type SelectOption } from "@ai-pos/ui";

/** The Business Pro searchable dropdown, including inline creation when the caller is allowed to add a record. */
export function CreatableLookupField<T extends string>({
  label,
  error,
  hint,
  required = false,
  ...props
}: {
  label: string;
  error?: string;
  hint?: string;
  required?: boolean;
  value: T;
  options: readonly SelectOption<T>[];
  onChange: (value: T) => void;
  placeholder?: string;
  disabled?: boolean;
  onCreate?: (name: string) => void;
  createMinLength?: number;
  createHint?: string;
}) {
  return (
    <div className="block text-sm">
      <span className="mb-1.5 block font-medium text-zinc-800 dark:text-zinc-100">
        {label}
        {required ? <span className="text-red-600"> *</span> : null}
      </span>
      <Select {...props} searchable invalid={Boolean(error)} />
      {error ? (
        <span role="alert" className="mt-1.5 block text-xs font-medium text-red-700">
          {error}
        </span>
      ) : hint ? (
        <span className="mt-1.5 block text-xs text-zinc-500">{hint}</span>
      ) : null}
    </div>
  );
}
