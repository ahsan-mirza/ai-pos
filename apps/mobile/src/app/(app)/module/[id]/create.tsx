import { router, useLocalSearchParams } from "expo-router";
import { AppText } from "@/components/primitives/Text";
import { ScreenContainer } from "@/components/layout/Screen";
import { useI18n } from "@/i18n/I18nProvider";
import { moduleById } from "@/modules/catalog";
import { RecordForm } from "@/features/records/RecordForm";

export default function CreateRoute() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { t } = useI18n();
  const module = typeof id === "string" ? moduleById(id) : undefined;
  if (!module?.create) {
    return (
      <ScreenContainer scroll>
        <AppText>{t("notFound")}</AppText>
      </ScreenContainer>
    );
  }
  return <RecordForm module={module} onBack={() => router.back()} onDone={() => router.back()} />;
}
