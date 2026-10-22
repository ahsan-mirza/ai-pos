import type { SyncEntityType, SyncOperation } from "./enums.js";

export interface SyncEvent {
  idempotency_key: string;
  entity_type: SyncEntityType;
  operation: SyncOperation;
  payload: Record<string, unknown>;
  occurred_at: string;
}

export interface SyncPushRequest {
  device_id: string;
  events: SyncEvent[];
}

export interface SyncPushResult {
  idempotency_key: string;
  status: "applied" | "duplicate";
}

export interface SyncPushResponse {
  results: SyncPushResult[];
}
