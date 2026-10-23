import { listen } from "@tauri-apps/api/event";
import { useEffect, useState } from "react";
import { checkAppUpdate, inTauri, installAppUpdate, type AppUpdate } from "../../lib/tauri";

/** Shown once at startup when the store's server has a newer Windows installer. Offline boots skip this. */
export function UpdatePrompt() {
  const [offer, setOffer] = useState<AppUpdate | null>(null);
  const [percent, setPercent] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!inTauri()) return;
    let live = true;
    const unlisten = listen<{ percent: number }>("update-progress", (event) => {
      if (live) setPercent(event.payload.percent);
    });
    checkAppUpdate()
      .then((found) => {
        if (live) setOffer(found);
      })
      .catch(() => undefined);
    return () => {
      live = false;
      void unlisten.then((stop) => stop());
    };
  }, []);

  if (offer === null) return null;

  const update = () => {
    setBusy(true);
    setError(null);
    setPercent(0);
    void installAppUpdate().catch((caught: unknown) => {
      setBusy(false);
      setPercent(null);
      setError(caught instanceof Error ? caught.message : "The update could not be installed.");
    });
  };

  return (
    <div className="modal-backdrop" style={{ zIndex: 90 }} role="presentation">
      <div role="dialog" aria-modal="true" aria-labelledby="pos-update-title" className="modal-card max-w-md">
        <h2 id="pos-update-title" className="text-xl font-semibold">
          Version {offer.version} is available
        </h2>
        <p className="mt-2 text-sm text-charcoal/70 dark:text-zinc-300">
          {offer.notes ?? "Update now? The register installs the new version and restarts. Sales already on this till stay."}
        </p>
        {percent !== null ? (
          <p className="mt-4 text-sm font-medium tabular-nums">Downloading… {percent}%</p>
        ) : null}
        {error ? <p className="mt-3 text-sm text-red-600">{error}</p> : null}
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => setOffer(null)}
            className="rounded-full border border-gray-200 px-5 py-2 text-sm font-medium disabled:opacity-40"
          >
            Later
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={update}
            className="rounded-full bg-accent px-5 py-2 text-sm font-semibold text-white disabled:opacity-40"
          >
            {busy ? "Updating…" : "Update"}
          </button>
        </div>
      </div>
    </div>
  );
}
