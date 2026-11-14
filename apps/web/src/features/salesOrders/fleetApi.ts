import { apiDelete, apiGet, apiGetPage, apiPost } from "../../lib/api";

const BASE = "/api/v1/fleet";

export interface FleetCapacity {
  cargo_weight_grams: number | null;
  cargo_volume_cm3: number | null;
  cargo_weight_incomplete: boolean;
  cargo_volume_incomplete: boolean;
  vehicle_weight_grams: number | null;
  vehicle_volume_cm3: number | null;
  remaining_weight_grams: number | null;
  remaining_volume_cm3: number | null;
  weight_over: boolean;
  volume_over: boolean;
  blocked: boolean;
  policy: string;
}

export interface FleetOrderRow {
  id: string;
  number: string;
  customer_name: string;
  status: string;
  scheduling_status: string;
  requested_date: string | null;
  promised_on: string | null;
  window_start: string | null;
  window_end: string | null;
  delivery_zone_id: string | null;
  zone_name: string | null;
  delivery_address: string | null;
  store_id: string;
  plan_id: string | null;
  plan_number: string | null;
  plan_status: string | null;
  cargo_weight_incomplete: boolean;
  cargo_volume_incomplete: boolean;
}

export interface ZoneSlot {
  id: string;
  weekday: number;
  start_time: string;
  end_time: string;
  is_active: boolean;
}

export interface DeliveryZone {
  id: string;
  store_id: string;
  code: string;
  name: string;
  description: string;
  is_active: boolean;
  fee_cents: number | null;
  slots: ZoneSlot[];
}

export interface FleetVehicle {
  id: string;
  store_id: string;
  code: string;
  registration: string;
  vehicle_type: string;
  max_weight_grams: number | null;
  weight_unit: string;
  weight_amount: string | null;
  max_volume_cm3: number | null;
  volume_unit: string;
  volume_amount: string | null;
  availability: string;
  maintenance_status: string;
  is_active: boolean;
  notes: string;
}

export interface DriverProfile {
  id: string;
  user_id: string;
  name: string;
  store_id: string;
  phone: string;
  license_number: string | null;
  license_on_file: boolean;
  license_expiry: string | null;
  availability: string;
  is_active: boolean;
}

export interface DispatchPlan {
  id: string;
  number: string;
  store_id: string;
  service_date: string;
  vehicle_id: string;
  vehicle_code: string;
  driver_user_id: string;
  driver_name: string;
  status: string;
  notes: string;
  capacity_override_by_id: string | null;
  confirmed_at: string | null;
  timezone: string;
  assignments: {
    order_id: string;
    order_number: string;
    customer_name: string;
    position: number;
    cargo_weight_grams: number | null;
    cargo_volume_cm3: number | null;
    cargo_weight_incomplete: boolean;
    cargo_volume_incomplete: boolean;
  }[];
  capacity: FleetCapacity;
}

function query(params: Record<string, string | null | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) if (value) search.set(key, value);
  const text = search.toString();
  return text ? `?${text}` : "";
}

export const fleetApi = {
  orders: (filters: { view: string; store_id?: string | null; promised_on?: string | null; zone_id?: string | null }) =>
    apiGet<FleetOrderRow[]>(`${BASE}/orders${query({ ...filters, limit: "100" })}`),
  orderPage: (
    filters: { view: string; store_id?: string | null; promised_on?: string | null; zone_id?: string | null },
    page: { offset: number; limit: number },
  ) => apiGetPage<FleetOrderRow>(`${BASE}/orders${query(filters)}`, page),
  schedule: (orderId: string, body: Record<string, string | null>) =>
    apiPost<unknown>(`${BASE}/orders/${orderId}/schedule`, body),
  cancelSchedule: (orderId: string) => apiPost<unknown>(`${BASE}/orders/${orderId}/cancel-schedule`, {}),
  zones: (storeId: string | null) => apiGet<DeliveryZone[]>(`${BASE}/zones${query({ store_id: storeId })}`),
  createZone: (body: Record<string, unknown>) => apiPost<DeliveryZone>(`${BASE}/zones`, body),
  addSlot: (zoneId: string, body: Record<string, unknown>) => apiPost<DeliveryZone>(`${BASE}/zones/${zoneId}/slots`, body),
  vehicles: (storeId: string | null) => apiGet<FleetVehicle[]>(`${BASE}/vehicles${query({ store_id: storeId })}`),
  createVehicle: (body: Record<string, unknown>) => apiPost<FleetVehicle>(`${BASE}/vehicles`, body),
  drivers: (storeId: string | null) => apiGet<DriverProfile[]>(`${BASE}/drivers${query({ store_id: storeId })}`),
  createDriver: (body: Record<string, unknown>) => apiPost<DriverProfile>(`${BASE}/drivers`, body),
  plans: (filters: { store_id?: string | null; service_date?: string | null }) =>
    apiGet<DispatchPlan[]>(`${BASE}/plans${query(filters)}`),
  createPlan: (body: Record<string, unknown>) => apiPost<DispatchPlan>(`${BASE}/plans`, body),
  addOrder: (planId: string, orderId: string) => apiPost<DispatchPlan>(`${BASE}/plans/${planId}/orders`, { order_id: orderId }),
  removeOrder: (planId: string, orderId: string) => apiDelete(`${BASE}/plans/${planId}/orders/${orderId}`),
  confirmPlan: (planId: string, body: { override?: boolean; reason?: string }) =>
    apiPost<DispatchPlan>(`${BASE}/plans/${planId}/confirm`, body),
  cancelPlan: (planId: string) => apiPost<DispatchPlan>(`${BASE}/plans/${planId}/cancel`, {}),
  users: () => apiGet<{ id: string; full_name: string }[]>("/api/v1/users"),
};
