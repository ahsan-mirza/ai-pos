export interface Device {
  id: string;
  store_id: string;
  store_code: string;
  code: string;
  name: string;
  key_hint: string;
  invoice_prefix: string;
  last_invoice_value: number;
  last_seen_at: string | null;
  revoked_at: string | null;
  created_at: string;
  /** active, offline, pending, or revoked. */
  activation_status: "active" | "offline" | "pending" | "revoked";
  machine_name: string | null;
}

export interface RegisterCapacity {
  used: number;
  limit: number | null;
  available: number | null;
}

/** The plaintext key is returned exactly once; it goes into the register's DEVICE_KEY. */
export interface DeviceKey {
  device: Device;
  key: string;
}

/** One-time key a new register exchanges (with the store subdomain) for its device token. */
export interface DeviceActivationKey {
  device_id: string;
  activation_key: string;
  expires_at: string;
  tenant_domain: string;
}

export interface DeviceCreate {
  store_id: string;
  code: string;
  name: string;
}
