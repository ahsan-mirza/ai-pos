import { PROFILE_PRESETS, capabilitySpec, isCapability, type BusinessProfile, type MigrationPreflight, type TenantRow } from "@ai-pos/shared-types";
import { AlertTriangle, CheckCircle2, OctagonX } from "lucide-react";
import { useState } from "react";
import { Select } from "@ai-pos/ui";
import { ErrorNote, Field, GhostButton, Modal, PrimaryButton } from "../components/ui";
import { ConsoleError, api, errorText } from "../lib/api";
import { useSession } from "../lib/session";

function moduleLabel(key: string): string {
  return isCapability(key) ? capabilitySpec(key).label : key;
}

/** Business-type migration: pick the new type, run the safety checks, type the subdomain, then apply. */
export function MigrationModal({
  tenant,
  requestId,
  initialTarget,
  onClose,
  onDone,
}: {
  tenant: TenantRow;
  requestId: string | null;
  initialTarget: string | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const { operator } = useSession();
  const profiles = (Object.keys(PROFILE_PRESETS) as BusinessProfile[]).filter((id) => id !== tenant.business_profile);
  const [target, setTarget] = useState<string>(initialTarget && initialTarget !== tenant.business_profile ? initialTarget : (profiles[0] ?? ""));
  const [check, setCheck] = useState<MigrationPreflight | null>(null);
  const [slug, setSlug] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runChecks() {
    setBusy(true);
    setError(null);
    try {
      setCheck(await api.post<MigrationPreflight>(`/tenants/${tenant.id}/migrate-business-type/preflight`, { target_profile: target }));
    } catch (caught) {
      setError(errorText(caught, "Could not run the safety checks."));
    } finally {
      setBusy(false);
    }
  }

  async function apply() {
    if (!check) return;
    setBusy(true);
    setError(null);
    try {
      await api.post(`/tenants/${tenant.id}/migrate-business-type`, {
        target_profile: check.target_profile,
        preflight_token: check.preflight_token,
        confirm_slug: slug.trim(),
        reason: reason.trim(),
        change_request_id: requestId,
      });
      onDone();
    } catch (caught) {
      if (caught instanceof ConsoleError && (caught.code === "preflight_changed" || caught.code === "preflight_expired")) setCheck(null);
      setError(errorText(caught, "The migration did not run."));
      setBusy(false);
    }
  }

  const ready = check !== null && check.blockers.length === 0;
  const isAdmin = operator?.role === "ADMIN";

  return (
    <Modal
      wide
      title={`Change ${tenant.name}'s business type`}
      subtitle={`Now ${tenant.profile_label}. Data is kept; modules that no longer fit are switched off.`}
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          {check === null ? (
            <PrimaryButton disabled={busy || target === ""} onClick={() => void runChecks()}>
              {busy ? "Checking…" : "Run safety checks"}
            </PrimaryButton>
          ) : (
            <PrimaryButton disabled={busy || !ready || !isAdmin || slug.trim() !== tenant.slug || reason.trim().length < 3} onClick={() => void apply()}>
              {busy ? "Migrating…" : "Migrate store"}
            </PrimaryButton>
          )}
        </>
      }
    >
      <label className="block text-sm font-medium" htmlFor="migration-target">
        New business type
      </label>
      <Select
        id="migration-target"
        className="mt-1.5"
        aria-label="New business type"
        value={target}
        onChange={(value) => {
          setTarget(value);
          setCheck(null);
        }}
        options={profiles.map((id) => ({ value: id, label: PROFILE_PRESETS[id].label }))}
      />

      {check ? (
        <div className="mt-5 space-y-4 text-sm">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-2xl bg-emerald-50 p-4">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-emerald-700">Switched on</p>
              <p className="mt-1">{check.gained.length ? check.gained.map(moduleLabel).join(", ") : "Nothing new"}</p>
            </div>
            <div className="rounded-2xl bg-surface p-4">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-charcoal/60">Switched off</p>
              <p className="mt-1">{check.lost.length ? check.lost.map(moduleLabel).join(", ") : "Nothing"}</p>
            </div>
          </div>
          {check.blockers.length > 0 ? (
            <ul className="space-y-1.5 rounded-2xl bg-danger/10 p-4">
              {check.blockers.map((item) => (
                <li key={item.code} className="flex gap-2 text-danger">
                  <OctagonX size={16} className="mt-0.5 shrink-0" aria-hidden="true" /> {item.message}
                </li>
              ))}
              <li className="pt-1 text-xs text-charcoal/70">Ask the store to finish these, then run the checks again.</li>
            </ul>
          ) : (
            <p className="flex items-center gap-2 rounded-2xl bg-emerald-50 p-4 text-emerald-800">
              <CheckCircle2 size={16} aria-hidden="true" /> No live data blocks this change.
            </p>
          )}
          {check.warnings.length > 0 ? (
            <ul className="space-y-1.5 rounded-2xl bg-amber-50 p-4 text-amber-900">
              {check.warnings.map((item) => (
                <li key={item.code} className="flex gap-2">
                  <AlertTriangle size={16} className="mt-0.5 shrink-0" aria-hidden="true" /> {item.message}
                </li>
              ))}
            </ul>
          ) : null}
          {ready ? (
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label={`Type ${tenant.slug} to confirm`} value={slug} onChange={(event) => setSlug(event.target.value)} autoComplete="off" />
              <Field label="Reason" value={reason} maxLength={500} onChange={(event) => setReason(event.target.value)} placeholder="Ticket and the store's request" />
            </div>
          ) : null}
          {ready && !isAdmin ? <p className="text-xs text-charcoal/60">Only a console admin can apply a migration; share these results with one.</p> : null}
          <p className="text-xs text-charcoal/50">These checks expire at {check.expires_at.slice(11, 16)} UTC.</p>
        </div>
      ) : null}
      <ErrorNote message={error} />
    </Modal>
  );
}
