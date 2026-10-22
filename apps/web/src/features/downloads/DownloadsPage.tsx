import type { AppRelease, DownloadsList, InstallerFile } from "@ai-pos/shared-types";
import { Check, Copy, Download, KeyRound, MonitorDown, PackageOpen, ShieldAlert } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorNote, GhostButton, PrimaryButton } from "../../components/ui/Field";
import { apiBlob, apiGet } from "../../lib/api";
import { errorMessage } from "../users/api";

function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

function formatDay(value: string): string {
  return new Date(value).toLocaleDateString(undefined, { dateStyle: "medium" });
}

const KIND_LABEL: Record<InstallerFile["kind"], { title: string; hint: string }> = {
  exe: { title: "Windows installer (.exe)", hint: "Recommended. Double-click on the register PC and follow the steps." },
  msi: { title: "Windows package (.msi)", hint: "For IT teams deploying to many PCs with Group Policy or Intune." },
};

function CopyHash({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={() => {
        void navigator.clipboard.writeText(value).then(() => {
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1500);
        });
      }}
      title="Copy SHA-256"
      className="inline-flex max-w-full items-center gap-1.5 rounded-lg bg-surface px-2 py-1 font-mono text-[11px] text-charcoal/60 hover:text-charcoal"
    >
      <span className="truncate">SHA-256 {value.slice(0, 16)}…</span>
      {copied ? <Check size={12} aria-hidden="true" /> : <Copy size={12} aria-hidden="true" />}
    </button>
  );
}

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
      <section className="rounded-card border border-line bg-white p-6 text-sm text-charcoal/60">
        {error ?? "Loading downloads…"}
      </section>
    );
  }

  const [latest, ...older] = data.releases;
  return (
    <section className="space-y-4">
      {latest ? <LatestRelease release={latest} busy={busy} onDownload={download} /> : <NothingPublished />}
      <ErrorNote message={error} />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="rounded-card border border-line bg-white p-6">
          <h3 className="text-lg font-semibold">Set up a register</h3>
          <ol className="mt-4 space-y-4 text-sm">
            {[
              ["Install", "Run the installer on the Windows PC at the counter. It needs Windows 10 or 11."],
              [
                "Create an activation key",
                "In Registers, register the till for its branch and issue a one-time activation key.",
              ],
              [
                "Activate",
                "Open AI POS on the PC, enter your store's web address and the key. The till syncs its catalog and is ready.",
              ],
            ].map(([title, body], index) => (
              <li key={title} className="flex gap-3">
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent/10 text-xs font-bold text-accent">
                  {index + 1}
                </span>
                <span>
                  <span className="block font-semibold">{title}</span>
                  <span className="text-charcoal/60">{body}</span>
                </span>
              </li>
            ))}
          </ol>
          <Link
            to="/registers"
            className="mt-5 inline-flex items-center gap-2 rounded-full border border-line px-4 py-2 text-sm font-medium hover:bg-surface"
          >
            <KeyRound size={15} aria-hidden="true" />
            Go to Registers
          </Link>
        </div>

        <div className="rounded-card border border-line bg-white p-6">
          <h3 className="text-lg font-semibold">Earlier versions</h3>
          {older.length === 0 ? (
            <p className="mt-3 text-sm text-charcoal/60">Only the current version has been published.</p>
          ) : (
            <ul className="mt-3 divide-y divide-line">
              {older.map((release) => (
                <li key={release.version} className="flex flex-wrap items-center justify-between gap-3 py-3">
                  <span>
                    <span className="block text-sm font-semibold">Version {release.version}</span>
                    <span className="text-xs text-charcoal/50">Published {formatDay(release.published_at)}</span>
                  </span>
                  <span className="flex flex-wrap gap-2">
                    {release.files.map((file) => (
                      <GhostButton
                        key={file.name}
                        disabled={busy !== null}
                        onClick={() => void download(file)}
                        aria-label={`Download ${file.name}`}
                      >
                        <Download size={14} className="mr-1.5" aria-hidden="true" />.{file.kind}
                      </GhostButton>
                    ))}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-4 flex gap-2 rounded-2xl bg-surface px-4 py-3 text-xs text-charcoal/60">
            <ShieldAlert size={14} className="mt-0.5 shrink-0" aria-hidden="true" />
            Older versions are for reinstalling a till that must match others. Registers on any version keep syncing.
          </p>
        </div>
      </div>
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
  return (
    <div className="rounded-card border border-line bg-white p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-4">
          <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-accent text-white">
            <MonitorDown size={26} aria-hidden="true" />
          </span>
          <div>
            <h2 className="text-2xl font-semibold">AI POS for Windows</h2>
            <p className="text-sm text-charcoal/60">
              Version {release.version} · published {formatDay(release.published_at)} · works offline, syncs when online
            </p>
          </div>
        </div>
        <span className="rounded-full bg-emerald-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-wider text-emerald-700">
          Latest
        </span>
      </div>

      {release.notes ? <p className="mt-4 whitespace-pre-line text-sm text-charcoal/70">{release.notes}</p> : null}

      <div className="mt-6 grid gap-3 md:grid-cols-2">
        {release.files.map((file) => {
          const label = KIND_LABEL[file.kind];
          const downloading = busy === file.download_path;
          const Button = file.kind === "exe" ? PrimaryButton : GhostButton;
          return (
            <div key={file.name} className="flex flex-col justify-between gap-3 rounded-2xl border border-line p-4">
              <div>
                <p className="font-semibold">{label.title}</p>
                <p className="text-xs text-charcoal/60">{label.hint}</p>
                <p className="mt-2 truncate text-xs text-charcoal/50" title={file.name}>
                  {file.name} · {formatSize(file.size_bytes)}
                </p>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <CopyHash value={file.sha256} />
                <Button disabled={busy !== null} onClick={() => void onDownload(file)}>
                  <Download size={16} className="mr-2" aria-hidden="true" />
                  {downloading ? "Downloading…" : "Download"}
                </Button>
              </div>
            </div>
          );
        })}
      </div>
      <p className="mt-4 text-xs text-charcoal/50">
        Windows may show “Windows protected your PC” the first time: choose More info, then Run anyway.
      </p>
    </div>
  );
}

function NothingPublished() {
  return (
    <div className="rounded-card border border-line bg-white p-8">
      <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-surface text-charcoal/60">
        <PackageOpen size={22} aria-hidden="true" />
      </span>
      <h2 className="mt-4 text-2xl font-semibold">No POS installer published yet</h2>
      <p className="mt-2 max-w-2xl text-sm text-charcoal/60">
        Installers appear here once a release is published. Tagging a version (for example <code>v0.2.0</code>) builds
        the Windows installer and copies it to this server automatically.
      </p>
    </div>
  );
}
