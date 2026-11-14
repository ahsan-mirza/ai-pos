import type { Store } from "@ai-pos/shared-types";
import { useLocale } from "@ai-pos/ui";
import { useEffect, useState } from "react";
import { ErrorNote, PrimaryButton } from "../../components/ui/Field";
import { apiDelete, apiGet, apiPost, apiPut } from "../../lib/api";
import { storesApi } from "../users/api";

interface EcDevice {
  assignment_id: string | null;
  name: string;
  device_type: string;
  serial: string;
  order_reference: string;
  payment_status: string;
  fulfillment_status: string;
  registration_status: string;
  store_id: string | null;
  store_label: string;
  register_id: string | null;
  payment_verified: boolean;
  delivered: boolean;
  registered: boolean;
  assigned: boolean;
  connected: boolean;
  payment_ready: boolean;
  history: { action?: string; previous_register_id?: string | null }[];
}

interface RegisterRow {
  id: string;
  name: string;
  store_id: string;
  active: boolean;
}

interface Readiness {
  production_ready: boolean;
  blockers: string[];
}

/** Delivered machines the business confirms and assigns. Registration does not enable live card payments. */
export function EcDevicesPanel() {
  const { t } = useLocale();
  const [devices, setDevices] = useState<EcDevice[] | null>(null);
  const [stores, setStores] = useState<Store[]>([]);
  const [registers, setRegisters] = useState<RegisterRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [serial, setSerial] = useState("");
  const [storeId, setStoreId] = useState("");
  const [registerId, setRegisterId] = useState("");
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () => {
    void Promise.all([
      apiGet<EcDevice[]>("/api/v1/billing/ec-devices"),
      storesApi.list(),
      apiGet<RegisterRow[]>("/api/v1/billing/ec-registers"),
    ])
      .then(([rows, branches, tills]) => {
        setDevices(rows);
        setStores(branches);
        setRegisters(tills);
        setStoreId((current) => current || branches[0]?.id || "");
      })
      .catch((caught: unknown) => setError(caught instanceof Error ? caught.message : t("Could not load this list")));
  };

  useEffect(load, [t]);

  const selected = devices?.find((row) => row.assignment_id) ?? null;
  const branchRegisters = registers.filter((row) => row.active && row.store_id === storeId);

  const run = async (work: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await work();
      load();
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : t("Could not save this."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="rounded-3xl border border-line bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
      <h2 className="text-lg font-semibold text-charcoal dark:text-white">{t("My Terminals")}</h2>
      <p className="mt-1 text-sm text-charcoal/70 dark:text-white/70">
        {t("Confirm the serial recorded at delivery, then choose a branch and a register. This does not turn on live card payments.")}
      </p>
      <ErrorNote message={error} />
      {devices === null ? <p className="mt-3 text-sm text-charcoal/60">{t("Loading")}</p> : null}
      {devices && devices.length === 0 ? <p className="mt-3 text-sm text-charcoal/60">{t("No terminal orders yet.")}</p> : null}
      <div className="mt-4 grid gap-3">
        {(devices ?? []).map((device) => (
          <article key={device.assignment_id ?? device.order_reference} className="rounded-2xl border border-line p-4 dark:border-zinc-800">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h3 className="font-semibold text-charcoal dark:text-white">{device.name}</h3>
              <span className="text-sm" dir="ltr">{device.order_reference}</span>
            </div>
            <p className="mt-1 text-sm text-charcoal/70 dark:text-white/70">
              {device.device_type === "ANDROID" ? t("Android") : t("Wired")}
              {" · "}
              <span dir="ltr">{device.serial || "—"}</span>
            </p>
            <ul className="mt-2 grid gap-1 text-sm text-charcoal/70 dark:text-white/70 sm:grid-cols-2">
              <li>{t("Payment verified")}: {device.payment_verified ? t("Yes") : t("No")}</li>
              <li>{t("Delivered")}: {device.delivered ? t("Yes") : t("No")}</li>
              <li>{t("Registered")}: {device.registered ? t("Yes") : t("No")}</li>
              <li>{t("Assigned")}: {device.assigned ? t("Yes") : t("No")}</li>
              <li>{t("Connected")}: {device.connected ? t("Yes") : t("Connection status unavailable until terminal integration is configured.")}</li>
              <li>{t("Payment ready")}: {device.payment_ready ? t("Yes") : t("No")}</li>
            </ul>
            {device.assignment_id && device.delivered && !device.registered ? (
              <form
                className="mt-3 flex flex-wrap items-end gap-2"
                onSubmit={(event) => {
                  event.preventDefault();
                  const id = device.assignment_id;
                  if (!id) return;
                  void run(() => apiPost(`/api/v1/billing/ec-devices/${id}/register`, { serial, label: device.name }));
                }}
              >
                <label className="text-sm text-charcoal dark:text-white">
                  {t("Serial number")}
                  <input className="mt-1 block rounded-lg border border-line bg-white px-3 py-2 dark:border-zinc-700 dark:bg-zinc-950" dir="ltr" value={serial} onChange={(event) => setSerial(event.target.value)} />
                </label>
                <PrimaryButton disabled={busy} type="submit">{t("Register device")}</PrimaryButton>
              </form>
            ) : null}
            {device.assignment_id && device.registered ? (
              <form
                className="mt-3 flex flex-wrap items-end gap-2"
                onSubmit={(event) => {
                  event.preventDefault();
                  const id = device.assignment_id;
                  if (!id || !storeId || !registerId) return;
                  void run(() => apiPut(`/api/v1/billing/ec-devices/${id}/assignment`, { store_id: storeId, register_id: registerId }));
                }}
              >
                <label className="text-sm text-charcoal dark:text-white">
                  {t("Branch")}
                  <select className="mt-1 block rounded-lg border border-line bg-white px-2 py-2 dark:border-zinc-700 dark:bg-zinc-950" value={storeId} onChange={(event) => setStoreId(event.target.value)}>
                    {stores.map((store) => <option key={store.id} value={store.id}>{store.name}</option>)}
                  </select>
                </label>
                <label className="text-sm text-charcoal dark:text-white">
                  {t("Register")}
                  <select className="mt-1 block rounded-lg border border-line bg-white px-2 py-2 dark:border-zinc-700 dark:bg-zinc-950" value={registerId} onChange={(event) => setRegisterId(event.target.value)}>
                    <option value="">{t("Choose a register")}</option>
                    {branchRegisters.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
                  </select>
                </label>
                <PrimaryButton disabled={busy || !registerId} type="submit">{device.assigned ? t("Reassign") : t("Assign")}</PrimaryButton>
                {device.assigned ? (
                  <button
                    type="button"
                    className="rounded-full border border-line px-4 py-2 text-sm font-semibold dark:border-zinc-700"
                    disabled={busy}
                    onClick={() => {
                      const id = device.assignment_id;
                      if (id) void run(() => apiDelete(`/api/v1/billing/ec-devices/${id}/assignment`));
                    }}
                  >
                    {t("Unassign")}
                  </button>
                ) : null}
              </form>
            ) : null}
            {device.assignment_id ? (
              <button
                type="button"
                className="mt-3 text-sm font-semibold text-accent"
                onClick={() => {
                  const id = device.assignment_id;
                  if (!id) return;
                  void apiGet<Readiness>(`/api/v1/billing/ec-devices/${id}/readiness`).then(setReadiness).catch((caught: unknown) => {
                    setError(caught instanceof Error ? caught.message : t("Could not load this list"));
                  });
                }}
              >
                {t("View readiness")}
              </button>
            ) : null}
          </article>
        ))}
      </div>
      {readiness ? (
        <div className="mt-4 rounded-2xl bg-charcoal/5 p-4 text-sm dark:bg-white/5">
          <p className="font-semibold text-charcoal dark:text-white">{t("Pay by Card Readiness")}</p>
          <p className="mt-1">{readiness.production_ready ? t("Yes") : t("Production payments are not available.")}</p>
          <ul className="mt-2 list-disc ps-5">
            {readiness.blockers.map((code) => <li key={code} dir="ltr">{code}</li>)}
          </ul>
        </div>
      ) : null}
      {selected && selected.history.length > 0 ? (
        <p className="mt-3 text-sm text-charcoal/60 dark:text-white/60">{t("Assignment history is kept when a machine moves to another register.")}</p>
      ) : null}
    </section>
  );
}
