export const Permission = {
  UsersCreate: "users:create",
  UsersRead: "users:read",
  UsersUpdate: "users:update",
  UsersDelete: "users:delete",
  RolesManage: "roles:manage",
  PosAccess: "pos:access",
  PosDiscount: "pos:discount",
  PosRefund: "pos:refund",
  PosDrawerOverride: "pos:drawer_override",
  PosPriceOverride: "pos:price_override",
  PosCreditSale: "pos:credit_sale",
  PortalAccess: "portal:access",
  PortalReportsRead: "portal:reports_read",
  PortalInventoryManage: "portal:inventory_manage",
  PortalPricingManage: "portal:pricing_manage",
  InventoryAdjustStock: "inventory:adjust_stock",
  CustomersManage: "customers:manage",
  RepairsCreate: "repairs:create",
  RepairsUpdate: "repairs:update",
  SettingsManage: "settings:manage",
  PosOpenPrice: "pos:open_price",
  PosBelowFloorOverride: "pos:below_floor_override",
  PosShiftManage: "pos:shift_manage",
  ReportsVat: "reports:vat",
  DevicesManage: "devices:manage",
  ChequesManage: "cheques:manage",
  WarrantyManage: "warranty:manage",
  ReplenishmentManage: "replenishment:manage",
  MessagingManage: "messaging:manage",
  CurrenciesManage: "currencies:manage",
  PayablesManage: "payables:manage",
  ExpensesManage: "expenses:manage",
  PosTradeIn: "pos:trade_in",
  PromotionsManage: "promotions:manage",
  StaffManage: "staff:manage",
  PayrollManage: "payroll:manage",
  BankingManage: "banking:manage",
  AccountingManage: "accounting:manage",
  AuditRead: "audit:read",
  PosOrders: "pos:orders",
  PosVoidSentItem: "pos:void_sent_item",
  KdsOperate: "kds:operate",
  SalesOrders: "sales:orders",
  GiftCardsManage: "gift_cards:manage",
  TaxFreeManage: "tax_free:manage",
  OnlineOrders: "online_orders:manage",
} as const;
export type Permission = (typeof Permission)[keyof typeof Permission];

export const SystemRoleId = {
  SuperAdmin: "00000000-0000-4000-8000-0000000000a1",
  StoreManager: "00000000-0000-4000-8000-0000000000a2",
  Cashier: "00000000-0000-4000-8000-0000000000a3",
  Technician: "00000000-0000-4000-8000-0000000000a4",
} as const;
export type SystemRoleId = (typeof SystemRoleId)[keyof typeof SystemRoleId];

export type TokenScope = "portal" | "pos";

export interface RoleSummary {
  id: string;
  name: string;
  /** Largest discount (basis points) the role gives without a manager; null uses the business default. */
  max_discount_bps?: number | null;
}

export interface Role {
  id: string;
  name: string;
  description: string;
  is_system: boolean;
  permissions: Permission[];
  user_count: number;
  /** Largest cashier discount without a manager, in basis points; null uses the till rules default. */
  max_discount_bps?: number | null;
  created_at: string;
  updated_at: string;
}

export interface PermissionGroup {
  group: string;
  permissions: { key: Permission; label: string }[];
}

export interface User {
  id: string;
  username: string;
  email: string;
  full_name: string;
  is_active: boolean;
  store_id: string | null;
  role: RoleSummary;
  permissions: Permission[];
  has_pos_access: boolean;
  has_portal_access: boolean;
  /** Extra grant to type a price on open-price items. A role may already include the same permission. */
  can_sell_open_price: boolean;
  has_password: boolean;
  has_pin: boolean;
  locked_until: string | null;
  last_login_at: string | null;
  created_at: string;
  updated_at: string;
  /** Active purchased add-ons this user may use. */
  addon_modules?: string[];
  /** Media URL for this user's photo. Null when they have not uploaded one. */
  avatar_url?: string | null;
}

export interface PasswordLoginRequest {
  username: string;
  password: string;
}

export interface PinLoginRequest {
  username: string;
  pin: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
  scope: TokenScope;
  expires_in: number;
  user: User;
}

export interface UserCreate {
  username: string;
  email: string;
  full_name: string;
  role_id: string;
  store_id?: string | null;
  password?: string | null;
  pin?: string | null;
  has_pos_access: boolean;
  has_portal_access: boolean;
  can_sell_open_price?: boolean;
  is_active: boolean;
}

export interface UserUpdate {
  email?: string;
  full_name?: string;
  role_id?: string;
  store_id?: string;
  clear_store?: boolean;
  has_pos_access?: boolean;
  has_portal_access?: boolean;
  can_sell_open_price?: boolean;
  is_active?: boolean;
}

export interface RoleCreate {
  name: string;
  description?: string;
  permissions: Permission[];
  max_discount_bps?: number | null;
}

export interface RoleUpdate {
  name?: string;
  description?: string;
  permissions?: Permission[];
  max_discount_bps?: number | null;
}

export const PIN_PATTERN = /^\d{4,6}$/;
export const PASSWORD_MIN_LENGTH = 10;

export function hasPermission(user: Pick<User, "permissions"> | null, permission: Permission): boolean {
  return user !== null && user.permissions.includes(permission);
}
