/** Device language for the portal and the register. English copy stays the source string. */

export type Locale = "en" | "ar";

const KEY = "ai-pos.language";

/**
 * Arabic interface copy is a draft for layout and direction.
 * It is not approved production copy until a native review.
 * Product names, customer names, and amounts are never translated here.
 * Digits stay Western (0-9) so money and quantities match the stored values.
 */
const arabic: Record<string, string> = {
  Language: "اللغة",
  English: "English",
  "العربية": "العربية",
  Restaurant: "مطعم",
  Workspace: "مساحة العمل",
  Dashboard: "لوحة المعلومات",
  "AI insights": "تحليلات ذكية",
  "Manager app": "تطبيق المدير",
  Rentals: "الإيجارات",
  Sales: "المبيعات",
  Returns: "المرتجعات",
  "Card & pay later": "البطاقة والدفع لاحقاً",
  Promotions: "العروض",
  "Store credit": "رصيد المتجر",
  "Gift cards": "بطاقات الهدايا",
  "Margin guard": "حماية الهامش",
  "Shifts & drawers": "الورديات والأدراج",
  "Wholesale & credit": "الجملة والائتمان",
  "Quotations & layaway": "عروض الأسعار والتقسيط",
  "Sales orders": "أوامر البيع",
  "Reorder management": "إعادة الطلب",
  "Cheques & PDCs": "الشيكات",
  Consignment: "البضاعة بالأمانة",
  Service: "الخدمات",
  "Repairs & warranties": "الصيانة والضمان",
  Warranties: "الضمانات",
  "Trade-ins": "الاستبدال",
  "Food & Beverage": "الأغذية والمشروبات",
  "Floor plan & tables": "مخطط الصالة والطاولات",
  "Table reservations": "حجوزات الطاولات",
  "Kitchen display": "شاشة المطبخ",
  "Kitchen agent": "مساعد المطبخ",
  "Recipes & ingredients": "الوصفات والمكونات",
  "Menu modifiers": "إضافات القائمة",
  "Delivery Integrations": "تكاملات التوصيل",
  Finance: "المالية",
  Payables: "الذمم الدائنة",
  Expenses: "المصروفات",
  Accounting: "المحاسبة",
  "Bank reconciliation": "مطابقة البنك",
  "VAT report": "تقرير الضريبة",
  "Exports & loyalty": "التصدير والولاء",
  "Management reports": "تقارير الإدارة",
  Cancellations: "الإلغاءات",
  "Deep analytics": "تحليلات متقدمة",
  "Tips & service": "الإكراميات والخدمة",
  Compliance: "الامتثال",
  "e-Invoicing": "الفوترة الإلكترونية",
  Administration: "الإدارة",
  AxizReach: "AxizReach",
  Users: "المستخدمون",
  "Staff & payroll": "الموظفون والرواتب",
  "Store settings": "إعدادات المتجر",
  "Restaurant settings": "إعدادات المطعم",
  "Cafe settings": "إعدادات المقهى",
  "Quick service settings": "إعدادات الخدمة السريعة",
  General: "عام",
  "Add-ons": "الإضافات",
  Stores: "الفروع",
  Roles: "الأدوار",
  "Add-on access": "صلاحيات الإضافات",
  Registers: "أجهزة البيع",
  Downloads: "التنزيلات",
  Currencies: "العملات",
  "Delivery channels": "قنوات التوصيل",
  "Audit trail": "سجل التدقيق",
  Inventory: "المخزون",
  Customers: "العملاء",
  Checkout: "الدفع",
  "Orders & Tables": "الطلبات والطاولات",
  "Void & waste": "الإلغاء والهدر",
  Repairs: "الصيانة",
  "Returns & Exchanges": "المرتجعات والاستبدال",
  "Reorder alerts": "تنبيهات إعادة الطلب",
  "Time clock": "الحضور",
  Shift: "الوردية",
  "Sync Center": "مركز المزامنة",
  "Customer display": "شاشة العميل",
  Settings: "الإعدادات",
  "Practice mode": "وضع التدريب",
  "Expand sidebar": "توسيع القائمة",
  "Collapse sidebar": "طي القائمة",
  "Open navigation": "فتح القائمة",
  "Close navigation": "إغلاق القائمة",
  Light: "فاتح",
  Dark: "داكن",
  "Colour theme": "مظهر الألوان",
  Live: "مباشر",
  Synced: "متزامن",
  Offline: "غير متصل",
  Pending: "قيد الانتظار",
  Register: "جهاز البيع",
  Sell: "البيع",
  "Lock register": "قفل الجهاز",
  "Lock Register": "قفل الجهاز",
  "Lock register / switch cashier": "قفل الجهاز أو تبديل أمين الصندوق",
  Notifications: "التنبيهات",
  unread: "غير مقروء",
  "Mark all read": "تعليم الكل كمقروء",
  "Nothing needs your attention right now.": "لا يوجد ما يحتاج إلى انتباهك الآن.",
  "AI Assistant": "المساعد الذكي",
  "Ask your business": "اسأل عن نشاطك",
  "Business currency": "عملة النشاط",
  Breadcrumb: "مسار التنقل",
  Primary: "القائمة الرئيسية",
  "Locked until payment is verified": "مغلق حتى يتم التحقق من الدفع",
};

const listeners = new Set<() => void>();
let memory: Locale = "en";

export function isLocale(value: string | null | undefined): value is Locale {
  return value === "en" || value === "ar";
}

export function readLocale(): Locale {
  try {
    const stored = globalThis.localStorage?.getItem(KEY);
    if (isLocale(stored)) {
      memory = stored;
      return stored;
    }
  } catch {
    /* Storage can be blocked. The in-memory choice still applies on this page. */
  }
  return memory;
}

export function localize(text: string, locale: Locale = readLocale()): string {
  if (locale !== "ar") return text;
  return arabic[text] ?? text;
}

export function missingArabic(labels: readonly string[]): string[] {
  return labels.filter((label) => arabic[label] === undefined);
}

export function applyDocumentLocale(locale: Locale): void {
  if (typeof document === "undefined") return;
  document.documentElement.lang = locale;
  document.documentElement.dir = locale === "ar" ? "rtl" : "ltr";
}

export function setLocale(locale: Locale): void {
  memory = locale;
  try {
    globalThis.localStorage?.setItem(KEY, locale);
  } catch {
    /* Private mode can block storage. The current page still switches. */
  }
  applyDocumentLocale(locale);
  listeners.forEach((listener) => listener());
}

export function subscribeLocale(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
