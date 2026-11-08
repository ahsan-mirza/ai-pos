import { ModuleDirectory } from "@/features/modules/ModuleDirectory";
import { useI18n } from "@/i18n/I18nProvider";

export default function FinanceTab() {
  const { t } = useI18n();
  return <ModuleDirectory group="finance" title={t("finance")} />;
}
