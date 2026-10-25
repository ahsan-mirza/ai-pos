import { profileSpec } from "@ai-pos/shared-types";
import { Keyboard } from "lucide-react";
import { terminal } from "../../config/terminal";
import { store } from "../../features/checkout/catalog";
import { useVirtualKeyboard } from "../../hooks/useVirtualKeyboard";
import { useCapabilities } from "../../lib/capabilities";
import { VirtualKeyboard } from "../common/VirtualKeyboard";

const connectionLabel: Record<string, string> = {
  wired: "USB",
  bluetooth: "Bluetooth",
  surface_cover: "Surface Cover",
  none: "",
};

/** Bottom register bar: hardware keyboard state, and a manual show/hide for the touch keyboard. */
export function KeyboardStatusBar() {
  const { status, enabled, layout, toggle, hide, press } = useVirtualKeyboard();
  const { profile } = useCapabilities();
  const activation = terminal();
  const spec = profileSpec(profile);
  const restaurantName = activation?.tenant_name || store.name;
  const physical = status.hasPhysicalKeyboard;
  const detail = connectionLabel[status.connectionType];

  return (
    <>
      <footer className="flex h-9 shrink-0 items-center justify-between gap-3 border-t border-slate-800 bg-slate-900 px-3">
        <p
          className="min-w-0 truncate text-xs text-slate-300"
          title={`${restaurantName} · ${spec.label} · ${store.code} · ${store.name}${activation?.register_code ? ` · ${activation.register_code}` : ""}`}
        >
          <span className="font-semibold text-slate-100">{restaurantName}</span>
          <span className="text-slate-500"> · </span>
          <span>{spec.shortLabel}</span>
        </p>
        <button
          type="button"
          onClick={toggle}
          aria-pressed={enabled}
          title={physical ? "A physical keyboard is connected. Click to show the touch keyboard." : "Touch mode. Click to hide the touch keyboard."}
          className="inline-flex h-7 shrink-0 items-center gap-2 rounded-full px-2 text-xs font-medium text-slate-300 hover:bg-slate-800"
        >
          <span className={`h-2 w-2 rounded-full ${physical ? "bg-emerald-500" : "bg-orange-500"}`} aria-hidden="true" />
          <Keyboard className="w-4 h-4 text-slate-400" />
          <span>{physical ? "Physical Keyboard" : "Touch Keyboard"}</span>
          {physical && detail ? <span className="text-slate-500">{detail}</span> : null}
        </button>
      </footer>
      {layout ? <VirtualKeyboard layout={layout} onKey={press} onHide={hide} /> : null}
    </>
  );
}
