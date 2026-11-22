import { Permission } from "@ai-pos/shared-types";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { validateIntake, type DraftLine } from "./intakeModel";
import {
  defaultStation,
  openingStation,
  primaryTabs,
  registerPageLabel,
  registerPageTarget,
  secondaryTabs,
  sectionOf,
  workspaceDestinations,
} from "./laundryNav";
import { visibleStations } from "./productionAccess";
import { LaundryIntakePage } from "./LaundryIntakePage";
import { LaundrySectionBars } from "./ui";

const floor = [
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
];

function line(patch: Partial<DraftLine> = {}): DraftLine {
  return {
    key: "line-1",
    service_id: "dry",
    quantity: "1",
    garment_type: "Shirt",
    description: "",
    brand: "",
    colour: "",
    fabric: "",
    size: "",
    condition: "",
    stains: "",
    instructions: "",
    gross: "",
    tare: "",
    ...patch,
  };
}

describe("laundry orders navigation", () => {
  it("keeps Checkout for retail and uses Orders for a laundry business", () => {
    expect(registerPageLabel("retail", "checkout", "Checkout")).toBe("Checkout");
    expect(registerPageLabel("laundry", "checkout", "Checkout")).toBe("Orders");
    expect(registerPageTarget("retail", "checkout")).toBe("checkout");
    expect(registerPageTarget("laundry", "checkout")).toBe("laundry");
    expect(registerPageLabel("fnb", "orders", "Orders & Tables")).toBe("Orders & Tables");
  });

  it("puts laundry sections on one underline row and keeps production routes underneath", () => {
    const stations = visibleStations(floor);
    const html = renderToStaticMarkup(
      <LaundrySectionBars
        primary={primaryTabs()}
        secondary={secondaryTabs("orders", stations)}
        activePrimary="orders"
        activeSecondary="intake"
        onPrimary={() => undefined}
        onSecondary={() => undefined}
      />,
    );
    expect(primaryTabs().map((tab) => tab.label)).toEqual(["Orders", "Production", "Services", "Customers", "Reports"]);
    expect(html).not.toContain(">Settings<");
    expect(secondaryTabs("settings", stations)).toEqual([]);
    expect(html.match(/role="tablist"/g)?.length).toBe(2);
    expect(html).toContain("overflow-x-auto");
    expect(html).toContain("flex-nowrap");
    expect(html).toContain("h-12");
    expect(html).toContain("bg-[var(--tab-underline)]");
    expect(html).toContain(">Orders<");
    expect(html).toContain(">New Order<");
    expect(html).not.toContain("Daily operations");
    expect(html).not.toContain("rounded-2xl");
    expect(secondaryTabs("production", stations).map((tab) => tab.id)).toEqual([
      "scan",
      "sorting",
      "production",
      "machines",
      "quality",
      "rework",
      "packing",
      "incidents",
      "shift",
    ]);
    expect(secondaryTabs("services", stations).map((tab) => tab.label)).toEqual([
      "Laundry Services",
      "Service Categories",
      "Garment Types",
      "Service Pricing",
    ]);
    expect(secondaryTabs("orders", stations).some((tab) => tab.label === "Ready for Collection")).toBe(true);
    expect(sectionOf("intake")).toBe("orders");
    expect(sectionOf("sorting")).toBe("production");
    expect(sectionOf("shift")).toBe("reports");
    expect(defaultStation("orders", stations)).toBe("intake");
    expect(defaultStation("production", stations)).toBe("scan");
    expect(openingStation("", workspaceDestinations(floor).map((station) => station.id))).toBe("intake");
    expect(openingStation("#/laundry/sorting", stations.map((station) => station.id))).toBe("sorting");
    expect(openingStation("#/laundry/dashboard", stations.map((station) => station.id))).toBe("dashboard");
    expect(openingStation("#/laundry/intake", stations.map((station) => station.id))).toBe("intake");
  });

  it("keeps garment type separate from service and accepts piece and kilogram lines", () => {
    const services = [
      { id: "dry", name: "Dry Clean", pricing_unit: "PIECE" },
      { id: "iron", name: "Ironing", pricing_unit: "PIECE" },
      { id: "wash", name: "Wash & Fold", pricing_unit: "KG" },
    ];
    const errors = validateIntake({
      customerId: "customer",
      lines: [
        line({ key: "a", service_id: "dry", garment_type: "Shirt", quantity: "2" }),
        line({ key: "b", service_id: "iron", garment_type: "Shirt", quantity: "1" }),
        line({ key: "c", service_id: "wash", garment_type: "Bedsheet", quantity: "", gross: "2500", tare: "100" }),
      ],
      services,
      deposit: "500",
      discount: "",
      canDiscount: false,
    });
    expect(errors).toEqual({});
    const missing = validateIntake({
      customerId: "",
      lines: [line({ quantity: "0" })],
      services,
      deposit: "",
      discount: "",
      canDiscount: false,
    });
    expect(missing.customer).toBeTruthy();
    expect(missing["line-line-1-quantity"]).toBeTruthy();
  });

  it("keeps the intake actions in normal flow and does not offer a draft", () => {
    const html = renderToStaticMarkup(
      <LaundryIntakePage
        session={{
          mode: "online",
          unlocked_at: 1,
          user: {
            id: "user",
            username: "cashier",
            full_name: "Cashier",
            store_id: "store",
            role_name: "Cashier",
            permissions: [Permission.LaundryOrdersCreate],
          },
        }}
      />,
    );
    expect(html).not.toContain("Save draft");
    expect(html).not.toContain("server draft");
    expect(html).not.toContain("sticky bottom-0");
    expect(html).toContain("Create Laundry Order");
    expect(html).toContain("Create and print receipt");
    expect(html).toContain("Unlock the register to create the order");
    expect(html).toContain("disabled");
    expect(html).toContain("Express");
    expect(html).toContain("Special instructions");
  });
});
