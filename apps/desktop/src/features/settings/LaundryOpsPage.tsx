import { useEffect, useState } from "react";
import { laundryCall } from "../laundry/diagnostics";
import { visibleStations } from "../laundry/productionAccess";
import { SettingsReadOnlyNotice, SettingsSectionCard } from "./settingsUi";

interface LaundrySettings {
  operating_modes: string[];
  tracking_mode: string;
  express_daily_capacity: number | null;
}

interface Workflow {
  id: string;
  code: string;
  stages: string[];
}

export function LaundryOpsPage({
  topic,
  permissions,
}: {
  topic: "services" | "workflows" | "stations" | "machines" | "quality" | "tags" | "notifications";
  permissions: string[];
}) {
  const [settings, setSettings] = useState<LaundrySettings | null>(null);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (topic !== "services" && topic !== "workflows") return;
    let cancelled = false;
    void laundryCall<LaundrySettings>("GET", "/api/v1/laundry/settings")
      .then((next) => {
        if (!cancelled) setSettings(next);
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(caught instanceof Error ? caught.message : "Laundry settings could not be loaded.");
      });
    if (topic === "workflows") {
      void laundryCall<Workflow[]>("GET", "/api/v1/laundry/production/workflows")
        .then((rows) => {
          if (!cancelled) setWorkflows(rows);
        })
        .catch(() => {
          if (!cancelled) setWorkflows([]);
        });
    }
    return () => {
      cancelled = true;
    };
  }, [topic]);

  if (topic === "services") {
    return (
      <SettingsSectionCard>
        <h2 className="text-lg font-semibold">Service catalogue</h2>
        <p className="mt-2 text-sm text-zinc-600">Services, piece rates, kilogram rates, and tax stay in the Business Pro catalogue. Intake uses the active service list. This register does not edit prices.</p>
        {settings ? <p className="mt-3 text-sm">Tracking {settings.tracking_mode}. Express capacity {settings.express_daily_capacity ?? "not set"}.</p> : null}
        {error ? <p className="mt-3 text-sm text-red-700">{error}</p> : null}
      </SettingsSectionCard>
    );
  }
  if (topic === "workflows") {
    return (
      <div className="space-y-4">
        <SettingsSectionCard>
          <h2 className="text-lg font-semibold">Operating modes</h2>
          <p className="mt-2 text-sm text-zinc-600">Business Pro manages which modes are enabled.</p>
          {settings ? <ul className="mt-3 text-sm">{settings.operating_modes.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="mt-3 text-sm text-zinc-500">{error ?? "Loading operating modes…"}</p>}
        </SettingsSectionCard>
        <SettingsSectionCard>
          <h2 className="text-lg font-semibold">Workflow templates</h2>
          {workflows.length > 0 ? (
            <ul className="mt-3 space-y-1 text-sm">{workflows.map((item) => <li key={item.id}>{item.code}: {item.stages.join(" → ")}</li>)}</ul>
          ) : (
            <p className="mt-3 text-sm text-zinc-500">No workflow template was returned for this sign-in.</p>
          )}
        </SettingsSectionCard>
      </div>
    );
  }
  if (topic === "stations") {
    const stations = visibleStations(permissions);
    return (
      <SettingsSectionCard>
        <h2 className="text-lg font-semibold">Production stations</h2>
        <p className="mt-2 text-sm text-zinc-600">Stations follow the signed-in role. A refused station stays on the floor and does not sign the cashier out.</p>
        <p className="mt-3 text-sm">{stations.map((item) => item.label).join(", ") || "This role has no laundry stations."}</p>
      </SettingsSectionCard>
    );
  }
  if (topic === "machines") {
    return <SettingsReadOnlyNotice title="Machines" detail="Registration, capacity, and maintenance are managed in Business Pro. The Machines station starts a cycle on an available machine." />;
  }
  if (topic === "quality") {
    return <SettingsReadOnlyNotice title="Quality rules" detail="The inspector records cleaning, stain, finishing, ironing, fabric, buttons, zippers, tag, order, and instructions. Fail, rework, and manager review need a reason." />;
  }
  if (topic === "tags") {
    return <SettingsReadOnlyNotice title="Tags and labels" detail="A tag is issued when the server accepts an order. Reprint stays on the accepted order." />;
  }
  return <SettingsReadOnlyNotice title="Laundry notifications" detail="This register has no separate laundry notification channel. Sync and session messages stay on the floor." />;
}
