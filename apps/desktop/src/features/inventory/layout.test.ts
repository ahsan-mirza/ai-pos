import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { inventoryTabListClass, inventoryTableClass, inventoryTableFrameClass, inventoryWorkspaceClass } from "./layout";

function windowDrop(name: string): boolean | undefined {
  const path = fileURLToPath(new URL(`../../../src-tauri/${name}`, import.meta.url));
  const config = JSON.parse(readFileSync(path, "utf8")) as { app?: { windows?: Array<{ dragDropEnabled?: boolean }> } };
  return config.app?.windows?.[0]?.dragDropEnabled;
}

describe("inventory layout at 1024px", () => {
  it("keeps the workspace inside the pane", () => {
    expect(inventoryWorkspaceClass).toContain("min-w-0");
    expect(inventoryWorkspaceClass).toContain("max-w-full");
  });

  it("wraps section tabs instead of clipping them", () => {
    expect(inventoryTabListClass).toContain("flex-wrap");
    expect(inventoryTabListClass).toContain("min-w-0");
    expect(inventoryTabListClass).not.toContain("overflow-x-auto");
  });

  it("leaves file drops with the product photo control", () => {
    expect(windowDrop("tauri.conf.json")).toBe(false);
    expect(windowDrop("tauri.inventory-acceptance.conf.json")).toBe(false);
  });

  it("lets the product table scroll inside its frame", () => {
    expect(inventoryTableFrameClass).toContain("overflow-x-auto");
    expect(inventoryTableFrameClass).toContain("max-w-full");
    expect(inventoryTableClass).toContain("w-full");
  });
});
