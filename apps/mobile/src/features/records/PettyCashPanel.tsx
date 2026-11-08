import { formatMoney, Permission } from "@ai-pos/shared-types";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { View } from "react-native";
import { apiGet, apiPost } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import { Button } from "@/components/buttons/Button";
import { InformationCard } from "@/components/cards/Cards";
import { CurrencyInput, SelectField } from "@/components/inputs/Fields";
import { Input } from "@/components/inputs/Input";
import { AppText } from "@/components/primitives/Text";
import { useToast } from "@/components/overlays/Overlays";
import { useI18n } from "@/i18n/I18nProvider";
import { isRecord } from "@/modules/records";
import { useTenant } from "@/tenant/TenantProvider";

function cents(value: string): number {
  return Math.round(Number(value) * 100);
}

export function PettyCashPanel() {
  const { locale } = useI18n();
  const tenant = useTenant();
  const auth = useAuth();
  const toast = useToast();
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [storeId, setStoreId] = useState(tenant.storeId ?? "");
  const [amount, setAmount] = useState("");
  const [source, setSource] = useState("bank");
  const [counted, setCounted] = useState("");
  const [note, setNote] = useState("");
  const stores = useQuery({
    queryKey: ["stores", "petty"],
    enabled: open && tenant.storeId === null,
    queryFn: async () => {
      const rows = await apiGet<unknown>("/api/v1/stores?limit=200");
      return Array.isArray(rows) ? rows.filter(isRecord) : [];
    },
  });
  const chosen = tenant.storeId ?? storeId;
  const box = useQuery({
    queryKey: ["petty-cash", chosen],
    enabled: open && chosen !== "" && auth.can(Permission.ExpensesManage),
    queryFn: () => apiGet<{ balance_cents: number; store_code: string }>(`/api/v1/expenses/petty-cash/${chosen}`),
  });
  const save = useMutation({
    mutationFn: async (body: { path: string; payload: unknown }) => apiPost(body.path, body.payload),
    onSuccess: async () => {
      toast.show("Saved", "success");
      setAmount("");
      setCounted("");
      setNote("");
      await client.invalidateQueries({ queryKey: ["petty-cash", chosen] });
    },
    onError: (error: Error) => toast.show(error.message, "danger"),
  });
  if (!auth.can(Permission.ExpensesManage)) return null;
  const localeTag = locale === "ar" ? "ar" : "en";
  const storeOptions = (stores.data ?? []).map((store) => ({ value: String(store.id ?? ""), label: String(store.name ?? store.code ?? store.id) }));
  return (
    <View style={{ gap: 8 }}>
      <Button variant="outline" label={open ? "Hide petty cash" : "Petty cash"} accessibilityLabel="Petty cash" onPress={() => setOpen((current) => !current)} />
      {open ? (
        <View style={{ gap: 8 }}>
          {tenant.storeId === null ? <SelectField label="Branch" value={storeId} onChange={setStoreId} options={storeOptions} /> : null}
          {box.data ? (
            <InformationCard title="Drawer" rows={[{ label: "Balance", value: formatMoney(box.data.balance_cents, tenant.currency, localeTag) }, { label: "Store", value: box.data.store_code }]} />
          ) : null}
          {box.isError ? <AppText tone="danger">{box.error.message}</AppText> : null}
          <CurrencyInput label="Top up" value={amount} onChangeText={setAmount} currency={tenant.currency} />
          <SelectField label="From" value={source} onChange={setSource} options={[{ value: "bank", label: "Bank" }, { value: "till", label: "Till" }]} />
          <Button
            label="Add cash"
            accessibilityLabel="Add cash"
            disabled={chosen === "" || !/^\d+(\.\d{1,2})?$/.test(amount.trim()) || cents(amount) < 1 || save.isPending}
            onPress={() => save.mutate({ path: "/api/v1/expenses/petty-cash/top-up", payload: { store_id: chosen, amount_cents: cents(amount), source, note: "" } })}
          />
          <CurrencyInput label="Counted cash" value={counted} onChangeText={setCounted} currency={tenant.currency} />
          <Input variant="multiline" label="Count note" value={note} onChangeText={setNote} helperText="At least 3 characters" accessibilityLabel="Count note" />
          <Button
            variant="outline"
            label="Save count"
            accessibilityLabel="Save count"
            disabled={chosen === "" || !/^\d+(\.\d{1,2})?$/.test(counted.trim()) || note.trim().length < 3 || save.isPending}
            onPress={() => save.mutate({ path: "/api/v1/expenses/petty-cash/count", payload: { store_id: chosen, counted_cents: cents(counted), note: note.trim() } })}
          />
        </View>
      ) : null}
    </View>
  );
}
