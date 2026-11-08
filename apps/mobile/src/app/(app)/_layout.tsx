import AsyncStorage from "@react-native-async-storage/async-storage";
import { Redirect, Stack, router, usePathname } from "expo-router";
import { useEffect, useRef } from "react";
import { LoadingBlock } from "@/components/feedback/Feedback";
import { useAuth } from "@/auth/AuthProvider";
import { useI18n } from "@/i18n/I18nProvider";

const PATH_KEY = "axizpos.last-path";

function RememberRoute() {
  const path = usePathname();
  const restored = useRef(false);
  useEffect(() => {
    if (!restored.current) {
      restored.current = true;
      void AsyncStorage.getItem(PATH_KEY).then((saved) => {
        if (saved && saved.startsWith("/module/")) router.replace(saved);
      });
      return;
    }
    if (path.startsWith("/module/") || path === "/account" || path === "/showcase") {
      void AsyncStorage.setItem(PATH_KEY, path);
    }
  }, [path]);
  return null;
}

export default function AppLayout() {
  const { status } = useAuth();
  const { t } = useI18n();
  if (status === "checking") return <LoadingBlock label={t("loading")} />;
  if (status === "signed-out") return <Redirect href="/" />;
  return (
    <>
      <RememberRoute />
      <Stack screenOptions={{ headerShown: false }} />
    </>
  );
}
