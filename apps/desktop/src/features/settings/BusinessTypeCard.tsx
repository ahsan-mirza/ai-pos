import { capabilitySpec, profileSpec } from "@ai-pos/shared-types";
import { LayoutGrid } from "lucide-react";
import { ui } from "../../components/shell/tokens";
import { useCapabilities } from "../../lib/capabilities";

/** What this register is set up for. Read-only: the business type and its modules are chosen in the admin portal. */
export function BusinessTypeCard() {
  const { profile, enabled, practice } = useCapabilities();
  const spec = profileSpec(profile);
  const modules = [...enabled].map((capability) => capabilitySpec(capability).label);
  return (
    <section aria-labelledby="business-type-title" className={`rounded-2xl border p-6 xl:col-span-2 ${ui.panel} ${ui.border}`}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary text-white">
            <LayoutGrid size={20} aria-hidden="true" />
          </span>
          <div>
            <h2 id="business-type-title" className="text-lg font-semibold">
              {spec.label}
            </h2>
            <p className={`text-sm ${ui.muted}`}>{spec.description}</p>
          </div>
        </div>
        {practice ? (
          <span className="rounded-full bg-amber-500/10 px-3 py-1 text-xs font-semibold text-amber-800 ring-1 ring-amber-500/25 dark:text-amber-300">
            Practice mode
          </span>
        ) : null}
      </div>
      <p className={`mt-5 ${ui.label}`}>Modules on this register</p>
      {modules.length > 0 ? (
        <ul className="mt-2 flex flex-wrap gap-2">
          {modules.map((label) => (
            <li key={label} className={`rounded-full px-3 py-1 text-xs font-medium ring-1 ring-zinc-200 dark:ring-zinc-700 ${ui.surface}`}>
              {label}
            </li>
          ))}
        </ul>
      ) : (
        <p className={`mt-2 text-sm ${ui.muted}`}>Core selling only.</p>
      )}
      <p className={`mt-4 text-xs ${ui.muted}`}>
        The business type and its modules are changed in the admin portal under {spec.settingsLabel}; this register picks
        them up on its next sync.
      </p>
    </section>
  );
}
