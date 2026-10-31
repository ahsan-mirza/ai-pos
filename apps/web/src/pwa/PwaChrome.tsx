import { Download, RefreshCw, WifiOff, X } from "lucide-react";
import { useState } from "react";
import { usePwa } from "./PwaContext";
import { enablePush, PUSH_NOT_CONFIGURED, pushConfigured } from "./push";

export function PwaChrome() {
  const pwa = usePwa();
  return (
    <>
      {pwa.updateReady ? (
        <div className="flex w-full flex-wrap items-center justify-between gap-2 bg-charcoal px-4 py-2 text-sm text-white">
          <p>A new version of Business Pro is ready. Finish what you are doing, then update.</p>
          <button type="button" className="inline-flex items-center gap-1 rounded-full bg-accent px-3 py-1.5 font-semibold" onClick={pwa.updateNow}>
            <RefreshCw size={14} aria-hidden="true" /> Update now
          </button>
        </div>
      ) : null}
      {pwa.online ? null : (
        <div className="flex w-full items-start gap-2 bg-amber-100 px-4 py-2 text-sm text-amber-950" role="status">
          <WifiOff size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
          <p>You are offline. Business Pro can open, but sales, customers, inventory, and reports need a connection. Nothing on screen should be treated as live.</p>
        </div>
      )}
      {pwa.showBanner ? (
        <div className="flex w-full flex-wrap items-center justify-between gap-2 border-b border-line bg-white px-4 py-2 text-sm">
          <p>Install Business Pro on this device.</p>
          <span className="flex items-center gap-2">
            {pwa.surface === "prompt" ? (
              <button type="button" className="inline-flex items-center gap-1 rounded-full bg-accent px-3 py-1.5 font-semibold text-white" onClick={() => void pwa.install()}>
                <Download size={14} aria-hidden="true" /> Install Business Pro
              </button>
            ) : (
              <button type="button" className="inline-flex items-center gap-1 rounded-full bg-accent px-3 py-1.5 font-semibold text-white" onClick={pwa.openIosHelp}>
                How to install
              </button>
            )}
            <button type="button" aria-label="Dismiss install" className="rounded-full p-1 text-charcoal/60" onClick={pwa.dismissBanner}>
              <X size={16} aria-hidden="true" />
            </button>
          </span>
        </div>
      ) : null}
      {pwa.iosOpen ? <IosInstallHelp onClose={pwa.closeIosHelp} /> : null}
    </>
  );
}

export function IosInstallHelp({ onClose }: { onClose: () => void }) {
  return (
    <div className="modal-backdrop fixed inset-0 z-50 flex items-end justify-center bg-charcoal/40 p-4 sm:items-center" role="presentation" onMouseDown={onClose}>
      <div
        role="dialog"
        aria-labelledby="ios-install-title"
        className="modal-card w-full max-w-md rounded-card bg-white p-5 text-charcoal"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <h2 id="ios-install-title" className="text-lg font-semibold">Add Business Pro to your Home Screen</h2>
        <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm">
          <li>Open Business Pro in Safari.</li>
          <li>Tap Share.</li>
          <li>Select Add to Home Screen.</li>
          <li>Confirm Add.</li>
        </ol>
        <button type="button" className="mt-4 rounded-full bg-charcoal px-4 py-2 text-sm font-semibold text-white" onClick={onClose}>
          Close
        </button>
      </div>
    </div>
  );
}

export function DeviceAlertsCard() {
  const [message, setMessage] = useState<string | null>(null);
  return (
    <section className="rounded-card border border-line bg-white p-6">
      <h2 className="text-lg font-semibold">Device alerts</h2>
      <p className="mt-1 text-sm text-charcoal/60">
        Business Pro asks for notification permission only after you turn alerts on. A push service has to be configured before a device can subscribe.
      </p>
      <button
        type="button"
        className="mt-4 rounded-full bg-charcoal px-4 py-2 text-sm font-semibold text-white"
        onClick={() => {
          void enablePush()
            .then(() => setMessage("This device can receive Business Pro alerts."))
            .catch((caught: unknown) => setMessage(caught instanceof Error ? caught.message : PUSH_NOT_CONFIGURED));
        }}
      >
        {pushConfigured() ? "Turn on alerts" : "Check alert setup"}
      </button>
      {message ? <p className="mt-3 text-sm text-charcoal/70">{message}</p> : null}
    </section>
  );
}

export function InstallBusinessProCard() {
  const pwa = usePwa();
  if (pwa.surface === "installed") {
    return (
      <section className="rounded-card border border-line bg-white p-6">
        <h2 className="text-lg font-semibold">Business Pro is installed</h2>
        <p className="mt-1 text-sm text-charcoal/60">This device opens Business Pro as its own app. Live records still come from the server.</p>
      </section>
    );
  }
  if (pwa.menu === null && pwa.surface === "hidden") {
    return (
      <section className="rounded-card border border-line bg-white p-6">
        <h2 className="text-lg font-semibold">Install Business Pro</h2>
        <p className="mt-1 text-sm text-charcoal/60">
          This browser cannot install the app. Use Chrome or Edge on a computer, or Safari on an iPhone or iPad.
        </p>
      </section>
    );
  }
  return (
    <section className="rounded-card border border-line bg-white p-6">
      <h2 className="text-lg font-semibold">Install Business Pro</h2>
      <p className="mt-1 text-sm text-charcoal/60">
        Keep Business Pro on this phone, tablet, or computer. Installing it does not change your sign-in or store access.
      </p>
      <div className="mt-4">
        {pwa.menu === "install" ? (
          <button type="button" className="rounded-full bg-accent px-4 py-2 text-sm font-semibold text-white" onClick={() => void pwa.install()}>
            Install Business Pro
          </button>
        ) : (
          <button type="button" className="rounded-full bg-accent px-4 py-2 text-sm font-semibold text-white" onClick={pwa.openIosHelp}>
            Show iPhone and iPad steps
          </button>
        )}
      </div>
    </section>
  );
}
