import { env } from "../../config/env";
import { getAccessToken } from "../../lib/api";
import {
  OFFLINE_MESSAGE,
  filenameFromDisposition,
  isWorkbookReport,
  type WorkbookReport,
} from "./workbook";

function headers(extra?: Record<string, string>): Record<string, string> {
  const result: Record<string, string> = { "X-Client-Device": "web" };
  if (env.tenantDomain !== null) result["X-Tenant-Domain"] = env.tenantDomain;
  const token = getAccessToken();
  if (token !== null) result.Authorization = `Bearer ${token}`;
  if (extra) Object.assign(result, extra);
  return result;
}

function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function refused(response: Response): Promise<string> {
  const value = (await response.json().catch(() => null)) as { error?: { message?: string } } | null;
  return value?.error?.message ?? "The workbook was refused.";
}

export async function downloadWorkbook(path: string, fallback: string): Promise<string> {
  let response: Response;
  try {
    response = await fetch(`${env.apiBaseUrl}${path}`, { headers: headers() });
  } catch {
    throw new Error(OFFLINE_MESSAGE);
  }
  if (!response.ok) throw new Error(await refused(response));
  const filename = filenameFromDisposition(response.headers.get("Content-Disposition"), fallback);
  saveBlob(await response.blob(), filename);
  return filename;
}

export async function postWorkbook(
  path: string,
  file: File,
  fields: Record<string, string>,
  idempotencyKey?: string,
): Promise<{ report?: WorkbookReport; filename?: string }> {
  const form = new FormData();
  form.append("file", file);
  for (const [key, value] of Object.entries(fields)) form.append(key, value);
  let response: Response;
  try {
    response = await fetch(`${env.apiBaseUrl}${path}`, {
      method: "POST",
      headers: headers(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined),
      body: form,
    });
  } catch {
    throw new Error(OFFLINE_MESSAGE);
  }
  const type = response.headers.get("Content-Type") ?? "";
  if (type.includes("spreadsheetml")) {
    if (!response.ok) throw new Error(await refused(response));
    const filename = filenameFromDisposition(
      response.headers.get("Content-Disposition"),
      "AxizPOS_Product_Menu_Errors.xlsx",
    );
    saveBlob(await response.blob(), filename);
    return { filename };
  }
  const value = (await response.json().catch(() => null)) as unknown;
  if (isWorkbookReport(value) && (response.ok || response.status === 422)) return { report: value };
  const message =
    value !== null && typeof value === "object" && "error" in value
      ? (value as { error?: { message?: string } }).error?.message
      : undefined;
  throw new Error(message || "The workbook was refused.");
}
