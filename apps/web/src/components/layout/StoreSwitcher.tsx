import { useLocale } from "@ai-pos/ui";
import { Store } from "lucide-react";
import { storeOptions } from "../../features/inventory/shared";
import { useStoreScope } from "../../lib/storeScope";
import { Select } from "../ui/Select";

export function StoreSwitcher({ className = "" }: { className?: string }) {
  const { t } = useLocale();
  const { stores, storeId, setStoreId, pinned } = useStoreScope();
  const options = [...(pinned ? [] : [{ value: "", label: t("All stores") }]), ...storeOptions(stores)];
  return (
    <Select
      aria-label={t("Store")}
      size="sm"
      icon={Store}
      className={className}
      value={storeId ?? ""}
      options={options}
      placeholder={pinned ? t("Your store") : t("All stores")}
      disabled={pinned}
      onChange={(next) => setStoreId(next === "" ? null : next)}
    />
  );
}
