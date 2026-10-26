import seed from "@ai-pos/catalog/seed.json";
import { EMIRATE_LABELS, Permission, type Emirate, type Store } from "@ai-pos/shared-types";
import { PhoneField, phoneError, requiredError } from "@ai-pos/ui";
import { MapPin, Phone, Warehouse } from "lucide-react";
import { useEffect, useState } from "react";
import { ErrorNote, GhostButton, PrimaryButton, SelectField, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { Toggle } from "../../components/ui/Toggle";
import { apiGet } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useCurrency } from "../../lib/currency";
import { message, storesApi } from "../inventory/api";
import { fieldErrors, type FieldErrors } from "../inventory/formErrors";

const stamped = "2026-10-19T00:00:00.000Z";
const sampleStores: Store[] = [seed.store, ...seed.branches].map((store) => ({
  ...store,
  created_at: stamped,
  updated_at: stamped,
}));

export function StoresPage() {
  const { currency } = useCurrency();
  const { can, user } = useAuth();
  const [live, setLive] = useState<Store[] | null>(null);
  const [editing, setEditing] = useState<Store | null>(null);
  const stores = live ?? sampleStores.map((store) => ({ ...store, currency }));
  const source = live === null ? "sample" : "live";
  const manage = can(Permission.PortalInventoryManage);

  const reload = () => {
    apiGet<Store[]>("/api/v1/stores?limit=200")
      .then(setLive)
      .catch(() => setLive(null));
  };
  useEffect(reload, []);

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-2xl font-semibold">Branches & warehouses</h2>
        <p className="text-sm text-charcoal/60">
          {source === "live" ? "Each branch holds its own stock." : "Showing sample locations until the API responds."}
        </p>
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {stores.map((store) => {
          const dark = store.is_warehouse === true;
          const editable = manage && source === "live" && (user?.store_id === null || user?.store_id === store.id);
          return (
            <article
              key={store.id}
              className={`rounded-card p-6 ${dark ? "bg-charcoal text-white" : "border border-line bg-white"} ${
                store.is_active === false ? "opacity-60" : ""
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <p className={`text-xs font-semibold uppercase tracking-[0.16em] ${dark ? "text-white/60" : "text-charcoal/50"}`}>
                  {store.code}
                </p>
                <span
                  className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${
                    dark ? "bg-accent text-white" : "bg-surface text-charcoal"
                  }`}
                >
                  {dark ? <Warehouse size={12} aria-hidden="true" /> : null}
                  {dark ? "Warehouse" : "Retail branch"}
                  {store.is_active === false ? " · inactive" : ""}
                </span>
              </div>
              <h3 className="mt-2 text-2xl font-semibold">{store.name}</h3>
              <p className={`mt-4 flex items-center gap-2 text-sm ${dark ? "text-white/70" : "text-charcoal/70"}`}>
                <MapPin size={14} aria-hidden="true" /> {store.address ?? "No address"}
                {store.emirate ? ` · ${EMIRATE_LABELS[store.emirate]}` : ""}
              </p>
              <p className={`mt-1 flex items-center gap-2 text-sm ${dark ? "text-white/70" : "text-charcoal/70"}`}>
                <Phone size={14} aria-hidden="true" /> {store.phone ?? "No phone"}
              </p>
              <div className="mt-6 flex items-center justify-between">
                <p className="text-sm">
                  Currency <span className="font-semibold tabular-nums">{store.currency}</span>
                </p>
                {editable ? (
                  <button
                    type="button"
                    onClick={() => setEditing(store)}
                    className={`rounded-full px-4 py-1.5 text-sm font-semibold ${dark ? "bg-white/10" : "border border-line"}`}
                  >
                    Edit
                  </button>
                ) : null}
              </div>
            </article>
          );
        })}
      </div>
      {editing ? (
        <StoreModal
          store={editing}
          canChangeType={user?.store_id === null}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            reload();
          }}
        />
      ) : null}
    </section>
  );
}

function StoreModal({
  store,
  canChangeType,
  onClose,
  onSaved,
}: {
  store: Store;
  canChangeType: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(store.name);
  const [address, setAddress] = useState(store.address ?? "");
  const [phone, setPhone] = useState(store.phone ?? "");
  const [emirate, setEmirate] = useState<Emirate | "">(store.emirate ?? "");
  const [warehouse, setWarehouse] = useState(store.is_warehouse ?? false);
  const [active, setActive] = useState(store.is_active ?? true);
  const [error, setError] = useState<string | null>(null);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [busy, setBusy] = useState(false);

  const save = async () => {
    const next: FieldErrors = {};
    const nameProblem = requiredError(name, "the branch name");
    if (nameProblem) next.name = nameProblem;
    const phoneProblem = phoneError(phone);
    if (phoneProblem) next.phone = phoneProblem;
    setErrors(next);
    if (Object.keys(next).length > 0) return;
    setBusy(true);
    setError(null);
    try {
      await storesApi.update(store.id, {
        name: name.trim(),
        address: address.trim() || null,
        phone: phone.trim() || null,
        emirate: emirate || null,
        ...(canChangeType ? { is_warehouse: warehouse, is_active: active } : {}),
      });
      onSaved();
    } catch (caught) {
      const fields = fieldErrors(caught);
      setErrors(fields);
      setError(Object.keys(fields).length > 0 ? null : message(caught, "Could not save the branch."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title={`Edit ${store.code}`}
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy} onClick={() => void save()}>
            {busy ? "Saving…" : "Save"}
          </PrimaryButton>
        </>
      }
    >
      <div className="space-y-4">
        <TextField
          label="Name"
          required
          value={name}
          error={errors.name}
          onChange={(event) => {
            setName(event.target.value);
            setErrors((current) => ({ ...current, name: "" }));
          }}
        />
        <TextField label="Address" value={address} onChange={(event) => setAddress(event.target.value)} />
        <PhoneField
          label="Phone"
          value={phone}
          error={errors.phone}
          onChange={(next) => {
            setPhone(next);
            setErrors((current) => ({ ...current, phone: "" }));
          }}
        />
        <SelectField<Emirate | "">
          label="Emirate"
          hint="Printed on tax invoices and used for the VAT return's per-emirate boxes."
          value={emirate}
          onChange={setEmirate}
          options={[
            { value: "", label: "Not set" },
            ...(Object.entries(EMIRATE_LABELS) as [Emirate, string][]).map(([value, label]) => ({ value, label })),
          ]}
        />
        {canChangeType ? (
          <>
            <Toggle
              label="Central warehouse"
              description="Distribution warehouse rather than a retail outlet"
              checked={warehouse}
              onChange={setWarehouse}
            />
            <Toggle label="Active" description="Inactive branches cannot receive or ship stock" checked={active} onChange={setActive} />
          </>
        ) : null}
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}
