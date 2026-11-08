import { Redirect } from "expo-router";
import { LoginScreen } from "@/features/auth/LoginScreen";
import { LoadingBlock } from "@/components/feedback/Feedback";
import { useAuth } from "@/auth/AuthProvider";
import { useI18n } from "@/i18n/I18nProvider";

export default function Index() {
  const { status } = useAuth();
  const { t } = useI18n();
  if (status === "checking") return <LoadingBlock label={t("loading")} />;
  if (status === "signed-out") return <LoginScreen />;
  return <Redirect href="/(app)/(tabs)/home" />;
}
