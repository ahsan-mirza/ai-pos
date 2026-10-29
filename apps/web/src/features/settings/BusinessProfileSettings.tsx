import {
  CAPABILITIES,
  PROFILE_PRESETS,
  capabilitySpec,
  isBusinessProfile,
  isCapability,
  supportMailto,
  type BusinessProfile,
  type BusinessSettings,
  type Capability,
  type ChangeKind,
  type ChangeRequest,
  formatMoney,
  type BillingCatalog,
  type BillingCheckout,
  type ProfileUpdate,
  type TenantModules,
} from "@ai-pos/shared-types";
import { AlertTriangle, LayoutGrid, LifeBuoy, Lock, Mail, Send } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Select } from "@ai-pos/ui";
import { ErrorNote, GhostButton, PrimaryButton } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { ApiRequestError, apiGet, apiPost, apiPut } from "../../lib/api";
import { setCapabilityPreview, useCapabilities } from "../../lib/capabilities";
import { useCurrency } from "../../lib/currency";
import { errorMessage } from "../users/api";
import {
  ModuleList,
  PROFILE_ICONS,
  ProfilePicker,
  plannedModules,
  presetSelection,
  sameSelection,
  toggleModule,
} from "./profileParts";

/** After onboarding the business type is shown, not picked: changing it needs a data migration by IT Support. */
function LockedProfile({ profile }: { profile: BusinessProfile }) {
  const spec = PROFILE_PRESETS[profile];
  const Icon = PROFILE_ICONS[profile];
  return (
    <div className="mt-6 flex flex-wrap items-center gap-4 rounded-3xl border border-line bg-surface p-4">
      <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-charcoal text-white">
        <Icon size={22} aria-hidden="true" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-charcoal/50">Business type</p>
        <p className="text-lg font-semibold">{spec.label}</p>
        <p className="text-xs text-charcoal/60">{spec.description}</p>
      </div>
      <span className="inline-flex items-center gap-1.5 rounded-full bg-charcoal px-3 py-1.5 text-xs font-semibold text-white">
        <Lock size={13} aria-hidden="true" /> Locked
      </span>
    </div>
  );
}

const STATUS_TONE: Record<ChangeRequest["status"], string> = {
  PENDING: "bg-amber-400/20 text-amber-200",
  RESOLVED: "bg-emerald-400/20 text-emerald-200",
  REJECTED: "bg-white/10 text-white/60",
};

function requestLabel(request: ChangeRequest): string {
  if (request.kind === "BUSINESS_TYPE") {
    return `Business type → ${isBusinessProfile(request.requested_value) ? PROFILE_PRESETS[request.requested_value].label : request.requested_value}`;
  }
  return `Module → ${isCapability(request.requested_value) ? capabilitySpec(request.requested_value).label : request.requested_value}`;
}

function SupportCard({
  tenant,
  requests,
  onRequest,
}: {
  tenant: TenantModules;
  requests: ChangeRequest[];
  onRequest: () => void;
}) {
  return (
    <div className="mt-6 rounded-3xl bg-charcoal p-5 text-white">
      <div className="flex flex-wrap items-center gap-4">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-white/10">
          <LifeBuoy size={20} aria-hidden="true" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="font-semibold">Need to switch your business type?</p>
          <p className="text-sm text-white/70">
            Because your store contains active sales and inventory data, structural changes require data migration.
          </p>
        </div>
        <button
          type="button"
          onClick={onRequest}
          className="inline-flex h-11 items-center gap-2 rounded-full border border-white/25 px-5 text-sm font-semibold hover:bg-white/10"
        >
          <Send size={15} aria-hidden="true" /> Request a change
        </button>
        <a
          href={supportMailto(tenant.support_email, tenant.tenant_name)}
          className="inline-flex h-11 items-center gap-2 rounded-full bg-accent px-5 text-sm font-semibold text-white hover:bg-accent/90"
        >
          <Mail size={16} aria-hidden="true" /> Contact IT Support
        </a>
      </div>
      {requests.length > 0 ? (
        <ul className="mt-4 space-y-1.5 border-t border-white/10 pt-3 text-sm">
          {requests.slice(0, 5).map((request) => (
            <li key={request.id} className="flex flex-wrap items-center gap-2">
              <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${STATUS_TONE[request.status]}`}>
                {request.status.toLowerCase()}
              </span>
              <span className="font-medium">{requestLabel(request)}</span>
              <span className="text-xs text-white/50 tabular-nums">{request.created_at.slice(0, 10)}</span>
              {request.resolution_notes ? <span className="text-xs text-white/60">· {request.resolution_notes}</span> : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function RequestChangeModal({
  tenant,
  onClose,
  onSent,
}: {
  tenant: TenantModules;
  onClose: () => void;
  onSent: () => void;
}) {
  const [kind, setKind] = useState<ChangeKind>("BUSINESS_TYPE");
  const profiles = (Object.keys(PROFILE_PRESETS) as BusinessProfile[]).filter((id) => id !== tenant.business_profile);
  const shown = new Set<string>([...tenant.enabled, ...tenant.available, ...tenant.planned]);
  const modules = CAPABILITIES.filter((spec) => !shown.has(spec.id));
  const [value, setValue] = useState<string>(profiles[0] ?? "");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pick = (next: ChangeKind) => {
    setKind(next);
    setValue(next === "BUSINESS_TYPE" ? (profiles[0] ?? "") : (modules[0]?.id ?? ""));
  };

  async function send() {
    setBusy(true);
    setError(null);
    try {
      await apiPost<ChangeRequest>("/api/v1/tenant/change-requests", { kind, requested_value: value, reason: reason.trim() });
      onSent();
    } catch (caught) {
      if (caught instanceof ApiRequestError && caught.code === "support_contact") {
        window.location.href = supportMailto(tenant.support_email, tenant.tenant_name);
        onClose();
        return;
      }
      setError(errorMessage(caught, "Could not send the request."));
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm" role="presentation">
      <div role="dialog" aria-modal="true" aria-labelledby="change-request-title" className="flex max-h-[90vh] w-full max-w-lg flex-col overflow-hidden rounded-3xl bg-white shadow-2xl">
        <header className="sticky top-0 z-20 flex-none border-b border-line bg-white px-6 py-4">
        <h2 id="change-request-title" className="text-xl font-semibold">
          Request a change from IT Support
        </h2>
        <p className="mt-1 text-sm text-charcoal/60">
          Support checks your sales, stock and open orders, then migrates your store. You are emailed when it is done.
        </p>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
        <div className="mt-4 inline-flex rounded-full bg-surface p-1" role="group" aria-label="What to change">
          {(["BUSINESS_TYPE", "MODULE"] as const).map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={kind === option}
              disabled={option === "MODULE" && modules.length === 0}
              onClick={() => pick(option)}
              className={`h-9 rounded-full px-4 text-sm font-semibold disabled:opacity-40 ${kind === option ? "bg-charcoal text-white" : "text-charcoal/70"}`}
            >
              {option === "BUSINESS_TYPE" ? "Business type" : "Another module"}
            </button>
          ))}
        </div>
        <label className="mt-4 block text-sm font-medium" htmlFor="change-request-value">
          {kind === "BUSINESS_TYPE" ? "New business type" : "Module"}
        </label>
        <Select
          id="change-request-value"
          className="mt-1.5"
          aria-label={kind === "BUSINESS_TYPE" ? "Business type" : "Module"}
          value={value}
          onChange={setValue}
          options={
            kind === "BUSINESS_TYPE"
              ? profiles.map((id) => ({ value: id, label: PROFILE_PRESETS[id].label }))
              : modules.map((spec) => ({ value: spec.id, label: spec.label }))
          }
        />
        <label className="mt-4 block text-sm font-medium" htmlFor="change-request-reason">
          Why do you need it?
        </label>
        <textarea
          id="change-request-reason"
          value={reason}
          maxLength={1000}
          rows={4}
          onChange={(event) => setReason(event.target.value)}
          placeholder="e.g. We opened a café corner and need tables and a kitchen screen."
          className="mt-1.5 w-full rounded-2xl border border-line px-3 py-2 text-sm focus:border-accent focus:outline-none"
        />
        <ErrorNote message={error} />
        </div>
        <footer className="sticky bottom-0 z-20 flex flex-none items-center justify-end gap-3 border-t border-line bg-white px-6 py-4">
          <GhostButton onClick={onClose} disabled={busy}>
            Cancel
          </GhostButton>
          <PrimaryButton disabled={busy || value === "" || reason.trim().length < 3} onClick={() => void send()}>
            {busy ? "Sending…" : "Send request"}
          </PrimaryButton>
        </footer>
      </div>
    </div>
  );
}

export async function saveProfile(update: ProfileUpdate): Promise<BusinessSettings> {
  return apiPut<BusinessSettings>("/api/v1/settings/profile", update);
}

function includedVisible(tenant: TenantModules, visible: ReadonlySet<Capability> | undefined): Set<Capability> {
  const optional = new Set<Capability>(tenant.optional ?? []);
  const shown = visible ?? new Set<Capability>(tenant.base ?? []);
  return new Set([...shown].filter((capability) => !optional.has(capability)));
}

function modulePrices(catalog: BillingCatalog, currency: string): Partial<Record<Capability, string>> {
  const prices: Partial<Record<Capability, string>> = {};
  for (const addon of catalog.addons) {
    if (!addon.active || !isCapability(addon.code)) continue;
    const parts: string[] = [];
    if (addon.monthly_fils > 0) parts.push(`${formatMoney(addon.monthly_fils, currency)} / month`);
    if (addon.one_time_fils > 0) {
      parts.push(
        addon.refundable
          ? `${formatMoney(addon.one_time_fils, currency)} refundable deposit`
          : formatMoney(addon.one_time_fils, currency),
      );
    }
    if (parts.length > 0) prices[addon.code] = parts.join(", ");
    else if (addon.module_keys.length > 0) prices[addon.code] = "Price is set in the console.";
  }
  return prices;
}

export function BusinessProfileSettings() {
  const { settings, applySettings, currency } = useCurrency();
  const location = useLocation();
  const navigate = useNavigate();
  const capabilities = useCapabilities();
  const saved = useMemo(
    () => new Set<Capability>([...capabilities.enabled, ...capabilities.planned]),
    [capabilities.enabled, capabilities.planned],
  );
  const [profile, setProfile] = useState<BusinessProfile>(capabilities.profile);
  const [selected, setSelected] = useState<Set<Capability>>(saved);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    setProfile(capabilities.profile);
    setSelected(saved);
  }, [capabilities.profile, saved]);

  useEffect(() => {
    const id = location.hash === "#add-modules" || location.hash === "#business-profile" ? location.hash.slice(1) : null;
    if (id) document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
  }, [location.hash]);

  const [tenant, setTenant] = useState<TenantModules | null>(null);
  const [requests, setRequests] = useState<ChangeRequest[]>([]);
  const [requesting, setRequesting] = useState(false);
  const [catalog, setCatalog] = useState<BillingCatalog | null>(null);
  const [prices, setPrices] = useState<Partial<Record<Capability, string>>>({});
  useEffect(() => {
    apiGet<BillingCatalog>("/api/v1/billing/catalog")
      .then((next) => {
        setCatalog(next);
        setPrices(modulePrices(next, currency));
      })
      .catch(() => {
        setCatalog(null);
        setPrices({});
      });
  }, [currency]);
  const loadTenant = useCallback(async () => {
    try {
      setTenant(await apiGet<TenantModules>("/api/v1/tenant/modules"));
      setRequests(await apiGet<ChangeRequest[]>("/api/v1/tenant/change-requests").catch(() => []));
    } catch {
      setTenant(null);
    }
  }, []);
  useEffect(() => {
    void loadTenant();
  }, [loadTenant, capabilities.enabled]);
  const locked = tenant?.locked ?? settings?.onboarded ?? false;
  const visible = useMemo(
    () =>
      locked && tenant
        ? new Set<Capability>([
            ...tenant.enabled,
            ...tenant.available,
            ...tenant.planned,
            ...saved,
            ...(Object.keys(tenant.managed) as Capability[]),
          ])
        : undefined,
    [locked, tenant, saved],
  );

  const changed = profile !== capabilities.profile || !sameSelection(selected, saved);
  const switchingOff = [...capabilities.enabled].filter((capability) => !selected.has(capability));

  useEffect(() => {
    if (!changed) {
      setCapabilityPreview(null);
      return;
    }
    setCapabilityPreview(selected);
    return () => setCapabilityPreview(null);
  }, [changed, selected]);

  const choose = (next: BusinessProfile) => {
    setProfile(next);
    setSelected(presetSelection(next));
    setNotice(null);
  };

  const buyAddon = async (code: string) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await apiPost<BillingCheckout>(`/api/v1/billing/addons/${code}/checkout`, {});
      navigate("/subscription");
    } catch (caught) {
      setError(errorMessage(caught, "Could not start the add-on invoice."));
    } finally {
      setBusy(false);
    }
  };

  const addModule = (capability: Capability, on: boolean) => {
    if (!on) {
      setSelected((current) => toggleModule(current, capability, false));
      return;
    }
    const addon = catalog?.addons.find((row) => row.active && row.code === capability && row.module_keys.length > 0);
    if (addon) {
      if (addon.monthly_fils > 0) void buyAddon(addon.code);
      else setNotice("The price for this add-on is set in the console.");
      return;
    }
    setSelected((current) => toggleModule(current, capability, true));
  };

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const preset = presetSelection(profile);
      const next = await saveProfile({
        business_profile: profile,
        capabilities: sameSelection(selected, preset) ? null : [...selected],
      });
      applySettings(next);
      void loadTenant();
      setConfirming(false);
      setNotice("Saved. The sidebar now follows these modules. Registers pick the change up on their next sync.");
    } catch (caught) {
      setError(errorMessage(caught, "Could not save the business profile."));
      if (caught instanceof ApiRequestError && (caught.status === 402 || caught.status === 409)) {
        setProfile(capabilities.profile);
        setSelected(new Set(saved));
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div id="business-profile" className="scroll-mt-20 rounded-card border border-line bg-white p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-accent text-white">
            <LayoutGrid size={20} aria-hidden="true" />
          </span>
          <div>
            <h2 className="text-2xl font-semibold">Business profile & modules</h2>
            <p className="text-sm text-charcoal/60">
              {locked
                ? "Your business type, and the modules the portal and registers show."
                : "Pick the kind of business you run, then fine-tune which modules the portal and registers show."}
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <GhostButton
            disabled={!changed || busy}
            onClick={() => {
              setProfile(capabilities.profile);
              setSelected(saved);
            }}
          >
            Reset
          </GhostButton>
          <PrimaryButton
            disabled={!changed || busy || settings === null}
            onClick={() => {
              setError(null);
              setNotice(null);
              if (switchingOff.length > 0) setConfirming(true);
              else void save();
            }}
          >
            {busy && !confirming ? "Saving…" : "Save modules"}
          </PrimaryButton>
        </div>
      </div>

      {locked ? (
        <LockedProfile profile={capabilities.profile} />
      ) : (
        <div className="mt-6">
          <ProfilePicker value={profile} onChange={choose} current={capabilities.profile} />
        </div>
      )}

      {!locked && plannedModules(profile).length > 0 ? (
        <p className="mt-4 rounded-2xl bg-amber-50 px-4 py-3 text-sm text-amber-900">
          Still on the way for {PROFILE_PRESETS[profile].label.toLowerCase()} businesses:{" "}
          {plannedModules(profile).join(", ")}. They are planned now and switch on by themselves when they ship.
        </p>
      ) : null}

      <p className="mt-4 text-xs text-charcoal/60">
        The sidebar updates as soon as you switch a module. Save modules to keep the change.
      </p>

      <h3 className="mb-3 mt-7 text-sm font-semibold">{locked ? "Included with your business type" : "Modules"}</h3>
      {locked ? (
        <p className="-mt-2 mb-3 text-xs text-charcoal/60">
          These come with a {tenant?.profile_label ?? PROFILE_PRESETS[capabilities.profile].label} store. Switch one off
          only if you do not use it. Modules that do not fit this business type are added by IT Support.
        </p>
      ) : null}
      {locked && tenant && ((tenant.base ?? []).length > 0 || (tenant.optional ?? []).length > 0) ? (
        <>
          <ModuleList
            selected={selected}
            disabled={busy}
            visible={includedVisible(tenant, visible)}
            managed={tenant.managed}
            included={new Set(tenant.base ?? [])}
            onToggle={(capability, on) => setSelected((current) => toggleModule(current, capability, on))}
          />
          <h3 id="add-modules" className="mb-3 mt-7 scroll-mt-20 text-sm font-semibold">
            Add modules
          </h3>
          <p className="-mt-2 mb-3 text-xs text-charcoal/60">
            Extra modules for this business type. Turning one on starts an invoice. It switches on after the payment
            is verified. Register hardware is billed from the subscription page.
          </p>
          {(tenant.optional ?? []).length === 0 ? (
            <p className="rounded-2xl bg-surface px-4 py-3 text-sm text-charcoal/70">
              This business type already includes every module it can use.
            </p>
          ) : (
            <ModuleList
              selected={selected}
              disabled={busy}
              visible={new Set(tenant.optional ?? [])}
              managed={tenant.managed}
              prices={prices}
              onToggle={addModule}
            />
          )}
        </>
      ) : (
        <ModuleList
          selected={selected}
          disabled={busy}
          visible={visible}
          managed={tenant?.managed}
          onToggle={(capability, on) => setSelected((current) => toggleModule(current, capability, on))}
        />
      )}

      {locked && tenant ? <SupportCard tenant={tenant} requests={requests} onRequest={() => setRequesting(true)} /> : null}
      {requesting && tenant ? (
        <RequestChangeModal
          tenant={tenant}
          onClose={() => setRequesting(false)}
          onSent={() => {
            setRequesting(false);
            setNotice("Request sent. IT Support will contact you before changing anything.");
            void loadTenant();
          }}
        />
      ) : null}

      {notice ? (
        <p role="status" className="mt-4 rounded-2xl bg-surface px-4 py-3 text-sm text-charcoal/80">
          {notice}
        </p>
      ) : null}
      <ErrorNote message={confirming ? null : error} />

      {confirming ? (
        <Modal
          title={`Switch off ${switchingOff.length} module${switchingOff.length === 1 ? "" : "s"}?`}
          subtitle={switchingOff.map((capability) => capabilitySpec(capability).label).join(", ")}
          onClose={() => (busy ? undefined : setConfirming(false))}
          footer={
            <>
              <GhostButton disabled={busy} onClick={() => setConfirming(false)}>
                Cancel
              </GhostButton>
              <PrimaryButton disabled={busy} onClick={() => void save()}>
                {busy ? "Saving…" : "Switch off"}
              </PrimaryButton>
            </>
          }
        >
          <div className="flex gap-3 rounded-2xl bg-warning/10 p-4 text-sm text-charcoal">
            <AlertTriangle size={18} className="mt-0.5 shrink-0 text-warning" aria-hidden="true" />
            <p>
              These pages and register controls are hidden for everyone. Nothing is deleted: existing records stay and
              come back when you switch the module on again, and sales registers took offline still sync.
            </p>
          </div>
          <ErrorNote message={error} />
        </Modal>
      ) : null}
    </div>
  );
}
