import { describe, expect, it } from "vitest";
import { isIssuedTag, isPlaceholderTag, keptServiceTag, openSession, orderHeader, type TableSession } from "./tableSessions";

function session(overrides: Partial<TableSession> = {}): TableSession {
  return {
    id: "c49bc0fc-bf6a-4b01-8ce8-aaca502032bd",
    tenant_id: "portion",
    store_id: "store",
    table_number: "Delivery",
    guest_count: 1,
    guest_name: "Portion Rider",
    address: "12 Acceptance Road",
    phone: "0502223344",
    order_mode: "delivery",
    status: "OPEN",
    server_order_id: null,
    server_revision: 0,
    created_at: "2026-11-22T21:00:00.000Z",
    updated_at: "2026-11-22T21:00:00.000Z",
    items: [],
    ...overrides,
  };
}

describe("delivery order header", () => {
  it("sends the guest phone and street address with a delivery ticket", () => {
    expect(orderHeader(session())).toEqual({
      name: "Portion Rider",
      covers: 1,
      deliveryPhone: "0502223344",
      deliveryAddress: "12 Acceptance Road",
    });
  });

  it("keeps zone and driver off the server address", () => {
    const packed = ["12 Acceptance Road", "City", "Sam", "18:00"].join("\u001f");
    expect(orderHeader(session({ address: packed })).deliveryAddress).toBe("12 Acceptance Road");
  });

  it("keeps an issued tag when the guest or pickup changes", () => {
    expect(isPlaceholderTag("Takeaway")).toBe(true);
    expect(isPlaceholderTag("")).toBe(true);
    expect(isIssuedTag("TW001")).toBe(true);
    expect(isIssuedTag("TW-AB12-001")).toBe(true);
    expect(isIssuedTag("TW1")).toBe(false);
    expect(keptServiceTag("TW001", "TW999", "takeaway")).toBe("TW001");
    expect(keptServiceTag("Takeaway", "TW002", "takeaway")).toBe("TW002");
    expect(keptServiceTag("TW1", "TW002", "takeaway")).toBe("TW1");
    const existing = session({ order_mode: "takeaway", table_number: "TW001", guest_name: "Amina" });
    const updated = openSession({
      storeId: existing.store_id,
      mode: "takeaway",
      tableNumber: "TW999",
      guestCount: 1,
      guestName: "Noura",
      phone: "0501111111",
      address: "18:30",
      existing,
    });
    expect(updated.id).toBe(existing.id);
    expect(updated.table_number).toBe("TW001");
    expect(updated.guest_name).toBe("Noura");
    expect(updated.phone).toBe("0501111111");
    const seated = openSession({
      storeId: existing.store_id,
      mode: "dine_in",
      tableNumber: "5",
      guestCount: 2,
      existing,
    });
    expect(seated.table_number).toBe("5");
  });

  it("does not treat a takeaway phone as a delivery address", () => {
    expect(orderHeader(session({ order_mode: "takeaway", table_number: "TW1" }))).toEqual({
      name: "Portion Rider",
      covers: 1,
    });
  });
});
