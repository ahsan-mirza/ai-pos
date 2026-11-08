export class ApiRequestError extends Error {
  readonly status: number;
  readonly code: string | null;
  readonly details: unknown;
  readonly fieldErrors: Record<string, string> | null;

  constructor(
    message: string,
    status: number,
    code: string | null = null,
    details: unknown = null,
    fieldErrors: Record<string, string> | null = null,
  ) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.fieldErrors = fieldErrors;
  }
}

export function parseErrorBody(status: number, body: unknown): ApiRequestError {
  if (typeof body === "object" && body !== null && "error" in body) {
    const error = (body as { error?: { message?: string; code?: string; details?: unknown; field_errors?: Record<string, string> } }).error;
    if (error?.message) {
      return new ApiRequestError(error.message, status, error.code ?? null, error.details ?? null, error.field_errors ?? null);
    }
  }
  return new ApiRequestError(`Request failed (${status}).`, status);
}

export function isOfflineError(error: unknown): boolean {
  return error instanceof ApiRequestError && (error.status === 0 || error.code === "api_unreachable");
}
