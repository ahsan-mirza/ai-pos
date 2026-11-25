import { ItemType, emptyPharmacyDraft } from "@ai-pos/shared-types";
import { describe, expect, it } from "vitest";
import { skuFromParts } from "@ai-pos/shared-types";
import {
  POS_PRODUCT_FIELDS,
  emptyProductForm,
  productCreateBody,
  productUpdateBody,
  resolvedSku,
  validateProductForm,
} from "./productPayload";

function ready() {
  const state = emptyProductForm("store-a", false);
  state.name = "Acceptance Rice 1kg";
  state.sku = "INV-RICE";
  state.barcode = "6291000002222";
  state.price = "4.50";
  state.categoryId = "cat-1";
  return state;
}

const options = { fashion: false, variantKeys: [] as string[], pharmacy: null };

describe("product form payload", () => {
  it("requires the same commercial fields as Business Pro", () => {
    const errors = validateProductForm(emptyProductForm(null, false), {
      editing: false,
      pharmacy: false,
      dispensingClass: "",
    });
    expect(errors.name).toBeTruthy();
    expect(errors.sku).toBeTruthy();
    expect(errors.barcode).toBeTruthy();
    const named = ready();
    named.barcode = "";
    named.sku = "";
    named.skuManual = false;
    const open = validateProductForm(named, { editing: false, pharmacy: false, dispensingClass: "", autoBarcode: true });
    expect(open.barcode).toBeUndefined();
    expect(resolvedSku(named, false)).toBe(skuFromParts("", named.name, named.specs));
    expect(errors.price).toBeTruthy();
    expect(errors.category).toBeTruthy();
  });

  it("lets a restaurant or cafe item omit the SKU and still requires one for grocery", () => {
    const state = ready();
    state.sku = "";
    state.skuManual = true;
    const menu = validateProductForm(state, { editing: false, pharmacy: false, dispensingClass: "", skuOptional: true });
    expect(menu.sku).toBeUndefined();
    expect(productCreateBody(state, options).sku).toBe("");
    expect(resolvedSku(state, false, true)).toBe("");
    const grocery = validateProductForm(state, { editing: false, pharmacy: false, dispensingClass: "" });
    expect(grocery.sku).toBeTruthy();
  });

  it("still requires a category or model for a pharmacy product", () => {
    const errors = validateProductForm(ready(), { editing: false, pharmacy: true, dispensingClass: "" });
    expect(errors.category).toBeUndefined();
    expect(errors.dispensing).toBeTruthy();
    const blank = ready();
    blank.categoryId = "";
    expect(validateProductForm(blank, { editing: false, pharmacy: true, dispensingClass: "OTC" }).category).toBeTruthy();
  });

  it("stores weighed opening stock in grams and keeps sellable units to the piece", () => {
    const state = ready();
    state.weighed = true;
    state.plu = "1234";
    state.opening = "1.25";
    state.packs = ["BOX"];
    const body = productCreateBody(state, options);
    expect(body.opening_quantity).toBe(1250);
    expect(body.sellable_units).toEqual(["PIECE"]);
    expect(body.plu_code).toBe("1234");
  });

  it("rejects a PLU on a product that is not weighed and rejects serialized opening stock", () => {
    const state = ready();
    state.plu = "1234";
    expect(validateProductForm(state, { editing: false, pharmacy: false, dispensingClass: "" }).plu).toBeTruthy();
    state.plu = "";
    state.serialized = true;
    state.opening = "2";
    expect(validateProductForm(state, { editing: false, pharmacy: false, dispensingClass: "" }).opening).toBeTruthy();
    expect(productCreateBody({ ...state, opening: "0" }, options).opening_quantity).toBe(0);
  });

  it("sends the pharmacy draft on the inventory product endpoint and omits sku on edit", () => {
    const draft = emptyPharmacyDraft();
    draft.dispensing_class = "OTC";
    draft.generic_name = "Paracetamol";
    const created = productCreateBody(ready(), { ...options, pharmacy: draft });
    expect(created.pharmacy).toMatchObject({ generic_name: "Paracetamol", dispensing_class: "OTC" });
    const updated = productUpdateBody(ready(), { ...options, pharmacy: draft });
    expect(updated.sku).toBeUndefined();
    expect(updated.barcode).toBeUndefined();
    expect(updated.opening_quantity).toBeUndefined();
    expect(updated.is_active).toBe(true);
  });

  it("covers the Business Pro product payload keys the drawer collects", () => {
    const body = productCreateBody(ready(), { ...options, fashion: true });
    for (const key of POS_PRODUCT_FIELDS) {
      if (key === "pharmacy" || key === "is_active") continue;
      expect(body).toHaveProperty(key);
    }
    expect(productUpdateBody(ready(), options)).toHaveProperty("is_active");
    expect(body.item_type).toBe(ItemType.PrePackaged);
  });
});
