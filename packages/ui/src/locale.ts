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
  "Store WhatsApp": "واتساب المتجر",
  "Connect the number this store uses for marketing. Scan the QR from WhatsApp, then Linked devices.":
    "اربط الرقم الذي يستخدمه هذا المتجر للتسويق. امسح رمز QR من واتساب، ثم الأجهزة المرتبطة.",
  "QR waiting for scan": "بانتظار مسح رمز QR",
  Connected: "متصل",
  Connecting: "جارٍ الاتصال",
  Disconnected: "غير متصل",
  "Connection error": "خطأ في الاتصال",
  "Not connected": "غير متصل",
  "WhatsApp connection service is unavailable.": "خدمة اتصال واتساب غير متاحة.",
  "Evolution API could not be reached.": "تعذر الوصول إلى واجهة Evolution.",
  "Existing store settings are unchanged.": "إعدادات المتجر الحالية لم تتغير.",
  Retry: "إعادة المحاولة",
  "WhatsApp number": "رقم واتساب",
  "Last update": "آخر تحديث",
  "Not connected yet": "لم يتم الاتصال بعد",
  Webhook: "ويب هوك",
  "Not registered": "غير مسجّل",
  registered: "مسجّل",
  "Connection service": "الخدمة",
  Available: "متاحة",
  "Authentication error": "خطأ في المصادقة",
  Unavailable: "غير متاحة",
  "The connection check timed out. Refresh the QR and scan again.": "انتهت مهلة فحص الاتصال. حدّث رمز QR ثم امسحه مرة أخرى.",
  "Working…": "جارٍ العمل…",
  "Check connection": "فحص الاتصال",
  "Refresh QR": "تحديث رمز QR",
  "Connect WhatsApp": "ربط واتساب",
  "Refresh status": "تحديث الحالة",
  Disconnect: "قطع الاتصال",
  "WhatsApp QR code for this store": "رمز QR لواتساب هذا المتجر",
  "This QR may have expired. Refresh it, then scan again.": "قد يكون رمز QR منتهي الصلاحية. حدّثه ثم امسحه مرة أخرى.",
  "Scan within {seconds} seconds, then keep this page open.": "امسح خلال {seconds} ثانية، ثم أبقِ هذه الصفحة مفتوحة.",
  "Send a test message": "إرسال رسالة تجريبية",
  "Uses the same outbox as other WhatsApp messages. The session must be open, and the channel must use Evolution.":
    "تستخدم صندوق الإرسال نفسه لرسائل واتساب الأخرى. يجب أن تكون الجلسة متصلة، وأن تستخدم القناة Evolution.",
  "Test destination": "وجهة الرسالة التجريبية",
  "Sending…": "جارٍ الإرسال…",
  "Refresh until the session is open before sending.": "حدّث الحالة حتى تصبح الجلسة متصلة قبل الإرسال.",
  "The test message was not sent.": "لم تُرسل الرسالة التجريبية.",
  Recipient: "المستلم",
  Message: "الرسالة",
  Submitted: "وقت الإرسال",
  Outbox: "صندوق الإرسال",
  Provider: "المزوّد",
  Error: "خطأ",
  "Queued. It is in the outbox and has not been accepted yet.": "في الانتظار. الرسالة في صندوق الإرسال ولم تُقبل بعد.",
  "Accepted by the provider. Delivered and read are shown only after a webhook.":
    "قبلها المزوّد. يظهر التسليم والقراءة بعد وصول إشعار الويب هوك فقط.",
  "Failed.": "فشلت.",
  "Skipped.": "تم التخطي.",
  "All time": "كل الفترات",
  Weekly: "أسبوعي",
  Monthly: "شهري",
  Timeframe: "الفترة",
  "Retail Inventory": "مخزون التجزئة",
  "Totals could not be loaded.": "تعذر تحميل الإجماليات.",
  "Loading totals…": "جارٍ تحميل الإجماليات…",
  "Completed sales in {currency}.": "المبيعات المكتملة بعملة {currency}.",
  "Net revenue": "صافي الإيراد",
  "{count} total orders": "{count} طلبًا",
  "Units sold": "الوحدات المباعة",
  "No prior period": "لا توجد فترة سابقة",
  "No tenders": "لا توجد مدفوعات",
  "Average ticket": "متوسط الفاتورة",
  "Category mix": "توزيع الفئات",
  "Revenue by category": "الإيراد حسب الفئة",
  "POS register": "جهاز نقاط البيع",
  "Unlock register": "فتح جهاز البيع",
  "Select your cashier and enter your POS PIN to continue.": "اختر أمين الصندوق وأدخل الرقم السري للمتابعة.",
  Username: "اسم المستخدم",
  Cashiers: "أمناء الصندوق",
  "No cashier profiles are on this register yet.": "لا توجد ملفات أمناء صندوق على هذا الجهاز بعد.",
  "Choose a cashier": "اختيار أمين صندوق",
  "Use username instead": "استخدام اسم المستخدم",
  "New activation": "تفعيل جديد",
  "Username login": "الدخول باسم المستخدم",
  "Select a cashier": "اختر أمين صندوق",
  "Delete digit": "حذف رقم",
  "Clear PIN": "مسح الرقم السري",
  Clear: "مسح",
  "Checking…": "جارٍ التحقق…",
  Unlock: "فتح",
  "{count} digits entered": "تم إدخال {count} أرقام",
  "Receipt language": "لغة الإيصال",
  "Follow store preference": "اتباع تفضيل المتجر",
  "Printed receipts use this language. It does not follow the language of this screen.":
    "الإيصالات المطبوعة تستخدم هذه اللغة، وهي مستقلة عن لغة هذه الشاشة.",
  "Preview language": "لغة المعاينة",
  "Preview only. Saving uses the receipt language above.": "للمعاينة فقط. الحفظ يستخدم لغة الإيصال أعلاه.",
  "English preview": "معاينة بالإنجليزية",
  "Arabic preview": "معاينة بالعربية",
};

/** Latin tokens that stay unchanged in Arabic mode. The checker allows these exact values. */
export const localeKeepEnglish = ["English", "العربية", "AxizReach", "AxizPOS", "QR", "SKU", "VAT", "KDS"] as const;

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

export function localize(
  text: string,
  locale: Locale = readLocale(),
  vars?: Record<string, string | number>,
): string {
  let value = locale === "ar" ? (arabic[text] ?? text) : text;
  if (vars) {
    for (const [key, raw] of Object.entries(vars)) value = value.replaceAll(`{${key}}`, String(raw));
  }
  return value;
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
