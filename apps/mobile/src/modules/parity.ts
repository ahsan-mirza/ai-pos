import type { PortalModule } from "@/modules/catalog";

/** How far the mobile screen goes. A screen that opens is not treated as a finished workflow. */
export type ParityStatus =
  | "native-functional"
  | "native-read"
  | "native-partial-write"
  | "specialized-web"
  | "device-or-public";

export interface ParityRow {
  status: ParityStatus;
  remaining: string;
}

const READ = "The list and the open record load the live API. Creating or changing a record stays on the portal.";

const OVERRIDES: Record<string, ParityRow> = {
  dashboard: { status: "native-functional", remaining: "Today's summary is the screen. Insight actions stay on their own modules." },
  account: { status: "native-functional", remaining: "Language, biometric unlock and sign-out use the session already stored on the device." },
  showcase: { status: "native-functional", remaining: "Sample controls only. It does not call business APIs." },
  customers: {
    status: "native-partial-write",
    remaining: "Create, contact update, cash card or transfer payments, credit hold, and statement send post to the customer API while B2B credit is on. Cheque payments stay on the portal.",
  },
  products: {
    status: "native-partial-write",
    remaining: "Create, optional opening stock, barcode or text lookup, name price or PLU update, and a library photo use the product API. Variants and serialized setup stay on the portal.",
  },
  expenses: {
    status: "native-partial-write",
    remaining: "Create, void, petty-cash top-up and petty-cash count post to the expenses API.",
  },
  "purchase-orders": {
    status: "native-partial-write",
    remaining: "Create, place, cancel and receive remaining non-serialized lines post to the purchase-order API. Serialized receiving stays on the portal.",
  },
  stock: {
    status: "native-partial-write",
    remaining: "Status filter and stock adjustment post to the inventory API, including a branch choice for a business-wide user. The adjustment is not queued offline.",
  },
  suppliers: {
    status: "native-partial-write",
    remaining: "Create posts name and contact to the supplier API. Import templates and batch upload stay on the portal.",
  },
  approvals: {
    status: "native-partial-write",
    remaining: "Approve and decline post to the approval API. Raising a new approval from the register stays on the device that asked.",
  },
  reach: {
    status: "native-partial-write",
    remaining: "Overview, conversations, campaigns, agent, templates, automations, outbox, analytics and credits load from the server. Connection status can be refreshed. Sending a campaign or replying in a thread stays on the portal. The app does not call Evolution or a local model.",
  },
  "floor-plan": { status: "specialized-web", remaining: "Live floor status loads. Drawing the floor plan stays on the portal." },
  pricing: { status: "specialized-web", remaining: "The pricing matrix payload loads. Editing the matrix stays on the portal." },
  journals: { status: "specialized-web", remaining: "Journal rows load. Posting a journal entry stays on the portal." },
  bank: { status: "specialized-web", remaining: "Bank accounts load. Statement import and matching stay on the portal." },
  einvoicing: { status: "specialized-web", remaining: "Invoice rows load. Submission stays on the portal." },
  deliveries: { status: "specialized-web", remaining: "Sales orders load. Proof-of-delivery signature capture stays on the portal." },
  settings: { status: "native-read", remaining: "Business settings load. The receipt designer stays on the portal." },
  kitchen: { status: "device-or-public", remaining: "Kitchen stations load for staff. The full-screen board still signs in with a device token at /kds." },
};

export function parityFor(module: PortalModule): ParityRow {
  return OVERRIDES[module.id] ?? { status: "native-read", remaining: READ };
}

export function parityIds(): string[] {
  return Object.keys(OVERRIDES);
}
