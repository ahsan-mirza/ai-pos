import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useForm, Controller } from "react-hook-form";
import { View } from "react-native";
import { z } from "zod";
import { apiGet, apiPost } from "@/api/client";
import { Button } from "@/components/buttons/Button";
import { CurrencyInput, PhoneInput, SelectField } from "@/components/inputs/Fields";
import { Input } from "@/components/inputs/Input";
import { AppHeader, FormFooter, ScreenContainer } from "@/components/layout/Screen";
import { useToast } from "@/components/overlays/Overlays";
import { useI18n } from "@/i18n/I18nProvider";
import type { PortalModule } from "@/modules/catalog";
import { isRecord } from "@/modules/records";
import { useTenant } from "@/tenant/TenantProvider";

const customerSchema = z.object({
  name: z.string().trim().min(1).max(120),
  phone: z.string().trim().max(40).optional(),
  email: z.string().trim().email().optional().or(z.literal("")),
  customer_type: z.enum(["RETAIL", "WHOLESALE"]),
  address: z.string().trim().max(255).optional(),
});

const productSchema = z.object({
  name: z.string().trim().min(1).max(160),
  sku: z.string().trim().min(1).max(64),
  barcode: z.string().trim().min(1).max(64),
  price: z.string().trim().regex(/^\d+(\.\d{1,2})?$/),
  category_id: z.string().min(1),
  opening_quantity: z.string().trim().regex(/^\d+$/).or(z.literal("")),
  opening_store_id: z.string(),
});

const expenseSchema = z.object({
  store_id: z.string().min(1),
  category: z.enum(["RENT", "UTILITIES", "SALARIES", "TRANSPORT", "MARKETING", "MAINTENANCE", "OFFICE", "BANK_FEES", "OTHER"]),
  description: z.string().trim().min(2).max(200),
  payee: z.string().trim().max(120),
  spent_on: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  total: z.string().trim().regex(/^\d+(\.\d{1,2})?$/),
  paid_from: z.enum(["PETTY_CASH", "BANK", "CARD"]),
});

const supplierSchema = z.object({
  name: z.string().trim().min(2).max(120),
  contact_name: z.string().trim().max(120).optional(),
  phone: z.string().trim().max(40).optional(),
  email: z.string().trim().email().optional().or(z.literal("")),
});

const orderSchema = z.object({
  supplier_name: z.string().trim().min(1).max(120),
  destination_store_id: z.string().min(1),
  product_id: z.string().min(1),
  quantity: z.string().regex(/^\d+$/),
  unit_cost: z.string().regex(/^\d+(\.\d{1,2})?$/),
});

function cents(value: string): number {
  return Math.round(Number(value) * 100);
}

function today(): string {
  const date = new Date();
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

export function RecordForm(props: { module: PortalModule; onDone: () => void; onBack: () => void }) {
  const toast = useToast();
  const { t } = useI18n();
  const tenant = useTenant();
  const kind = props.module.create;
  const categories = useQuery({
    queryKey: ["categories"],
    enabled: kind === "product",
    queryFn: async () => {
      const rows = await apiGet<unknown>("/api/v1/categories");
      return Array.isArray(rows) ? rows.filter(isRecord) : [];
    },
  });
  const stores = useQuery({
    queryKey: ["stores"],
    enabled: kind === "expense" || kind === "purchase-order" || kind === "product",
    queryFn: async () => {
      const rows = await apiGet<unknown>("/api/v1/stores?limit=200");
      return Array.isArray(rows) ? rows.filter(isRecord) : [];
    },
  });
  const products = useQuery({
    queryKey: ["products", "picker"],
    enabled: kind === "purchase-order",
    queryFn: async () => {
      const rows = await apiGet<unknown>("/api/v1/products?limit=50");
      return Array.isArray(rows) ? rows.filter(isRecord) : [];
    },
  });

  const customer = useForm({ resolver: zodResolver(customerSchema), defaultValues: { name: "", phone: "", email: "", customer_type: "RETAIL" as const, address: "" } });
  const product = useForm({ resolver: zodResolver(productSchema), defaultValues: { name: "", sku: "", barcode: "", price: "", category_id: "", opening_quantity: "", opening_store_id: tenant.storeId ?? "" } });
  const expense = useForm({ resolver: zodResolver(expenseSchema), defaultValues: { store_id: tenant.storeId ?? "", category: "OFFICE" as const, description: "", payee: "", spent_on: today(), total: "", paid_from: "BANK" as const } });
  const order = useForm({ resolver: zodResolver(orderSchema), defaultValues: { supplier_name: "", destination_store_id: tenant.storeId ?? "", product_id: "", quantity: "1", unit_cost: "" } });
  const supplier = useForm({ resolver: zodResolver(supplierSchema), defaultValues: { name: "", contact_name: "", phone: "", email: "" } });

  const save = useMutation({
    mutationFn: async (body: unknown) => {
      const path =
        kind === "customer"
          ? "/api/v1/customers"
          : kind === "product"
            ? "/api/v1/products"
            : kind === "expense"
              ? "/api/v1/expenses"
              : kind === "supplier"
                ? "/api/v1/inventory/suppliers"
                : "/api/v1/inventory/purchase-orders";
      return apiPost(path, body);
    },
    onSuccess: () => {
      toast.show("Saved", "success");
      props.onDone();
    },
    onError: (error: Error) => toast.show(error.message, "danger"),
  });

  const storeOptions = (stores.data ?? []).map((store) => ({ value: String(store.id ?? ""), label: String(store.name ?? store.code ?? store.id) }));
  const categoryOptions = (categories.data ?? []).map((row) => ({ value: String(row.id ?? ""), label: String(row.name ?? row.id) }));
  const productOptions = (products.data ?? []).map((row) => ({ value: String(row.id ?? ""), label: String(row.name ?? row.sku ?? row.id) }));

  return (
    <ScreenContainer
      scroll
      footer={
        <FormFooter>
          <Button label={t("save")} accessibilityLabel={t("save")} loading={save.isPending} onPress={() => {
            if (kind === "customer") {
              void customer.handleSubmit((values) => save.mutate({ name: values.name, phone: values.phone || null, email: values.email || null, customer_type: values.customer_type, address: values.address || null, price_tier: values.customer_type === "WHOLESALE" ? "TIER_1" : "RETAIL", credit_limit_cents: 0, payment_terms: "DUE_ON_RECEIPT", is_active: true }))();
            } else if (kind === "product") {
              void product.handleSubmit((values) => {
                const opening = Number(values.opening_quantity || "0");
                const storeId = values.opening_store_id || tenant.storeId || "";
                if (opening > 0 && storeId === "") {
                  toast.show("Choose the branch that holds the opening stock.", "danger");
                  return;
                }
                save.mutate({
                  name: values.name,
                  sku: values.sku,
                  barcode: values.barcode,
                  price_cents: cents(values.price),
                  category_id: values.category_id,
                  is_serialized: false,
                  ...(opening > 0 ? { opening_quantity: opening, opening_store_id: storeId } : {}),
                });
              })();
            } else if (kind === "expense") {
              void expense.handleSubmit((values) => save.mutate({ store_id: values.store_id, category: values.category, description: values.description, payee: values.payee, spent_on: values.spent_on, total_cents: cents(values.total), paid_from: values.paid_from, has_tax_invoice: false, reference: "" }))();
            } else if (kind === "purchase-order") {
              void order.handleSubmit((values) => save.mutate({ supplier_name: values.supplier_name, destination_store_id: values.destination_store_id, lines: [{ product_id: values.product_id, quantity_ordered: Number(values.quantity), unit_cost_cents: cents(values.unit_cost) }] }))();
            } else if (kind === "supplier") {
              void supplier.handleSubmit((values) => save.mutate({ name: values.name, contact_name: values.contact_name || null, phone: values.phone || null, email: values.email || null }))();
            }
          }} />
        </FormFooter>
      }
    >
      <AppHeader title={t("create")} onBack={props.onBack} />
      {kind === "customer" ? (
        <View style={{ gap: 12 }}>
          <Controller control={customer.control} name="name" render={({ field, fieldState }) => <Input label="Name" value={field.value} onChangeText={field.onChange} error={fieldState.error?.message} required accessibilityLabel="Name" />} />
          <Controller control={customer.control} name="phone" render={({ field }) => <PhoneInput label="Phone" value={field.value ?? ""} onChangeText={field.onChange} />} />
          <Controller control={customer.control} name="email" render={({ field, fieldState }) => <Input variant="email" label="Email" value={field.value ?? ""} onChangeText={field.onChange} error={fieldState.error?.message} accessibilityLabel="Email" />} />
          <Controller control={customer.control} name="customer_type" render={({ field }) => <SelectField label="Type" value={field.value} onChange={field.onChange} options={[{ value: "RETAIL", label: "Retail" }, { value: "WHOLESALE", label: "Wholesale" }]} />} />
          <Controller control={customer.control} name="address" render={({ field }) => <Input variant="multiline" label="Address" value={field.value ?? ""} onChangeText={field.onChange} accessibilityLabel="Address" />} />
        </View>
      ) : null}
      {kind === "product" ? (
        <View style={{ gap: 12 }}>
          <Controller control={product.control} name="name" render={({ field, fieldState }) => <Input label="Name" value={field.value} onChangeText={field.onChange} error={fieldState.error?.message} required accessibilityLabel="Name" />} />
          <Controller control={product.control} name="sku" render={({ field, fieldState }) => <Input label="SKU" value={field.value} onChangeText={field.onChange} error={fieldState.error?.message} required accessibilityLabel="SKU" />} />
          <Controller control={product.control} name="barcode" render={({ field, fieldState }) => <Input label="Barcode" value={field.value} onChangeText={field.onChange} error={fieldState.error?.message} required accessibilityLabel="Barcode" />} />
          <Controller control={product.control} name="price" render={({ field, fieldState }) => <CurrencyInput label="Retail price" value={field.value} onChangeText={field.onChange} error={fieldState.error?.message} currency={tenant.currency} />} />
          <Controller control={product.control} name="category_id" render={({ field, fieldState }) => <SelectField label="Category" value={field.value} onChange={field.onChange} error={fieldState.error?.message} options={categoryOptions} />} />
          <Controller control={product.control} name="opening_quantity" render={({ field, fieldState }) => <Input variant="number" label="Opening quantity" value={field.value} onChangeText={field.onChange} error={fieldState.error?.message} helperText="Leave blank when stock is received later" accessibilityLabel="Opening quantity" />} />
          {tenant.storeId === null ? <Controller control={product.control} name="opening_store_id" render={({ field }) => <SelectField label="Opening branch" value={field.value} onChange={field.onChange} options={storeOptions} />} /> : null}
        </View>
      ) : null}
      {kind === "expense" ? (
        <View style={{ gap: 12 }}>
          <Controller control={expense.control} name="store_id" render={({ field, fieldState }) => <SelectField label="Store" value={field.value} onChange={field.onChange} error={fieldState.error?.message} options={storeOptions} />} />
          <Controller control={expense.control} name="category" render={({ field }) => <SelectField label="Category" value={field.value} onChange={field.onChange} options={["RENT", "UTILITIES", "SALARIES", "TRANSPORT", "MARKETING", "MAINTENANCE", "OFFICE", "BANK_FEES", "OTHER"].map((value) => ({ value, label: value }))} />} />
          <Controller control={expense.control} name="description" render={({ field, fieldState }) => <Input label="Description" value={field.value} onChangeText={field.onChange} error={fieldState.error?.message} required accessibilityLabel="Description" />} />
          <Controller control={expense.control} name="payee" render={({ field }) => <Input label="Payee" value={field.value} onChangeText={field.onChange} accessibilityLabel="Payee" />} />
          <Controller control={expense.control} name="spent_on" render={({ field }) => <Input label="Spent on" value={field.value} onChangeText={field.onChange} accessibilityLabel="Spent on" />} />
          <Controller control={expense.control} name="total" render={({ field, fieldState }) => <CurrencyInput label="Total paid" value={field.value} onChangeText={field.onChange} error={fieldState.error?.message} currency={tenant.currency} />} />
          <Controller control={expense.control} name="paid_from" render={({ field }) => <SelectField label="Paid from" value={field.value} onChange={field.onChange} options={[{ value: "BANK", label: "Bank" }, { value: "PETTY_CASH", label: "Petty cash" }, { value: "CARD", label: "Card" }]} />} />
        </View>
      ) : null}
      {kind === "purchase-order" ? (
        <View style={{ gap: 12 }}>
          <Controller control={order.control} name="supplier_name" render={({ field, fieldState }) => <Input label="Supplier" value={field.value} onChangeText={field.onChange} error={fieldState.error?.message} required accessibilityLabel="Supplier" />} />
          <Controller control={order.control} name="destination_store_id" render={({ field, fieldState }) => <SelectField label="Deliver to" value={field.value} onChange={field.onChange} error={fieldState.error?.message} options={storeOptions} />} />
          <Controller control={order.control} name="product_id" render={({ field, fieldState }) => <SelectField label="Product" value={field.value} onChange={field.onChange} error={fieldState.error?.message} options={productOptions} />} />
          <Controller control={order.control} name="quantity" render={({ field, fieldState }) => <Input variant="number" label="Quantity" value={field.value} onChangeText={field.onChange} error={fieldState.error?.message} accessibilityLabel="Quantity" />} />
          <Controller control={order.control} name="unit_cost" render={({ field, fieldState }) => <CurrencyInput label="Unit cost" value={field.value} onChangeText={field.onChange} error={fieldState.error?.message} currency={tenant.currency} />} />
        </View>
      ) : null}
      {kind === "supplier" ? (
        <View style={{ gap: 12 }}>
          <Controller control={supplier.control} name="name" render={({ field, fieldState }) => <Input label="Name" value={field.value} onChangeText={field.onChange} error={fieldState.error?.message} required accessibilityLabel="Name" />} />
          <Controller control={supplier.control} name="contact_name" render={({ field }) => <Input label="Contact" value={field.value ?? ""} onChangeText={field.onChange} accessibilityLabel="Contact" />} />
          <Controller control={supplier.control} name="phone" render={({ field }) => <PhoneInput label="Phone" value={field.value ?? ""} onChangeText={field.onChange} />} />
          <Controller control={supplier.control} name="email" render={({ field, fieldState }) => <Input variant="email" label="Email" value={field.value ?? ""} onChangeText={field.onChange} error={fieldState.error?.message} accessibilityLabel="Email" />} />
        </View>
      ) : null}
    </ScreenContainer>
  );
}
