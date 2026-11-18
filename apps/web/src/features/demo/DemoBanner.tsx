import { Info } from "lucide-react";
import { useAuth } from "../../lib/auth";

/** Shown for a demo session only. The server still enforces what that account may do. */
export function DemoBanner() {
  const { demo, logout } = useAuth();
  if (demo === null) return null;
  return (
    <div className="border-b border-warning/40 bg-[#fff7ed] px-4 py-3 text-charcoal">
      <div className="mx-auto flex max-w-6xl flex-col gap-2">
        <div className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">
            <span className="shrink-0 rounded-md bg-warning px-2 py-0.5 text-[11px] font-semibold tracking-wide text-white">DEMO MODE</span>
            <strong className="truncate text-sm">AxizPOS Demo {demo.businessName}</strong>
          </div>
          <Info className="shrink-0 text-charcoal/50" size={16} aria-hidden="true" />
        </div>
        <p className="text-xs text-charcoal/70">
          You are exploring a shared demonstration environment. Changes may be visible to other visitors and the environment may be reset.
        </p>
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs text-charcoal/60">Restricted demo access</p>
          <button type="button" className="text-sm font-semibold text-charcoal underline-offset-2 hover:underline" onClick={logout}>
            Exit Demo
          </button>
        </div>
      </div>
    </div>
  );
}
