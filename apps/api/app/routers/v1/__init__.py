from fastapi import APIRouter, Depends

from app.core.capabilities import Capability, require_capability
from app.routers.v1.accounting import router as accounting_router
from app.routers.v1.addon_access import router as addon_access_router
from app.routers.v1.analytics import router as analytics_router
from app.routers.v1.approvals import router as approvals_router
from app.routers.v1.assistant import router as assistant_router
from app.routers.v1.audit import router as audit_router
from app.routers.v1.auth import router as auth_router
from app.routers.v1.banking import router as banking_router
from app.routers.v1.batches import router as batches_router
from app.routers.v1.billing import router as billing_router
from app.routers.v1.brands import models_router as product_models_router
from app.routers.v1.brands import router as brands_router
from app.routers.v1.catalogue import router as catalogue_router
from app.routers.v1.categories import router as categories_router
from app.routers.v1.channels import router as channels_router
from app.routers.v1.cheques import router as cheques_router
from app.routers.v1.consignment import router as consignment_router
from app.routers.v1.currencies import router as currencies_router
from app.routers.v1.customers import router as customers_router
from app.routers.v1.devices import router as devices_router
from app.routers.v1.dining import router as dining_router
from app.routers.v1.downloads import router as downloads_router
from app.routers.v1.einvoices import router as einvoices_router
from app.routers.v1.expenses import router as expenses_router
from app.routers.v1.expiry import router as expiry_router
from app.routers.v1.fnb_table_orders import router as fnb_table_orders_router
from app.routers.v1.fnb_table_orders import ws_router as fnb_table_ws_router
from app.routers.v1.gift_cards import router as gift_cards_router
from app.routers.v1.grocery import router as grocery_router
from app.routers.v1.insights import router as insights_router
from app.routers.v1.integrations import router as integrations_router
from app.routers.v1.inventory import router as inventory_router
from app.routers.v1.kds import router as kds_router
from app.routers.v1.kitchen_agent import router as kitchen_agent_router
from app.routers.v1.labels import router as labels_router
from app.routers.v1.live_socket import router as live_ws_router
from app.routers.v1.loyalty import exports_router
from app.routers.v1.loyalty import router as loyalty_router
from app.routers.v1.management_reports import router as management_router
from app.routers.v1.manager import router as manager_router
from app.routers.v1.margin import router as margin_router
from app.routers.v1.markdowns import router as markdowns_router
from app.routers.v1.menu import router as menu_router
from app.routers.v1.messaging import jobs_router
from app.routers.v1.messaging import router as messaging_router
from app.routers.v1.onboarding import router as onboarding_router
from app.routers.v1.orders import router as orders_router
from app.routers.v1.payables import router as payables_router
from app.routers.v1.payments import router as payments_router
from app.routers.v1.price_lists import router as price_lists_router
from app.routers.v1.pricing import router as pricing_router
from app.routers.v1.products import router as products_router
from app.routers.v1.promotions import router as promotions_router
from app.routers.v1.quotes import router as quotes_router
from app.routers.v1.recipes import router as recipes_router
from app.routers.v1.register import router as register_router
from app.routers.v1.reorders import router as reorders_router
from app.routers.v1.repair_workshop import router as repair_workshop_router
from app.routers.v1.repairs import router as repairs_router
from app.routers.v1.replenishment import router as replenishment_router
from app.routers.v1.reports import router as reports_router
from app.routers.v1.returns import router as returns_router
from app.routers.v1.roles import router as roles_router
from app.routers.v1.sales import router as sales_router
from app.routers.v1.sales_orders import router as sales_orders_router
from app.routers.v1.serials import router as serials_router
from app.routers.v1.settings import router as settings_router
from app.routers.v1.shifts import router as shifts_router
from app.routers.v1.site import router as site_router
from app.routers.v1.staff import router as staff_router
from app.routers.v1.stock_counts import router as stock_counts_router
from app.routers.v1.store_credits import router as store_credits_router
from app.routers.v1.stores import router as stores_router
from app.routers.v1.sync import router as sync_router
from app.routers.v1.tenant import router as tenant_router
from app.routers.v1.terminals import router as terminals_router
from app.routers.v1.timesheets import router as timesheets_router
from app.routers.v1.trade_ins import router as trade_ins_router
from app.routers.v1.units import router as units_router
from app.routers.v1.users import router as users_router
from app.routers.v1.warranties import router as warranties_router


def module(capability: Capability) -> list:
    """Gates a whole router behind a business module (capability); 403 while it is switched off."""
    return [Depends(require_capability(capability))]


api_router = APIRouter()
api_router.include_router(tenant_router, prefix="/tenant", tags=["tenancy"])
api_router.include_router(terminals_router, prefix="/terminals", tags=["tenancy"])
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(addon_access_router, prefix="/addon-access", tags=["addon access"])
api_router.include_router(users_router, prefix="/users", tags=["users"])
api_router.include_router(roles_router, prefix="/roles", tags=["roles"])
api_router.include_router(stores_router, prefix="/stores", tags=["stores"])
api_router.include_router(products_router, prefix="/products", tags=["products"])
api_router.include_router(catalogue_router, tags=["catalogue"])
api_router.include_router(units_router, prefix="/units", tags=["units of measure"])
api_router.include_router(categories_router, prefix="/categories", tags=["categories"])
api_router.include_router(brands_router, prefix="/brands", tags=["brands"])
api_router.include_router(product_models_router, prefix="/product-models", tags=["brands"])
api_router.include_router(stock_counts_router, prefix="/inventory/counts", tags=["stock counts"])
api_router.include_router(inventory_router, prefix="/inventory", tags=["inventory"])
api_router.include_router(register_router, prefix="/inventory", tags=["inventory"])
api_router.include_router(batches_router, prefix="/inventory", tags=["purchase batches"])
api_router.include_router(expiry_router, prefix="/inventory", tags=["expiry"], dependencies=module(Capability.FEFO))
api_router.include_router(grocery_router, prefix="/grocery", tags=["grocery"])
api_router.include_router(
    pricing_router, prefix="/pricing", tags=["pricing"], dependencies=module(Capability.WHOLESALE_PRICING)
)
api_router.include_router(price_lists_router, prefix="/price-lists", tags=["price lists"])
api_router.include_router(customers_router, prefix="/customers", tags=["customers"])
api_router.include_router(
    quotes_router, prefix="/quotes", tags=["quotes"], dependencies=module(Capability.QUOTES_LAYAWAY)
)
api_router.include_router(sales_router, prefix="/sales", tags=["sales"])
api_router.include_router(
    sales_orders_router,
    prefix="/sales-orders",
    tags=["sales orders"],
    dependencies=module(Capability.SALES_ORDERS),
)
api_router.include_router(
    reorders_router,
    prefix="/reorders",
    tags=["reorders"],
    dependencies=module(Capability.CUSTOMER_REORDERS),
)
api_router.include_router(returns_router, prefix="/returns", tags=["returns"])
api_router.include_router(
    repair_workshop_router, prefix="/repairs", tags=["repairs"], dependencies=module(Capability.REPAIRS)
)
api_router.include_router(repairs_router, prefix="/repairs", tags=["repairs"], dependencies=module(Capability.REPAIRS))
api_router.include_router(analytics_router, prefix="/analytics", tags=["analytics"])
api_router.include_router(sync_router, prefix="/sync", tags=["sync"])
api_router.include_router(settings_router, prefix="/settings", tags=["settings"])
api_router.include_router(audit_router, prefix="/audit-logs", tags=["audit"])
api_router.include_router(devices_router, prefix="/devices", tags=["devices"])
api_router.include_router(downloads_router, prefix="/downloads", tags=["downloads"])
api_router.include_router(management_router, prefix="/reports/management", tags=["management reports"])
api_router.include_router(insights_router, prefix="/insights", tags=["insights"])
api_router.include_router(reports_router, prefix="/reports", tags=["reports"])
api_router.include_router(shifts_router, prefix="/shifts", tags=["shifts"])
api_router.include_router(cheques_router, prefix="/cheques", tags=["cheques"], dependencies=module(Capability.CHEQUES))
api_router.include_router(einvoices_router, prefix="/einvoices", tags=["einvoices"])
api_router.include_router(labels_router, prefix="/labels", tags=["labels"])
api_router.include_router(markdowns_router, prefix="/markdowns", tags=["markdowns"])
api_router.include_router(
    consignment_router, prefix="/consignment", tags=["consignment"], dependencies=module(Capability.CONSIGNMENT)
)
api_router.include_router(messaging_router, prefix="/messaging", tags=["messaging"])
api_router.include_router(jobs_router, prefix="/jobs", tags=["jobs"])
api_router.include_router(margin_router, prefix="/margin", tags=["margin"])
api_router.include_router(menu_router, prefix="/menu", tags=["menu"], dependencies=module(Capability.MENU_MODIFIERS))
api_router.include_router(orders_router, prefix="/orders", tags=["orders"], dependencies=module(Capability.OPEN_ORDERS))
api_router.include_router(dining_router, prefix="/dining", tags=["dining"], dependencies=module(Capability.TABLES))
api_router.include_router(
    fnb_table_orders_router,
    prefix="/fnb",
    tags=["fnb"],
    dependencies=module(Capability.OPEN_ORDERS) + module(Capability.TABLES),
)
api_router.include_router(fnb_table_ws_router, prefix="/ws", tags=["fnb"])
api_router.include_router(live_ws_router, prefix="/ws", tags=["live"])
api_router.include_router(kds_router, prefix="/kds", tags=["kds"], dependencies=module(Capability.KDS))
api_router.include_router(
    channels_router, prefix="/channels", tags=["channels"], dependencies=module(Capability.DELIVERY_CHANNELS)
)
api_router.include_router(recipes_router, prefix="/recipes", tags=["recipes"], dependencies=module(Capability.RECIPES))
api_router.include_router(
    kitchen_agent_router,
    prefix="/kitchen-agent",
    tags=["kitchen agent"],
    dependencies=module(Capability.RECIPES),
)
api_router.include_router(
    warranties_router, prefix="/warranties", tags=["warranties"], dependencies=module(Capability.WARRANTY)
)
api_router.include_router(replenishment_router, prefix="/replenishment", tags=["replenishment"])
api_router.include_router(payments_router, prefix="/payments", tags=["payments"])
api_router.include_router(integrations_router, prefix="/integrations", tags=["integrations"])
api_router.include_router(
    currencies_router, prefix="/currencies", tags=["currencies"], dependencies=module(Capability.MULTI_CURRENCY)
)
api_router.include_router(loyalty_router, prefix="/loyalty", tags=["loyalty"], dependencies=module(Capability.LOYALTY))
api_router.include_router(exports_router, prefix="/exports", tags=["exports"])
api_router.include_router(store_credits_router, prefix="/store-credits", tags=["store credit"])
api_router.include_router(
    gift_cards_router, prefix="/gift-cards", tags=["gift cards"], dependencies=module(Capability.GIFT_CARDS)
)
api_router.include_router(payables_router, prefix="/payables", tags=["payables"])
api_router.include_router(expenses_router, prefix="/expenses", tags=["expenses"])
api_router.include_router(
    trade_ins_router, prefix="/trade-ins", tags=["trade-ins"], dependencies=module(Capability.TRADE_IN)
)
api_router.include_router(
    promotions_router, prefix="/promotions", tags=["promotions"], dependencies=module(Capability.PROMOTIONS)
)
api_router.include_router(timesheets_router, prefix="/timesheets", tags=["timesheets"])
api_router.include_router(staff_router, prefix="/staff", tags=["staff"])
api_router.include_router(banking_router, prefix="/bank", tags=["bank reconciliation"])
api_router.include_router(approvals_router, prefix="/approvals", tags=["approvals"])
api_router.include_router(manager_router, prefix="/manager", tags=["manager"])
api_router.include_router(assistant_router, prefix="/assistant", tags=["assistant"])
api_router.include_router(accounting_router, prefix="/accounting", tags=["accounting"])
api_router.include_router(serials_router, prefix="/serials", tags=["serials"])
api_router.include_router(onboarding_router, prefix="/onboarding", tags=["onboarding"])
api_router.include_router(billing_router, prefix="/billing", tags=["billing"])
api_router.include_router(site_router, prefix="/site", tags=["site"])
