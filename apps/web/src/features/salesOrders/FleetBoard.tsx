import { Permission } from "@ai-pos/shared-types";
import { DateInput, formatDate, useLocale } from "@ai-pos/ui";
import { useEffect, useState } from "react";
import { DataTable, type DataTableColumn } from "../../components/ui/DataTable";
import { ErrorNote, GhostButton, PrimaryButton } from "../../components/ui/Field";
import { useAuth } from "../../lib/auth";
import { errorMessage } from "../users/api";
import { capacityKey, formatGrams, formatVolume } from "./fleetCapacity";
import { dispatchPickerEmpty, measureProblem, overrideProblem, planProblems, scheduleProblems } from "./fleetRules";
import {
  fleetApi,
  type DeliveryZone,
  type DispatchPlan,
  type DriverProfile,
  type FleetOrderRow,
  type FleetVehicle,
} from "./fleetApi";

const fieldClass = "h-10 w-full rounded-lg border border-line bg-white px-3 text-sm text-charcoal";

export type FleetSection =
  | "unscheduled"
  | "scheduled"
  | "unassigned"
  | "plans"
  | "assigned"
  | "dispatched"
  | "delivered"
  | "exceptions"
  | "fleet";

function clock(value: string): string | null {
  if (!value) return null;
  return value.length === 5 ? `${value}:00` : value;
}

function schedulingLabel(status: string, t: (text: string) => string): string {
  if (status === "UNSCHEDULED") return t("Unscheduled");
  if (status === "SCHEDULED") return t("Scheduled");
  if (status === "CANCELLED") return t("Cancelled");
  return status;
}

function OrderCards({
  rows,
  onOpen,
}: {
  rows: FleetOrderRow[];
  onOpen: (id: string) => void;
}) {
  const { t } = useLocale();
  return (
    <div className="space-y-3 md:hidden">
      {rows.map((row) => (
        <article key={row.id} className="rounded-2xl border border-line bg-white p-3">
          <div className="flex items-start justify-between gap-3">
            <span dir="ltr" className="font-mono text-xs font-semibold">
              {row.number}
            </span>
            <span className="text-xs font-semibold">{schedulingLabel(row.scheduling_status, t)}</span>
          </div>
          <p className="mt-1 text-sm font-medium">{row.customer_name}</p>
          <p className="mt-1 text-sm text-charcoal/70">
            {t("Promised")}{" "}
            {row.promised_on ? <span dir="ltr">{formatDate(row.promised_on)}</span> : t("Not promised")}
          </p>
          <button type="button" onClick={() => onOpen(row.id)} className="mt-2 text-xs font-semibold text-accent">
            {t("Open order")}
          </button>
        </article>
      ))}
    </div>
  );
}

function OrderTable({
  rows,
  loading,
  error,
  onRetry,
  onOpen,
  empty,
}: {
  rows: FleetOrderRow[];
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  onOpen: (id: string) => void;
  empty: string;
}) {
  const { t } = useLocale();
  const columns: DataTableColumn<FleetOrderRow>[] = [
    { id: "number", header: t("Order"), cell: (row) => <span dir="ltr">{row.number}</span> },
    { id: "customer", header: t("Customer"), accessorKey: "customer_name" },
    { id: "status", header: t("Status"), cell: (row) => schedulingLabel(row.scheduling_status, t) },
    {
      id: "promised",
      header: t("Promised"),
      cell: (row) => (row.promised_on ? <span dir="ltr">{formatDate(row.promised_on)}</span> : t("Not promised")),
    },
    { id: "zone", header: t("Zone"), cell: (row) => row.zone_name ?? "—" },
    {
      id: "capacity",
      header: t("Capacity"),
      cell: (row) =>
        row.cargo_weight_incomplete || row.cargo_volume_incomplete ? t("Weight or volume is missing on an item.") : "—",
    },
  ];
  return (
    <div>
      <div className="md:hidden">
        {loading ? <p className="px-2 py-8 text-center text-sm text-charcoal/60">{t("Loading")}</p> : null}
        {!loading && error ? (
          <div className="px-2 py-8 text-center">
            <p className="text-sm text-charcoal/70">{error}</p>
            <button type="button" onClick={onRetry} className="mt-3 text-sm font-semibold text-accent">
              {t("Try again")}
            </button>
          </div>
        ) : null}
        {!loading && !error && rows.length === 0 ? (
          <p className="px-2 py-8 text-center text-sm text-charcoal/70">{empty}</p>
        ) : null}
        {!loading && !error && rows.length > 0 ? <OrderCards rows={rows} onOpen={onOpen} /> : null}
      </div>
      <div className="hidden md:block">
        <DataTable
          aria-label={t("Delivery orders")}
          columns={columns}
          data={rows}
          getRowId={(row) => row.id}
          isLoading={loading}
          error={error}
          onRetry={onRetry}
          pagination={false}
          onRowClick={(row) => onOpen(row.id)}
          emptyState={empty}
          minWidth="760px"
        />
      </div>
    </div>
  );
}

export function ScheduleForm({
  zones,
  onSave,
  busy,
}: {
  zones: DeliveryZone[];
  onSave: (body: Record<string, string | null>) => void;
  busy: boolean;
}) {
  const { t } = useLocale();
  const [promised, setPromised] = useState("");
  const [requested, setRequested] = useState("");
  const [start, setStart] = useState("09:00");
  const [end, setEnd] = useState("11:00");
  const [zoneId, setZoneId] = useState("");
  const [instructions, setInstructions] = useState("");
  const [problems, setProblems] = useState<string[]>([]);
  const zone = zones.find((item) => item.id === zoneId);
  return (
    <form
      className="grid gap-3 md:grid-cols-2"
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        const next = scheduleProblems({
          promised,
          requested,
          start,
          end,
          zoneId,
          zoneActive: zone ? zone.is_active : null,
        });
        setProblems(next);
        if (next.length > 0) return;
        onSave({
          promised_on: promised || null,
          requested_date: requested || null,
          window_start: clock(start),
          window_end: clock(end),
          delivery_zone_id: zoneId || null,
          delivery_instructions: instructions,
        });
      }}
    >
      <label className="block text-sm">
        <span className="mb-1 block text-charcoal/70">{t("Requested delivery date")}</span>
        <DateInput value={requested} onChange={(event) => setRequested(event.target.value)} />
      </label>
      <label className="block text-sm">
        <span className="mb-1 block text-charcoal/70">{t("Promised delivery date")}</span>
        <DateInput value={promised} onChange={(event) => setPromised(event.target.value)} />
      </label>
      <label className="block text-sm">
        <span className="mb-1 block text-charcoal/70">{t("Window start")}</span>
        <input className={fieldClass} type="time" value={start} onChange={(event) => setStart(event.target.value)} />
      </label>
      <label className="block text-sm">
        <span className="mb-1 block text-charcoal/70">{t("Window end")}</span>
        <input className={fieldClass} type="time" value={end} onChange={(event) => setEnd(event.target.value)} />
      </label>
      <label className="block text-sm md:col-span-2">
        <span className="mb-1 block text-charcoal/70">{t("Delivery zone")}</span>
        <select className={fieldClass} value={zoneId} onChange={(event) => setZoneId(event.target.value)}>
          <option value="">{t("No zone")}</option>
          {zones.map((item) => (
            <option key={item.id} value={item.id}>
            {item.code} · {item.name}
            {item.is_active ? "" : ` · ${t("Inactive")}`}
          </option>
          ))}
        </select>
      </label>
      <label className="block text-sm md:col-span-2">
        <span className="mb-1 block text-charcoal/70">{t("Delivery instructions")}</span>
        <input className={fieldClass} value={instructions} onChange={(event) => setInstructions(event.target.value)} />
      </label>
      <div className="md:col-span-2">
        {problems.length > 0 ? (
          <ul className="mb-3 space-y-1" role="alert">
            {problems.map((problem) => (
              <li key={problem} className="text-sm text-danger">
                {t(problem)}
              </li>
            ))}
          </ul>
        ) : null}
        <PrimaryButton type="submit" disabled={busy}>
          {t("Save schedule")}
        </PrimaryButton>
      </div>
    </form>
  );
}

export function DispatchSummary({ plan, canOverride }: { plan: DispatchPlan; canOverride: boolean }) {
  const { t } = useLocale();
  const key = capacityKey(plan.capacity);
  const message =
    key === "Vehicle capacity is unknown."
      ? t("Vehicle capacity is unknown.")
      : key === "Weight or volume is missing on an item."
        ? t("Weight or volume is missing on an item.")
        : key === "This plan is over the vehicle capacity."
          ? t("This plan is over the vehicle capacity.")
          : t("Capacity is within the vehicle.");
  return (
    <div className="rounded-card border border-line bg-white p-4 text-sm">
      <p dir="ltr" className="font-semibold text-charcoal">
        {plan.number} · {plan.vehicle_code} · {plan.driver_name}
      </p>
      <p className="mt-1 text-charcoal/70">
        {t("Delivery date")} <span dir="ltr" className="whitespace-nowrap">{formatDate(plan.service_date)}</span>
      </p>
      <p className="mt-2 text-charcoal/80">{message}</p>
      <p className="mt-1 text-charcoal/70">
        {t("Weight")} <span dir="ltr">{formatGrams(plan.capacity.cargo_weight_grams)}</span> · {t("Remaining")}{" "}
        <span dir="ltr">{formatGrams(plan.capacity.remaining_weight_grams)}</span>
      </p>
      <p className="text-charcoal/70">
        {t("Volume")} <span dir="ltr">{formatVolume(plan.capacity.cargo_volume_cm3)}</span> · {t("Remaining")}{" "}
        <span dir="ltr">{formatVolume(plan.capacity.remaining_volume_cm3)}</span>
      </p>
      {plan.capacity.blocked && !canOverride ? (
        <p className="mt-2 text-charcoal/70">{t("An authorised user can override this capacity check.")}</p>
      ) : null}
    </div>
  );
}

export function FleetBoard({
  section,
  storeId,
  onOpen,
}: {
  section: FleetSection;
  storeId: string;
  onOpen: (id: string) => void;
}) {
  const { t } = useLocale();
  const { can } = useAuth();
  const [rows, setRows] = useState<FleetOrderRow[]>([]);
  const [plans, setPlans] = useState<DispatchPlan[]>([]);
  const [zones, setZones] = useState<DeliveryZone[]>([]);
  const [vehicles, setVehicles] = useState<FleetVehicle[]>([]);
  const [drivers, setDrivers] = useState<DriverProfile[]>([]);
  const [users, setUsers] = useState<{ id: string; full_name: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [serviceDate, setServiceDate] = useState("");
  const [pickerCounts, setPickerCounts] = useState({ promised: 0, available: 0 });
  const [planErrors, setPlanErrors] = useState<string[]>([]);
  const [reasonError, setReasonError] = useState<string | null>(null);
  const [vehicleId, setVehicleId] = useState("");
  const [driverId, setDriverId] = useState("");
  const [saved, setSaved] = useState<DispatchPlan | null>(null);
  const [overrideReason, setOverrideReason] = useState("");
  const [zoneCode, setZoneCode] = useState("");
  const [zoneName, setZoneName] = useState("");
  const [vehicleCode, setVehicleCode] = useState("");
  const [registration, setRegistration] = useState("");
  const [weightAmount, setWeightAmount] = useState("");
  const [volumeAmount, setVolumeAmount] = useState("");
  const [userId, setUserId] = useState("");
  const [phone, setPhone] = useState("");
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    const run = async () => {
      try {
        if (section === "fleet") {
          const [zoneRows, vehicleRows, driverRows, people] = await Promise.all([
            fleetApi.zones(storeId || null),
            fleetApi.vehicles(storeId || null),
            fleetApi.drivers(storeId || null),
            fleetApi.users().catch(() => []),
          ]);
          if (cancelled) return;
          setZones(zoneRows);
          setVehicles(vehicleRows);
          setDrivers(driverRows);
          setUsers(people);
        } else if (section === "plans") {
          const [planRows, zoneRows, vehicleRows, driverRows, orderRows] = await Promise.all([
            fleetApi.plans({ store_id: storeId || null, service_date: serviceDate || null }),
            fleetApi.zones(storeId || null),
            fleetApi.vehicles(storeId || null),
            fleetApi.drivers(storeId || null),
            fleetApi.orders({
              view: "scheduled",
              store_id: storeId || null,
              promised_on: serviceDate || null,
            }),
          ]);
          if (cancelled) return;
          setPlans(planRows);
          setZones(zoneRows);
          setVehicles(vehicleRows);
          setDrivers(driverRows);
          const open = orderRows.filter((row) => !row.plan_id && row.scheduling_status !== "CANCELLED");
          setPickerCounts({ promised: orderRows.length, available: open.length });
          setRows(open);
        } else {
          const orderRows = await fleetApi.orders({ view: section, store_id: storeId || null });
          if (cancelled) return;
          setRows(orderRows);
          if (section === "unscheduled" || section === "scheduled") {
            setZones(await fleetApi.zones(storeId || null));
          }
        }
      } catch (caught: unknown) {
        if (!cancelled) setError(errorMessage(caught, "Could not load this list"));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [section, storeId, serviceDate, reload]);

  const fail = (caught: unknown) => setNotice(errorMessage(caught, t("Could not save this.")));

  const saveSchedule = async (orderId: string, body: Record<string, string | null>) => {
    setBusy(true);
    setNotice(null);
    try {
      await fleetApi.schedule(orderId, body);
      setReload((value) => value + 1);
    } catch (caught: unknown) {
      fail(caught);
    } finally {
      setBusy(false);
    }
  };

  const savePlan = async () => {
    const problems = planProblems({
      storeId,
      date: serviceDate,
      vehicleId,
      driverId,
      orders: selected.length,
    });
    setPlanErrors(problems);
    if (problems.length > 0) return;
    setBusy(true);
    setNotice(null);
    try {
      const plan = await fleetApi.createPlan({
        store_id: storeId,
        service_date: serviceDate,
        vehicle_id: vehicleId,
        driver_user_id: driverId,
        order_ids: selected,
      });
      setSaved(plan);
      setSelected([]);
      setReload((value) => value + 1);
    } catch (caught: unknown) {
      fail(caught);
    } finally {
      setBusy(false);
    }
  };

  const confirm = async (plan: DispatchPlan, override: boolean) => {
    setBusy(true);
    setNotice(null);
    try {
      const next = await fleetApi.confirmPlan(plan.id, override ? { override: true, reason: overrideReason } : {});
      setSaved(next);
      setReload((value) => value + 1);
    } catch (caught: unknown) {
      fail(caught);
    } finally {
      setBusy(false);
    }
  };

  const empty =
    section === "unscheduled"
      ? t("No unscheduled orders")
      : section === "exceptions"
        ? t("No delivery exceptions")
        : t("No orders in this list");

  return (
    <div className="mt-4 space-y-4">
      {notice ? <ErrorNote message={notice} /> : null}
      {section === "plans" ? (
        <div className="space-y-4 rounded-card border border-line bg-white p-4">
          <h2 className="text-lg font-semibold text-charcoal">{t("Dispatch plans")}</h2>
          <p className="text-sm text-charcoal/70">
            {t("Confirming a plan assigns the vehicle and driver. It does not invoice the order or mark it paid.")}
          </p>
          <div className="grid gap-3 md:grid-cols-3">
            <label className="block text-sm">
              <span className="mb-1 block text-charcoal/70">{t("Delivery date")}</span>
              <DateInput value={serviceDate} onChange={(event) => setServiceDate(event.target.value)} />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block text-charcoal/70">{t("Vehicle")}</span>
              <select className={fieldClass} value={vehicleId} onChange={(event) => setVehicleId(event.target.value)}>
                <option value="">{t("Select a vehicle")}</option>
                {vehicles
                  .filter((item) => item.is_active && item.availability === "AVAILABLE" && item.maintenance_status !== "IN_SHOP")
                  .map((item) => (
                  <option key={item.id} value={item.id}>
                    {`${item.code} · ${item.registration}${item.max_weight_grams == null ? ` · ${t("Weight unknown")}` : ""}`}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              <span className="mb-1 block text-charcoal/70">{t("Driver")}</span>
              <select className={fieldClass} value={driverId} onChange={(event) => setDriverId(event.target.value)}>
                <option value="">{t("Select a driver")}</option>
                {drivers
                  .filter((item) => item.is_active && item.availability === "AVAILABLE")
                  .map((item) => (
                  <option key={item.user_id} value={item.user_id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <OrderTable
            rows={rows}
            loading={loading}
            error={error}
            onRetry={() => setReload((value) => value + 1)}
            onOpen={onOpen}
            empty={
              t(
                dispatchPickerEmpty(serviceDate, pickerCounts.promised, pickerCounts.available) ||
                  "No orders in this list",
              )
            }
          />
          <div className="flex flex-wrap gap-2">
            {rows.map((row) => (
              <label key={row.id} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={selected.includes(row.id)}
                  onChange={() =>
                    setSelected((current) =>
                      current.includes(row.id) ? current.filter((id) => id !== row.id) : [...current, row.id],
                    )
                  }
                />
                {row.number}
              </label>
            ))}
          </div>
          {planErrors.length > 0 ? (
            <ul role="alert" className="space-y-1">
              {planErrors.map((problem) => (
                <li key={problem} className="text-sm text-danger">
                  {t(problem)}
                </li>
              ))}
            </ul>
          ) : null}
          <PrimaryButton type="button" onClick={() => void savePlan()} disabled={busy}>
            {t("Save dispatch plan")}
          </PrimaryButton>
          {saved ? <DispatchSummary plan={saved} canOverride={can(Permission.SalesDispatchOverride)} /> : null}
          {saved && saved.status === "DRAFT" ? (
            <div className="flex flex-wrap items-end gap-3">
              {saved.capacity.blocked && can(Permission.SalesDispatchOverride) ? (
                <label className="block text-sm">
                  <span className="mb-1 block text-charcoal/70">{t("Override reason")}</span>
                  <input
                    className={fieldClass}
                    value={overrideReason}
                    aria-invalid={reasonError !== null}
                    onChange={(event) => {
                      setOverrideReason(event.target.value);
                      setReasonError(null);
                    }}
                  />
                  {reasonError ? (
                    <span role="alert" className="mt-1 block text-danger">
                      {t(reasonError)}
                    </span>
                  ) : null}
                </label>
              ) : null}
              {saved.capacity.blocked ? null : (
                <PrimaryButton type="button" disabled={busy} onClick={() => void confirm(saved, false)}>
                  {t("Confirm dispatch")}
                </PrimaryButton>
              )}
              {saved.capacity.blocked && can(Permission.SalesDispatchOverride) ? (
                <GhostButton
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    const problem = overrideProblem(overrideReason);
                    setReasonError(problem);
                    if (problem) return;
                    void confirm(saved, true);
                  }}
                >
                  {t("Override and confirm")}
                </GhostButton>
              ) : null}
            </div>
          ) : null}
          <ul className="space-y-2">
            {plans.map((plan) => (
              <li key={plan.id}>
                <DispatchSummary plan={plan} canOverride={can(Permission.SalesDispatchOverride)} />
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {section !== "plans" && section !== "fleet" ? (
        <div className="space-y-4">
          <OrderTable
            rows={rows}
            loading={loading}
            error={error}
            onRetry={() => setReload((value) => value + 1)}
            onOpen={onOpen}
            empty={empty}
          />
          {section === "unscheduled" || section === "scheduled" ? (
            <div className="rounded-card border border-line bg-white p-4">
              <h2 className="mb-3 text-lg font-semibold text-charcoal">{t("Schedule a delivery")}</h2>
              <label className="mb-3 block text-sm">
                <span className="mb-1 block text-charcoal/70">{t("Order")}</span>
                <select
                  className={fieldClass}
                  value={selected[0] ?? ""}
                  onChange={(event) => setSelected(event.target.value ? [event.target.value] : [])}
                >
                  <option value="">{t("Select an order")}</option>
                  {rows.map((row) => (
                    <option key={row.id} value={row.id}>
                      {row.number} · {row.customer_name}
                    </option>
                  ))}
                </select>
              </label>
              <ScheduleForm
                zones={zones}
                busy={busy}
                onSave={(body) => {
                  const orderId = selected[0];
                  if (!orderId) {
                    setNotice(t("Select an order"));
                    return;
                  }
                  void saveSchedule(orderId, body);
                }}
              />
              {section === "scheduled" && selected[0] ? (
                <GhostButton
                  className="mt-3"
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    const orderId = selected[0];
                    if (!orderId) return;
                    setBusy(true);
                    void fleetApi
                      .cancelSchedule(orderId)
                      .then(() => setReload((value) => value + 1))
                      .catch(fail)
                      .finally(() => setBusy(false));
                  }}
                >
                  {t("Cancel schedule")}
                </GhostButton>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}

      {section === "fleet" ? (
        <div className="grid gap-4 lg:grid-cols-3">
          <form
            className="space-y-3 rounded-card border border-line bg-white p-4"
            onSubmit={(event) => {
              event.preventDefault();
              if (!storeId) return;
              setBusy(true);
              void fleetApi
                .createZone({ store_id: storeId, code: zoneCode, name: zoneName, is_active: true })
                .then(() => setReload((value) => value + 1))
                .catch(fail)
                .finally(() => setBusy(false));
            }}
          >
            <h2 className="text-lg font-semibold">{t("Delivery zones")}</h2>
            {loading ? <p className="text-sm text-charcoal/60">{t("Loading")}</p> : null}
            {error ? <ErrorNote message={error} /> : null}
            {zones.length === 0 && !loading ? <p className="text-sm text-charcoal/60">{t("No delivery zones yet")}</p> : null}
            <ul className="space-y-1 text-sm">
              {zones.map((item) => (
                <li key={item.id}>
                  {item.code} · {item.name}
                  {item.is_active ? "" : ` · ${t("Inactive")}`}
                </li>
              ))}
            </ul>
            <input className={fieldClass} placeholder={t("Zone code")} value={zoneCode} onChange={(event) => setZoneCode(event.target.value)} />
            <input className={fieldClass} placeholder={t("Zone name")} value={zoneName} onChange={(event) => setZoneName(event.target.value)} />
            <PrimaryButton type="submit" disabled={busy || !storeId}>
              {t("Add zone")}
            </PrimaryButton>
          </form>
          <form
            className="space-y-3 rounded-card border border-line bg-white p-4"
            onSubmit={(event) => {
              event.preventDefault();
              const weightError = measureProblem(weightAmount, "weight");
              const volumeError = measureProblem(volumeAmount, "volume");
              const problem = !storeId
                ? "Choose a branch before saving a dispatch plan."
                : !vehicleCode.trim()
                  ? "Enter a vehicle code."
                  : !registration.trim()
                    ? "Enter a registration."
                    : weightError || volumeError;
              if (problem) {
                setNotice(t(problem));
                return;
              }
              setBusy(true);
              void fleetApi
                .createVehicle({
                  store_id: storeId,
                  code: vehicleCode,
                  registration,
                  vehicle_type: "van",
                  weight_amount: weightAmount || null,
                  weight_unit: "kg",
                  volume_amount: volumeAmount || null,
                  volume_unit: "m3",
                })
                .then(() => setReload((value) => value + 1))
                .catch(fail)
                .finally(() => setBusy(false));
            }}
          >
            <h2 className="text-lg font-semibold">{t("Vehicles")}</h2>
            {vehicles.length === 0 && !loading ? <p className="text-sm text-charcoal/60">{t("No vehicles yet")}</p> : null}
            <ul className="space-y-1 text-sm">
              {vehicles.map((item) => (
                <li key={item.id}>
                  {item.code} · {item.registration} · {formatGrams(item.max_weight_grams)} · {formatVolume(item.max_volume_cm3)}
                </li>
              ))}
            </ul>
            <input className={fieldClass} placeholder={t("Vehicle code")} value={vehicleCode} onChange={(event) => setVehicleCode(event.target.value)} />
            <input className={fieldClass} placeholder={t("Registration")} value={registration} onChange={(event) => setRegistration(event.target.value)} />
            <input className={fieldClass} placeholder={t("Max weight kg")} value={weightAmount} onChange={(event) => setWeightAmount(event.target.value)} />
            <input className={fieldClass} placeholder={t("Max volume m3")} value={volumeAmount} onChange={(event) => setVolumeAmount(event.target.value)} />
            <p className="text-xs text-charcoal/60">{t("Leave weight or volume empty when it is unknown. Empty is not zero.")}</p>
            <PrimaryButton type="submit" disabled={busy}>
              {t("Add vehicle")}
            </PrimaryButton>
          </form>
          <form
            className="space-y-3 rounded-card border border-line bg-white p-4"
            onSubmit={(event) => {
              event.preventDefault();
              if (!storeId || !userId) {
                setNotice(t(!storeId ? "Choose a branch before saving a dispatch plan." : "Choose a driver."));
                return;
              }
              setBusy(true);
              void fleetApi
                .createDriver({ user_id: userId, store_id: storeId, phone, availability: "AVAILABLE", is_active: true })
                .then(() => setReload((value) => value + 1))
                .catch(fail)
                .finally(() => setBusy(false));
            }}
          >
            <h2 className="text-lg font-semibold">{t("Drivers")}</h2>
            {drivers.length === 0 && !loading ? <p className="text-sm text-charcoal/60">{t("No drivers yet")}</p> : null}
            <ul className="space-y-1 text-sm">
              {drivers.map((item) => (
                <li key={item.id}>
                  {item.name} · {item.phone || t("No phone")}
                </li>
              ))}
            </ul>
            <select className={fieldClass} value={userId} onChange={(event) => setUserId(event.target.value)}>
              <option value="">{t("Select a staff user")}</option>
              {users.map((person) => (
                <option key={person.id} value={person.id}>
                  {person.full_name}
                </option>
              ))}
            </select>
            <input className={fieldClass} placeholder={t("Phone")} value={phone} onChange={(event) => setPhone(event.target.value)} />
            <PrimaryButton type="submit" disabled={busy}>
              {t("Add driver")}
            </PrimaryButton>
          </form>
        </div>
      ) : null}
    </div>
  );
}
