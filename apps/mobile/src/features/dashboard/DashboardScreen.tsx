import { AnalyticsTimeframe, Capability, businessCodeLabel, formatMoney, Permission, profileSpec } from "@ai-pos/shared-types";
import { useQuery } from "@tanstack/react-query";
import { router } from "expo-router";
import { useState } from "react";
import { Pressable, View } from "react-native";
import { apiGet } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import { BarChart, DonutChart, LineChart } from "@/components/charts/Charts";
import { ActionCard, KPICard, TransactionCard } from "@/components/cards/Cards";
import { ErrorState, LoadingSkeleton } from "@/components/feedback/Feedback";
import { Avatar } from "@/components/feedback/Feedback";
import { SelectField } from "@/components/inputs/Fields";
import { ResponsiveGrid, ScreenContainer } from "@/components/layout/Screen";
import { Icon } from "@/components/primitives/Icon";
import { AppText } from "@/components/primitives/Text";
import { useResponsive } from "@/hooks/useResponsive";
import { useI18n } from "@/i18n/I18nProvider";
import { moduleVisible, type AccessContext } from "@/modules/access";
import { modules, modulesIn, type PortalModule } from "@/modules/catalog";
import { collectRows, recordSubtitle, recordTitle } from "@/modules/records";
import { useTenant } from "@/tenant/TenantProvider";
import type { AnalyticsSummary } from "@ai-pos/shared-types";
import { useTheme } from "@/theme/ThemeProvider";

const PERIODS = [AnalyticsTimeframe.Daily, AnalyticsTimeframe.Weekly, AnalyticsTimeframe.Monthly, AnalyticsTimeframe.AllTime] as const;

export function DashboardScreen() {
  const { t, text, locale } = useI18n();
  const theme = useTheme();
  const tenant = useTenant();
  const auth = useAuth();
  const layout = useResponsive();
  const [period, setPeriod] = useState<AnalyticsTimeframe>(AnalyticsTimeframe.Daily);
  const summary = useQuery({
    queryKey: ["dashboard", tenant.currency, period],
    queryFn: () => apiGet<AnalyticsSummary>(`/api/v1/analytics/summary?timeframe=${period}&currency=${tenant.currency}`),
  });
  const recent = useQuery({
    queryKey: ["dashboard", "recent-sales"],
    enabled: auth.can(Permission.PortalReportsRead),
    queryFn: async () => collectRows(await apiGet<unknown>("/api/v1/sales?limit=5&offset=0"), null).rows.slice(0, 5),
  });
  const access: AccessContext = {
    can: auth.can,
    superAdmin: auth.superAdmin,
    storeId: tenant.storeId,
    profile: tenant.profile,
    capabilities: tenant.capabilities,
    capabilitiesKnown: tenant.capabilitiesKnown,
    profileReady: tenant.ready,
  };
  const shortcuts = ["sales", "products", "customers", "purchase-orders", "management-reports"]
    .map((id) => modules.find((item) => item.id === id))
    .filter((item): item is PortalModule => item !== undefined && moduleVisible(item, access))
    .slice(0, layout.isTablet ? 6 : 4);
  const homeLinks = modulesIn("home").filter((item) => item.id !== "dashboard" && moduleVisible(item, access));
  const audit = modules.find((item) => item.id === "audit");
  const money = (cents: number | undefined) => formatMoney(cents ?? 0, tenant.currency, locale === "ar" ? "ar" : "en");
  const data = summary.data;
  const growth = data?.units_growth_bps;
  const growthLabel = growth === null || growth === undefined ? undefined : `${(growth / 100).toFixed(1)}%`;
  const localeTag = locale === "ar" ? "ar" : "en";
  return (
    <ScreenContainer scroll>
      <View style={{ flexDirection: "row", alignItems: "center", gap: theme.space.md }}>
        <View style={{ flex: 1, minWidth: 0, gap: 2 }}>
          <AppText variant="title" numberOfLines={1}>{tenant.businessName ?? t("appName")}</AppText>
          <AppText variant="caption" tone="secondary" numberOfLines={2}>
            {(tenant.storeCode || auth.storeCode) ? `${businessCodeLabel(tenant.profile, locale)} ${tenant.storeCode || auth.storeCode}` : businessCodeLabel(tenant.profile, locale)}
            {" · "}
            {tenant.storeId === null ? t("allBranches") : t("assignedBranch")}
          </AppText>
        </View>
        {audit && moduleVisible(audit, access) ? (
          <Pressable accessibilityRole="button" accessibilityLabel={t("activity")} onPress={() => router.push("/module/audit")} style={{ minWidth: theme.touchTarget, minHeight: theme.touchTarget, alignItems: "center", justifyContent: "center" }}>
            <Icon name="bell" size={theme.iconSize.lg} color={theme.colors.text} />
          </Pressable>
        ) : null}
        <Pressable accessibilityRole="button" accessibilityLabel={t("openProfile")} onPress={() => router.push("/account")}>
          <Avatar name={auth.user?.full_name ?? t("account")} />
        </Pressable>
      </View>
      <AppText variant="caption" tone="secondary">{profileSpec(tenant.profile).shortLabel}</AppText>
      {tenant.capabilitiesKnown ? <AppText variant="caption" tone="secondary">{tenant.capabilities.includes(Capability.B2bCredit) ? t("creditOn") : t("creditOff")}</AppText> : null}
      <SelectField
        label={t("period")}
        value={period}
        onChange={(value) => {
          const next = PERIODS.find((item) => item === value);
          if (next) setPeriod(next);
        }}
        options={PERIODS.map((value) => ({ value, label: t(value === "all_time" ? "allTime" : value) }))}
      />
      {summary.isLoading ? <LoadingSkeleton /> : null}
      {summary.isError ? <ErrorState message={summary.error.message} retryLabel={t("retry")} onRetry={() => void summary.refetch()} /> : null}
      {data ? (
        <ResponsiveGrid columns={layout.columns > 2 ? 2 : layout.columns} gap={layout.spacing.gap}>
          <KPICard title="Revenue" value={money(data.net_revenue_cents)} comparison={t(period === "all_time" ? "allTime" : period)} />
          <KPICard title="Units sold" value={String(data.units_sold)} trend={growth !== null && growth !== undefined && growth < 0 ? "down" : growth ? "up" : "flat"} percentage={growthLabel} />
          <KPICard title="Average ticket" value={money(data.average_ticket_cents)} />
          {data.gross_margin_cents !== undefined ? <KPICard title="Gross profit" value={money(data.gross_margin_cents)} status={data.receivables_cents ? `Due ${money(data.receivables_cents)}` : undefined} /> : null}
        </ResponsiveGrid>
      ) : null}
      {data ? <LineChart title="Revenue" values={data.revenue_series} /> : null}
      {data ? <DonutChart title="Payments" values={data.payment_split.map((item) => ({ label: item.method, value: item.revenue_cents }))} /> : null}
      {data ? <BarChart title="Categories" values={data.categories.map((item) => ({ label: item.category, value: item.revenue_cents }))} /> : null}
      {recent.data && recent.data.length > 0 ? (
        <View style={{ gap: layout.spacing.gap }}>
          <AppText variant="heading">{t("recentSales")}</AppText>
          {recent.data.map((row, index) => {
            const title = recordTitle(row);
            const amount = typeof row.total_cents === "number" ? formatMoney(row.total_cents, tenant.currency, localeTag) : "";
            return <TransactionCard key={String(row.id ?? index)} title={title} when={recordSubtitle(row, title)} amount={amount} onPress={() => router.push("/module/sales")} />;
          })}
        </View>
      ) : null}
      {shortcuts.length > 0 ? <AppText variant="heading">{t("quickActions")}</AppText> : null}
      <View style={{ gap: layout.spacing.gap }}>
        {shortcuts.map((item) => (
          <ActionCard key={item.id} title={text(item.title)} subtitle={text(item.summary)} onPress={() => router.push(`/module/${item.id}`)} />
        ))}
      </View>
      {homeLinks.length > 0 ? (
        <View style={{ gap: layout.spacing.gap }}>
          {homeLinks.map((item) => (
            <ActionCard key={item.id} title={text(item.title)} subtitle={text(item.summary)} onPress={() => router.push(`/module/${item.id}`)} />
          ))}
        </View>
      ) : null}
    </ScreenContainer>
  );
}
