import { CAPABILITIES, isCapability } from "@ai-pos/shared-types";

const LABELS = new Map(CAPABILITIES.map((spec) => [spec.id, spec.label]));

export function moduleLabel(id: string): string {
  if (!isCapability(id)) return id;
  return LABELS.get(id) ?? id;
}
