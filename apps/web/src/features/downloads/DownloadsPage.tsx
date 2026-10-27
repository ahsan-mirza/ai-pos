import type { AppRelease, DownloadsList, InstallerFile } from "@ai-pos/shared-types";
import { Download, KeyRound, PackageOpen } from "lucide-react";
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
  return (
    <section className="mx-auto max-w-xl">
      {latest ? <LatestRelease release={latest} busy={busy} onDownload={download} /> : <NothingPublished />}
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
  const installer = release.files.find((file) => file.kind === "exe");

  return (
    <div className="overflow-hidden rounded-card border border-line bg-white shadow-sm">
      <div className="px-5 pb-8 pt-8 sm:px-8">
        <div className="flex items-start justify-between gap-4">
          <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-accent text-white shadow-sm shadow-accent/30">
            <WindowsMark />
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
              {busy === installer.download_path ? "Downloading…" : "Download Windows Installer"}
            </button>
            <p className="mt-2 text-center text-xs text-charcoal/50">
              Version {release.version} · .exe · {formatSize(installer.size_bytes)}
            </p>
          </div>
        ) : (
          <p className="mt-6 text-center text-sm text-charcoal/60">The Windows installer is not available for this release.</p>
        )}
      </div>

      <div className="border-t border-line bg-[#f8fafc] px-5 py-7 sm:px-8">
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

function WindowsMark() {
  return (
    <svg viewBox="0 0 24 24" width="26" height="26" aria-hidden="true" fill="currentColor">
      <path d="M3 5.1 10.5 4.1v7.2H3V5.1Zm8.3-1.1L21 2.4v8.9h-9.7V4Zm0 9.2H21v8.9l-9.7-1.4V13.2ZM3 12.7h7.5v7.2L3 18.7v-6Z" />
    </svg>
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
