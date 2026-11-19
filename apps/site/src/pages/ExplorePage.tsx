import {
  BUSINESS_SETTINGS_STORAGE_KEY,
  DEMO_BUSINESSES,
  DemoOpenError,
  PORTAL_SESSION_STORAGE_KEY,
  POS_DEMO_HANDOFF_FILENAME,
  POS_INSTALLER_FILENAME,
  PosInstallerError,
  STORE_CODE_STORAGE_KEY,
  claimDemoClick,
  exchangeDemo,
  formatInstallerSize,
  friendlyDemoError,
  installerDigestMatches,
  loadPosInstallerRelease,
  planDemoOpen,
  posInstallerMessage,
  readPosInstallerBytes,
  rememberPosDemoBusiness,
  requestPosDemoHandoff,
  storedDemoSession,
  type DemoBusiness,
  type DemoBusinessCode,
  type PosInstallerRelease,
} from "@ai-pos/shared-types";
import { useState } from "react";
import { apiBaseUrl, portalUrl } from "../env";
import { ResponsiveImage } from "../responsiveImage";
import { track } from "../track";

function endedNotice(): string | null {
  const notice = new URLSearchParams(window.location.search).get("notice");
  return notice === "ended" ? "This demo session ended. Choose a business to continue." : null;
}

function clearPreviousStore(): void {
  localStorage.removeItem(PORTAL_SESSION_STORAGE_KEY);
  sessionStorage.removeItem(PORTAL_SESSION_STORAGE_KEY);
  localStorage.removeItem(BUSINESS_SETTINGS_STORAGE_KEY);
  const assistant: string[] = [];
  for (let index = 0; index < localStorage.length; index += 1) {
    const key = localStorage.key(index);
    if (key !== null && key.startsWith("ai-pos.assistant.")) assistant.push(key);
  }
  for (const key of assistant) localStorage.removeItem(key);
}

function ownedBuffer(bytes: Uint8Array): ArrayBuffer {
  const copy = new ArrayBuffer(bytes.byteLength);
  new Uint8Array(copy).set(bytes);
  return copy;
}

async function sha256Hex(bytes: Uint8Array): Promise<string> {
  const subtle = globalThis.crypto?.subtle;
  if (subtle === undefined) throw new PosInstallerError("browser");
  const digest = await subtle.digest("SHA-256", ownedBuffer(bytes));
  return [...new Uint8Array(digest)].map((part) => part.toString(16).padStart(2, "0")).join("");
}

function startBrowserDownload(bytes: Uint8Array, name: string): void {
  const urlApi = globalThis.URL;
  if (urlApi?.createObjectURL === undefined || typeof document === "undefined") throw new PosInstallerError("browser");
  const blob = new Blob([ownedBuffer(bytes)], { type: "application/vnd.microsoft.portable-executable" });
  const url = urlApi.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  urlApi.revokeObjectURL(url);
}

export function ExplorePage() {
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(endedNotice);
  const [downloadBusiness, setDownloadBusiness] = useState<DemoBusiness | null>(null);
  const [downloadPhase, setDownloadPhase] = useState<"checking" | "downloading" | "started" | "failed">("checking");
  const [release, setRelease] = useState<PosInstallerRelease | null>(null);
  const [sizeLabel, setSizeLabel] = useState<string | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  async function open(code: DemoBusinessCode) {
    if (claimDemoClick(pending, code) === null) return;
    const business = DEMO_BUSINESSES.find((item) => item.code === code);
    if (business === undefined) return;
    setPending(code);
    setError(null);
    track("click_demo_card", { business_code: code });
    const plan = planDemoOpen(window.location.origin, portalUrl, code);
    if (plan.kind === "navigate") {
      window.location.assign(plan.href);
      return;
    }
    try {
      const result = await exchangeDemo(apiBaseUrl, code, fetch);
      const stored = storedDemoSession(
        {
          access_token: result.access_token,
          expires_in: result.expires_in,
          business_code: code,
          business_name: result.business_name ?? business.title,
          demo: true,
        },
        Date.now(),
      );
      clearPreviousStore();
      localStorage.setItem(STORE_CODE_STORAGE_KEY, business.slug);
      localStorage.setItem(PORTAL_SESSION_STORAGE_KEY, JSON.stringify(stored));
      track("demo_entered", { business_code: code });
      window.location.assign(plan.href);
    } catch (caught) {
      const status = caught instanceof DemoOpenError ? caught.status : 500;
      setError(friendlyDemoError(status, business.short));
      setPending(null);
    }
  }

  async function download(code: DemoBusinessCode) {
    if (pending !== null) return;
    const business = DEMO_BUSINESSES.find((item) => item.code === code);
    if (business === undefined || !rememberPosDemoBusiness(sessionStorage, code)) return;
    setPending(`download:${code}`);
    setDownloadBusiness(business);
    setDownloadPhase("checking");
    setRelease(null);
    setSizeLabel(null);
    setProgress(null);
    setDownloadError(null);
    track("click_pos_download", { business_code: code });
    try {
      const published = await loadPosInstallerRelease(apiBaseUrl, fetch);
      setRelease(published);
      setDownloadPhase("downloading");
      const file = await readPosInstallerBytes(published, fetch, (received, total) => {
        const label = total === null ? null : formatInstallerSize(total);
        setSizeLabel(label);
        setProgress(total === null || total === 0 ? null : Math.min(100, Math.round((received / total) * 100)));
      });
      const digest = await sha256Hex(file.bytes);
      if (!installerDigestMatches(digest, published.sha256)) throw new PosInstallerError("invalid");
      startBrowserDownload(file.bytes, POS_INSTALLER_FILENAME);
      setDownloadPhase("started");
    } catch (caught) {
      const failure = caught instanceof PosInstallerError ? caught.failure : "download";
      setDownloadError(posInstallerMessage(failure));
      setDownloadPhase("failed");
    } finally {
      setPending(null);
    }
  }

  function closeDownload() {
    setDownloadBusiness(null);
  }

  return (
    <section className="mx-auto max-w-page px-5 py-14 sm:px-8">
      <p className="text-sm font-semibold uppercase tracking-[0.16em] text-[#f26a21]">Explore AxizPOS</p>
      <h1 className="mt-3 max-w-3xl text-4xl font-semibold tracking-tight text-[#171717] sm:text-5xl">Experience AxizPOS in Action</h1>
      <p className="mt-4 max-w-2xl text-lg text-[#5c5c5c]">
        Choose your business and explore how AxizPOS simplifies billing, inventory, sales and business management.
      </p>
      <p className="mt-3 max-w-2xl text-sm text-[#5c5c5c]">
        Each demo is a shared environment. Other visitors can see the same sales, tables and stock, and the data is reset from time to time.
      </p>
      <p className="mt-3 max-w-2xl text-sm text-[#5c5c5c]">
        The pharmacy card opens a shared catalogue demonstration. It is not a licensed pharmacy ERP, and it is not a statement that compliance, licensing, or offline verification are complete.
      </p>
      {error !== null ? (
        <p className="mt-6 max-w-2xl rounded-2xl border border-[#f26a21]/30 bg-[#fff6f0] px-4 py-3 text-sm text-[#171717]" role="alert">
          {error}
        </p>
      ) : null}
      <div className="mt-10 grid grid-cols-1 gap-6 md:grid-cols-2">
        {DEMO_BUSINESSES.map((business) => {
          const opening = pending === business.code;
          const saving = pending === `download:${business.code}`;
          return (
            <article key={business.code} className="flex flex-col overflow-hidden rounded-3xl border border-[#ececec] bg-white shadow-[0_16px_40px_rgba(17,17,17,0.06)]">
              <ResponsiveImage src={business.image} alt="" width={1774} height={887} sizes="(min-width: 768px) 50vw, 100vw" loading="lazy" className="h-48 w-full object-cover" />
              <div className="flex flex-1 flex-col gap-4 p-6">
                <h2 className="text-2xl font-semibold text-[#171717]">{business.title}</h2>
                <ul className="space-y-1.5 text-sm text-[#5c5c5c]">
                  {business.features.map((feature) => (
                    <li key={feature}>{feature}</li>
                  ))}
                </ul>
                <div className="mt-auto flex flex-col gap-3 sm:flex-row">
                  <button
                    type="button"
                    className="inline-flex h-12 flex-1 items-center justify-center rounded-2xl bg-[#f26a21] px-4 text-sm font-semibold text-white disabled:cursor-wait disabled:opacity-70"
                    disabled={pending !== null}
                    aria-busy={opening}
                    onClick={() => void open(business.code)}
                  >
                    {opening ? "Opening demo…" : "Explore Business Pro"}
                  </button>
                  <button
                    type="button"
                    className="inline-flex h-12 flex-1 items-center justify-center rounded-2xl border border-[#f26a21] bg-white px-4 text-sm font-semibold text-[#f26a21] disabled:cursor-wait disabled:opacity-70"
                    disabled={pending !== null}
                    aria-busy={saving}
                    onClick={() => void download(business.code)}
                  >
                    {saving ? "Preparing download…" : "Download POS Register"}
                  </button>
                </div>
              </div>
            </article>
          );
        })}
      </div>
      <div className="mt-10 flex flex-wrap gap-4 text-sm font-semibold">
        <a className="text-[#f26a21]" href="/#pricing">
          See pricing
        </a>
        <a className="text-[#171717]" href="/#contact">
          Contact sales
        </a>
      </div>
      {downloadBusiness !== null ? (
        <PosInstallPanel
          business={downloadBusiness}
          phase={downloadPhase}
          release={release}
          sizeLabel={sizeLabel}
          progress={progress}
          error={downloadError}
          onClose={closeDownload}
        />
      ) : null}
    </section>
  );
}

function ConnectionFile({ business }: { business: DemoBusiness }) {
  const [phase, setPhase] = useState<"idle" | "working" | "started" | "failed">("idle");
  const [message, setMessage] = useState<string | null>(null);

  const download = async () => {
    setPhase("working");
    setMessage(null);
    track("click_pos_connect", { business: business.code });
    try {
      const documentText = await requestPosDemoHandoff(apiBaseUrl, business.code, (input, init) => fetch(input, init));
      const url = URL.createObjectURL(new Blob([documentText], { type: "application/json" }));
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = POS_DEMO_HANDOFF_FILENAME;
      anchor.click();
      URL.revokeObjectURL(url);
      setPhase("started");
      setMessage("The connection file download has started. Open it in AxizPOS POS Register.");
    } catch (caught) {
      setPhase("failed");
      const unavailable = caught instanceof PosInstallerError && caught.failure === "unavailable";
      setMessage(
        unavailable
          ? "This demo is not available right now."
          : caught instanceof PosInstallerError
            ? posInstallerMessage(caught.failure)
            : "The connection file could not be downloaded.",
      );
    }
  };

  return (
    <div className="mt-4">
      <button
        type="button"
        className="inline-flex h-11 items-center justify-center rounded-2xl border border-[#f26a21] px-5 text-sm font-semibold text-[#f26a21] disabled:opacity-60"
        disabled={phase === "working"}
        onClick={() => void download()}
      >
        {phase === "working" ? "Preparing connection file…" : "Download connection file"}
      </button>
      {message !== null ? (
        <p className="mt-2 text-sm text-[#5c5c5c]" role="status">
          {message}
        </p>
      ) : null}
    </div>
  );
}

function PosInstallPanel({
  business,
  phase,
  release,
  sizeLabel,
  progress,
  error,
  onClose,
}: {
  business: DemoBusiness;
  phase: "checking" | "downloading" | "started" | "failed";
  release: PosInstallerRelease | null;
  sizeLabel: string | null;
  progress: number | null;
  error: string | null;
  onClose: () => void;
}) {
  const status =
    phase === "checking"
      ? "Checking the Windows installer…"
      : phase === "downloading"
        ? progress === null
          ? "Downloading the installer…"
          : `Downloading the installer… ${progress}%`
        : phase === "started"
          ? "The installer download has started."
          : error;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-[#171717]/40 p-4 sm:items-center" role="presentation">
      <div
        className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-3xl bg-white p-6 shadow-[0_24px_60px_rgba(17,17,17,0.18)]"
        role="dialog"
        aria-modal="true"
        aria-labelledby="pos-install-title"
      >
        <p className="text-sm font-semibold uppercase tracking-[0.16em] text-[#f26a21]">Windows application</p>
        <h2 id="pos-install-title" className="mt-2 text-2xl font-semibold text-[#171717]">
          Install AxizPOS POS Register
        </h2>
        <p className="mt-3 text-sm text-[#5c5c5c]">
          This is the actual AxizPOS POS Register for Windows. Windows 10 or Windows 11 is required. The same installer is used for every business.
        </p>
        <p className="mt-2 text-sm text-[#5c5c5c]">
          {business.title} is selected. The installer does not sign the register in and does not contain a connection ticket. After the application is installed, download a connection file and open it from the activation screen. The file works once and expires after a few minutes.
        </p>
        <ol className="mt-4 list-decimal space-y-1 pl-5 text-sm text-[#171717]">
          <li>Download AxizPOS POS Register.</li>
          <li>Open the Windows installer.</li>
          <li>Complete installation and launch the application.</li>
          <li>Download the connection file and open it in the register.</li>
        </ol>
        <p className="mt-4 text-sm text-[#5c5c5c]">
          You&apos;re using a shared demo environment. Other visitors may create sales or update demo data. Demo data is periodically reset.
        </p>
        <p className="mt-4 text-sm font-semibold text-[#171717]" role="status">
          {status}
        </p>
        {release !== null ? <p className="mt-1 text-sm text-[#5c5c5c]">Version {release.version}</p> : null}
        {sizeLabel !== null ? <p className="mt-1 text-sm text-[#5c5c5c]">Size {sizeLabel}</p> : null}
        {progress !== null && phase === "downloading" ? (
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-[#f3f3f3]" aria-hidden="true">
            <div className="h-full bg-[#f26a21]" style={{ width: `${progress}%` }} />
          </div>
        ) : null}
        <ConnectionFile business={business} />
        <button
          type="button"
          className="mt-3 inline-flex h-11 items-center justify-center rounded-2xl bg-[#171717] px-5 text-sm font-semibold text-white"
          onClick={onClose}
        >
          Close
        </button>
      </div>
    </div>
  );
}
