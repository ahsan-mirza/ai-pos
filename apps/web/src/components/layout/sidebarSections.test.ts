import assert from "node:assert/strict";
import test from "node:test";
import { revealSection, toggleSection } from "./sidebarSections.ts";

const sections = ["workspace", "sales", "wholesale", "finance", "administration"];

test("every section can stay open, and collapsing one leaves the rest", () => {
  let open = new Set<string>();
  for (const id of sections) open = toggleSection(open, id);
  assert.deepEqual([...open], sections);

  open = toggleSection(open, "finance");
  assert.equal(open.has("finance"), false);
  assert.deepEqual([...open], ["workspace", "sales", "wholesale", "administration"]);

  open = toggleSection(open, "finance");
  assert.equal(open.has("finance"), true);
  assert.equal(open.size, 5);
});

test("a route change opens the destination section and does not close the others", () => {
  const open = new Set(["workspace", "sales"]);
  const next = revealSection(open, "finance");
  assert.equal(next.has("workspace"), true);
  assert.equal(next.has("sales"), true);
  assert.equal(next.has("finance"), true);

  assert.equal(revealSection(next, "sales"), next);
  assert.equal(revealSection(next, null), next);
});
