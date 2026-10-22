// Purchase import wizard and FIFO batch inventory. Money values are integer cents in the business currency.

export const ImportSource = {
  Excel: "EXCEL",
  Csv: "CSV",
  PdfInvoice: "PDF_INVOICE",
  Manual: "MANUAL",
} as const;
export type ImportSource = (typeof ImportSource)[keyof typeof ImportSource];

export const BatchStatus = {
  Active: "ACTIVE",
  PartiallySold: "PARTIALLY_SOLD",
  Exhausted: "EXHAUSTED",
  Reversed: "REVERSED",
} as const;
export type BatchStatus = (typeof BatchStatus)[keyof typeof BatchStatus];

export const BATCH_STATUS_LABELS: Record<BatchStatus, string> = {
  ACTIVE: "Active",
  PARTIALLY_SOLD: "Partially sold",
  EXHAUSTED: "Exhausted",
  REVERSED: "Reversed",
};

export const IMPORT_SOURCE_LABELS: Record<ImportSource, string> = {
  EXCEL: "Excel",
  CSV: "CSV",
  PDF_INVOICE: "PDF invoice",
  MANUAL: "Manual",
};

export type ImportField =
  | "name"
  | "code"
  | "quantity"
  | "cost"
  | "price"
  | "model_number"
  | "category"
  | "sub_category"
  | "serials"
  | "expiry_date";

export interface ImportFieldSpec {
  field: ImportField;
  label: string;
  required: boolean;
  hint?: string;
}

export const IMPORT_FIELDS: readonly ImportFieldSpec[] = [
  { field: "name", label: "Product Name", required: true },
  { field: "code", label: "SKU / Barcode", required: true, hint: "Matches existing products" },
  { field: "quantity", label: "Quantity", required: true },
  { field: "cost", label: "Purchase Cost", required: true, hint: "Per unit" },
  { field: "price", label: "Selling Price", required: true, hint: "Per unit, retail" },
  { field: "model_number", label: "Model Number", required: false },
  { field: "category", label: "Category", required: false, hint: "Created if new" },
  { field: "sub_category", label: "Sub-Category", required: false },
  { field: "serials", label: "IMEI / Serials", required: false, hint: "One per unit, any separator" },
  { field: "expiry_date", label: "Expiry Date", required: false },
];

export type ImportMapping = Partial<Record<ImportField, string>>;

export interface ImportOptions {
  auto_generate_codes: boolean;
  update_master_price: boolean;
}

export interface Supplier {
  id: string;
  name: string;
  code: string;
  contact_name: string | null;
  phone: string | null;
  email: string | null;
  is_active: boolean;
  batch_count: number;
}

export interface SupplierCreate {
  name: string;
  contact_name?: string | null;
  phone?: string | null;
  email?: string | null;
}

export interface MappingTemplate {
  id: string;
  name: string;
  supplier_id: string | null;
  supplier_name: string | null;
  mapping: ImportMapping;
  options: ImportOptions;
  updated_at: string;
}

export interface MappingTemplateWrite {
  name: string;
  supplier_id: string | null;
  mapping: ImportMapping;
  options: ImportOptions;
}

export interface ImportUpload {
  upload_id: string;
  file_name: string;
  import_source: ImportSource;
  headers: string[];
  sample_rows: string[][];
  total_rows: number;
  suggested_mapping: ImportMapping;
  warnings: string[];
}

export interface ImportPreviewRequest {
  upload_id: string;
  store_id: string;
  mapping: ImportMapping;
  options: ImportOptions;
  /** Rows as edited in the preview grid; omit to map fresh from the file. */
  rows?: ImportRow[];
}

export interface ImportRow {
  row_number: number;
  include: boolean;
  name: string;
  code: string;
  quantity: number | null;
  cost_cents: number | null;
  price_cents: number | null;
  model_number: string;
  category: string;
  sub_category: string;
  serials: string[];
  expiry_date: string | null;
}

export type ImportRowStatus = "NEW" | "EXISTING" | "ERROR";

export interface ImportPreviewRow extends ImportRow {
  status: ImportRowStatus;
  product_id: string | null;
  existing_name: string | null;
  existing_cost_cents: number | null;
  existing_price_cents: number | null;
  is_serialized: boolean;
  generated_code: boolean;
  errors: string[];
  warnings: string[];
}

export interface ImportPreviewTotals {
  rows: number;
  included: number;
  new_products: number;
  existing_products: number;
  errors: number;
  units: number;
  cost_cents: number;
  retail_cents: number;
}

export interface ImportPreview {
  upload_id: string;
  currency: string;
  rows: ImportPreviewRow[];
  totals: ImportPreviewTotals;
}

export interface ImportCommitRequest extends ImportPreviewRequest {
  supplier_id: string | null;
  rows: ImportRow[];
  save_template_as: string | null;
  notes: string;
  /** Supplier-owned stock, settled as it sells (needs a supplier). */
  consignment?: boolean;
}

export interface BatchRow {
  id: string;
  batch_number: string;
  store_id: string;
  store_code: string;
  store_name: string;
  supplier_id: string | null;
  supplier_name: string | null;
  import_source: ImportSource;
  file_name: string | null;
  status: BatchStatus;
  currency: string;
  line_count: number;
  total_items_count: number;
  total_cost_amount: number;
  units_remaining: number;
  units_sold: number;
  sold_percent: number;
  revenue_cents: number;
  realized_profit_cents: number;
  created_by_name: string | null;
  created_at: string;
  is_consignment?: boolean;
}

export interface BatchLedgerTotals {
  batches: number;
  units: number;
  cost_cents: number;
  remaining_cost_cents: number;
  realized_profit_cents: number;
}

export interface BatchPage {
  rows: BatchRow[];
  total: number;
  totals: BatchLedgerTotals;
}

export interface BatchQuery {
  store_id?: string;
  status?: BatchStatus;
  supplier_id?: string;
  q?: string;
  offset?: number;
  limit?: number;
}

export interface BatchItem {
  id: string;
  position: number;
  product_id: string;
  product_name: string;
  sku: string;
  barcode: string;
  is_serialized: boolean;
  quantity_imported: number;
  quantity_remaining: number;
  quantity_sold: number;
  quantity_removed: number;
  purchase_cost_per_unit: number;
  selling_price_per_unit: number;
  master_price_cents: number;
  expiry_date: string | null;
  serial_count: number;
  serials_last4: string[];
  revenue_cents: number;
  cogs_cents: number;
  realized_profit_cents: number;
  editable_quantity: boolean;
}

export interface BatchSale {
  sale_id: string;
  sale_item_id: string;
  product_name: string;
  quantity: number;
  returned: number;
  unit_cost_cents: number;
  unit_sale_cents: number;
  profit_cents: number;
  sold_at: string;
}

export interface BatchDetail extends BatchRow {
  notes: string;
  mapping_template_used: { mapping?: ImportMapping; options?: ImportOptions; template_name?: string | null } | null;
  file_url: string | null;
  reversal_reason: string | null;
  reversed_at: string | null;
  reversed_by_name: string | null;
  cogs_cents: number;
  items: BatchItem[];
  sales: BatchSale[];
}

export interface BatchItemUpdate {
  id: string;
  purchase_cost_per_unit?: number;
  selling_price_per_unit?: number;
  quantity_imported?: number;
  expiry_date?: string;
  clear_expiry?: boolean;
}

export interface BatchUpdate {
  supplier_id?: string | null;
  clear_supplier?: boolean;
  notes?: string;
  items?: BatchItemUpdate[];
  apply_price_to_master?: boolean;
  reason?: string | null;
}

export interface RollbackConflict {
  product_name: string;
  sku: string;
  imported: number;
  sold: number;
  removed: number;
  remaining: number;
  reversible: number;
  blocked: number;
  detail: string;
}

export type RollbackMode = "DELETE" | "REVERSE";

export interface RollbackPreview {
  batch_id: string;
  batch_number: string;
  mode: RollbackMode;
  units_to_remove: number;
  units_sold: number;
  units_blocked: number;
  cost_written_back_cents: number;
  conflicts: RollbackConflict[];
  can_rollback: boolean;
}

export interface RollbackResult {
  batch_id: string;
  batch_number: string;
  mode: RollbackMode;
  units_removed: number;
  status: BatchStatus | "DELETED";
}

export const ROLLBACK_REASON_MIN_LENGTH = 3;
export const IMPORT_MAX_FILE_BYTES = 10 * 1024 * 1024;
export const IMPORT_ACCEPT = ".xlsx,.xls,.csv,.pdf";
