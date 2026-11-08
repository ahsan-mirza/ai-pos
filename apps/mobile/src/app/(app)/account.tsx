import * as LocalAuthentication from "expo-local-authentication";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { router } from "expo-router";
import { useEffect, useState } from "react";
import { View } from "react-native";
import { businessCodeLabel } from "@ai-pos/shared-types";
import { Button } from "@/components/buttons/Button";
import { InformationCard } from "@/components/cards/Cards";
import { SwitchField } from "@/components/inputs/Fields";
import { AppHeader, ScreenContainer } from "@/components/layout/Screen";
import { AppText } from "@/components/primitives/Text";
import { useAuth } from "@/auth/AuthProvider";
import { useI18n } from "@/i18n/I18nProvider";
import { useTheme } from "@/theme/ThemeProvider";
import { useTenant } from "@/tenant/TenantProvider";

const BIOMETRIC_KEY = "axizpos.biometric";

export default function AccountRoute() {
  const { user, logout, storeCode } = useAuth();
  const tenant = useTenant();
  const { t, locale, setLocale } = useI18n();
  const theme = useTheme();
  const [biometric, setBiometric] = useState(false);
  useEffect(() => {
    void AsyncStorage.getItem(BIOMETRIC_KEY).then((value) => setBiometric(value === "1"));
  }, []);
  return (
    <ScreenContainer scroll>
      <AppHeader title={t("account")} onBack={() => router.back()} />
      <InformationCard
        title={user?.full_name ?? t("account")}
        rows={[
          { label: t("username"), value: user?.username ?? "—" },
          { label: "Role", value: user?.role.name ?? "—" },
          { label: t("business"), value: tenant.businessName ?? "—" },
          { label: businessCodeLabel(tenant.profile, locale), value: tenant.storeCode || storeCode || "—" },
          { label: "Store", value: tenant.storeId === null ? t("allBranches") : t("assignedBranch") },
          { label: "Currency", value: tenant.currency },
        ]}
      />
      <View style={{ gap: theme.space.sm }}>
        <AppText variant="label" tone="secondary">{t("language")}</AppText>
        <View style={{ flexDirection: "row", gap: theme.space.sm }}>
          <Button variant={locale === "en" ? "primary" : "outline"} label={t("english")} accessibilityLabel={t("english")} onPress={() => setLocale("en")} />
          <Button variant={locale === "ar" ? "primary" : "outline"} label={t("arabic")} accessibilityLabel={t("arabic")} onPress={() => setLocale("ar")} />
        </View>
      </View>
      <View style={{ gap: theme.space.sm }}>
        <AppText variant="label" tone="secondary">{t("account")}</AppText>
        <SwitchField
          label={t("biometric")}
          value={biometric}
          onChange={(next) => {
            void (async () => {
              if (next) {
                const available = await LocalAuthentication.hasHardwareAsync();
                if (!available) return;
                const result = await LocalAuthentication.authenticateAsync({ promptMessage: t("biometric") });
                if (!result.success) return;
              }
              setBiometric(next);
              await AsyncStorage.setItem(BIOMETRIC_KEY, next ? "1" : "0");
            })();
          }}
        />
      </View>
      <Button variant="danger" label={t("signOut")} accessibilityLabel={t("signOut")} onPress={logout} />
    </ScreenContainer>
  );
}
