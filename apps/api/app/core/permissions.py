from enum import StrEnum


class Permission(StrEnum):
    USERS_CREATE = "users:create"
    USERS_READ = "users:read"
    USERS_UPDATE = "users:update"
    USERS_DELETE = "users:delete"
    ROLES_MANAGE = "roles:manage"
    POS_ACCESS = "pos:access"
    POS_DISCOUNT = "pos:discount"
    POS_REFUND = "pos:refund"
    POS_DRAWER_OVERRIDE = "pos:drawer_override"
    POS_PRICE_OVERRIDE = "pos:price_override"
    POS_CREDIT_SALE = "pos:credit_sale"
    PORTAL_ACCESS = "portal:access"
    PORTAL_REPORTS_READ = "portal:reports_read"
    PORTAL_INVENTORY_MANAGE = "portal:inventory_manage"
    PORTAL_PRICING_MANAGE = "portal:pricing_manage"
    INVENTORY_ADJUST_STOCK = "inventory:adjust_stock"
    CUSTOMERS_MANAGE = "customers:manage"
    REPAIRS_CREATE = "repairs:create"
    REPAIRS_UPDATE = "repairs:update"
    SETTINGS_MANAGE = "settings:manage"
    AUDIT_READ = "audit:read"
    POS_OPEN_PRICE = "pos:open_price"
    POS_BELOW_FLOOR_OVERRIDE = "pos:below_floor_override"
    POS_SHIFT_MANAGE = "pos:shift_manage"
    REPORTS_VAT = "reports:vat"
    DEVICES_MANAGE = "devices:manage"
    CHEQUES_MANAGE = "cheques:manage"
    WARRANTY_MANAGE = "warranty:manage"
    REPLENISHMENT_MANAGE = "replenishment:manage"
    MESSAGING_MANAGE = "messaging:manage"
    CURRENCIES_MANAGE = "currencies:manage"
    PAYABLES_MANAGE = "payables:manage"
    EXPENSES_MANAGE = "expenses:manage"
    POS_TRADE_IN = "pos:trade_in"
    PROMOTIONS_MANAGE = "promotions:manage"
    STAFF_MANAGE = "staff:manage"
    PAYROLL_MANAGE = "payroll:manage"
    BANKING_MANAGE = "banking:manage"
    ACCOUNTING_MANAGE = "accounting:manage"
    POS_ORDERS = "pos:orders"
    POS_VOID_SENT_ITEM = "pos:void_sent_item"
    KDS_OPERATE = "kds:operate"
    SALES_ORDERS = "sales:orders"
    GIFT_CARDS_MANAGE = "gift_cards:manage"
    TAX_FREE_MANAGE = "tax_free:manage"
    ONLINE_ORDERS = "online_orders:manage"


# Granted to Store Managers by migration 20261019_0012.
ERP_MANAGER_PERMISSIONS = (
    "pos:open_price",
    "pos:below_floor_override",
    "pos:shift_manage",
    "reports:vat",
    "devices:manage",
    "cheques:manage",
    "warranty:manage",
    "replenishment:manage",
    "messaging:manage",
    "currencies:manage",
)

# Granted to Store Managers by migrations 20261020_0031 (staff:manage by 20261020_0035).
BACK_OFFICE_MANAGER_PERMISSIONS = (
    "payables:manage",
    "expenses:manage",
    "pos:trade_in",
    "promotions:manage",
    "staff:manage",
)

# Restaurant permissions, granted by migration 20261021_0050: managers get all of them, cashiers take orders.
RESTAURANT_MANAGER_PERMISSIONS = ("pos:orders", "pos:void_sent_item", "kds:operate")
RESTAURANT_CASHIER_PERMISSIONS = ("pos:orders",)

# Wholesale fulfilment, granted to Store Managers by migration 20261021_0058.
FULFILMENT_MANAGER_PERMISSIONS = ("sales:orders",)

# Retail and fashion back office, granted to Store Managers by migration 20261021_0059.
RETAIL_MANAGER_PERMISSIONS = ("gift_cards:manage", "tax_free:manage", "online_orders:manage")


ALL_PERMISSIONS: frozenset[str] = frozenset(item.value for item in Permission)

PERMISSION_GROUPS: dict[str, list[tuple[Permission, str]]] = {
    "Users": [
        (Permission.USERS_CREATE, "Create users"),
        (Permission.USERS_READ, "View users"),
        (Permission.USERS_UPDATE, "Edit users, reset passwords and PINs"),
        (Permission.USERS_DELETE, "Delete users"),
    ],
    "Roles": [(Permission.ROLES_MANAGE, "Create and edit roles")],
    "Point of sale": [
        (Permission.POS_ACCESS, "Unlock a register and sell"),
        (Permission.POS_DISCOUNT, "Apply discounts"),
        (Permission.POS_REFUND, "Issue refunds"),
        (Permission.POS_DRAWER_OVERRIDE, "Open the cash drawer without a sale"),
        (Permission.POS_PRICE_OVERRIDE, "Approve manual price overrides"),
        (Permission.POS_CREDIT_SALE, "Sell on account to wholesale customers"),
        (Permission.POS_OPEN_PRICE, "Sell open-price items with a typed price"),
        (Permission.POS_BELOW_FLOOR_OVERRIDE, "Approve prices below the margin floor"),
        (Permission.POS_SHIFT_MANAGE, "Review and force-close other cashiers' shifts"),
        (Permission.POS_TRADE_IN, "Buy used devices from customers as trade-ins"),
        (Permission.POS_ORDERS, "Open tables and tabs, and send orders to the kitchen"),
        (Permission.POS_VOID_SENT_ITEM, "Approve voiding items already sent to the kitchen"),
        (Permission.KDS_OPERATE, "Work kitchen display tickets (start, ready, bump, recall)"),
    ],
    "Finance": [
        (Permission.REPORTS_VAT, "View and export VAT reports"),
        (Permission.GIFT_CARDS_MANAGE, "Issue, void and review gift cards"),
        (Permission.TAX_FREE_MANAGE, "Export tax-free forms and record their refund status"),
        (Permission.CHEQUES_MANAGE, "Manage post-dated cheques"),
        (Permission.CURRENCIES_MANAGE, "Manage accepted currencies and exchange rates"),
        (Permission.PAYABLES_MANAGE, "Record supplier bills and pay suppliers"),
        (Permission.EXPENSES_MANAGE, "Record expenses and petty cash"),
        (Permission.BANKING_MANAGE, "Import bank statements and reconcile bank accounts"),
        (Permission.ACCOUNTING_MANAGE, "General ledger, journals, financial statements, closing and corporate tax"),
    ],
    "Marketing": [(Permission.PROMOTIONS_MANAGE, "Create promotions, bundles and coupon codes")],
    "Staff": [
        (Permission.STAFF_MANAGE, "Approve timesheets and set sales commissions"),
        (Permission.PAYROLL_MANAGE, "See salaries, run payroll and export the WPS file"),
    ],
    "Operations": [
        (Permission.DEVICES_MANAGE, "Register and revoke POS registers"),
        (Permission.WARRANTY_MANAGE, "Manage warranties and service plans"),
        (Permission.REPLENISHMENT_MANAGE, "Run and accept replenishment suggestions"),
        (Permission.MESSAGING_MANAGE, "Configure customer messaging"),
    ],
    "Web portal": [
        (Permission.PORTAL_ACCESS, "Sign in to the web portal"),
        (Permission.PORTAL_REPORTS_READ, "View sales and analytics"),
        (Permission.PORTAL_INVENTORY_MANAGE, "Manage stores and products"),
        (Permission.PORTAL_PRICING_MANAGE, "Manage price tiers and volume discounts"),
    ],
    "Inventory": [
        (Permission.INVENTORY_ADJUST_STOCK, "Manually adjust branch stock and write off IMEI units"),
    ],
    "Customers": [
        (Permission.CUSTOMERS_MANAGE, "Manage customer accounts, credit, and payments"),
        (Permission.SALES_ORDERS, "Take sales orders, pick, dispatch and invoice deliveries"),
        (Permission.ONLINE_ORDERS, "Fulfil online-store orders and manage store connections"),
    ],
    "Repairs": [
        (Permission.REPAIRS_CREATE, "Open repair tickets"),
        (Permission.REPAIRS_UPDATE, "Update repair tickets"),
    ],
    "Settings": [(Permission.SETTINGS_MANAGE, "Change business settings such as the currency")],
    "Security": [(Permission.AUDIT_READ, "View and export the audit trail")],
}

SUPER_ADMIN_ROLE_ID = "00000000-0000-4000-8000-0000000000a1"
STORE_MANAGER_ROLE_ID = "00000000-0000-4000-8000-0000000000a2"
CASHIER_ROLE_ID = "00000000-0000-4000-8000-0000000000a3"
TECHNICIAN_ROLE_ID = "00000000-0000-4000-8000-0000000000a4"

SYSTEM_ROLES: list[dict[str, object]] = [
    {
        "id": SUPER_ADMIN_ROLE_ID,
        "name": "Super Admin",
        "description": "Unrestricted access across every store.",
        "permissions": sorted(ALL_PERMISSIONS),
        "max_discount_bps": 10_000,
    },
    {
        "id": STORE_MANAGER_ROLE_ID,
        "name": "Store Manager",
        "description": "Runs one store: staff, registers, inventory, and reports.",
        "max_discount_bps": 5_000,
        "permissions": sorted(
            [
                Permission.USERS_CREATE,
                Permission.USERS_READ,
                Permission.USERS_UPDATE,
                Permission.POS_ACCESS,
                Permission.POS_DISCOUNT,
                Permission.POS_REFUND,
                Permission.POS_DRAWER_OVERRIDE,
                Permission.POS_PRICE_OVERRIDE,
                Permission.POS_CREDIT_SALE,
                Permission.PORTAL_ACCESS,
                Permission.PORTAL_REPORTS_READ,
                Permission.PORTAL_INVENTORY_MANAGE,
                Permission.PORTAL_PRICING_MANAGE,
                Permission.INVENTORY_ADJUST_STOCK,
                Permission.CUSTOMERS_MANAGE,
                Permission.REPAIRS_CREATE,
                Permission.REPAIRS_UPDATE,
                *(Permission(item) for item in ERP_MANAGER_PERMISSIONS),
                *(Permission(item) for item in BACK_OFFICE_MANAGER_PERMISSIONS),
                *(Permission(item) for item in RESTAURANT_MANAGER_PERMISSIONS),
                *(Permission(item) for item in FULFILMENT_MANAGER_PERMISSIONS),
                *(Permission(item) for item in RETAIL_MANAGER_PERMISSIONS),
            ]
        ),
    },
    {
        "id": CASHIER_ROLE_ID,
        "name": "Cashier",
        "description": "Sells at the register and opens repair tickets.",
        "permissions": sorted(
            [Permission.POS_ACCESS, Permission.POS_CREDIT_SALE, Permission.REPAIRS_CREATE, Permission.POS_ORDERS]
        ),
    },
    {
        "id": TECHNICIAN_ROLE_ID,
        "name": "Technician",
        "description": "Works repair tickets.",
        "permissions": sorted([Permission.POS_ACCESS, Permission.REPAIRS_CREATE, Permission.REPAIRS_UPDATE]),
    },
]
