import { Tabs } from "expo-router";
import { Icon } from "@/components/primitives/Icon";
import { AppText } from "@/components/primitives/Text";
import { useI18n } from "@/i18n/I18nProvider";
import { useTheme } from "@/theme/ThemeProvider";

export default function TabLayout() {
  const { t } = useI18n();
  const theme = useTheme();
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: theme.colors.primary,
        tabBarInactiveTintColor: theme.colors.textSecondary,
        tabBarHideOnKeyboard: true,
        tabBarStyle: { backgroundColor: theme.colors.surface, borderTopColor: theme.colors.border },
        tabBarLabel: ({ color, children }) => (
          <AppText variant="caption" numberOfLines={1} style={{ color, textAlign: "center" }}>{String(children)}</AppText>
        ),
      }}
    >
      <Tabs.Screen name="home" options={{ title: t("home"), tabBarIcon: ({ color }) => <Icon name="home" color={String(color)} /> }} />
      <Tabs.Screen name="business" options={{ title: t("business"), tabBarIcon: ({ color }) => <Icon name="business" color={String(color)} /> }} />
      <Tabs.Screen name="inventory" options={{ title: t("inventory"), tabBarIcon: ({ color }) => <Icon name="inventory" color={String(color)} /> }} />
      <Tabs.Screen name="finance" options={{ title: t("finance"), tabBarIcon: ({ color }) => <Icon name="finance" color={String(color)} /> }} />
      <Tabs.Screen name="more" options={{ title: t("more"), tabBarIcon: ({ color }) => <Icon name="more" color={String(color)} /> }} />
    </Tabs>
  );
}
