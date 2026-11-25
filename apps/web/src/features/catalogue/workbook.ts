export const OFFLINE_MESSAGE =
  "Import and export need a connection to the server. Nothing was changed.";

export const IMPORT_MODES = [
  { id: "create_only", label: "Create new records only" },
  { id: "update_only", label: "Update matching existing records" },
  { id: "upsert", label: "Create new and update matching records" },
] as const;

export type ImportMode = (typeof IMPORT_MODES)[number]["id"];

export const MAX_WORKBOOK_BYTES = 10 * 1024 * 1024;

export const TEMPLATE_NAME = "AxizPOS_Product_Menu_Import_Template.xlsx";

export function importModeLabel(mode: string): string {
  return IMPORT_MODES.find((item) => item.id === mode)?.label ?? mode;
}

export function workbookFileProblem(name: string, size: number): string | null {
  if (!name.toLowerCase().endsWith(".xlsx")) return "Choose an .xlsx workbook.";
  if (size <= 0) return "The workbook is empty.";
  if (size > MAX_WORKBOOK_BYTES) return "The workbook is larger than 10 MB.";
  return null;
}

export function exportPath(query: string): string {
  const trimmed = query.trim();
  if (trimmed === "") return "/api/v1/catalogue/workbook/export";
  return `/api/v1/catalogue/workbook/export?q=${encodeURIComponent(trimmed)}`;
}

export interface WorkbookIssue {
  sheet: string;
  row: number;
  field: string;
  message: string;
}

export interface WorkbookReport {
  job_id: string;
  workbook_version: string;
  mode: string;
  product_rows: number;
  menu_rows: number;
  pricing_rows: number;
  modifier_rows: number;
  created: number;
  updated: number;
  unchanged: number;
  pricing_created: number;
  pricing_updated: number;
  modifier_changes: number;
  failed: number;
  committed: boolean;
  replayed: boolean;
  errors: WorkbookIssue[];
  warnings: WorkbookIssue[];
}

export function isWorkbookReport(value: unknown): value is WorkbookReport {
  if (typeof value !== "object" || value === null) return false;
  const report = value as Partial<WorkbookReport>;
  return typeof report.job_id === "string" && typeof report.failed === "number";
}

export function filenameFromDisposition(header: string | null, fallback: string): string {
  if (header === null) return fallback;
  const match = /filename="([^"]+)"/.exec(header);
  return match?.[1] && match[1] !== "" ? match[1] : fallback;
}

export function canCommitReport(report: WorkbookReport): boolean {
  return report.failed === 0;
}
