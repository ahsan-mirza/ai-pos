import { Permission } from "@ai-pos/shared-types";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { RetailRequestError } from "../../lib/retailClient";
import { dashboardPhase, laundryCall, noticeFromError, registerSignedIn, sessionHeadline } from "./diagnostics";
import { filterReady, nextActionCopy, packingProgress, priorityWork, productionColumns, reworkRate, type FloorGarment } from "./floorModel";
import { nextScrollTop, scrollGeometry, TOUCH_MIN_PX } from "./shellScroll";
import { intakeCounts, intakePayload, validateIntake, type DraftLine } from "./intakeModel";
import { laundryStationFromLocation, resolveLaundryStation } from "./laundryRoute";
import { visibleStations } from "./productionAccess";
import { LaundryErrorState, LaundryMetricCard, LaundryStationNavigation, LaundrySyncStatus } from "./ui";

function garment(patch: Partial<FloorGarment> = {}): FloorGarment {
  return {
    id: "g1",
    order_id: "o1",
    order_code: "LD-1",
    customer_name: "Walk-in",
    description: "Shirt",
    stage: "SORTING",
    workflow_code: "WASH_FOLD",
    service_name: "Wash",
    colour: "Blue",
    fabric: "Cotton",
    condition: "Stain",
    instructions: "Cold",
    tag_code: "LD-1-01",
    hold: false,
    qc_result: "",
    rework_count: 0,
    promised_at: null,
    stage_entered_at: null,
    operational_status: "IN_PRODUCTION",
    total_cents: 1000,
    amount_paid_cents: 0,
    balance_due_cents: 1000,
    location: "Plant",
    ...patch,
  };
}

function line(patch: Partial<DraftLine> = {}): DraftLine {
  return {
    key: "line-1",
    service_id: "svc",
    quantity: "1",
    garment_type: "Shirt",
    description: "Blue shirt",
    brand: "",
    colour: "Blue",
    fabric: "Cotton",
    size: "M",
    condition: "",
    stains: "",
    instructions: "",
    gross: "",
    tare: "",
    ...patch,
  };
}

describe("laundry floor UX", () => {
  it("keeps laundry sections on one underline row and hides stations the user cannot open", () => {
    const stations = visibleStations([
      Permission.LaundryProductionView,
      Permission.LaundryOrdersCreate,
      Permission.LaundryProductionSort,
      Permission.LaundryProductionProcess,
      Permission.LaundryProductionFinish,
      Permission.LaundryQualityInspect,
      Permission.LaundryPacking,
      Permission.LaundryIncidentsReport,
      Permission.LaundryMachinesOperate,
      Permission.LaundryBatchesManage,
    ]);
    expect(stations.find((item) => item.id === "sorting")?.group).toBe("production");
    expect(stations.map((item) => item.id)).toEqual([
      "dashboard",
      "intake",
      "lookup",
      "scan",
      "sorting",
      "production",
      "machines",
      "quality",
      "rework",
      "packing",
      "ready",
      "incidents",
      "shift",
      "settings",
    ]);
    const sorter = visibleStations([Permission.LaundryProductionSort]);
    const html = renderToStaticMarkup(
      <LaundryStationNavigation stations={sorter} active="sorting" counts={{ sorting: 2 }} onSelect={() => undefined} />,
    );
    expect(html).toContain('role="tablist"');
    expect(html).toContain('aria-label="Laundry sections"');
    expect(html).toContain("overflow-x-auto");
    expect(html).toContain("flex-nowrap");
    expect(html).toContain("whitespace-nowrap");
    expect(html).toContain("h-12");
    expect(html).toContain("bg-[var(--tab-underline)]");
    expect(html).toContain('aria-selected="true"');
    expect(html).not.toContain("Daily operations");
    expect(html).not.toContain("Management");
    expect(html).not.toContain("rounded-2xl");
    expect(html).not.toContain("bg-zinc-900");
    expect(html).not.toContain("Machines");
    expect(resolveLaundryStation("#/laundry/sorting", sorter.map((item) => item.id))).toBe("sorting");
    expect(resolveLaundryStation("#/laundry/machines", sorter.map((item) => item.id))).toBe("dashboard");
    expect(laundryStationFromLocation("#/laundry/quality")).toBe("quality");
    expect(html.match(/role="tab"/g)?.length).toBe(sorter.length);
  });

  it("renders dashboard metrics from the numbers it is given", () => {
    const html = renderToStaticMarkup(<LaundryMetricCard label="Received Today" value={7} onOpen={() => undefined} />);
    expect(html).toContain("Received Today");
    expect(html).toContain(">7<");
  });

  it("explains a missing token separately from an unreachable API and from a real permission denial", () => {
    const session = noticeFromError(new RetailRequestError(401, "authentication_required", "This action requires a signed-in user.", "req-9"));
    expect(session.kind).toBe("unauthenticated");
    expect(session.requestId).toBe("req-9");
    expect(session.canRetry).toBe(false);
    expect(session.title).toMatch(/Unlock the register/);
    const devicePrincipal = noticeFromError(new RetailRequestError(403, "forbidden", "This action requires a signed-in user.", "req-device"));
    expect(devicePrincipal.kind).toBe("unauthenticated");
    expect(devicePrincipal.requestId).toBe("req-device");
    const denied = noticeFromError(new RetailRequestError(403, "forbidden", "You do not have permission for this action.", "req-403"));
    expect(denied.kind).toBe("forbidden");
    expect(denied.canRetry).toBe(false);
    expect(denied.title).toMatch(/not permitted/i);
    const missing = noticeFromError(new RetailRequestError(404, "not_found", "Order was not found.", "req-404"));
    expect(missing.kind).toBe("missing");
    const invalid = noticeFromError(new RetailRequestError(422, "invalid_request", "Quantity must be at least 1.", "req-422"));
    expect(invalid.kind).toBe("validation");
    const server = noticeFromError(new RetailRequestError(500, "server_error", "Traceback (most recent call last)", "req-500"));
    expect(server.kind).toBe("server");
    expect(server.kind).not.toBe("unauthenticated");
    expect(server.detail).not.toContain("Traceback");
    expect(server.serverMessage).toContain("Traceback");
    const offline = noticeFromError(new RetailRequestError(0, "offline", "The server is unreachable."), "sync");
    expect(offline.tone).toBe("offline");
    expect(offline.kind).toBe("offline");
    expect(offline.title).not.toMatch(/Synchronization failed/);
    const failed = noticeFromError(new Error("Queue rejected"), "sync");
    expect(failed.tone).toBe("sync");
    expect(failed.title).toBe("Synchronization failed");
    const html = renderToStaticMarkup(
      <LaundrySyncStatus api="API reachable" session="Not signed in" queue={1} sync="Sync failed" notice={sessionHeadline(false)} />,
    );
    expect(html).toContain("API reachable");
    expect(html).toContain("Not signed in");
    expect(html).toContain("does not replace that token");
    const alert = renderToStaticMarkup(<LaundryErrorState notice={session} />);
    expect(alert).toContain("req-9");
    expect(alert).toContain("Unlock the register");
    expect(alert).toContain("Support reference");
    expect(dashboardPhase({ signedIn: false, loaded: false, garmentCount: 0, notice: null })).toBe("signed-out");
    expect(dashboardPhase({ signedIn: false, offlineSession: true, loaded: false, garmentCount: 0, notice: null })).toBe("offline");
    expect(dashboardPhase({ signedIn: true, loaded: false, garmentCount: 0, notice: denied })).toBe("permission");
    expect(dashboardPhase({ signedIn: true, loaded: false, garmentCount: 0, notice: server })).toBe("failure");
    expect(dashboardPhase({ signedIn: true, loaded: false, garmentCount: 0, notice: offline })).toBe("offline");
    expect(dashboardPhase({ signedIn: true, loaded: false, garmentCount: 0, notice: null })).toBe("loading");
    expect(dashboardPhase({ signedIn: true, loaded: true, garmentCount: 0, notice: null })).toBe("empty");
    expect(dashboardPhase({ signedIn: true, loaded: true, garmentCount: 2, notice: null })).toBe("ready");
    expect(registerSignedIn("online")).toBe(false);
    expect(registerSignedIn("offline")).toBe(false);
  });

  it("validates intake before a duplicate submit and keeps the server payload", () => {
    const missing = validateIntake({ customerId: "", lines: [line({ quantity: "0" })], services: [{ id: "svc", name: "Fold", pricing_unit: "PIECE" }], deposit: "abc", discount: "", canDiscount: false });
    expect(missing.customer).toBeTruthy();
    expect(missing["line-line-1-quantity"]).toBeTruthy();
    expect(missing.deposit).toBeTruthy();
    const payload = intakePayload({
      clientId: "12345678",
      storeId: "store",
      customerId: "customer",
      orderType: "WALK_IN",
      promised: "",
      instructions: "",
      express: false,
      lines: [line()],
      services: [{ id: "svc", name: "Fold", pricing_unit: "PIECE" }],
      deposit: "",
      discount: "",
    });
    expect(payload.garments).toEqual([expect.objectContaining({ colour: "Blue", quantity: 1 })]);
    expect(intakeCounts([line(), line({ key: "bag", service_id: "kg", gross: "1000", tare: "100" })], [{ id: "svc", name: "Fold", pricing_unit: "PIECE" }, { id: "kg", name: "Bag", pricing_unit: "KG" }])).toEqual({ garments: 1, bags: 1, weight: 900 });
  });

  it("keeps packing incomplete until every garment is scanned and separates payment from ready", () => {
    expect(packingProgress(4, 3)).toEqual({ expected: 4, scanned: 3, remaining: 1, complete: false });
    expect(packingProgress(2, 2).complete).toBe(true);
    const now = Date.parse("2026-11-21T12:00:00Z");
    const ready = garment({ id: "ready", stage: "READY", operational_status: "READY_FOR_COLLECTION", balance_due_cents: 500 });
    const paid = garment({ id: "paid", stage: "READY", operational_status: "READY_FOR_COLLECTION", balance_due_cents: 0, amount_paid_cents: 1000 });
    const held = garment({ id: "held", stage: "READY", operational_status: "READY_FOR_COLLECTION", hold: true });
    expect(filterReady([ready, paid, held], "unpaid", now).map((item) => item.id)).toEqual(["ready", "held"]);
    expect(filterReady([ready, paid], "paid", now).map((item) => item.id)).toEqual(["paid"]);
    const late = garment({ promised_at: "2026-11-21T08:00:00Z", stage_entered_at: "2026-11-21T08:00:00Z", qc_result: "FAIL", rework_count: 1 });
    const work = priorityWork([late], now);
    expect(work.overdue).toHaveLength(1);
    expect(work.qcFailures).toHaveLength(1);
    expect(work.waiting).toHaveLength(1);
    expect(reworkRate([late, garment({ id: "g2" })])).toBe(50);
    const columns = productionColumns([late], ["RECEIVED", "TAGGED", "SORTING", "QUALITY_CHECK"]);
    expect(columns.find((column) => column.id === "SORTING")?.cards).toHaveLength(1);
  });

  it("scrolls a long floor without covering the last control and keeps a ready garment still", async () => {
    const box = { scrollHeight: 1800, clientHeight: 700, scrollTop: 0 };
    expect(scrollGeometry(box).overflows).toBe(true);
    const down = nextScrollTop(box, "PageDown");
    expect(down).toBeGreaterThan(0);
    const end = nextScrollTop({ ...box, scrollTop: down ?? 0 }, "End") ?? 0;
    expect(scrollGeometry({ ...box, scrollTop: end }).endReachesLast).toBe(true);
    expect(nextScrollTop(box, "a")).toBeNull();
    expect(TOUCH_MIN_PX).toBeGreaterThanOrEqual(44);
    expect(registerSignedIn()).toBe(false);
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    await expect(laundryCall("GET", "/api/v1/laundry/production/board")).rejects.toMatchObject({
      status: 401,
      code: "authentication_required",
    });
    expect(fetchMock).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
    expect(nextActionCopy("READY", [], "Already scanned")).toMatch(/production path is complete/i);
    expect(nextActionCopy("SORTING", ["WASHING"], "")).toMatch(/WASHING/);
    const denied = noticeFromError(new RetailRequestError(403, "forbidden", "Wrong branch."));
    expect(denied.title).toMatch(/not permitted/i);
    expect(denied.canRetry).toBe(false);
  });
});
