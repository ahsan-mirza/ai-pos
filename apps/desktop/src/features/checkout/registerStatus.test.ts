import { describe, expect, it } from "vitest";
import { registerHeaderStatus } from "./registerStatus";

describe("register header status", () => {
  const base = { desktop: true, detail: "queue" };

  it("keeps an empty queue from looking like an online session", () => {
    expect(registerHeaderStatus({ ...base, sessionMode: "online", apiReachable: true, pending: 0 }).label).toBe("Online · Queue clear");
    expect(registerHeaderStatus({ ...base, sessionMode: "offline", apiReachable: false, pending: 0 }).label).toBe("Offline · Queue clear");
    expect(registerHeaderStatus({ ...base, sessionMode: "offline", apiReachable: false, pending: 3 }).label).toBe("Offline · 3 pending");
    expect(registerHeaderStatus({ ...base, sessionMode: "offline", apiReachable: true, pending: 0 }).label).toBe(
      "Connection restored · Re-authenticate",
    );
    expect(registerHeaderStatus({ ...base, sessionMode: "offline", apiReachable: true, pending: 2 }).label).toBe(
      "Connection restored · 2 pending",
    );
    expect(registerHeaderStatus({ ...base, sessionMode: "online", apiReachable: true, pending: 2 }).label).toBe("Online · Sync pending");
    expect(registerHeaderStatus({ ...base, sessionMode: "online", apiReachable: true, pending: 0, failed: 1 }).label).toBe(
      "Online · 1 sync failed",
    );
    expect(registerHeaderStatus({ ...base, sessionMode: "online", apiReachable: true, pending: 1, failed: 2 }).label).toBe(
      "Online · Sync pending",
    );
  });
});
