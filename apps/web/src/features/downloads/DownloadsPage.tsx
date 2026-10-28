import type { DownloadsList, InstallerFile } from "@ai-pos/shared-types";
import { Download, KeyRound } from "lucide-react";
import { useCallback, useEffect, useState, type ReactNode } from "react";
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
  { title: "Activate", body: "Open AxizPOS Register, enter the store address and the key. The catalog syncs and the till is ready." },
] as const;

type PlatformId = "windows" | "android" | "ios";

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
      <section className="mx-auto max-w-6xl rounded-card border border-line bg-white p-8 text-sm text-charcoal/60">
        {error ?? "Loading the installer…"}
      </section>
    );
  }

  const latest = data.releases[0];
  const installer = latest?.files.find((file) => file.kind === "exe");

  return (
    <section className="mx-auto max-w-6xl">
      <div className="mb-6 grid gap-3 sm:grid-cols-2">
        <p className="rounded-2xl border border-line bg-white px-4 py-3 text-sm text-charcoal/70">
          <span className="font-semibold text-charcoal">AxizPOS Register.</span> Checkout, sales, and the register workflows that keep working offline and sync when the store is back online.
        </p>
        <p className="rounded-2xl border border-line bg-white px-4 py-3 text-sm text-charcoal/70">
          <span className="font-semibold text-charcoal">AxizPOS Business.</span> Store operations, inventory, customers, reports, staff, and the other management tools in this portal. The same store, role, and modules apply.
        </p>
      </div>

      <h2 className="text-sm font-semibold uppercase tracking-[0.12em] text-charcoal/45">Available now</h2>
      <div className="mt-3 grid grid-cols-1 items-stretch gap-4 lg:max-w-xl">
        <ProductCard
          name="AxizPOS Register for Windows"
          platform="windows"
          prominent
          status="Available"
          description={
            latest
              ? `Version ${latest.version} · ${formatDay(latest.published_at)} · works offline and syncs when the store is online`
              : "The point-of-sale application for cashiers and store staff. The current Windows installer has not been published on this server yet."
          }
          action={
            installer ? (
              <div>
                <button
                  type="button"
                  disabled={busy !== null}
                  onClick={() => void download(installer)}
                  className="inline-flex h-12 w-full items-center justify-center gap-2 rounded-full bg-accent text-sm font-semibold text-white shadow-sm shadow-accent/25 transition-colors hover:bg-accent-hover disabled:opacity-40"
                >
                  <Download size={18} aria-hidden="true" />
                  {busy === installer.download_path ? "Downloading…" : "Download Windows Installer"}
                </button>
                <p className="mt-2 text-center text-xs text-charcoal/50">
                  Version {latest?.version} · .exe · {formatSize(installer.size_bytes)}
                </p>
              </div>
            ) : (
              <button type="button" disabled aria-disabled="true" className="inline-flex h-12 w-full cursor-not-allowed items-center justify-center rounded-full bg-charcoal/10 text-sm font-semibold text-charcoal/45">
                Installer not published
              </button>
            )
          }
        />
      </div>

      <h2 className="mb-3 mt-8 text-sm font-semibold uppercase tracking-[0.12em] text-charcoal/45">Coming soon</h2>
      <div className="grid grid-cols-1 items-stretch gap-4 md:grid-cols-2 xl:grid-cols-4">
        <ProductCard
          name="AxizPOS Register for Android"
          platform="android"
          muted
          status="Coming Soon"
          description="Bring checkout and point-of-sale operations to supported Android devices."
          action={<SoonButton />}
        />
        <ProductCard
          name="AxizPOS Register for iOS"
          platform="ios"
          muted
          status="Coming Soon"
          description="Point-of-sale capabilities for compatible Apple mobile devices are planned."
          action={<SoonButton />}
        />
        <ProductCard
          name="AxizPOS Business for Android"
          platform="android"
          muted
          status="Coming Soon"
          description="Manage your store and business operations from your Android device."
          action={<SoonButton />}
        />
        <ProductCard
          name="AxizPOS Business for iOS"
          platform="ios"
          muted
          status="Coming Soon"
          description="Access your business management tools on compatible Apple mobile devices."
          action={<SoonButton />}
        />
      </div>

      <SetupSteps />
      <ErrorNote message={error} />
    </section>
  );
}

function ProductCard({
  name,
  platform,
  status,
  description,
  action,
  prominent = false,
  muted = false,
}: {
  name: string;
  platform: PlatformId;
  status: string;
  description: string;
  action: ReactNode;
  prominent?: boolean;
  muted?: boolean;
}) {
  return (
    <article className={`flex h-full flex-col rounded-card border p-5 ${prominent ? "border-line bg-white shadow-sm" : muted ? "border-line bg-[#f8fafc]" : "border-line bg-white"}`}>
      <div className="flex items-start justify-between gap-3">
        <PlatformIcon platform={platform} prominent={prominent} />
        <StatusBadge label={status} tone={muted ? "muted" : "live"} />
      </div>
      <h3 className={`mt-5 text-lg font-semibold tracking-tight ${muted ? "text-charcoal/70" : "text-charcoal"}`}>{name}</h3>
      <p className={`mt-1 flex-1 text-sm ${muted ? "text-charcoal/50" : "text-charcoal/60"}`}>{description}</p>
      <div className="mt-6">{action}</div>
    </article>
  );
}

function StatusBadge({ label, tone }: { label: string; tone: "live" | "muted" }) {
  const className =
    tone === "live"
      ? "bg-emerald-50 text-emerald-700"
      : "bg-charcoal/5 text-charcoal/45";
  return <span className={`rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-wider ${className}`}>{label}</span>;
}

function SoonButton() {
  return (
    <button
      type="button"
      disabled
      aria-disabled="true"
      className="inline-flex h-12 w-full cursor-not-allowed items-center justify-center rounded-full bg-charcoal/5 text-sm font-semibold text-charcoal/40"
    >
      Coming Soon
    </button>
  );
}

function SetupSteps() {
  return (
    <div className="mt-8 rounded-card border border-line bg-[#f8fafc] px-5 py-7 sm:px-8">
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
        className="mt-6 inline-flex h-11 w-full items-center justify-center gap-2 rounded-full bg-charcoal text-sm font-semibold text-white transition-colors hover:bg-charcoal/90 sm:w-auto sm:px-6"
      >
        <KeyRound size={16} aria-hidden="true" />
        Create an activation key
      </Link>
    </div>
  );
}

function PlatformIcon({ platform, prominent }: { platform: PlatformId; prominent?: boolean }) {
  const className = prominent
    ? "flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-accent text-white shadow-sm shadow-accent/30"
    : "flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-charcoal/5 text-charcoal/55";
  return (
    <span className={className}>
      {platform === "windows" ? <WindowsMark /> : platform === "android" ? <AndroidMark /> : <AppleMark />}
    </span>
  );
}

function WindowsMark() {
  return (
    <svg viewBox="0 0 24 24" width="26" height="26" aria-hidden="true" fill="currentColor">
      <path d="M3 5.1 10.5 4.1v7.2H3V5.1Zm8.3-1.1L21 2.4v8.9h-9.7V4Zm0 9.2H21v8.9l-9.7-1.4V13.2ZM3 12.7h7.5v7.2L3 18.7v-6Z" />
    </svg>
  );
}

function AndroidMark() {
  return (
    <svg viewBox="0 0 24 24" width="26" height="26" aria-hidden="true" fill="currentColor">
      <path d="M7.2 8.2h9.6a1 1 0 0 1 1 1V18a2 2 0 0 1-2 2h-1.1v1.2a1 1 0 1 1-2 0V20h-1.4v1.2a1 1 0 1 1-2 0V20H8.2a2 2 0 0 1-2-2V9.2a1 1 0 0 1 1-1Zm.3-2.5 1-1.6a.4.4 0 0 1 .7.4L8.3 5.8a6.2 6.2 0 0 1 7.4 0l-.9-1.3a.4.4 0 1 1 .7-.4l1 1.6A5.8 5.8 0 0 0 7.5 5.7ZM9 10.2a.8.8 0 1 0 0 1.6.8.8 0 0 0 0-1.6Zm6 0a.8.8 0 1 0 0 1.6.8.8 0 0 0 0-1.6Z" />
    </svg>
  );
}

function AppleMark() {
  return (
    <svg viewBox="0 0 24 24" width="26" height="26" aria-hidden="true" fill="currentColor">
      <path d="M16.4 12.6c0-2.2 1.8-3.2 1.9-3.3-1-1.5-2.6-1.7-3.2-1.7-1.3-.1-2.6.8-3.3.8s-1.7-.8-2.9-.7c-1.5.1-2.8.9-3.6 2.2-1.5 2.7-.4 6.6 1.1 8.8.7 1.1 1.6 2.3 2.7 2.2 1.1 0 1.5-.7 2.8-.7s1.7.7 2.9.7 1.9-1.1 2.6-2.2c.8-1.2 1.2-2.3 1.2-2.4-.1 0-2.2-.9-2.2-3.7ZM14.7 6.4c.6-.7 1-1.7.9-2.7-1 .1-2.1.6-2.8 1.4-.6.7-1.1 1.7-.9 2.6 1 .1 2.1-.5 2.8-1.3Z" />
    </svg>
  );
}
