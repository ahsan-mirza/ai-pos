import { Keyboard } from "lucide-react";
import { VirtualKeyboard } from "../common/VirtualKeyboard";
import { useVirtualKeyboard } from "../../hooks/useVirtualKeyboard";

const connectionLabel: Record<string, string> = {
  wired: "USB",
  bluetooth: "Bluetooth",
  surface_cover: "Surface Cover",
  none: "",
};

/** Bottom register bar: hardware keyboard state, and a manual show/hide for the touch keyboard. */
export function KeyboardStatusBar() {
  const { status, enabled, layout, toggle, hide, press } = useVirtualKeyboard();
  const physical = status.hasPhysicalKeyboard;
  const detail = connectionLabel[status.connectionType];

  return (
    <>
      <footer className="flex h-9 shrink-0 items-center justify-end border-t border-slate-800 bg-slate-900 px-3">
        <button
          type="button"
          onClick={toggle}
          aria-pressed={enabled}
          title={physical ? "A physical keyboard is connected. Click to show the touch keyboard." : "Touch mode. Click to hide the touch keyboard."}
          className="inline-flex h-7 items-center gap-2 rounded-full px-2 text-xs font-medium text-slate-300 hover:bg-slate-800"
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
