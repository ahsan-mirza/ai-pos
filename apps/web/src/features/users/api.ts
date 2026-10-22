import type { PermissionGroup, Role, RoleCreate, RoleUpdate, Store, User, UserCreate, UserUpdate } from "@ai-pos/shared-types";
import { apiDelete, apiGet, apiPatch, apiPost } from "../../lib/api";

export const usersApi = {
  list: () => apiGet<User[]>("/api/v1/users"),
  create: (body: UserCreate) => apiPost<User>("/api/v1/users", body),
  update: (id: string, body: UserUpdate) => apiPatch<User>(`/api/v1/users/${id}`, body),
  resetPassword: (id: string, password: string) => apiPost<User>(`/api/v1/users/${id}/password`, { password }),
  resetPin: (id: string, pin: string) => apiPost<User>(`/api/v1/users/${id}/pin`, { pin }),
  remove: (id: string) => apiDelete(`/api/v1/users/${id}`),
};

export const rolesApi = {
  list: () => apiGet<Role[]>("/api/v1/roles"),
  permissions: () => apiGet<PermissionGroup[]>("/api/v1/roles/permissions"),
  create: (body: RoleCreate) => apiPost<Role>("/api/v1/roles", body),
  update: (id: string, body: RoleUpdate) => apiPatch<Role>(`/api/v1/roles/${id}`, body),
  remove: (id: string) => apiDelete(`/api/v1/roles/${id}`),
};

export const storesApi = {
  list: () => apiGet<Store[]>("/api/v1/stores?limit=200"),
};

export function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}
