import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { Category } from "@ai-pos/shared-types";
import { MoveModelsModal } from "./CategoriesPage";

const source = {
  id: "source",
  name: "Handsets",
  code: "HANDSETS",
  description: "",
  product_count: 1,
  created_at: "2026-11-27T00:00:00Z",
  is_active: true,
  sub_categories: [],
} satisfies Category;

describe("move models modal", () => {
  it("lists the assigned models and asks to move them before deleting", () => {
    const html = renderToStaticMarkup(
      <MoveModelsModal
        category={source}
        models={[{ id: "n1", name: "N1", brand_name: "Northwind", sub_category_name: "Phones" }]}
        destinations={[{ ...source, id: "audio", name: "Audio", code: "AUDIO" }]}
        onClose={() => undefined}
        onMoved={async () => undefined}
      />,
    );
    expect(html).toContain("Delete Handsets");
    expect(html).toContain("1 model is assigned.");
    expect(html).toContain("Northwind");
    expect(html).toContain("N1");
    expect(html).toContain("Phones");
    expect(html).toContain("Move Models &amp; Delete Category");
    expect(html).toContain("Choose a category");
  });

  it("explains that another active category is required", () => {
    const html = renderToStaticMarkup(
      <MoveModelsModal
        category={source}
        models={[
          { id: "n1", name: "N1", brand_name: "Northwind", sub_category_name: "Phones" },
          { id: "n2", name: "N2", brand_name: "Northwind", sub_category_name: "Phones" },
        ]}
        destinations={[]}
        onClose={() => undefined}
        onMoved={async () => undefined}
      />,
    );
    expect(html).toContain("2 models are assigned.");
    expect(html).toContain("Create another active category before moving these models.");
  });
});
