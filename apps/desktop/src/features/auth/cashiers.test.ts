import { describe, expect, it } from "vitest";
import { directoryStorageKey, parseDirectory } from "./cashiers";

describe("cashier directory cache", () => {
  it("keeps a directory for one branch and drops a broken payload", () => {
    expect(directoryStorageKey("store-a")).not.toBe(directoryStorageKey("store-b"));
    const cards = parseDirectory(
      JSON.stringify([
        { id: "1", display_name: "Ahsan Khalil", initials: "AK", role_label: "Cashier", avatar_url: null },
        { id: "2" },
      ]),
    );
    expect(cards).toHaveLength(1);
    expect(cards[0]?.display_name).toBe("Ahsan Khalil");
    expect(parseDirectory("{")).toEqual([]);
    expect(JSON.stringify(cards[0])).not.toContain("pin");
  });
});
