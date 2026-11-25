import { businessIdentityError, type BusinessSettings } from "@ai-pos/shared-types";
import { CountryField, formatDateTime } from "@ai-pos/ui";
import { useEffect, useRef, useState } from "react";
import { ErrorNote, PrimaryButton, TextField } from "../../components/ui/Field";
import { ApiRequestError, apiGet, apiPut } from "../../lib/api";
import { useCanManageSettings, useCurrency } from "../../lib/currency";

function savedLine(settings: BusinessSettings | null): string {
  if (!settings?.updated_at) return "No business-settings timestamp was returned.";
  try {
    const when = formatDateTime(settings.updated_at, settings.timezone);
    if (when === "") return "No business-settings timestamp was returned.";
    const actor = settings.updated_by_name?.trim() ?? "";
    return `Last saved ${when}${actor === "" ? "" : ` by ${actor}`}.`;
  } catch {
    return "No business-settings timestamp was returned.";
  }
}

export function BusinessIdentitySettings() {
  const canManage = useCanManageSettings();
  const { settings, applySettings, loadError } = useCurrency();
  const [legalName, setLegalName] = useState(settings?.legal_name ?? "");
  const [legalNameAr, setLegalNameAr] = useState(settings?.legal_name_ar ?? "");
  const [country, setCountry] = useState(settings?.country ?? "");
  const [location, setLocation] = useState(settings?.location ?? "");
  const [touched, setTouched] = useState(false);
  const [remote, setRemote] = useState(false);
  const touchedRef = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
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
  const status = !canManage ? "Read only" : loadError ? "Offline" : remote ? "Conflict" : busy ? "Saving" : touched ? "Not saved" : settings ? "Synced" : "Waiting";

  const reload = () => {
    touchedRef.current = false;
    setTouched(false);
    setRemote(false);
    void apiGet<BusinessSettings>("/api/v1/settings").then(applySettings).catch((caught: unknown) => {
      setError(caught instanceof Error ? caught.message : "Business settings could not be loaded.");
    });
  };

  const save = async () => {
    if (busy || !canManage) return;
    setSaved(false);
    if (loadError) {
      setError("Business Pro is offline. The business identity was not changed.");
      return;
    }
    const validation = businessIdentityError({ legalName, legalNameAr, location });
    if (validation) {
      setError(validation);
      return;
    }
    if (revision < 1 || !settings) {
      setError("Business settings have not loaded, so this change was not sent.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const next = await apiPut<BusinessSettings>("/api/v1/settings/identity", {
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
      applySettings(next);
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : caught instanceof Error ? caught.message : "The business identity was not saved.");
      if (caught instanceof ApiRequestError && caught.code === "stale_settings") setRemote(true);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="rounded-3xl border border-charcoal/10 bg-white p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-2xl font-semibold">Business identity</h2>
          <p className="text-sm text-charcoal/60">Tenant managed. This does not change the tax rate, currency, or business type.</p>
        </div>
        <p className="rounded-full bg-charcoal/5 px-3 py-1 text-xs font-semibold">{status}</p>
      </div>
      {canManage ? (
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <TextField label="Legal name" required value={legalName} disabled={busy} onChange={(event) => { touchedRef.current = true; setTouched(true); setSaved(false); setLegalName(event.target.value); }} />
          <TextField label="Legal name in Arabic" value={legalNameAr} disabled={busy} onChange={(event) => { touchedRef.current = true; setTouched(true); setSaved(false); setLegalNameAr(event.target.value); }} />
          <CountryField label="Country" value={country} disabled={busy} onChange={(iso) => { touchedRef.current = true; setTouched(true); setSaved(false); setCountry(iso); }} />
          <TextField label="Location" value={location} disabled={busy} onChange={(event) => { touchedRef.current = true; setTouched(true); setSaved(false); setLocation(event.target.value); }} />
        </div>
      ) : (
        <dl className="mt-4 grid gap-3 text-sm md:grid-cols-2">
          <div><dt className="text-charcoal/50">Legal name</dt><dd className="font-medium">{settings?.legal_name?.trim() || "Not registered"}</dd></div>
          <div><dt className="text-charcoal/50">Legal name in Arabic</dt><dd className="font-medium">{settings?.legal_name_ar?.trim() || "Not set"}</dd></div>
          <div><dt className="text-charcoal/50">Country</dt><dd className="font-medium">{settings?.country?.trim() || "Not set"}</dd></div>
          <div><dt className="text-charcoal/50">Location</dt><dd className="font-medium">{settings?.location?.trim() || "Not set"}</dd></div>
        </dl>
      )}
      <p className="mt-4 text-sm text-charcoal/70">{canManage ? savedLine(settings) : "Only a business-wide administrator can change the business identity."}</p>
      {revision > 0 ? <p className="mt-1 text-xs text-charcoal/50">Revision {revision}. The saving application is recorded on the audit event.</p> : null}
      {remote ? <p className="mt-2 text-sm text-amber-800">A newer save arrived. Reload the current values before saving over them.</p> : null}
      {saved ? <p className="mt-2 text-sm text-emerald-700">Saved. The server accepted this revision.</p> : null}
      <ErrorNote message={error} />
      {canManage ? (
        <div className="mt-4 flex flex-wrap gap-2">
          <PrimaryButton disabled={busy} onClick={() => void save()}>{busy ? "Saving…" : "Save"}</PrimaryButton>
          {remote ? <button type="button" onClick={reload} className="rounded-full border border-charcoal/20 px-4 py-2 text-sm font-semibold">Reload current values</button> : null}
        </div>
      ) : null}
    </section>
  );
}
