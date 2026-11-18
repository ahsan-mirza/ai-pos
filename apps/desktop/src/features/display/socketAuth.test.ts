import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const files = [
  "src/features/display/displayChannel.ts",
  "src/features/orders/tableSync.ts",
  "src/features/alerts/tableAlertClient.ts",
];

describe("desktop websocket authentication", () => {
  it("keeps the device token out of the socket URL", () => {
    for (const file of files) {
      const text = readFileSync(join(process.cwd(), file), "utf8");
      expect(text).not.toContain("?token=");
      expect(text).not.toContain("&token=");
      expect(text).toContain('type: "auth"');
    }
  });
});
