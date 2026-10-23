import { useEffect, useState } from "react";
import { ErrorNote, Field, PrimaryButton } from "../components/ui";
import { api, errorText } from "../lib/api";
import { useSession } from "../lib/session";

interface SiteContact {
  whatsapp: string;
}

export function LandingPage() {
  const { operator } = useSession();
  const admin = operator?.role === "ADMIN";
  const [whatsapp, setWhatsapp] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .get<SiteContact>("/site/contact")
      .then((row) => setWhatsapp(row.whatsapp))
      .catch((caught: unknown) => setError(errorText(caught, "Could not load the landing page contact.")));
  }, []);

  const save = () => {
    setBusy(true);
    setSaved(false);
    api
      .patch<SiteContact>("/site/contact", { whatsapp, reason: reason.trim() })
      .then((row) => {
        setWhatsapp(row.whatsapp);
        setReason("");
        setError(null);
        setSaved(true);
      })
      .catch((caught: unknown) => setError(errorText(caught, "Could not save the WhatsApp number.")))
      .finally(() => setBusy(false));
  };

  return (
    <section className="max-w-xl">
      <h1 className="text-2xl font-semibold">Landing page</h1>
      <p className="mt-1 text-sm text-charcoal/60">
        The number on the WhatsApp button at axizpos.com. Leave it blank to hide the button. Include the country code.
      </p>
      <div className="mt-6 rounded-3xl border border-line bg-white p-5">
        <Field
          label="WhatsApp number"
          value={whatsapp}
          placeholder="+971501234567"
          inputMode="tel"
          autoComplete="tel"
          disabled={!admin}
          onChange={(event) => setWhatsapp(event.target.value)}
        />
        {admin ? (
          <div className="mt-4">
            <Field
              label="Reason (kept in the audit log)"
              value={reason}
              maxLength={500}
              onChange={(event) => setReason(event.target.value)}
            />
            <div className="mt-4 flex items-center gap-3">
              <PrimaryButton disabled={busy || reason.trim().length < 3} onClick={save}>
                Save
              </PrimaryButton>
              {saved ? <p className="text-sm text-charcoal/60">Saved. The landing page uses this number.</p> : null}
            </div>
          </div>
        ) : (
          <p className="mt-3 text-sm text-charcoal/60">Only a console admin can change this number.</p>
        )}
        <ErrorNote message={error} />
      </div>
    </section>
  );
}
