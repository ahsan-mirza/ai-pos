import type { ComboChoice, ModifierChoice } from "./sale-item.js";

export interface ModifierOption {
  id: string;
  name: string;
  price_delta_cents: number;
  is_default: boolean;
  is_active: boolean;
  position: number;
}

export interface ModifierGroup {
  id: string;
  name: string;
  /** min_select >= 1 makes the group required. */
  min_select: number;
  max_select: number;
  position: number;
  is_active: boolean;
  options: ModifierOption[];
  product_ids?: string[];
}

export interface ModifierGroupInput {
  name: string;
  min_select: number;
  max_select: number;
  position?: number;
  is_active?: boolean;
  options: { id?: string; name: string; price_delta_cents: number; is_default?: boolean; is_active?: boolean }[];
}

export interface ComboSlotOption {
  product_id: string;
  name: string;
  category: string;
  price_cents: number;
  surcharge_cents: number;
  is_default: boolean;
  position: number;
}

/** One choice in a meal (Main, Side, Drink); the cashier picks between min_select and max_select options. */
export interface ComboSlot {
  id: string;
  name: string;
  min_select: number;
  max_select: number;
  position: number;
  options: ComboSlotOption[];
}

/** A meal as the admin portal manages it (GET /api/v1/menu/combos). */
export interface Combo {
  product_id: string;
  sku: string;
  name: string;
  category: string;
  category_id: string | null;
  price_cents: number;
  tax_category: string;
  slots: ComboSlot[];
}

export interface ComboInput {
  name: string;
  category_id?: string | null;
  category?: string | null;
  price_cents: number;
  tax_category?: string;
  sku?: string | null;
  slots: {
    name: string;
    min_select: number;
    max_select: number;
    options: { product_id: string; surcharge_cents: number; is_default: boolean }[];
  }[];
}

/** GET /api/v1/menu/register: active groups and the groups each product offers, in order, plus meal slots. */
export interface RegisterMenu {
  groups: ModifierGroup[];
  products: Record<string, string[]>;
  combos?: Record<string, ComboSlot[]>;
}

/** The default picks of a meal, so a cashier only changes what the customer asks to swap. */
export function comboDefaults(slots: readonly ComboSlot[]): ComboChoice[] {
  return slots.flatMap((slot) => {
    const defaults = slot.options.filter((option) => option.is_default);
    const picked = defaults.length > 0 ? defaults : slot.min_select === 1 && slot.options.length === 1 ? slot.options : [];
    return picked.slice(0, slot.max_select).map((option) => comboChoiceOf(slot, option));
  });
}

export function comboChoiceOf(slot: ComboSlot, option: ComboSlotOption): ComboChoice {
  return {
    slot_id: slot.id,
    product_id: option.product_id,
    slot: slot.name,
    name: option.name,
    surcharge_cents: option.surcharge_cents,
  };
}

/** Why a meal is not complete yet, or null when it can be added. */
export function comboSelectionError(slots: readonly ComboSlot[], chosen: readonly ComboChoice[]): string | null {
  for (const slot of slots) {
    const count = chosen.filter((item) => item.slot_id === slot.id).length;
    if (count < slot.min_select) return `Choose ${slot.min_select === 1 ? "a" : slot.min_select} ${slot.name.toLowerCase()}.`;
    if (count > slot.max_select) return `${slot.name} allows at most ${slot.max_select}.`;
  }
  return null;
}

export function comboDelta(chosen: readonly ComboChoice[] | undefined): number {
  return (chosen ?? []).reduce((sum, item) => sum + item.surcharge_cents, 0);
}

/** "Classic burger, Fries, Cola" */
export function comboSummary(chosen: readonly ComboChoice[] | undefined): string {
  return (chosen ?? []).map((item) => item.name ?? "").filter(Boolean).join(", ");
}

/** Why a selection is not complete yet, or null when it can be added. */
export function modifierSelectionError(groups: ModifierGroup[], chosen: ModifierChoice[]): string | null {
  for (const group of groups) {
    const count = chosen.filter((item) => item.group_id === group.id).length;
    if (count < group.min_select) return `Choose ${group.min_select === 1 ? "a" : group.min_select} ${group.name.toLowerCase()}.`;
    if (count > group.max_select) return `${group.name} allows at most ${group.max_select}.`;
  }
  return null;
}

export function modifierDelta(chosen: readonly ModifierChoice[] | undefined): number {
  return (chosen ?? []).reduce((sum, item) => sum + item.price_delta_cents, 0);
}

export function modifierSummary(chosen: readonly ModifierChoice[] | undefined): string {
  return (chosen ?? []).map((item) => item.option ?? "").filter(Boolean).join(", ");
}
