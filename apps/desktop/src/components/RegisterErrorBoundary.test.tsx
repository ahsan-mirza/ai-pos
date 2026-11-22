import { Permission } from "@ai-pos/shared-types";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { LaundryWorkspace } from "../features/laundry/LaundryWorkspace";
import type { CashierSession } from "../lib/tauri";
import { RegisterLayoutProvider } from "./RegisterLayout";
import { RegisterErrorBoundary, RegisterFailure } from "./RegisterErrorBoundary";
import { ShellContext, type ShellValue } from "./shell/ShellContext";

function session(): CashierSession {
  return {
    user: {
      id: "admin",
      username: "laundry-admin",
      full_name: "Laundry Admin",
      store_id: "branch-a",
      role_name: "Super Admin",
      permissions: Object.values(Permission),
    },
    mode: "online",
    unlocked_at: 1,
  };
}

describe("register screen recovery", () => {
  it("shows the thrown message instead of an empty document", () => {
    const html = renderToStaticMarkup(<RegisterFailure message="Laundry board failed." />);
    expect(html).toContain("This screen stopped");
    expect(html).toContain("Laundry board failed.");
    expect(html).toContain("Reload register");
  });

  it("turns a render error into that recovery state", () => {
    expect(RegisterErrorBoundary.getDerivedStateFromError(new Error("missing stage"))).toEqual({
      message: "missing stage",
    });
    expect(RegisterErrorBoundary.getDerivedStateFromError("x").message).toMatch(/stopped/i);
  });

  it("renders the laundry floor without throwing", () => {
    const shell: ShellValue = {
      session: session(),
      view: "laundry",
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
    };
    const html = renderToStaticMarkup(
      <RegisterLayoutProvider>
        <ShellContext.Provider value={shell}>
          <LaundryWorkspace session={session()} />
        </ShellContext.Provider>
      </RegisterLayoutProvider>,
    );
    expect(html).toContain("data-laundry-scroll");
    expect(html).toContain(">Orders<");
    expect(html).not.toContain(">Settings<");
    expect(html).toContain("Open drawer");
  });
});
