"""Add tenant_id to every operational table and isolate rows by store.

Revision ID: 20261024_0071
Revises: 20261024_0070
Create Date: 2026-10-24

Each existing store database is still one store. Rows are stamped with that store's id
(ALEMBIC_TENANT_ID, or the tenant registered for this database). A foreign key to tenants
is added only when that control table lives in the same database. Postgres also forces
row-level security; request sessions set app.tenant_id, and migrations set app.bypass_rls.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261024_0071"
down_revision: str | None = "20261024_0070"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "accepted_currencies",
    "approval_requests",
    "audit_logs",
    "bank_accounts",
    "bank_statement_lines",
    "bank_statements",
    "batch_allocations",
    "batch_items",
    "brands",
    "business_settings",
    "cash_movements",
    "categories",
    "channel_payouts",
    "cheque_events",
    "cheques",
    "combo_slot_options",
    "combo_slots",
    "commission_rules",
    "consignment_settlement_lines",
    "consignment_settlements",
    "customer_groups",
    "customer_ledger_entries",
    "customers",
    "delivery_channels",
    "delivery_note_lines",
    "delivery_notes",
    "demand_daily",
    "device_activations",
    "devices",
    "dining_areas",
    "dining_tables",
    "document_sequences",
    "e_invoice_chains",
    "e_invoices",
    "employee_profiles",
    "exchange_rates",
    "expenses",
    "gl_accounts",
    "goods_receipt_lines",
    "goods_receipts",
    "import_mapping_templates",
    "inventory_levels",
    "journal_entries",
    "journal_lines",
    "kitchen_stations",
    "kitchen_ticket_items",
    "kitchen_tickets",
    "loyalty_entries",
    "margin_policies",
    "markdown_events",
    "message_templates",
    "modifier_groups",
    "modifier_ingredients",
    "modifier_options",
    "open_order_items",
    "open_orders",
    "outbound_messages",
    "payment_intents",
    "payment_refunds",
    "payment_terminals",
    "payroll_lines",
    "payroll_runs",
    "petty_cash_entries",
    "pick_list_lines",
    "pick_lists",
    "price_changes",
    "price_list_items",
    "price_lists",
    "product_images",
    "product_models",
    "product_modifier_groups",
    "product_prices",
    "products",
    "promotion_redemptions",
    "promotions",
    "purchase_batches",
    "purchase_order_lines",
    "purchase_orders",
    "quote_payments",
    "recipe_lines",
    "recipe_usages",
    "recipes",
    "register_shifts",
    "repair_attachments",
    "repair_deposits",
    "repair_events",
    "repair_lines",
    "repair_tickets",
    "replenishment_runs",
    "replenishment_suggestions",
    "return_items",
    "return_tenders",
    "returns",
    "role_permissions",
    "roles",
    "sale_items",
    "sale_tenders",
    "sales",
    "sales_order_lines",
    "sales_orders",
    "scheduled_jobs",
    "scheduled_price_change_lines",
    "scheduled_price_changes",
    "seasonal_events",
    "serial_numbers",
    "stock_count_lines",
    "stock_counts",
    "stock_movements",
    "stock_transfer_lines",
    "stock_transfer_serials",
    "stock_transfers",
    "store_credit_redemptions",
    "store_credits",
    "stores",
    "sub_categories",
    "supplier_bill_lines",
    "supplier_bills",
    "supplier_payment_allocations",
    "supplier_payments",
    "suppliers",
    "sync_events",
    "tax_authority_credentials",
    "time_entries",
    "trade_ins",
    "units_of_measure",
    "users",
    "warranty_plans",
    "warranty_policies",
    "warranty_registrations",
)

UNIQUES = (
    ("audit_logs", "uq_audit_logs_client_event_id", ("tenant_id", "client_event_id")),
    ("bank_statement_lines", "uq_bank_statement_lines_hash", ("tenant_id", "account_id", "line_hash")),
    ("bank_statement_lines", "uq_bank_statement_lines_matched", ("tenant_id", "account_id", "matched_key")),
    ("brands", "uq_brands_code", ("tenant_id", "code")),
    ("brands", "uq_brands_name", ("tenant_id", "name")),
    ("categories", "uq_categories_code", ("tenant_id", "code")),
    ("categories", "uq_categories_name", ("tenant_id", "name")),
    ("combo_slot_options", "uq_combo_slot_options_slot_product", ("tenant_id", "slot_id", "product_id")),
    ("consignment_settlements", "uq_consignment_settlements_bill_id", ("tenant_id", "bill_id")),
    ("consignment_settlements", "uq_consignment_settlements_number", ("tenant_id", "number")),
    ("customer_groups", "uq_customer_groups_name", ("tenant_id", "name")),
    ("customers", "uq_customers_code", ("tenant_id", "code")),
    ("delivery_channels", "uq_delivery_channels_code", ("tenant_id", "code")),
    ("delivery_notes", "uq_delivery_notes_number", ("tenant_id", "number")),
    ("device_activations", "uq_device_activations_code_hash", ("tenant_id", "code_hash")),
    ("devices", "uq_devices_key_hash", ("tenant_id", "key_hash")),
    ("devices", "uq_devices_store_code", ("tenant_id", "store_id", "code")),
    ("dining_tables", "uq_dining_tables_area_label", ("tenant_id", "area_id", "label")),
    ("document_sequences", "uq_document_sequences_prefix", ("tenant_id", "prefix")),
    ("e_invoices", "uq_e_invoices_counter", ("tenant_id", "authority", "counter")),
    ("e_invoices", "uq_e_invoices_document_uuid", ("tenant_id", "document_uuid")),
    ("e_invoices", "uq_e_invoices_source", ("tenant_id", "source_type", "source_id")),
    ("employee_profiles", "uq_employee_profiles_user_id", ("tenant_id", "user_id")),
    ("expenses", "uq_expenses_number", ("tenant_id", "number")),
    ("gl_accounts", "uq_gl_accounts_code", ("tenant_id", "code")),
    ("goods_receipts", "uq_goods_receipts_number", ("tenant_id", "number")),
    ("import_mapping_templates", "uq_import_mapping_templates_supplier_name", ("tenant_id", "supplier_id", "name")),
    ("inventory_levels", "uq_inventory_levels_product_store", ("tenant_id", "product_id", "store_id")),
    ("journal_entries", "uq_journal_entries_number", ("tenant_id", "number")),
    ("margin_policies", "uq_margin_policy_target", ("tenant_id", "scope", "category_id", "product_id")),
    ("message_templates", "uq_message_templates_key", ("tenant_id", "key")),
    ("modifier_ingredients", "uq_modifier_ingredients_option_ingredient", ("tenant_id", "option_id", "ingredient_id")),
    ("open_orders", "uq_open_orders_channel_ref", ("tenant_id", "channel_id", "external_ref")),
    ("outbound_messages", "uq_outbound_messages_dedupe_key", ("tenant_id", "dedupe_key")),
    ("payment_terminals", "uq_payment_terminals_ref", ("tenant_id", "provider", "terminal_ref")),
    ("payroll_lines", "uq_payroll_lines_run_user", ("tenant_id", "run_id", "user_id")),
    ("payroll_runs", "uq_payroll_runs_period", ("tenant_id", "year", "month")),
    ("pick_lists", "uq_pick_lists_number", ("tenant_id", "number")),
    ("price_list_items", "uq_price_list_items_list_product", ("tenant_id", "price_list_id", "product_id")),
    ("product_images", "uq_product_images_key", ("tenant_id", "key")),
    ("product_images", "uq_product_images_thumb_key", ("tenant_id", "thumb_key")),
    ("product_models", "uq_product_models_brand_sub_name", ("tenant_id", "brand_id", "sub_category_id", "name")),
    ("product_prices", "uq_product_prices_product_tier", ("tenant_id", "product_id", "price_tier")),
    ("products", "uq_products_barcode", ("tenant_id", "barcode")),
    ("products", "uq_products_plu_code", ("tenant_id", "plu_code")),
    ("products", "uq_products_sku", ("tenant_id", "sku")),
    ("promotions", "uq_promotions_coupon_code", ("tenant_id", "coupon_code")),
    ("purchase_batches", "uq_purchase_batches_batch_number", ("tenant_id", "batch_number")),
    ("purchase_orders", "uq_purchase_orders_number", ("tenant_id", "number")),
    ("recipe_lines", "uq_recipe_lines_recipe_ingredient", ("tenant_id", "recipe_id", "ingredient_id")),
    ("recipes", "uq_recipes_product_id", ("tenant_id", "product_id")),
    ("register_shifts", "uq_register_shifts_z_number", ("tenant_id", "z_number")),
    ("repair_tickets", "uq_repair_tickets_tracking_token", ("tenant_id", "tracking_token")),
    ("returns", "uq_returns_credit_note_number", ("tenant_id", "credit_note_number")),
    ("roles", "uq_roles_name", ("tenant_id", "name")),
    ("sale_items", "uq_sale_items_gift_card_code", ("tenant_id", "gift_card_code")),
    ("sales", "uq_sales_client_sale_id", ("tenant_id", "client_sale_id")),
    ("sales", "uq_sales_invoice_number", ("tenant_id", "invoice_number")),
    ("sales_orders", "uq_sales_orders_number", ("tenant_id", "number")),
    ("serial_numbers", "uq_serial_numbers_value_hash", ("tenant_id", "value_hash")),
    ("stock_count_lines", "uq_stock_count_lines_count_product", ("tenant_id", "count_id", "product_id")),
    ("stock_counts", "uq_stock_counts_number", ("tenant_id", "number")),
    ("stock_transfers", "uq_stock_transfers_number", ("tenant_id", "number")),
    ("store_credit_redemptions", "uq_store_credit_redemption_sale", ("tenant_id", "store_credit_id", "sale_id")),
    ("store_credits", "uq_store_credits_code", ("tenant_id", "code")),
    ("stores", "uq_stores_code", ("tenant_id", "code")),
    ("sub_categories", "uq_sub_categories_category_code", ("tenant_id", "category_id", "code")),
    ("sub_categories", "uq_sub_categories_category_name", ("tenant_id", "category_id", "name")),
    ("supplier_bills", "uq_supplier_bills_goods_receipt_id", ("tenant_id", "goods_receipt_id")),
    ("supplier_bills", "uq_supplier_bills_purchase_batch_id", ("tenant_id", "purchase_batch_id")),
    ("supplier_bills", "uq_supplier_bills_supplier_number", ("tenant_id", "supplier_id", "number")),
    ("suppliers", "uq_suppliers_code", ("tenant_id", "code")),
    ("suppliers", "uq_suppliers_name", ("tenant_id", "name")),
    ("sync_events", "uq_sync_events_idempotency_key", ("tenant_id", "idempotency_key")),
    ("trade_ins", "uq_trade_ins_number", ("tenant_id", "number")),
    ("units_of_measure", "uq_units_of_measure_code", ("tenant_id", "code")),
    ("users", "uq_users_email", ("tenant_id", "email")),
    ("users", "uq_users_username", ("tenant_id", "username")),
    ("warranty_plans", "uq_warranty_plans_product_id", ("tenant_id", "product_id")),
    ("warranty_registrations", "uq_warranty_registrations_sale_item_id", ("tenant_id", "sale_item_id")),
)

POLICY = (
    "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid "
    "OR current_setting('app.bypass_rls', true) = 'on') "
    "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid "
    "OR current_setting('app.bypass_rls', true) = 'on')"
)


def _tenant_id() -> uuid.UUID:
    explicit = os.environ.get("ALEMBIC_TENANT_ID")
    if explicit:
        return uuid.UUID(explicit)
    from app.core.config import get_settings
    from app.tenancy.scoping import DEFAULT_TENANT_ID, tenant_ref_for_database

    if get_settings().tenancy_enabled:
        ref = tenant_ref_for_database(str(op.get_bind().engine.url))
        if ref.slug != "default":
            return uuid.UUID(ref.id)
    return DEFAULT_TENANT_ID


def _replace_uniques() -> None:
    inspector = sa.inspect(op.get_bind())
    by_table: dict[str, list[tuple[str, tuple[str, ...], tuple[str, ...]]]] = {}
    for table, name, cols in UNIQUES:
        by_table.setdefault(table, []).append((name, tuple(col for col in cols if col != "tenant_id"), tuple(cols)))
    for table, items in by_table.items():
        old = {item[1] for item in items}
        dropped: set[str] = set()
        for constraint in inspector.get_unique_constraints(table):
            cols = tuple(constraint.get("column_names") or ())
            cname = constraint.get("name")
            if cname and cols in old:
                op.drop_constraint(cname, table, type_="unique")
                dropped.add(cname)
        for index in inspector.get_indexes(table):
            iname = index.get("name") or ""
            cols = tuple(index.get("column_names") or ())
            if index.get("unique") and iname and iname not in dropped and cols in old and not iname.endswith("_pkey"):
                op.drop_index(iname, table_name=table)
        for name, _old, cols in items:
            op.create_unique_constraint(name, table, list(cols))


def upgrade() -> None:
    tid = _tenant_id()
    for table in TABLES:
        op.add_column(table, sa.Column("tenant_id", sa.Uuid(), nullable=True))
    for table in TABLES:
        op.execute(sa.text(f'UPDATE "{table}" SET tenant_id = :tid WHERE tenant_id IS NULL').bindparams(tid=tid))
    for table in TABLES:
        op.alter_column(table, "tenant_id", nullable=False)
        op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])
    _replace_uniques()
    bind = op.get_bind()
    if "tenants" in sa.inspect(bind).get_table_names():
        for table in TABLES:
            op.create_foreign_key(f"fk_{table}_tenant_id_tenants", table, "tenants", ["tenant_id"], ["id"])
    if bind.dialect.name == "postgresql":
        for table in TABLES:
            op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
            op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
            op.execute(sa.text(f'CREATE POLICY tenant_isolation ON "{table}" ' + POLICY))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in TABLES:
            op.execute(sa.text(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"'))
            op.execute(sa.text(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY'))
            op.execute(sa.text(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY'))
    if "tenants" in sa.inspect(bind).get_table_names():
        for table in TABLES:
            op.drop_constraint(f"fk_{table}_tenant_id_tenants", table, type_="foreignkey")
    for table, name, cols in UNIQUES:
        op.drop_constraint(name, table, type_="unique")
        op.create_unique_constraint(name, table, [col for col in cols if col != "tenant_id"])
    for table in TABLES:
        op.drop_index(f"ix_{table}_tenant_id", table_name=table)
        op.drop_column(table, "tenant_id")
