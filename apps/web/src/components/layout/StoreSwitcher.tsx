import { Store } from "lucide-react";
import { storeOptions } from "../../features/inventory/shared";
import { useStoreScope } from "../../lib/storeScope";
import { Select } from "../ui/Select";

export function StoreSwitcher({ className = "" }: { className?: string }) {
  const { stores, storeId, setStoreId, pinned } = useStoreScope();
  const options = [...(pinned ? [] : [{ value: "", label: "All stores" }]), ...storeOptions(stores)];
  return (
    <Select
      aria-label="Store"
      size="sm"
      icon={Store}
      className={className}
      value={storeId ?? ""}
      options={options}
      placeholder={pinned ? "Your store" : "All stores"}
      disabled={pinned}
      onChange={(next) => setStoreId(next === "" ? null : next)}
    />
  );
}
