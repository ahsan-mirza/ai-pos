import type { AppRelease, DownloadsList, InstallerFile } from "@ai-pos/shared-types";
import { Download, KeyRound, MonitorDown, PackageOpen } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorNote } from "../../components/ui/Field";
import { apiBlob, apiGet } from "../../lib/api";
import { errorMessage } from "../users/api";

function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

function formatDay(value: string): string {
  return new Date(value).toLocaleDateString(undefined, { dateStyle: "medium" });
}

const STEPS = [
  { title: "Install", body: "Run the installer on the Windows PC at the counter." },
  { title: "Create an activation key", body: "Register the till for its branch and issue a one-time key." },
  { title: "Activate", body: "Open AI POS, enter the store address and the key. The catalog syncs and the till is ready." },
] as const;

export function DownloadsPage() {
  const [data, setData] = useState<DownloadsList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    apiGet<DownloadsList>("/api/v1/downloads")
      .then((next) => live && setData(next))
      .catch((caught) => live && setError(errorMessage(caught, "Could not load the downloads.")));
    return () => {
      live = false;
    };
  }, []);

  const download = useCallback(async (file: InstallerFile) => {
    setBusy(file.download_path);
    setError(null);
    try {
      const path = file.download_path.split("/").map(encodeURIComponent).join("/");
      const blob = await apiBlob(`/api/v1${path}`);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = file.name;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (caught) {
      setError(errorMessage(caught, "Could not download the installer."));
    } finally {
      setBusy(null);
    }
  }, []);

  if (data === null) {
    return (
      <section className="mx-auto max-w-xl rounded-card border border-line bg-white p-8 text-sm text-charcoal/60">
        {error ?? "Loading the installer…"}
      </section>
    );
  }

  const latest = data.releases[0];
  const earlier = data.releases.slice(1);
  return (
    <section className="mx-auto max-w-xl">
      {latest ? <LatestRelease release={latest} busy={busy} onDownload={download} /> : <NothingPublished />}
      {earlier.length > 0 ? <EarlierReleases releases={earlier} busy={busy} onDownload={download} /> : null}
      <ErrorNote message={error} />
    </section>
  );
}

function LatestRelease({
  release,
  busy,
  onDownload,
}: {
  release: AppRelease;
  busy: string | null;
  onDownload: (file: InstallerFile) => Promise<void>;
}) {
  const installer = release.files.find((file) => file.kind === "exe") ?? release.files[0];
  const packageFile = release.files.find((file) => file.kind === "msi" && file !== installer);

  return (
    <div className="overflow-hidden rounded-card border border-line bg-white shadow-sm">
      <div className="px-8 pb-8 pt-8">
        <div className="flex items-start justify-between gap-4">
          <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-accent text-white shadow-sm shadow-accent/30">
            <MonitorDown size={26} aria-hidden="true" />
          </span>
          <span className="rounded-full bg-emerald-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-wider text-emerald-700">
            Latest
          </span>
        </div>
        <h2 className="mt-5 text-2xl font-semibold tracking-tight">AI POS for Windows</h2>
        <p className="mt-1 text-sm text-charcoal/60">
          Version {release.version} · {formatDay(release.published_at)} · works offline and syncs when the store is online
        </p>

        {installer ? (
          <div className="mt-6">
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => void onDownload(installer)}
              className="inline-flex h-12 w-full items-center justify-center gap-2 rounded-full bg-accent text-sm font-semibold text-white shadow-sm shadow-accent/25 transition-colors hover:bg-accent-hover disabled:opacity-40"
            >
              <Download size={18} aria-hidden="true" />
              {busy === installer.download_path ? "Downloading…" : "Download Windows installer"}
            </button>
            <p className="mt-2 text-center text-xs text-charcoal/50">
              Version {release.version} · .exe · {formatSize(installer.size_bytes)}
            </p>
          </div>
        ) : null}

        {packageFile ? (
          <p className="mt-4 text-center text-sm text-charcoal/60">
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => void onDownload(packageFile)}
              className="font-medium text-charcoal underline-offset-4 hover:underline disabled:opacity-40"
            >
              {busy === packageFile.download_path
                ? "Downloading package…"
                : `Windows package (.msi) · v${release.version}`}
            </button>
            <span> · {formatSize(packageFile.size_bytes)} for IT deployment</span>
          </p>
        ) : null}
      </div>

      <div className="border-t border-line bg-[#f8fafc] px-8 py-7">
        <h3 className="text-sm font-semibold uppercase tracking-[0.12em] text-charcoal/45">Set up a register</h3>
        <ol className="mt-4 space-y-4">
          {STEPS.map((step, index) => (
            <li key={step.title} className="flex gap-3">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-white text-xs font-bold text-accent ring-1 ring-accent/20">
                {index + 1}
              </span>
              <span>
                <span className="block text-sm font-semibold">{step.title}</span>
                <span className="text-sm text-charcoal/60">{step.body}</span>
              </span>
            </li>
          ))}
        </ol>
        <Link
          to="/registers"
          className="mt-6 inline-flex h-11 w-full items-center justify-center gap-2 rounded-full bg-charcoal text-sm font-semibold text-white transition-colors hover:bg-charcoal/90"
        >
          <KeyRound size={16} aria-hidden="true" />
          Create an activation key
        </Link>
      </div>
    </div>
  );
}

function EarlierReleases({
  releases,
  busy,
  onDownload,
}: {
  releases: AppRelease[];
  busy: string | null;
  onDownload: (file: InstallerFile) => Promise<void>;
}) {
  return (
    <div className="mt-4 overflow-hidden rounded-card border border-line bg-white shadow-sm">
      <h3 className="border-b border-line px-8 py-4 text-sm font-semibold uppercase tracking-[0.12em] text-charcoal/45">
        Earlier versions
      </h3>
      <ul>
        {releases.map((release) => {
          const installer = release.files.find((file) => file.kind === "exe") ?? release.files[0];
          const packageFile = release.files.find((file) => file.kind === "msi" && file !== installer);
          return (
            <li key={release.version} className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-8 py-4 last:border-b-0">
              <span>
                <span className="block text-sm font-semibold">Version {release.version}</span>
                <span className="text-xs text-charcoal/50">{formatDay(release.published_at)}</span>
              </span>
              <span className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
                {installer ? (
                  <button
                    type="button"
                    disabled={busy !== null}
                    onClick={() => void onDownload(installer)}
                    className="font-medium text-charcoal underline-offset-4 hover:underline disabled:opacity-40"
                  >
                    {busy === installer.download_path ? "Downloading…" : `.exe · ${formatSize(installer.size_bytes)}`}
                  </button>
                ) : null}
                {packageFile ? (
                  <button
                    type="button"
                    disabled={busy !== null}
                    onClick={() => void onDownload(packageFile)}
                    className="font-medium text-charcoal underline-offset-4 hover:underline disabled:opacity-40"
                  >
                    {busy === packageFile.download_path ? "Downloading…" : `.msi · ${formatSize(packageFile.size_bytes)}`}
                  </button>
                ) : null}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function NothingPublished() {
  return (
    <div className="rounded-card border border-line bg-white px-8 py-10 text-center shadow-sm">
      <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-surface text-charcoal/50">
        <PackageOpen size={22} aria-hidden="true" />
      </span>
      <h2 className="mt-4 text-2xl font-semibold tracking-tight">The Windows app is on its way</h2>
      <p className="mx-auto mt-2 max-w-sm text-sm text-charcoal/60">
        The installer will show up here as soon as the current release is published. You can still register tills in the meantime.
      </p>
      <Link
        to="/registers"
        className="mt-6 inline-flex h-11 items-center justify-center gap-2 rounded-full bg-accent px-6 text-sm font-semibold text-white hover:bg-accent-hover"
      >
        <KeyRound size={16} aria-hidden="true" />
        Go to registers
      </Link>
    </div>
  );
}
