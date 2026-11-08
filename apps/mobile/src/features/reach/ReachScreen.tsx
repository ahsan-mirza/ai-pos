import { useState } from "react";
import { View } from "react-native";
import { useQuery } from "@tanstack/react-query";
import { apiGet, apiPost } from "@/api/client";
import { Button } from "@/components/buttons/Button";
import { KPICard, ListCard } from "@/components/cards/Cards";
import { Tabs } from "@/components/inputs/Fields";
import { ResponsiveGrid, ScreenContainer, ScreenTitle } from "@/components/layout/Screen";
import { ErrorState, LoadingSkeleton } from "@/components/feedback/Feedback";
import { useResponsive } from "@/hooks/useResponsive";
import { useI18n } from "@/i18n/I18nProvider";
import { collectRows, recordSubtitle, recordTitle } from "@/modules/records";

const tabs = [
  { id: "overview", label: "Overview", path: "/api/v1/reach/overview" },
  { id: "connections", label: "Connections", path: "/api/v1/reach/connections" },
  { id: "campaigns", label: "Campaigns", path: "/api/v1/reach/campaigns" },
  { id: "agent", label: "AI Agent", path: "/api/v1/reach/ai/agent" },
  { id: "conversations", label: "Conversations", path: "/api/v1/reach/ai/conversations" },
  { id: "templates", label: "Templates", path: "/api/v1/reach/templates" },
  { id: "automations", label: "Automations", path: "/api/v1/messaging/settings" },
  { id: "actions", label: "Action Center", path: "/api/v1/reach/ai/actions" },
  { id: "history", label: "History", path: "/api/v1/messaging/outbox?limit=50" },
  { id: "analytics", label: "Analytics", path: "/api/v1/reach/ai/analytics" },
  { id: "credits", label: "Credits", path: "/api/v1/reach/credits" },
  { id: "settings", label: "Settings", path: "/api/v1/reach/channels" },
] as const;

export function ReachScreen() {
  const { t } = useI18n();
  const layout = useResponsive();
  const [tab, setTab] = useState<(typeof tabs)[number]["id"]>("overview");
  const current = tabs.find((item) => item.id === tab) ?? tabs[0];
  const query = useQuery({
    queryKey: ["reach", current.id],
    queryFn: () => apiGet<unknown>(current.path),
  });
  const collected = query.data === undefined ? null : collectRows(query.data, null);
  return (
    <ScreenContainer scroll>
      <ScreenTitle title="AxizReach" subtitle="WhatsApp, campaigns and the shared tenant connection." />
      <Tabs tabs={tabs.map((item) => ({ id: item.id, label: item.label }))} selected={tab} onChange={(id) => setTab(id as typeof tab)} />
      {query.isLoading ? <LoadingSkeleton /> : null}
      {query.isError ? <ErrorState message={query.error instanceof Error ? query.error.message : t("retry")} retryLabel={t("retry")} onRetry={() => void query.refetch()} /> : null}
      {collected?.summary ? (
        <ResponsiveGrid columns={layout.columns} gap={layout.spacing.gap}>
          {Object.entries(collected.summary).slice(0, 4).map(([key, value]) => (
            <KPICard key={key} title={key} value={String(value)} />
          ))}
        </ResponsiveGrid>
      ) : null}
      <View style={{ gap: 8 }}>
        {collected?.rows.map((row, index) => (
          <ListCard key={String(row.id ?? index)} title={recordTitle(row)} subtitle={recordSubtitle(row, recordTitle(row))} status={typeof row.status === "string" ? row.status : undefined} />
        ))}
      </View>
      {tab === "connections" && collected?.rows[0] && typeof collected.rows[0].id === "string" ? (
        <Button
          variant="outline"
          label="Refresh connection"
          accessibilityLabel="Refresh connection"
          onPress={() => {
            const id = collected.rows[0]?.id;
            if (typeof id === "string") void apiPost(`/api/v1/reach/connections/${id}/status`, {}).then(() => query.refetch());
          }}
        />
      ) : null}
    </ScreenContainer>
  );
}
