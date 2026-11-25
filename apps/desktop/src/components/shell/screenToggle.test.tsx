import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { RegisterLayoutProvider } from "../RegisterLayout";
import type { CashierSession } from "../../lib/tauri";
import { HeaderBar } from "./HeaderBar";
import { ScreenModeProvider, ScreenToggleButton } from "./ScreenToggle";
import { ShellContext, type ShellValue } from "./ShellContext";
import { drawerButtonClass } from "./settingsEntry";

vi.mock("../../lib/tauri", async () => {
  const actual = await vi.importActual<typeof import("../../lib/tauri")>("../../lib/tauri");
  return { ...actual, inTauri: () => true };
});

const session = {
  user: {
    id: "cashier",
    username: "cashier",
    full_name: "Cashier",
    store_id: "store",
    role_name: "Cashier",
    permissions: [],
  },
  mode: "offline",
  unlocked_at: 1,
} as CashierSession;

function shell(): ShellValue {
  return {
    session,
    view: "checkout",
    busy: false,
    setBusy: () => undefined,
    drawerHeld: false,
    setDrawerHeld: () => undefined,
    setNotifier: () => undefined,
    catalogSummary: null,
    setCatalogSummary: () => undefined,
    registerStatus: null,
    setRegisterStatus: () => undefined,
    navigate: () => undefined,
    onSession: () => undefined,
  };
}

function navbar() {
  return renderToStaticMarkup(
    <RegisterLayoutProvider>
      <ScreenModeProvider>
        <ShellContext.Provider value={shell()}>
          <HeaderBar title="Checkout" sync={{ tone: "offline", label: "Offline", title: "Offline" }} />
        </ShellContext.Provider>
      </ScreenModeProvider>
    </RegisterLayoutProvider>,
  );
}

describe("navbar screen toggle", () => {
  it("uses one exit control while the window is full screen", () => {
    const html = renderToStaticMarkup(<ScreenToggleButton fullscreen onToggle={() => undefined} />);
    expect(html).toContain('aria-label="Exit Full Screen"');
    expect(html).toContain('title="Exit Full Screen"');
    expect(html).toContain('aria-pressed="true"');
    expect(html).toContain('aria-keyshortcuts="F11"');
    expect(html).toContain('data-screen-mode="full"');
    expect(html.match(/<button/g)).toHaveLength(1);
    expect(html).toContain(drawerButtonClass);
  });

  it("uses one enter control while the window is windowed", () => {
    const html = renderToStaticMarkup(<ScreenToggleButton fullscreen={false} onToggle={() => undefined} />);
    expect(html).toContain('aria-label="Enter Full Screen"');
    expect(html).toContain('title="Enter Full Screen"');
    expect(html).toContain('aria-pressed="false"');
    expect(html).toContain('data-screen-mode="window"');
    expect(html.match(/<button/g)).toHaveLength(1);
  });

  it("keeps language, theme, and the cash drawer beside a single screen control", () => {
    const html = navbar();
    expect(html).toContain('aria-label="Language"');
    expect(html).toContain('aria-label="Light theme"');
    expect(html).toContain('aria-label="Dark theme"');
    expect(html).toContain('aria-label="Open drawer"');
    expect(html.match(/data-pos-screen-toggle/g)).toHaveLength(1);
    expect(html).toContain('aria-label="Exit Full Screen"');
    expect(html).not.toContain('aria-label="Enter Full Screen"');
  });
});
