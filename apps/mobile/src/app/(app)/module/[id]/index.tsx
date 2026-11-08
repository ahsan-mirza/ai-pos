import { router, useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { View } from "react-native";
import { Button } from "@/components/buttons/Button";
import { AppHeader, ScreenContainer } from "@/components/layout/Screen";
import { AppText } from "@/components/primitives/Text";
import { useAuth } from "@/auth/AuthProvider";
import { useI18n } from "@/i18n/I18nProvider";
import { useResponsive } from "@/hooks/useResponsive";
import { capabilityEnabled, moduleVisible, type AccessContext } from "@/modules/access";
import { moduleById } from "@/modules/catalog";
import { DashboardScreen } from "@/features/dashboard/DashboardScreen";
import { ReachScreen } from "@/features/reach/ReachScreen";
import { rememberRow } from "@/features/records/memory";
import { PettyCashPanel } from "@/features/records/PettyCashPanel";
import { RecordBrowser } from "@/features/records/RecordBrowser";
import { RecordDetail } from "@/features/records/RecordDetail";
import { useTenant } from "@/tenant/TenantProvider";
import { useTheme } from "@/theme/ThemeProvider";

export default function ModuleScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const module = typeof id === "string" ? moduleById(id) : undefined;
  const { t, text } = useI18n();
  const auth = useAuth();
  const tenant = useTenant();
  const layout = useResponsive();
  const theme = useTheme();
  const [selected, setSelected] = useState<string | null>(null);
  const access: AccessContext = {
    can: auth.can,
    superAdmin: auth.superAdmin,
    storeId: tenant.storeId,
    profile: tenant.profile,
    capabilities: tenant.capabilities,
    capabilitiesKnown: tenant.capabilitiesKnown,
    profileReady: tenant.ready,
  };
  if (!module) {
    return (
      <ScreenContainer scroll>
        <AppText>{t("notFound")}</AppText>
      </ScreenContainer>
    );
  }
  if (!moduleVisible(module, access)) {
    return (
      <ScreenContainer scroll>
        <AppHeader title={text(module.title)} onBack={() => router.back()} />
        <AppText>{module.permission && !auth.can(module.permission) ? t("forbidden") : t("capabilityOff")}</AppText>
      </ScreenContainer>
    );
  }
  if (!capabilityEnabled(module.capability, access)) {
    return (
      <ScreenContainer scroll>
        <AppHeader title={text(module.title)} onBack={() => router.back()} />
        <AppText>{t("capabilityOff")}</AppText>
      </ScreenContainer>
    );
  }
  if (module.kind === "dashboard") return <DashboardScreen />;
  if (module.kind === "reach") return <ReachScreen />;
  const browser = (
    <View style={{ flex: 1 }}>
      <AppHeader
        title={text(module.title)}
        onBack={() => router.back()}
        action={module.create ? <Button size="sm" label={t("create")} accessibilityLabel={t("create")} onPress={() => router.push(`/module/${module.id}/create`)} /> : undefined}
      />
      <RecordBrowser
        module={module}
        headerExtra={module.id === "expenses" ? <PettyCashPanel /> : undefined}
        onOpen={(recordId, row) => {
          rememberRow(module.id, recordId, row);
          if (layout.isTablet) setSelected(recordId);
          else router.push(`/module/${module.id}/${recordId}`);
        }}
      />
    </View>
  );
  if (layout.masterDetail) {
    return (
      <ScreenContainer>
        <View style={{ flex: 1, flexDirection: "row" }}>
          <View style={{ flex: 1 }}>{browser}</View>
          <View style={{ flex: 1, borderLeftWidth: 1, borderLeftColor: theme.colors.border }}>
            {selected ? <RecordDetail module={module} id={selected} seed={null} embedded onBack={() => setSelected(null)} /> : <AppText tone="secondary">{text(module.summary)}</AppText>}
          </View>
        </View>
      </ScreenContainer>
    );
  }
  return <ScreenContainer>{browser}</ScreenContainer>;
}
