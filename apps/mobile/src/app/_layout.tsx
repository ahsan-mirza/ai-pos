import { useEffect } from "react";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { KeyboardProvider } from "react-native-keyboard-controller";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { Slot } from "expo-router";
import { StatusBar } from "expo-status-bar";
import * as Sentry from "@sentry/react-native";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient } from "@/api/queryClient";
import { AuthProvider } from "@/auth/AuthProvider";
import { env, assertProductionApi } from "@/config/env";
import { ToastProvider } from "@/components/overlays/Overlays";
import { I18nProvider } from "@/i18n/I18nProvider";
import { TenantProvider } from "@/tenant/TenantProvider";
import { useTheme } from "@/theme/ThemeProvider";

if (env.sentryDsn !== "") {
  Sentry.init({
    dsn: env.sentryDsn,
    tracesSampleRate: 0.1,
    sendDefaultPii: false,
  });
}

function ThemedStatusBar() {
  const theme = useTheme();
  return <StatusBar style={theme.mode === "dark" ? "light" : "dark"} />;
}

export default function RootLayout() {
  useEffect(() => {
    assertProductionApi();
  }, []);
  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <KeyboardProvider>
          <I18nProvider>
            <QueryClientProvider client={queryClient}>
              <AuthProvider>
                <TenantProvider>
                  <ToastProvider>
                    <ThemedStatusBar />
                    <Slot />
                  </ToastProvider>
                </TenantProvider>
              </AuthProvider>
            </QueryClientProvider>
          </I18nProvider>
        </KeyboardProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
