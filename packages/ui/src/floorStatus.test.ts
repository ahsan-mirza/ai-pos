import { describe, expect, it } from "vitest";
import { aggregateService, floorCounts, matchesFloorFilter, tableTone, type FloorMatch } from "./floorStatus";

const open = (patch: Partial<FloorMatch>): FloorMatch => ({
  key: "t",
  areaId: "hall",
  search: "t-01",
  active: true,
  status: "seated",
  kitchen: "none",
  payment: "unpaid",
  ...patch,
});

describe("aggregateService", () => {
  it("keeps a future-less empty seat as a draft with no kitchen or payment", () => {
    expect(aggregateService(null)).toEqual({ kitchen: "none", payment: "none", orderProgress: "none" });
    expect(aggregateService({ sent: 0, marks: [], paid: 0, unpaid: 0, billRequested: false, hasItems: false })).toEqual({
      kitchen: "none",
      payment: "none",
      orderProgress: "draft",
    });
  });

  it("does not treat a sent order as preparing until a ticket is preparing", () => {
    expect(aggregateService({ sent: 2, marks: ["new", "new"], paid: 0, unpaid: 2, billRequested: false, hasItems: true })).toMatchObject({
      kitchen: "queued",
      payment: "unpaid",
      orderProgress: "submitted",
    });
    expect(aggregateService({ sent: 1, marks: [], paid: 0, unpaid: 1, billRequested: false, hasItems: true }).kitchen).toBe("queued");
  });

  it("separates kitchen, a partial ready pass, and payment", () => {
    const preparing = aggregateService({ sent: 2, marks: ["preparing", "new"], paid: 0, unpaid: 2, billRequested: false, hasItems: true });
    expect(preparing).toMatchObject({ kitchen: "preparing", payment: "unpaid", orderProgress: "in_progress" });
    const partial = aggregateService({ sent: 2, marks: ["ready", "preparing"], paid: 1, unpaid: 1, billRequested: false, hasItems: true });
    expect(partial).toMatchObject({ kitchen: "partial", payment: "partial" });
    const ready = aggregateService({ sent: 2, marks: ["ready", "bumped"], paid: 0, unpaid: 2, billRequested: true, hasItems: true });
    expect(ready).toMatchObject({ kitchen: "ready", payment: "pending" });
    const served = aggregateService({ sent: 1, marks: ["bumped"], paid: 1, unpaid: 0, billRequested: false, hasItems: true });
    expect(served).toMatchObject({ kitchen: "served", payment: "paid", orderProgress: "in_progress" });
  });
});

describe("tableTone", () => {
  it("paints payment and kitchen ahead of a plain occupied seat", () => {
    expect(tableTone({ active: true, status: "free", kitchen: "none", payment: "none", orderProgress: "none" })).toBe("available");
    expect(tableTone({ active: false, status: "free", kitchen: "none", payment: "none", orderProgress: "none" })).toBe("out");
    expect(tableTone({ active: true, status: "seated", kitchen: "none", payment: "unpaid", orderProgress: "draft" })).toBe("occupied");
    expect(tableTone({ active: true, status: "ordered", kitchen: "queued", payment: "unpaid", orderProgress: "submitted" })).toBe("preparing");
    expect(tableTone({ active: true, status: "ordered", kitchen: "preparing", payment: "unpaid", orderProgress: "in_progress" })).toBe("preparing");
    expect(tableTone({ active: true, status: "ordered", kitchen: "partial", payment: "unpaid", orderProgress: "in_progress" })).toBe("partial");
    expect(tableTone({ active: true, status: "ordered", kitchen: "ready", payment: "unpaid", orderProgress: "in_progress" })).toBe("ready");
    expect(tableTone({ active: true, status: "ordered", kitchen: "served", payment: "unpaid", orderProgress: "in_progress" })).toBe("served");
    expect(tableTone({ active: true, status: "bill", kitchen: "ready", payment: "pending", orderProgress: "in_progress" })).toBe("payment");
  });
});

describe("floor filters", () => {
  const items = [
    open({ key: "a", status: "free", payment: "none" }),
    open({ key: "s", status: "seated", kitchen: "none", payment: "unpaid" }),
    open({ key: "b", status: "ordered", kitchen: "preparing" }),
    open({ key: "p", status: "ordered", kitchen: "partial" }),
    open({ key: "c", status: "ordered", kitchen: "ready" }),
    open({ key: "v", status: "ordered", kitchen: "served", payment: "unpaid" }),
    open({ key: "d", status: "bill", payment: "pending" }),
    open({ key: "e", active: false, status: "free", payment: "none" }),
  ];

  it("counts each operational slice without collapsing them into occupancy", () => {
    expect(floorCounts(items)).toMatchObject({
      all: 8,
      available: 1,
      occupied: 1,
      preparing: 1,
      partial: 1,
      ready: 1,
      served: 1,
      payment: 1,
      out: 1,
    });
    expect(matchesFloorFilter("occupied", items[1]!)).toBe(true);
    expect(matchesFloorFilter("occupied", items[2]!)).toBe(false);
    expect(matchesFloorFilter("preparing", items[2]!)).toBe(true);
    expect(matchesFloorFilter("available", items[2]!)).toBe(false);
    expect(matchesFloorFilter("partial", items[3]!)).toBe(true);
    expect(matchesFloorFilter("ready", items[3]!)).toBe(false);
  });
});
