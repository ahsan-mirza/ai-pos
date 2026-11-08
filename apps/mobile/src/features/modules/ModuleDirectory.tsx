import { router } from "expo-router";
import { View } from "react-native";
import { ActionCard } from "@/components/cards/Cards";
import { ResponsiveGrid, ScreenContainer, ScreenTitle } from "@/components/layout/Screen";
import { AppText } from "@/components/primitives/Text";
import { useAuth } from "@/auth/AuthProvider";
import { useI18n } from "@/i18n/I18nProvider";
import { useResponsive } from "@/hooks/useResponsive";
import { moduleVisible, type AccessContext } from "@/modules/access";
import { modulesIn, type ModuleGroup } from "@/modules/catalog";
import { useTenant } from "@/tenant/TenantProvider";

export function ModuleDirectory({ group, title }: { group: ModuleGroup; title: string }) {
  const { text } = useI18n();
  const auth = useAuth();
  const tenant = useTenant();
  const layout = useResponsive();
  const access: AccessContext = {
    can: auth.can,
    superAdmin: auth.superAdmin,
    storeId: tenant.storeId,
    profile: tenant.profile,
    capabilities: tenant.capabilities,
    capabilitiesKnown: tenant.capabilitiesKnown,
    profileReady: tenant.ready,
  };
  const items = modulesIn(group).filter((item) => item.kind !== "dashboard" && moduleVisible(item, access));
  const sections: { title: string; items: typeof items }[] = [];
  for (const item of items) {
    const section = text(item.section);
    const last = sections[sections.length - 1];
    if (last && last.title === section) last.items.push(item);
    else sections.push({ title: section, items: [item] });
  }
  return (
    <ScreenContainer scroll>
      <ScreenTitle title={title} />
      {sections.map((section) => (
        <View key={section.title} style={{ gap: layout.spacing.gap }}>
          <AppText variant="label" tone="secondary">{section.title}</AppText>
          <ResponsiveGrid columns={layout.directoryColumns} gap={layout.spacing.gap}>
            {section.items.map((item) => (
              <ActionCard
                key={item.id}
                title={text(item.title)}
                subtitle={text(item.summary)}
                onPress={() => {
                  if (item.kind === "showcase") router.push("/showcase");
                  else if (item.kind === "account") router.push("/account");
                  else router.push(`/module/${item.id}`);
                }}
              />
            ))}
          </ResponsiveGrid>
        </View>
      ))}
    </ScreenContainer>
  );
}
