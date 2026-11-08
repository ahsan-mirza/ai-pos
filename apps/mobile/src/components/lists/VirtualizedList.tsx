import { type ReactElement, type ReactNode } from "react";
import { ActivityIndicator, RefreshControl, View } from "react-native";
import { FlashList } from "@shopify/flash-list";
import { Button } from "@/components/buttons/Button";
import { AppText } from "@/components/primitives/Text";
import { useI18n } from "@/i18n/I18nProvider";
import { useTheme } from "@/theme/ThemeProvider";

export interface VirtualizedListProps<T> {
  data: readonly T[];
  renderItem: (item: T, index: number) => ReactElement;
  keyExtractor: (item: T, index: number) => string;
  onRefresh?: () => void;
  refreshing?: boolean;
  onEndReached?: () => void;
  loading?: boolean;
  loadingMore?: boolean;
  error?: string | null;
  onRetry?: () => void;
  emptyState?: ReactNode;
  header?: ReactNode;
  selectable?: boolean;
  selectedKeys?: ReadonlySet<string>;
}

export function VirtualizedList<T>({
  data,
  renderItem,
  keyExtractor,
  onRefresh,
  refreshing = false,
  onEndReached,
  loading = false,
  loadingMore = false,
  error,
  onRetry,
  emptyState,
  header,
}: VirtualizedListProps<T>) {
  const theme = useTheme();
  const { t } = useI18n();
  if (loading && data.length === 0) {
    return (
      <View style={{ flex: 1, padding: theme.space.lg, gap: theme.space.sm }}>
        {header}
        {[0, 1, 2, 3].map((item) => (
          <View key={item} style={{ height: 72, borderRadius: theme.radius.lg, backgroundColor: theme.colors.surfaceMuted }} />
        ))}
      </View>
    );
  }
  if (error && data.length === 0) {
    return (
      <View style={{ flex: 1, padding: theme.space.xl, gap: theme.space.md }}>
        {header}
        <AppText tone="danger">{error}</AppText>
        {onRetry ? <Button label={t("retry")} accessibilityLabel={t("retry")} onPress={onRetry} /> : null}
      </View>
    );
  }
  return (
    <View style={{ flex: 1 }}>
      <FlashList
      data={data as T[]}
      keyExtractor={keyExtractor}
      renderItem={({ item, index }) => renderItem(item, index)}
      ListHeaderComponent={header ? <View style={{ paddingBottom: theme.space.sm }}>{header}</View> : null}
      ListEmptyComponent={<View style={{ padding: theme.space.xl }}>{emptyState ?? <AppText tone="secondary">{t("empty")}</AppText>}</View>}
      ListFooterComponent={loadingMore ? <ActivityIndicator style={{ margin: theme.space.lg }} color={theme.colors.primary} /> : <View style={{ height: theme.space.xl }} />}
      ItemSeparatorComponent={() => <View style={{ height: theme.space.sm }} />}
      contentContainerStyle={{ padding: theme.space.lg }}
      refreshControl={onRefresh ? <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={theme.colors.primary} /> : undefined}
      onEndReached={onEndReached}
      onEndReachedThreshold={0.4}
    />
    </View>
  );
}
