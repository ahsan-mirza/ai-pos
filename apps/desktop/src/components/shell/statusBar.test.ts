import { describe, expect, it } from "vitest";
import { statusBarModel, type StatusBarInput } from "./statusBar";

const base: StatusBarInput = {
  activated: true,
  demo: false,
  desktop: true,
  sessionMode: "online",
  apiKnown: true,
  apiReachable: true,
  page: { tone: "live", label: "Online · Queue clear", title: "Queue is clear." },
  syncing: false,
  pending: 0,
  failed: 0,
  catalogSummary: "12 products",
  readiness: "OFFLINE_READY",
};

function labels(input: Partial<StatusBarInput> = {}): string[] {
  return statusBarModel({ ...base, ...input }).chips.map((chip) => chip.label);
}

describe("status bar", () => {
  it("shows online once when the queue is clear", () => {
    expect(labels()).toEqual(["Activated", "Online"]);
    expect(labels()).not.toContain("Live");
    expect(statusBarModel(base).summary).toBe("12 products");
  });

  it("shows demo instead of activated", () => {
    expect(labels({ demo: true }).slice(0, 1)).toEqual(["Demo"]);
  });

  it("shows not activated when this register has no terminal", () => {
    expect(labels({ activated: false }).slice(0, 1)).toEqual(["Not activated"]);
  });

  it("shows offline once when nothing is waiting", () => {
    expect(
      labels({
        sessionMode: "offline",
        apiReachable: false,
        page: { tone: "offline", label: "Offline · Queue clear", title: "Offline." },
      }),
    ).toEqual(["Activated", "Offline"]);
  });

  it("shows the waiting count while offline", () => {
    const model = statusBarModel({
      ...base,
      sessionMode: "offline",
      apiReachable: false,
      pending: 3,
      page: { tone: "offline", label: "Offline · 3 pending", title: "Waiting." },
    });
    expect(model.chips.map((chip) => chip.label)).toEqual(["Activated", "Offline", "Queue · {count} pending"]);
    expect(model.chips[2]?.vars).toEqual({ count: 3 });
  });

  it("asks for a fresh sign-in when the connection returns with an empty queue", () => {
    expect(
      labels({
        sessionMode: "offline",
        apiReachable: true,
        pending: 0,
        page: { tone: "pending", label: "Connection restored · Re-authenticate", title: "Sign in." },
      }),
    ).toEqual(["Activated", "Connection restored", "Re-authenticate"]);
  });

  it("shows the queue while sales are still waiting", () => {
    const model = statusBarModel({
      ...base,
      pending: 2,
      failed: 1,
      page: { tone: "pending", label: "Online · Sync pending", title: "Waiting." },
    });
    expect(model.chips.map((chip) => chip.label)).toEqual(["Activated", "Online", "Queue · {count} pending · {failed} failed"]);
    expect(model.chips[2]?.vars).toEqual({ count: 2, failed: 1 });
  });

  it("shows a conflict instead of a clear queue", () => {
    expect(labels({ pending: 0, failed: 0, conflicts: 1 })).toEqual(["Activated", "Online", "Queue · 1 conflict"]);
  });

  it("shows a failed queue when a batch was rejected and nothing is waiting", () => {
    expect(labels({ pending: 0, failed: 1 })).toEqual(["Activated", "Online", "Queue · 1 failed"]);
    expect(labels({ pending: 0, failed: 2 })[2]).toBe("Queue · {failed} failed");
  });

  it("shows syncing with a spinner while online and keeps the queue beside it", () => {
    const model = statusBarModel({ ...base, syncing: true, pending: 4, catalogSummary: "Syncing catalogue…" });
    expect(model.chips.map((chip) => chip.label)).toEqual(["Activated", "Online", "Syncing", "Queue · {count} pending"]);
    expect(model.chips.find((chip) => chip.label === "Syncing")?.spin).toBe(true);
    expect(model.summary).toBeNull();
  });

  it("treats a catalogue refresh phrase as syncing before the activity flag arrives", () => {
    expect(labels({ catalogSummary: "Syncing catalogue…", syncing: false })[2]).toBe("Syncing");
  });

  it("drops to offline when the API probe fails", () => {
    expect(labels({ apiReachable: false, pending: 0 })[1]).toBe("Offline");
  });

  it("checks the connection before the first probe on a page that publishes nothing", () => {
    expect(
      labels({
        apiKnown: false,
        apiReachable: false,
        page: null,
        pending: null,
        failed: null,
        catalogSummary: null,
      }),
    ).toEqual(["Activated", "Checking"]);
  });

  it("shows a setup or recovery status when the local baseline is not ready", () => {
    expect(labels({ readiness: "BOOTSTRAP_INCOMPLETE" })).toContain("Setup incomplete");
    expect(labels({ readiness: "REQUIRES_ONLINE_RECOVERY" })).toContain("Recovery required");
    expect(labels({ readiness: "OFFLINE_READY" })).not.toContain("Sync required");
  });

  it("does not repeat sync required when a sync chip is already showing", () => {
    expect(labels({ readiness: "ONLINE_SYNC_REQUIRED", pending: 2 })).not.toContain("Sync required");
    expect(labels({ readiness: "ONLINE_SYNC_REQUIRED", pending: 0, sessionMode: "online" })).toContain("Sync required");
  });

  it("keeps a search summary beside the chips", () => {
    expect(statusBarModel({ ...base, catalogSummary: 'Searching…' }).summary).toBe("Searching…");
  });
});
