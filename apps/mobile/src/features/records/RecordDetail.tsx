import { AdjustmentReason, adjustmentReasonLabels, addressError, Capability, formatMoney, normalizeAddress, Permission, type PurchaseOrder } from "@ai-pos/shared-types";
import * as ImagePicker from "expo-image-picker";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { View } from "react-native";
import { apiGet, apiPatch, apiPost } from "@/api/client";
import { Button } from "@/components/buttons/Button";
import { InformationCard, ListCard } from "@/components/cards/Cards";
import { CurrencyInput, SelectField } from "@/components/inputs/Fields";
import { Input } from "@/components/inputs/Input";
import { AppText } from "@/components/primitives/Text";
import { AppHeader, ScreenContainer, StickyActionBar } from "@/components/layout/Screen";
import { ErrorState, LoadingSkeleton, StatusBadge } from "@/components/feedback/Feedback";
import { ConfirmationDialog } from "@/components/overlays/Overlays";
import { useToast } from "@/components/overlays/Overlays";
import { useI18n } from "@/i18n/I18nProvider";
import { isRecord, labelize, recordTitle } from "@/modules/records";
import type { PortalModule } from "@/modules/catalog";
import { useTenant } from "@/tenant/TenantProvider";
import { useAuth } from "@/auth/AuthProvider";

function detailPath(module: PortalModule, id: string): string | null {
  if (!module.path) return null;
  const base = module.path.split("?")[0] ?? module.path;
  if (/\/(summary|feed|dashboard|settings|floor|overview|pnl|access|marketplace)$/.test(base)) return null;
  return `${base}/${encodeURIComponent(id)}`;
}

function fieldsOf(row: Record<string, unknown>, currency: string, locale: string): { label: string; value: string }[] {
  return Object.entries(row)
    .filter(([, value]) => ["string", "number", "boolean"].includes(typeof value) || value === null)
    .slice(0, 24)
    .map(([key, value]) => ({
      label: labelize(key),
      value: key.endsWith("_cents") && typeof value === "number" ? formatMoney(value, currency, locale) : value === null ? "—" : String(value),
    }));
}

function newId(): string {
  const cryptoRef = globalThis.crypto;
  if (cryptoRef && "randomUUID" in cryptoRef) return cryptoRef.randomUUID();
  return `adj-${Date.now()}`;
}

export function RecordDetail(props: { module: PortalModule; id: string; seed?: Record<string, unknown> | null; embedded?: boolean; onBack: () => void }) {
  const { t, locale } = useI18n();
  const tenant = useTenant();
  const auth = useAuth();
  const toast = useToast();
  const client = useQueryClient();
  const path = detailPath(props.module, props.id);
  const detail = useQuery({
    queryKey: ["record", props.module.id, props.id],
    queryFn: () => apiGet<unknown>(path ?? ""),
    enabled: path !== null,
    initialData: props.seed,
  });
  const creditOn = !tenant.capabilitiesKnown || tenant.capabilities.includes(Capability.B2bCredit);
  const statement = useQuery({
    queryKey: ["statement", props.id],
    enabled: props.module.id === "customers" && creditOn,
    queryFn: () => apiGet<Record<string, unknown>>(`/api/v1/customers/${props.id}/statement`),
  });
  const row = isRecord(detail.data) ? detail.data : props.seed ?? null;
  const [confirm, setConfirm] = useState<null | { title: string; message: string; run: () => Promise<void>; danger?: boolean }>(null);
  const [adjust, setAdjust] = useState(false);
  const [mode, setMode] = useState<"add" | "remove" | "set">("set");
  const [quantity, setQuantity] = useState("0");
  const [reason, setReason] = useState<AdjustmentReason>(AdjustmentReason.PhysicalCountAudit);
  const [note, setNote] = useState("");
  const [adjustStore, setAdjustStore] = useState("");
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState("");
  const [editPhone, setEditPhone] = useState("");
  const [editEmail, setEditEmail] = useState("");
  const [editAddress, setEditAddress] = useState("");
  const [addressProblem, setAddressProblem] = useState<string | undefined>();
  const [editPrice, setEditPrice] = useState("");
  const [editPlu, setEditPlu] = useState("");
  const [voidReason, setVoidReason] = useState("");
  const [payAmount, setPayAmount] = useState("");
  const [payMethod, setPayMethod] = useState("cash");
  const [holdReason, setHoldReason] = useState("");
  const stores = useQuery({
    queryKey: ["stores", "adjust"],
    enabled: props.module.id === "stock" && adjust && tenant.storeId === null,
    queryFn: async () => {
      const rows = await apiGet<unknown>("/api/v1/stores?limit=200");
      return Array.isArray(rows) ? rows.filter(isRecord) : [];
    },
  });
  const mutation = useMutation({
    mutationFn: async (action: () => Promise<void>) => action(),
    onSuccess: async () => {
      toast.show("Saved", "success");
      await client.invalidateQueries({ queryKey: ["record", props.module.id, props.id] });
      await client.invalidateQueries({ queryKey: ["records", props.module.id] });
    },
    onError: (error: Error) => toast.show(error.message, "danger"),
  });

  const order = props.module.id === "purchase-orders" && isRecord(detail.data) ? (detail.data as unknown as PurchaseOrder) : null;
  const localeTag = locale === "ar" ? "ar" : "en";

  return (
    <ScreenContainer
      scroll
      embedded={props.embedded}
      footer={
        <StickyActionBar>
          {order && order.status === "draft" ? (
            <Button label="Place order" accessibilityLabel="Place order" onPress={() => setConfirm({ title: "Place order", message: order.number, run: async () => { await apiPost(`/api/v1/inventory/purchase-orders/${order.id}/order`, {}); } })} />
          ) : null}
          {order && (order.status === "ordered" || order.status === "partially_received") ? (
            <Button
              label="Receive remaining"
              accessibilityLabel="Receive remaining"
              onPress={() => {
                const lines = order.lines
                  .filter((line) => !line.is_serialized && line.quantity_ordered > line.quantity_received)
                  .map((line) => ({ purchase_order_line_id: line.id, quantity: line.quantity_ordered - line.quantity_received }));
                if (lines.length === 0) {
                  toast.show("Serialized lines stay on the portal.", "info");
                  return;
                }
                setConfirm({
                  title: "Receive goods",
                  message: "Receive every line that still has a balance.",
                  run: async () => {
                    await apiPost(`/api/v1/inventory/purchase-orders/${order.id}/receive`, {
                      note: "Received from AxizPOS Business",
                      lines,
                    });
                  },
                });
              }}
            />
          ) : null}
          {order && order.status !== "cancelled" && order.status !== "received" ? (
            <Button variant="danger" label="Cancel order" accessibilityLabel="Cancel order" onPress={() => setConfirm({ title: "Cancel order", message: order.number, danger: true, run: async () => { await apiPost(`/api/v1/inventory/purchase-orders/${order.id}/cancel`, {}); } })} />
          ) : null}
        </StickyActionBar>
      }
    >
      <AppHeader title={row ? recordTitle(row) : t("details")} onBack={props.onBack} />
      {detail.isLoading && !row ? <LoadingSkeleton /> : null}
      {detail.isError && !row ? <ErrorState message={detail.error.message} retryLabel={t("retry")} onRetry={() => void detail.refetch()} /> : null}
      {row ? (
        <View style={{ gap: 12 }}>
          {typeof row.status === "string" ? <StatusBadge label={row.status} /> : null}
          <InformationCard rows={fieldsOf(row, tenant.currency, localeTag)} />
          {order
            ? order.lines.map((line) => (
                <ListCard key={line.id} title={line.name} subtitle={line.sku} amount={formatMoney(line.unit_cost_cents, tenant.currency, localeTag)} status={`${line.quantity_received}/${line.quantity_ordered}`} />
              ))
            : null}
          {props.module.id === "stores" && auth.can(Permission.PortalInventoryManage) && (tenant.storeId === null || tenant.storeId === props.id) ? (
            <View style={{ gap: 8 }}>
              <Button
                variant="outline"
                label={editing ? "Hide address edit" : "Edit address"}
                accessibilityLabel="Edit store address"
                onPress={() => {
                  setEditAddress(typeof row.address === "string" ? row.address : "");
                  setAddressProblem(undefined);
                  setEditing((current) => !current);
                }}
              />
              {editing ? (
                <View style={{ gap: 8 }}>
                  <Input
                    label="Store address"
                    value={editAddress}
                    error={addressProblem}
                    autoCapitalize="sentences"
                    autoCorrect={false}
                    accessibilityLabel="Store address"
                    style={{ writingDirection: "auto" }}
                    onChangeText={(value) => {
                      setEditAddress(value);
                      setAddressProblem(undefined);
                    }}
                  />
                  <Button
                    label={t("save")}
                    accessibilityLabel={t("save")}
                    onPress={() => {
                      const problem = addressError(editAddress);
                      if (problem) {
                        setAddressProblem(problem);
                        return;
                      }
                      const next = normalizeAddress(editAddress);
                      setConfirm({
                        title: "Update store address",
                        message: next === "" ? "Clear the address" : next,
                        run: async () => {
                          await apiPatch(`/api/v1/stores/${props.id}`, { address: next === "" ? null : next });
                        },
                      });
                    }}
                  />
                </View>
              ) : null}
            </View>
          ) : null}
          {props.module.id === "customers" && statement.data ? (
            <InformationCard title="Statement" rows={fieldsOf(statement.data, tenant.currency, localeTag)} />
          ) : null}
          {props.module.id === "customers" && auth.can(Permission.CustomersManage) ? (
            <View style={{ gap: 8 }}>
              <Button
                variant="outline"
                label={editing ? "Hide contact edit" : "Edit contact"}
                accessibilityLabel="Edit contact"
                onPress={() => {
                  setEditName(typeof row.name === "string" ? row.name : "");
                  setEditPhone(typeof row.phone === "string" ? row.phone : "");
                  setEditEmail(typeof row.email === "string" ? row.email : "");
                  setEditAddress(typeof row.address === "string" ? row.address : "");
                  setEditing((current) => !current);
                }}
              />
              {editing ? (
                <View style={{ gap: 8 }}>
                  <Input label="Name" value={editName} onChangeText={setEditName} accessibilityLabel="Name" />
                  <Input variant="phone" label="Phone" value={editPhone} onChangeText={setEditPhone} accessibilityLabel="Phone" />
                  <Input variant="email" label="Email" value={editEmail} onChangeText={setEditEmail} accessibilityLabel="Email" />
                  <Input variant="multiline" label="Address" value={editAddress} onChangeText={setEditAddress} accessibilityLabel="Address" />
                  <Button
                    label={t("save")}
                    accessibilityLabel={t("save")}
                    disabled={editName.trim() === ""}
                    onPress={() =>
                      setConfirm({
                        title: "Update customer",
                        message: editName.trim(),
                        run: async () => {
                          await apiPatch(`/api/v1/customers/${props.id}`, {
                            name: editName.trim(),
                            phone: editPhone.trim() === "" ? null : editPhone.trim(),
                            email: editEmail.trim() === "" ? null : editEmail.trim(),
                            address: editAddress.trim() === "" ? null : editAddress.trim(),
                          });
                        },
                      })
                    }
                  />
                </View>
              ) : null}
            </View>
          ) : null}
          {props.module.id === "customers" && tenant.capabilitiesKnown && tenant.capabilities.includes(Capability.B2bCredit) && auth.can(Permission.CustomersManage) ? (
            <View style={{ gap: 8 }}>
              <CurrencyInput label="Payment" value={payAmount} onChangeText={setPayAmount} currency={tenant.currency} />
              <SelectField label="Method" value={payMethod} onChange={setPayMethod} options={[{ value: "cash", label: "Cash" }, { value: "card", label: "Card" }, { value: "transfer", label: "Transfer" }]} />
              <Button
                label="Receive payment"
                accessibilityLabel="Receive payment"
                disabled={!/^\d+(\.\d{1,2})?$/.test(payAmount.trim()) || Math.round(Number(payAmount) * 100) < 1}
                onPress={() =>
                  setConfirm({
                    title: "Receive payment",
                    message: "Cheque payments stay on the portal.",
                    run: async () => {
                      await apiPost(`/api/v1/customers/${props.id}/payments`, {
                        amount_cents: Math.round(Number(payAmount) * 100),
                        method: payMethod,
                        reference: "",
                        note: "",
                      });
                    },
                  })
                }
              />
              <Input label="Hold reason" value={holdReason} onChangeText={setHoldReason} accessibilityLabel="Hold reason" />
              <Button
                variant="outline"
                label={row.credit_hold === true ? "Release hold" : "Hold credit"}
                accessibilityLabel="Credit hold"
                onPress={() =>
                  setConfirm({
                    title: row.credit_hold === true ? "Release hold" : "Hold credit",
                    message: holdReason.trim() || recordTitle(row),
                    run: async () => {
                      await apiPost(`/api/v1/customers/${props.id}/credit-hold`, { hold: row.credit_hold !== true, reason: holdReason.trim() });
                    },
                  })
                }
              />
              <Button
                variant="outline"
                label="Send statement"
                accessibilityLabel="Send statement"
                onPress={() =>
                  setConfirm({
                    title: "Send statement",
                    message: "The server queues the statement. This does not mark it sent by itself.",
                    run: async () => {
                      const result = await apiPost<{ queued: number; skipped: number }>("/api/v1/customers/statements/send", { customer_ids: [props.id] });
                      toast.show(`Queued ${result.queued}, skipped ${result.skipped}`, "info");
                    },
                  })
                }
              />
            </View>
          ) : null}
          {props.module.id === "products" && auth.can(Permission.PortalInventoryManage) ? (
            <View style={{ gap: 8 }}>
              <Button
                variant="outline"
                label="Add photo"
                accessibilityLabel="Add photo"
                onPress={() => {
                  void ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], quality: 0.85 })
                    .then(async (result) => {
                      if (result.canceled) return;
                      const asset = result.assets[0];
                      if (!asset) return;
                      const body = new FormData();
                      body.append("file", { uri: asset.uri, name: asset.fileName ?? "product.jpg", type: asset.mimeType ?? "image/jpeg" } as unknown as Blob);
                      await apiPost(`/api/v1/inventory/products/${props.id}/images`, body);
                      toast.show("Saved", "success");
                    })
                    .catch((error: Error) => toast.show(error.message, "danger"));
                }}
              />
              <Button
                variant="outline"
                label={editing ? "Hide product edit" : "Edit product"}
                accessibilityLabel="Edit product"
                onPress={() => {
                  setEditName(typeof row.name === "string" ? row.name : "");
                  const centsValue = typeof row.price_cents === "number" ? row.price_cents : 0;
                  setEditPrice((centsValue / 100).toFixed(2));
                  setEditPlu(typeof row.plu_code === "string" ? row.plu_code : "");
                  setEditing((current) => !current);
                }}
              />
              {editing ? (
                <View style={{ gap: 8 }}>
                  <Input label="Name" value={editName} onChangeText={setEditName} accessibilityLabel="Name" />
                  <Input variant="currency" label="Retail price" value={editPrice} onChangeText={setEditPrice} accessibilityLabel="Retail price" />
                  {tenant.capabilities.includes(Capability.WeighedItems) && row.sold_by_weight === true ? (
                    <Input label="PLU" value={editPlu} onChangeText={setEditPlu} helperText="4 to 6 digits" accessibilityLabel="PLU" />
                  ) : null}
                  <Button
                    label={t("save")}
                    accessibilityLabel={t("save")}
                    disabled={editName.trim() === "" || !/^\d+(\.\d{1,2})?$/.test(editPrice.trim())}
                    onPress={() =>
                      setConfirm({
                        title: "Update product",
                        message: editName.trim(),
                        run: async () => {
                          const body: Record<string, unknown> = {
                            name: editName.trim(),
                            price_cents: Math.round(Number(editPrice) * 100),
                          };
                          if (tenant.capabilities.includes(Capability.WeighedItems) && row.sold_by_weight === true && /^\d{4,6}$/.test(editPlu.trim())) {
                            body.plu_code = editPlu.trim();
                          }
                          await apiPatch(`/api/v1/products/${props.id}`, body);
                        },
                      })
                    }
                  />
                </View>
              ) : null}
            </View>
          ) : null}
          {props.module.id === "expenses" && row.status === "RECORDED" && auth.can(Permission.ExpensesManage) ? (
            <View style={{ gap: 8 }}>
              <Input variant="multiline" label="Void reason" value={voidReason} onChangeText={setVoidReason} accessibilityLabel="Void reason" />
              <Button
                variant="danger"
                label="Void expense"
                accessibilityLabel="Void expense"
                disabled={voidReason.trim().length < 3}
                onPress={() =>
                  setConfirm({
                    title: "Void expense",
                    message: "This cannot be done offline.",
                    danger: true,
                    run: async () => {
                      await apiPost(`/api/v1/expenses/${props.id}/void`, { reason: voidReason.trim() });
                    },
                  })
                }
              />
            </View>
          ) : null}
          {props.module.id === "approvals" && row.status === "PENDING" ? (
            <View style={{ gap: 8 }}>
              <Button label="Approve" accessibilityLabel="Approve" onPress={() => setConfirm({ title: "Approve", message: recordTitle(row), run: async () => { await apiPost(`/api/v1/approvals/${props.id}/approve`, { note: "" }); } })} />
              <Button variant="danger" label="Decline" accessibilityLabel="Decline" onPress={() => setConfirm({ title: "Decline", message: recordTitle(row), danger: true, run: async () => { await apiPost(`/api/v1/approvals/${props.id}/decline`, { note: "" }); } })} />
            </View>
          ) : null}
          {props.module.id === "stock" && auth.can(Permission.InventoryAdjustStock) ? (
            <View style={{ gap: 8 }}>
              <Button
                variant="outline"
                label={adjust ? "Hide adjustment" : "Adjust stock"}
                accessibilityLabel="Adjust stock"
                onPress={() => {
                  if (typeof row.store_id === "string") setAdjustStore((current) => (current === "" ? row.store_id as string : current));
                  setAdjust((current) => !current);
                }}
              />
              {adjust ? (
                <View style={{ gap: 8 }}>
                  {tenant.storeId === null ? (
                    <SelectField
                      label="Branch"
                      value={adjustStore}
                      onChange={setAdjustStore}
                      options={(stores.data ?? []).map((store) => ({ value: String(store.id ?? ""), label: String(store.name ?? store.code ?? store.id) }))}
                    />
                  ) : null}
                  <SelectField label="Mode" value={mode} onChange={(value) => setMode(value as typeof mode)} options={[{ value: "set", label: "Set" }, { value: "add", label: "Add" }, { value: "remove", label: "Remove" }]} />
                  <Input variant="number" label="Quantity" value={quantity} onChangeText={setQuantity} accessibilityLabel="Quantity" />
                  <SelectField label="Reason" value={reason} onChange={(value) => setReason(value as AdjustmentReason)} options={Object.values(AdjustmentReason).map((value) => ({ value, label: adjustmentReasonLabels[value] }))} />
                  <Input variant="multiline" label="Note" value={note} onChangeText={setNote} maxLength={240} helperText="At least 10 characters" accessibilityLabel="Note" />
                  <Button
                    label="Submit adjustment"
                    accessibilityLabel="Submit adjustment"
                    disabled={note.trim().length < 10 || (tenant.storeId ?? adjustStore) === ""}
                    onPress={() =>
                      setConfirm({
                        title: "Adjust stock",
                        message: "This changes on-hand stock and cannot be done offline.",
                        run: async () => {
                          const productId = typeof row.product_id === "string" ? row.product_id : props.id;
                          const storeId = tenant.storeId ?? adjustStore;
                          await apiPost("/api/v1/inventory/adjust", {
                            adjustment_id: newId(),
                            product_id: productId,
                            store_id: storeId,
                            mode,
                            quantity: Number(quantity),
                            reason_code: reason,
                            note: note.trim(),
                          });
                        },
                      })
                    }
                  />
                  {tenant.storeId === null ? <AppText variant="caption" tone="secondary">Choose the branch this count belongs to.</AppText> : null}
                </View>
              ) : null}
            </View>
          ) : null}
        </View>
      ) : null}
      <ConfirmationDialog
        visible={confirm !== null}
        title={confirm?.title ?? ""}
        message={confirm?.message ?? ""}
        danger={confirm?.danger}
        loading={mutation.isPending}
        onClose={() => setConfirm(null)}
        onConfirm={() => {
          if (!confirm || mutation.isPending) return;
          mutation.mutate(confirm.run, { onSettled: () => setConfirm(null) });
        }}
      />
    </ScreenContainer>
  );
}
