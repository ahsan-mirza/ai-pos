import { AxizTabs } from "@ai-pos/ui";
import type { InventoryTab } from "./tabs";

/**
 * Inventory section navigation for the register.
 * Selection stays in the page, which already chooses the open section.
 * The row uses the same underline tabs as Business Pro.
 */
export function InventoryTabNavigation({
  tabs,
  activeTab,
  onChange,
}: {
  tabs: readonly InventoryTab[];
  activeTab: string;
  onChange: (id: string) => void;
}) {
  return (
    <AxizTabs
      ariaLabel="Inventory sections"
      className="sticky top-0 z-10"
      listClassName="overscroll-x-contain"
      tabs={tabs.map((item) => ({ id: item.id, label: item.label }))}
      activeTab={activeTab}
      onChange={onChange}
    />
  );
}
