import { ModuleDirectory } from "@/features/modules/ModuleDirectory";
import { useI18n } from "@/i18n/I18nProvider";

export default function InventoryTab() {
  const { t } = useI18n();
  return <ModuleDirectory group="inventory" title={t("inventory")} />;
}
