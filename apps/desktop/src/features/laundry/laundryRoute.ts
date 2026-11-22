/** Laundry sections live on the register hash so refresh and back/forward keep the open station. */
const PREFIX = "/laundry";

export function laundryLocation(station: string): string {
  return `#${PREFIX}/${station}`;
}

/** Station id from a location hash. Null when the hash is not a laundry route. */
export function laundryStationFromLocation(hash: string): string | null {
  const path = (hash.startsWith("#") ? hash.slice(1) : hash).split("?")[0] ?? "";
  if (path !== PREFIX && !path.startsWith(`${PREFIX}/`)) return null;
  const station = path.slice(PREFIX.length + 1);
  return station === "" ? "dashboard" : station;
}

/** The station to show. An unknown or hidden id falls back to the first allowed station. */
export function resolveLaundryStation(hash: string, allowed: readonly string[]): string {
  const requested = laundryStationFromLocation(hash);
  if (requested !== null && allowed.includes(requested)) return requested;
  return allowed[0] ?? "dashboard";
}

/** True when the hash names a laundry station this user must not open. */
export function laundryStationHidden(hash: string, allowed: readonly string[]): boolean {
  const requested = laundryStationFromLocation(hash);
  return requested !== null && !allowed.includes(requested);
}
