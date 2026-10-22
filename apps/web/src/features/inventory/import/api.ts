import type {
  BatchDetail,
  BatchPage,
  BatchQuery,
  BatchUpdate,
  ImportCommitRequest,
  ImportPreview,
  ImportPreviewRequest,
  ImportUpload,
  MappingTemplate,
  MappingTemplateWrite,
  RollbackPreview,
  RollbackResult,
  Supplier,
  SupplierCreate,
} from "@ai-pos/shared-types";
import { apiBlob, apiDelete, apiGet, apiPatch, apiPost, apiUpload } from "../../../lib/api";

const base = "/api/v1/inventory";

function query(params: object): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export const importApi = {
  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return apiUpload<ImportUpload>(`${base}/import/upload`, form);
  },
  preview: (body: ImportPreviewRequest) => apiPost<ImportPreview>(`${base}/import/preview`, body),
  commit: (body: ImportCommitRequest) => apiPost<BatchDetail>(`${base}/import/commit`, body),
  templates: (supplierId: string | null) =>
    apiGet<MappingTemplate[]>(`${base}/import/templates${query({ supplier_id: supplierId })}`),
  saveTemplate: (body: MappingTemplateWrite) => apiPost<MappingTemplate>(`${base}/import/templates`, body),
  deleteTemplate: (id: string) => apiDelete(`${base}/import/templates/${id}`),
  suppliers: () => apiGet<Supplier[]>(`${base}/suppliers`),
  createSupplier: (body: SupplierCreate) => apiPost<Supplier>(`${base}/suppliers`, body),
};

export const batchesApi = {
  list: (params: BatchQuery) => apiGet<BatchPage>(`${base}/batches${query(params)}`),
  get: (id: string) => apiGet<BatchDetail>(`${base}/batches/${id}`),
  update: (id: string, body: BatchUpdate) => apiPatch<BatchDetail>(`${base}/batches/${id}`, body),
  rollbackPreview: (id: string) => apiGet<RollbackPreview>(`${base}/batches/${id}/rollback-preview`),
  rollback: (id: string, reason: string) => apiPost<RollbackResult>(`${base}/batches/${id}/rollback`, { reason }),
  download: async (id: string, fileName: string) => {
    const blob = await apiBlob(`${base}/batches/${id}/file`);
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = fileName;
    link.click();
    URL.revokeObjectURL(url);
  },
};

/** "58.00" / "AED 1,200.50" -> cents; null for blank or junk. */
export function parseCents(value: string): number | null {
  const cleaned = value.replace(/[^\d.]/g, "");
  if (cleaned === "" || Number.isNaN(Number(cleaned))) return null;
  return Math.round(Number(cleaned) * 100);
}

export function centsInput(cents: number | null): string {
  return cents === null ? "" : (cents / 100).toFixed(2);
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
