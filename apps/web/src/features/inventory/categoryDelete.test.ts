import { describe, expect, it } from "vitest";
import { destinationCategories } from "./categoryDelete";
import type { Category } from "@ai-pos/shared-types";

function category(id: string, active: boolean | undefined = true): Category {
  return {
    id,
    name: id,
    code: id,
    description: "",
    product_count: 0,
    created_at: "2026-11-27T00:00:00Z",
    is_active: active,
    sub_categories: [],
  };
}

describe("destination categories", () => {
  it("keeps other active categories and drops the source and inactive ones", () => {
    const choices = destinationCategories(
      [category("source"), category("audio"), category("old", false), category("draft", undefined)],
      "source",
    );
    expect(choices.map((item) => item.id)).toEqual(["audio", "draft"]);
  });
});
