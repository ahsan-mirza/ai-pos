import AsyncStorage from "@react-native-async-storage/async-storage";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { View } from "react-native";

export type Locale = "en" | "ar";

export interface Localized {
  en: string;
  ar: string;
}

const STORAGE_KEY = "axizpos.locale";

const copy = {
  en: {
    appName: "AxizPOS Business",
    signIn: "Sign in",
    signInSubtitle: "Sign in to your business workspace.",
    storeCodePlaceholder: "Enter your store code",
    storeCodeHint: "Same code you enter when activating a register.",
    usernamePlaceholder: "Enter username",
    passwordPlaceholder: "Enter password",
    signOut: "Sign out",
    username: "Username",
    password: "Password",
    storeCode: "Store code",
    loading: "Loading",
    retry: "Try again",
    offline: "You are offline. Showing the last saved data.",
    online: "Online",
    empty: "Nothing to show yet",
    forbidden: "Your role does not include this page.",
    capabilityOff: "This module is switched off for your business.",
    search: "Search",
    filter: "Filter",
    save: "Save",
    cancel: "Cancel",
    confirm: "Confirm",
    create: "Create",
    back: "Back",
    more: "More",
    home: "Home",
    business: "Business",
    inventory: "Inventory",
    finance: "Finance",
    account: "Account",
    language: "Language",
    english: "English",
    arabic: "Arabic",
    required: "Required",
    showPassword: "Show password",
    hidePassword: "Hide password",
    clear: "Clear",
    apply: "Apply",
    from: "From",
    to: "To",
    designSystem: "Design system",
    quickActions: "Quick actions",
    recent: "Recent",
    notFound: "This screen is not in the business portal.",
    sessionExpired: "Your session ended. Sign in again.",
    biometric: "Unlock with biometrics",
    pull: "Pull to refresh",
    loadMore: "Loading more",
    details: "Details",
    actions: "Actions",
    yes: "Yes",
    no: "No",
    cached: "Saved data",
    weighed: "Weighed",
    plu: "PLU",
    allStatuses: "All",
    creditOn: "B2B credit is on for this business.",
    creditOff: "B2B credit is off for this business.",
    businessType: "Business type",
    hello: "Hello",
    topCategories: "Top categories",
    wholesaleSales: "Wholesale",
    retailSales: "Retail",
    appearance: "Appearance",
    light: "Light",
    dark: "Dark",
    period: "Period",
    daily: "Today",
    weekly: "This week",
    monthly: "This month",
    allTime: "All time",
    recentSales: "Recent sales",
    allBranches: "All branches",
    assignedBranch: "Assigned branch",
    openProfile: "Open profile",
    activity: "Activity",
  },
  ar: {
    appName: "أكسيز للأعمال",
    signIn: "تسجيل الدخول",
    signInSubtitle: "سجّل الدخول إلى مساحة عملك.",
    storeCodePlaceholder: "أدخل رمز المتجر",
    storeCodeHint: "نفس الرمز الذي تدخله عند تفعيل الصندوق.",
    usernamePlaceholder: "أدخل اسم المستخدم",
    passwordPlaceholder: "أدخل كلمة المرور",
    signOut: "تسجيل الخروج",
    username: "اسم المستخدم",
    password: "كلمة المرور",
    storeCode: "رمز المتجر",
    loading: "جار التحميل",
    retry: "إعادة المحاولة",
    offline: "لا يوجد اتصال. يتم عرض آخر بيانات محفوظة.",
    online: "متصل",
    empty: "لا توجد بيانات",
    forbidden: "دورك لا يشمل هذه الصفحة.",
    capabilityOff: "هذه الوحدة غير مفعّلة لنشاطك.",
    search: "بحث",
    filter: "تصفية",
    save: "حفظ",
    cancel: "إلغاء",
    confirm: "تأكيد",
    create: "إنشاء",
    back: "رجوع",
    more: "المزيد",
    home: "الرئيسية",
    business: "الأعمال",
    inventory: "المخزون",
    finance: "المالية",
    account: "الحساب",
    language: "اللغة",
    english: "الإنجليزية",
    arabic: "العربية",
    required: "مطلوب",
    showPassword: "إظهار كلمة المرور",
    hidePassword: "إخفاء كلمة المرور",
    clear: "مسح",
    apply: "تطبيق",
    from: "من",
    to: "إلى",
    designSystem: "نظام التصميم",
    quickActions: "إجراءات سريعة",
    recent: "الأحدث",
    notFound: "هذه الشاشة غير موجودة في بوابة الأعمال.",
    sessionExpired: "انتهت الجلسة. سجّل الدخول مرة أخرى.",
    biometric: "فتح بالبصمة",
    pull: "اسحب للتحديث",
    loadMore: "تحميل المزيد",
    details: "التفاصيل",
    actions: "إجراءات",
    yes: "نعم",
    no: "لا",
    cached: "بيانات محفوظة",
    weighed: "بالوزن",
    plu: "PLU",
    allStatuses: "الكل",
    creditOn: "ائتمان الجملة مفعّل لهذا النشاط.",
    creditOff: "ائتمان الجملة غير مفعّل لهذا النشاط.",
    businessType: "نوع النشاط",
    hello: "مرحبا",
    topCategories: "أعلى التصنيفات",
    wholesaleSales: "الجملة",
    retailSales: "التجزئة",
    appearance: "المظهر",
    light: "فاتح",
    dark: "داكن",
    period: "الفترة",
    daily: "اليوم",
    weekly: "هذا الأسبوع",
    monthly: "هذا الشهر",
    allTime: "كل الوقت",
    recentSales: "أحدث المبيعات",
    allBranches: "كل الفروع",
    assignedBranch: "الفرع المعيّن",
    openProfile: "فتح الملف",
    activity: "النشاط",
  },
} as const;

export type CopyKey = keyof (typeof copy)["en"];

interface I18nValue {
  locale: Locale;
  isRTL: boolean;
  setLocale: (locale: Locale) => void;
  t: (key: CopyKey) => string;
  text: (value: Localized) => string;
}

const I18nContext = createContext<I18nValue | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>("en");

  useEffect(() => {
    void AsyncStorage.getItem(STORAGE_KEY).then((stored) => {
      if (stored === "ar" || stored === "en") setLocaleState(stored);
    });
  }, []);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    void AsyncStorage.setItem(STORAGE_KEY, next);
  }, []);

  const value = useMemo<I18nValue>(() => {
    const isRTL = locale === "ar";
    return {
      locale,
      isRTL,
      setLocale,
      t: (key) => copy[locale][key],
      text: (item) => item[locale],
    };
  }, [locale, setLocale]);

  return (
    <I18nContext.Provider value={value}>
      <View style={{ flex: 1, direction: locale === "ar" ? "rtl" : "ltr" }}>{children}</View>
    </I18nContext.Provider>
  );
}

export function useI18n(): I18nValue {
  const value = useContext(I18nContext);
  if (value === null) throw new Error("useI18n must be used inside I18nProvider.");
  return value;
}
