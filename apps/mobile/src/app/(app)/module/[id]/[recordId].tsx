import { router, useLocalSearchParams } from "expo-router";
import { AppText } from "@/components/primitives/Text";
import { ScreenContainer } from "@/components/layout/Screen";
import { useI18n } from "@/i18n/I18nProvider";
import { moduleById } from "@/modules/catalog";
import { rememberedRow } from "@/features/records/memory";
import { RecordDetail } from "@/features/records/RecordDetail";

export default function RecordRoute() {
  const { id, recordId } = useLocalSearchParams<{ id: string; recordId: string }>();
  const { t } = useI18n();
  const module = typeof id === "string" ? moduleById(id) : undefined;
  if (!module || typeof recordId !== "string") {
    return (
      <ScreenContainer scroll>
        <AppText>{t("notFound")}</AppText>
      </ScreenContainer>
    );
  }
  return <RecordDetail module={module} id={recordId} seed={rememberedRow(module.id, recordId)} onBack={() => router.back()} />;
}
