import { useEffect, useRef, useState } from "react";
import { Image, View } from "react-native";
import { businessCodeLabel, businessCodePhrase, normalizeStoreCode, storeCodeError } from "@ai-pos/shared-types";
import { ApiRequestError } from "@/api/errors";
import { useAuth } from "@/auth/AuthProvider";
import { Button } from "@/components/buttons/Button";
import { Input } from "@/components/inputs/Input";
import { ScreenContainer } from "@/components/layout/Screen";
import { Icon } from "@/components/primitives/Icon";
import { AppText } from "@/components/primitives/Text";
import { useI18n } from "@/i18n/I18nProvider";
import { useTheme } from "@/theme/ThemeProvider";

export function LoginScreen() {
  const { login, storeCode } = useAuth();
  const { t, locale } = useI18n();
  const codeLabel = businessCodeLabel(null, locale);
  const theme = useTheme();
  const usernameRef = useRef<{ focus: () => void } | null>(null);
  const passwordRef = useRef<{ focus: () => void } | null>(null);
  const codeEdited = useRef(false);
  const [code, setCode] = useState(storeCode);
  useEffect(() => {
    if (!codeEdited.current) setCode(storeCode);
  }, [storeCode]);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const icon = <Icon name="store" size={theme.iconSize.md} color={theme.colors.textSecondary} />;

  function submit() {
    if (loading) return;
    const storeError = storeCodeError(code);
    if (storeError) {
      setError(storeError);
      return;
    }
    if (username.trim() === "" || password === "") {
      setError(t("required"));
      return;
    }
    setLoading(true);
    setError(null);
    void login(username.trim(), password, code)
      .catch((caught: unknown) => setError(caught instanceof ApiRequestError ? caught.message : "Sign-in failed."))
      .finally(() => setLoading(false));
  }

  return (
    <ScreenContainer scroll>
      <View style={{ alignItems: "center", gap: theme.space.sm, paddingTop: theme.space.lg, paddingBottom: theme.space.md }}>
        <Image source={require("../../../assets/icon.png")} style={{ width: 72, height: 72, borderRadius: theme.radius.lg }} accessibilityIgnoresInvertColors />
        <AppText variant="title">{t("appName")}</AppText>
        <AppText tone="secondary" style={{ textAlign: "center" }}>{t("signInSubtitle")}</AppText>
      </View>
      <Input
        label={codeLabel}
        placeholder={locale === "ar" ? "أدخل رمز المتجر" : businessCodePhrase(null, "placeholder")}
        value={code}
        onChangeText={(value) => {
          codeEdited.current = true;
          setCode(normalizeStoreCode(value));
        }}
        helperText={locale === "ar" ? "نفس الرمز الذي تدخله عند تفعيل الصندوق." : businessCodePhrase(null, "hintRegister")}
        autoCapitalize="none"
        autoCorrect={false}
        returnKeyType="next"
        onSubmitEditing={() => usernameRef.current?.focus()}
        leading={icon}
        accessibilityLabel={codeLabel}
      />
      <Input
        ref={usernameRef}
        leading={<Icon name="user" size={theme.iconSize.md} color={theme.colors.textSecondary} />}
        label={t("username")}
        placeholder={t("usernamePlaceholder")}
        value={username}
        onChangeText={setUsername}
        autoCapitalize="none"
        autoCorrect={false}
        required
        returnKeyType="next"
        onSubmitEditing={() => passwordRef.current?.focus()}
        accessibilityLabel={t("username")}
      />
      <Input
        ref={passwordRef}
        leading={<Icon name="lock" size={theme.iconSize.md} color={theme.colors.textSecondary} />}
        variant="password"
        label={t("password")}
        placeholder={t("passwordPlaceholder")}
        value={password}
        onChangeText={setPassword}
        required
        returnKeyType="done"
        onSubmitEditing={submit}
        accessibilityLabel={t("password")}
      />
      {error ? <AppText tone="danger">{error}</AppText> : null}
      <Button fullWidth size="lg" label={t("signIn")} accessibilityLabel={t("signIn")} loading={loading} disabled={loading} onPress={submit} />
    </ScreenContainer>
  );
}
