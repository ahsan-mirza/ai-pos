import { env, previewHeaders } from "../../config/env";
import { currentAccessToken } from "../auth/session";
import { inTauri } from "../../lib/tauri";
import { RetailRequestError } from "../../lib/retailClient";
import {
  OFFLINE_MESSAGE,
  filenameFromDisposition,
  isWorkbookReport,
  type WorkbookReport,
} from "./workbook";

interface ShellResult {
  status: number;
  filename?: string;
  content_base64?: string;
  body?: unknown;
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

function blobFromBase64(value: string): Blob {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return new Blob([bytes], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
}

function encodeBase64(bytes: Uint8Array): string {
  let binary = "";
  const step = 0x8000;
  for (let index = 0; index < bytes.length; index += step) {
    binary += String.fromCharCode(...bytes.subarray(index, index + step));
  }
  return btoa(binary);
}

function throwRetail(caught: unknown): never {
  const raw = String(caught);
  try {
    const parsed = JSON.parse(raw) as { status?: number; code?: string; message?: string };
    throw new RetailRequestError(parsed.status ?? 0, parsed.code ?? "rejected", parsed.message ?? OFFLINE_MESSAGE);
  } catch (inner) {
    if (inner instanceof RetailRequestError) throw inner;
    throw new RetailRequestError(0, "offline", OFFLINE_MESSAGE);
  }
}

async function viaShell(
  method: "GET" | "POST",
  path: string,
  file?: File,
  fields?: Record<string, string>,
  idempotencyKey?: string,
): Promise<ShellResult> {
  const core = await import("@tauri-apps/api/core");
  const contentBase64 = file ? encodeBase64(new Uint8Array(await file.arrayBuffer())) : null;
  try {
    return await core.invoke<ShellResult>("retail_workbook", {
      method,
      path,
      filename: file?.name ?? null,
      contentBase64,
      fields: fields ?? null,
      idempotencyKey: idempotencyKey ?? null,
    });
  } catch (caught) {
    throwRetail(caught);
  }
}

function browserHeaders(extra?: Record<string, string>): Record<string, string> {
  const token = currentAccessToken();
  return {
    ...previewHeaders(),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...extra,
  };
}

export async function downloadWorkbook(path: string, fallback: string): Promise<string> {
  if (inTauri()) {
    const result = await viaShell("GET", path);
    if (!result.content_base64) throw new Error("The workbook was empty.");
    const filename = result.filename || fallback;
    saveBlob(blobFromBase64(result.content_base64), filename);
    return filename;
  }
  let response: Response;
  try {
    response = await fetch(`${env.apiBaseUrl}${path}`, { headers: browserHeaders() });
  } catch {
    throw new Error(OFFLINE_MESSAGE);
  }
  if (!response.ok) {
    const value = (await response.json().catch(() => null)) as { error?: { message?: string } } | null;
    throw new Error(value?.error?.message ?? OFFLINE_MESSAGE);
  }
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
  if (inTauri()) {
    const result = await viaShell("POST", path, file, fields, idempotencyKey);
    if (result.content_base64) {
      const filename = result.filename || "AxizPOS_Product_Menu_Errors.xlsx";
      saveBlob(blobFromBase64(result.content_base64), filename);
      return { filename };
    }
    if (isWorkbookReport(result.body)) return { report: result.body };
    throw new Error("The workbook was refused.");
  }
  const form = new FormData();
  form.append("file", file);
  for (const [key, value] of Object.entries(fields)) form.append(key, value);
  let response: Response;
  try {
    response = await fetch(`${env.apiBaseUrl}${path}`, {
      method: "POST",
      headers: browserHeaders(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined),
      body: form,
    });
  } catch {
    throw new Error(OFFLINE_MESSAGE);
  }
  const type = response.headers.get("Content-Type") ?? "";
  if (type.includes("spreadsheetml") && response.ok) {
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
  throw new Error(message || OFFLINE_MESSAGE);
}
