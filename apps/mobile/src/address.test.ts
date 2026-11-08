import { ADDRESS_MAX_LENGTH, addressError, normalizeAddress } from "@ai-pos/shared-types";

const samples = [
  "Shop 12, Building A, Main Street",
  "Office #204, Al Nahda 2, Dubai",
  "House No. 25-B, Street 10, DHA Phase 6, Lahore",
  "Unit 4/5, Block-C, Industrial Area",
  "Flat 12, Sheikh Zayed Road, Dubai, UAE",
  "شارع الشيخ زايد، دبي",
  "O'Brien's Shop",
  "Suite (12) Tower",
  "Marks & Spencer, Mall",
  "Shop  12,  Main  Street",
  "Étage 3, Rue de l'Université",
  "Building 15, Floor 2, Apt. 304",
];

describe("store address", () => {
  test.each(samples)("keeps %s", (sample) => {
    const pasted = `  ${sample}  `;
    expect(addressError(pasted, true)).toBeUndefined();
    expect(normalizeAddress(pasted)).toBe(sample);
    expect(normalizeAddress(pasted)).not.toMatch(/^[a-z0-9-]+$/);
  });

  test("rejects an empty required address and whitespace", () => {
    expect(addressError("", true)).toBe("Enter the store address.");
    expect(addressError("   ", true)).toBe("Enter the store address.");
    expect(addressError("   ", false)).toBe("Enter the store address.");
    expect(addressError("", false)).toBeUndefined();
  });

  test("rejects an address over the maximum length", () => {
    const value = "a".repeat(ADDRESS_MAX_LENGTH + 1);
    expect(addressError(value, true)).toBe("Use 255 characters or fewer.");
    expect(addressError("a".repeat(ADDRESS_MAX_LENGTH), true)).toBeUndefined();
  });

  test("preserves internal spaces and punctuation", () => {
    expect(normalizeAddress("  Shop  12, #204  ")).toBe("Shop  12, #204");
  });
});
