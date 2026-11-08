import { Capability, Permission } from "@ai-pos/shared-types";
import type { PortalModule } from "./catalog";

export interface AccessContext {
  can: (permission: Permission) => boolean;
  superAdmin: boolean;
  storeId: string | null;
  profile: string | null;
  capabilities: readonly string[];
  capabilitiesKnown: boolean;
  profileReady: boolean;
}

export function moduleVisible(module: PortalModule, access: AccessContext): boolean {
  if (module.superAdminOnly && !access.superAdmin) return false;
  if (module.businessWide && access.storeId !== null) return false;
  if (module.permission !== undefined && !access.can(module.permission)) return false;
  if (module.profiles !== undefined) {
    if (!access.profileReady || access.profile === null) return false;
    if (!module.profiles.includes(access.profile)) return false;
  }
  if (module.capability !== undefined && access.capabilitiesKnown && !access.capabilities.includes(module.capability)) {
    return false;
  }
  return true;
}

export function capabilityEnabled(capability: Capability | undefined, access: AccessContext): boolean {
  if (capability === undefined || !access.capabilitiesKnown) return true;
  return access.capabilities.includes(capability);
}
