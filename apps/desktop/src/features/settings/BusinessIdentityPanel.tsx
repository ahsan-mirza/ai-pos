import { businessIdentityError, type BusinessSettings } from "@ai-pos/shared-types";
import { CountryField } from "@ai-pos/ui";
import { useEffect, useRef, useState } from "react";
import { syncBusinessCurrency } from "../checkout/currency";
import { RetailRequestError, retailCall } from "../../lib/retailClient";
import { settingsAuditSummary } from "./settingsAudit";
import { SettingsSectionCard } from "./settingsUi";

interface IdentityConflict {
  entitlement_revision?: number;
  legal_name?: string | null;
  updated_by_name?: string | null;
}

function text(value: string | null | undefined, empty = "Not set"): string {
  const trimmed = value?.trim() ?? "";
  return trimmed === "" ? empty : trimmed;
}

export function BusinessIdentityPanel({
  settings,
  canManage,
  restrictedReason,
  offline,
  onSaved,
  onReload,
}: {
  settings: BusinessSettings | null;
  canManage: boolean;
  restrictedReason: string;
  offline: boolean;
  onSaved: (settings: BusinessSettings) => void;
  onReload: () => void;
}) {
  const [legalName, setLegalName] = useState(settings?.legal_name ?? "");
  const [legalNameAr, setLegalNameAr] = useState(settings?.legal_name_ar ?? "");
  const [country, setCountry] = useState(settings?.country ?? "");
  const [location, setLocation] = useState(settings?.location ?? "");
  const [touched, setTouched] = useState(false);
  const [remote, setRemote] = useState(false);
  const touchedRef = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState<IdentityConflict | null>(null);
  const [saved, setSaved] = useState(false);
  const serverKey = [
    settings?.entitlement_revision ?? 0,
    settings?.updated_at ?? "",
    settings?.legal_name ?? "",
    settings?.legal_name_ar ?? "",
    settings?.country ?? "",
    settings?.location ?? "",
  ].join("|");

  useEffect(() => {
    if (touchedRef.current) {
      setRemote(true);
      return;
    }
    setLegalName(settings?.legal_name ?? "");
    setLegalNameAr(settings?.legal_name_ar ?? "");
    setCountry(settings?.country ?? "");
    setLocation(settings?.location ?? "");
    setRemote(false);
    setSaved(false);
  }, [serverKey, settings]);

  const revision = settings?.entitlement_revision ?? 0;
  const status = !canManage
    ? "Read only"
    : offline
      ? "Offline"
      : conflict
        ? "Conflict"
        : busy
          ? "Saving"
          : touched
            ? "Not saved"
            : settings
              ? "Synced"
              : "Waiting";

  const save = async () => {
    if (busy) return;
    setSaved(false);
    setConflict(null);
    if (!canManage) {
      setError(restrictedReason);
      return;
    }
    if (offline) {
      setError("This register is offline. The business identity was not changed.");
      return;
    }
    const validation = businessIdentityError({ legalName, legalNameAr, location });
    if (validation) {
      setError(validation);
      return;
    }
    if (revision < 1) {
      setError("Business settings have not loaded, so this change was not sent.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const next = await retailCall<BusinessSettings>("PUT", "/api/v1/settings/identity", {
        legal_name: legalName.trim(),
        legal_name_ar: legalNameAr.trim() === "" ? null : legalNameAr.trim(),
        country: country.trim() === "" ? null : country.trim(),
        location: location.trim() === "" ? null : location.trim(),
        expected_revision: revision,
      });
      touchedRef.current = false;
      setTouched(false);
      setRemote(false);
      setSaved(true);
      onSaved(next);
      void syncBusinessCurrency().catch(() => undefined);
    } catch (caught) {
      if (caught instanceof RetailRequestError && caught.code === "stale_settings") {
        setConflict((caught.details ?? null) as IdentityConflict | null);
        setError(caught.message);
      } else if (caught instanceof RetailRequestError && caught.offline) {
        setError("This register is offline. The business identity was not changed.");
      } else {
        setError(caught instanceof Error ? caught.message : "The business identity was not saved.");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <SettingsSectionCard>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Business identity</h2>
          <p className="mt-1 text-sm text-zinc-600">Tenant managed. Legal name, country, and location are one record for every branch.</p>
        </div>
        <p className="rounded-full bg-zinc-100 px-3 py-1 text-xs font-semibold text-zinc-700">{status}</p>
      </div>
      {canManage ? (
        <div className="mt-4 grid gap-3">
          <label className="block text-sm">
            <span className="font-medium">Legal name</span>
            <input
              value={legalName}
              disabled={busy || offline}
              onChange={(event) => {
                touchedRef.current = true;
                setTouched(true);
                setSaved(false);
                setLegalName(event.target.value);
              }}
              className="mt-1 w-full rounded-xl border border-zinc-200 px-3 py-2 dark:border-zinc-700 dark:bg-zinc-900"
            />
          </label>
          <label className="block text-sm">
            <span className="font-medium">Legal name in Arabic</span>
            <input
              value={legalNameAr}
              dir="auto"
              disabled={busy || offline}
              onChange={(event) => {
                touchedRef.current = true;
                setTouched(true);
                setSaved(false);
                setLegalNameAr(event.target.value);
              }}
              className="mt-1 w-full rounded-xl border border-zinc-200 px-3 py-2 dark:border-zinc-700 dark:bg-zinc-900"
            />
          </label>
          <CountryField
            label="Country"
            value={country}
            disabled={busy || offline}
            onChange={(iso) => {
              touchedRef.current = true;
              setTouched(true);
              setSaved(false);
              setCountry(iso);
            }}
          />
          <label className="block text-sm">
            <span className="font-medium">Location</span>
            <input
              value={location}
              disabled={busy || offline}
              onChange={(event) => {
                touchedRef.current = true;
                setTouched(true);
                setSaved(false);
                setLocation(event.target.value);
              }}
              className="mt-1 w-full rounded-xl border border-zinc-200 px-3 py-2 dark:border-zinc-700 dark:bg-zinc-900"
            />
          </label>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={busy || offline}
              onClick={() => void save()}
              className="rounded-full bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
            >
              {busy ? "Saving…" : "Save"}
            </button>
            {conflict ? (
              <button
                type="button"
                onClick={() => {
                  touchedRef.current = false;
                  setTouched(false);
                  setRemote(false);
                  setConflict(null);
                  onReload();
                }}
                className="rounded-full border border-zinc-300 px-4 py-2 text-sm font-semibold"
              >
                Reload current values
              </button>
            ) : null}
          </div>
        </div>
      ) : (
        <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
          <div><dt className="text-zinc-500">Legal name</dt><dd className="font-semibold">{text(settings?.legal_name, "Not registered")}</dd></div>
          <div><dt className="text-zinc-500">Legal name in Arabic</dt><dd className="font-semibold">{text(settings?.legal_name_ar)}</dd></div>
          <div><dt className="text-zinc-500">Country</dt><dd className="font-semibold">{text(settings?.country)}</dd></div>
          <div><dt className="text-zinc-500">Location</dt><dd className="font-semibold">{text(settings?.location)}</dd></div>
        </dl>
      )}
      <p className="mt-3 text-sm text-zinc-600">
        {canManage ? settingsAuditSummary(settings?.updated_at, settings?.updated_by_name, settings?.timezone) : restrictedReason}
      </p>
      {revision > 0 ? <p className="mt-1 text-xs text-zinc-500">Revision {revision}. The change source is stored on the audit event.</p> : null}
      {remote && !conflict ? <p className="mt-2 text-sm text-amber-800">A newer save arrived while you were editing. Reload before saving, or keep this copy.</p> : null}
      {saved ? <p className="mt-2 text-sm text-emerald-700">Saved. The server accepted this revision.</p> : null}
      {error ? <p role="alert" className="mt-2 text-sm text-red-700">{error}</p> : null}
      {conflict?.legal_name ? (
        <p className="mt-2 text-sm text-zinc-700">The server legal name is now {conflict.legal_name}{conflict.updated_by_name ? `, saved by ${conflict.updated_by_name}` : ""}.</p>
      ) : null}
      <p className="mt-3 text-sm text-zinc-500">Store code and business type stay read-only. Logo, hours, and contact details are not edited here.</p>
    </SettingsSectionCard>
  );
}
