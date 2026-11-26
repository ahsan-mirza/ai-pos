import type { RegisterCapacity } from "@ai-pos/shared-types";

export function registerStatus(status: string | null | undefined): { label: string; live: boolean } {
  if (status === "active") return { label: "Active", live: true };
  if (status === "offline") return { label: "Offline", live: false };
  if (status === "revoked") return { label: "Revoked", live: false };
  return { label: "Activation pending", live: false };
}

/** Same series rule as the API: letters and digits from the branch code and the register code. */
export function invoiceSeriesPreview(storeCode: string, registerCode: string): string {
  const series = (value: string) => {
    const parts = value.toUpperCase().match(/[A-Z0-9]+/g);
    return parts && parts.length > 0 ? parts.join("-") : "STORE";
  };
  return `${series(storeCode)}-${series(registerCode)}`;
}

export function seatSummary(capacity: RegisterCapacity): string {
  if (capacity.limit === null || capacity.available === null) {
    return `${capacity.used} tills registered. This package does not cap registers.`;
  }
  if (capacity.available === 0) {
    const noun = capacity.limit === 1 ? "register" : "registers";
    return `This plan includes ${capacity.limit} ${noun}. Release an existing till or upgrade the package.`;
  }
  const seat = capacity.available === 1 ? "seat" : "seats";
  return `${capacity.used} of ${capacity.limit} tills in use. ${capacity.available} ${seat} available.`;
}
