import { formatDateTime, useLocale } from "@ai-pos/ui";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiRequestError, apiBlob, apiGet, apiPost } from "../../../apps/web/src/lib/api";

export interface CampaignRun {
  id: string;
  campaign_id: string;
  campaign_name: string;
  run_number: number;
  status: string;
  phase?: string;
  channel: string;
  eligible_recipients: number;
  excluded_recipients: number;
  queued_count: number;
  processing_count: number;
  accepted_count: number;
  delivered_count: number;
  read_count: number;
  failed_count: number;
  skipped_count: number;
  cancelled_count: number;
  remaining: number;
  progress_percent: number;
  initiated_by: string | null;
  started_at: string | null;
  completed_at: string | null;
  report_built_at: string | null;
  delivery_updated_at: string | null;
  updated_at: string | null;
}

const HIDDEN_KEY = "axiz.reach.progress.hidden";

function phaseLabel(phase: string | undefined, t: (text: string) => string): string {
  if (phase === "preparing") return t("Preparing audience");
  if (phase === "sending") return t("Sending messages");
  if (phase === "waiting_for_delivery") return t("Waiting for delivery confirmations");
  if (phase === "partially_completed") return t("Partially completed");
  if (phase === "cancelled") return t("Cancelled");
  if (phase === "failed") return t("Failed");
  if (phase === "completed") return t("Completed");
  return phase || "";
}

async function downloadRun(runId: string, kind: "pdf" | "csv") {
  const path =
    kind === "pdf"
      ? `/api/v1/reach/campaign-runs/${runId}/report.pdf`
      : `/api/v1/reach/campaign-runs/${runId}/recipients.csv`;
  const blob = await apiBlob(path);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = kind === "pdf" ? "campaign-run.pdf" : "campaign-recipients.csv";
  link.click();
  URL.revokeObjectURL(url);
}

export function CampaignProgress() {
  const { t } = useLocale();
  const [runs, setRuns] = useState<CampaignRun[]>([]);
  const [hidden, setHidden] = useState(() => localStorage.getItem(HIDDEN_KEY) === "1");
  const [minimized, setMinimized] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);
  const [allowed, setAllowed] = useState(true);

  useEffect(() => {
    if (!allowed) return;
    let timer = 0;
    let wait = 4000;
    let stopped = false;

    const tick = async () => {
      try {
        const body = await apiGet<{ rows: CampaignRun[] }>("/api/v1/reach/campaign-runs/active");
        if (stopped) return;
        setRuns(body.rows);
        wait = body.rows.length ? 4000 : 15000;
      } catch (caught) {
        if (caught instanceof ApiRequestError && (caught.status === 403 || caught.status === 404)) {
          setAllowed(false);
          return;
        }
        wait = Math.min(wait * 2, 30000);
      }
      if (!stopped) timer = window.setTimeout(() => void tick(), wait);
    };

    void tick();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [allowed]);

  if (!allowed || runs.length === 0) return null;

  const hide = () => {
    localStorage.setItem(HIDDEN_KEY, "1");
    setHidden(true);
  };

  if (hidden) {
    return (
      <button
        type="button"
        className="fixed bottom-4 end-4 z-40 rounded-full bg-accent px-4 py-2 text-sm font-semibold text-white shadow-lg"
        onClick={() => {
          localStorage.setItem(HIDDEN_KEY, "0");
          setHidden(false);
        }}
      >
        {t("Campaigns")} ({runs.length})
      </button>
    );
  }

  return (
    <aside
      className="fixed bottom-4 end-4 z-40 w-[min(100vw-2rem,22rem)] rounded-2xl border border-line bg-white text-charcoal shadow-lg dark:border-zinc-700 dark:bg-zinc-900 dark:text-white"
      aria-label={t("Campaign progress")}
    >
      <div className="flex items-center justify-between gap-2 border-b border-line px-3 py-2 dark:border-zinc-700">
        <p className="text-sm font-semibold">{t("Campaign progress")}</p>
        <div className="flex gap-2 text-xs font-semibold text-accent">
          <button type="button" onClick={() => setMinimized((value) => !value)}>
            {minimized ? t("Expand") : t("Minimize")}
          </button>
          <button type="button" onClick={hide}>
            {t("Hide")}
          </button>
        </div>
      </div>
      {minimized ? null : (
        <ul className="max-h-80 space-y-2 overflow-y-auto p-3">
          {runs.map((run) => (
            <li key={run.id} className="rounded-xl bg-zinc-50 p-2 dark:bg-zinc-800">
              <button type="button" className="w-full text-start" onClick={() => setOpenId(openId === run.id ? null : run.id)}>
                <span className="block text-sm font-semibold">{run.campaign_name}</span>
                <span className="text-xs text-charcoal/60 dark:text-white/60">
                  {t("Run")} {run.run_number} · {run.channel} · {phaseLabel(run.phase, t)}
                </span>
                <span className="mt-1 block h-1.5 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-700">
                  <span className="block h-full bg-accent" style={{ width: `${Math.min(run.progress_percent, 100)}%` }} />
                </span>
              </button>
              {openId === run.id ? <RunFigures run={run} /> : null}
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}

function RunFigures({ run }: { run: CampaignRun }) {
  const { t } = useLocale();
  const when = run.updated_at ? formatDateTime(run.updated_at) : "";
  return (
    <div className="mt-2 space-y-1 text-xs">
      <p>{t("Queued")}: {run.queued_count}</p>
      <p>{t("Processing")}: {run.processing_count}</p>
      <p>{t("Accepted by provider")}: {run.accepted_count}</p>
      <p>{t("Delivered")}: {run.delivered_count}</p>
      <p>{t("Read")}: {run.read_count}</p>
      <p>{t("Failed")}: {run.failed_count}</p>
      <p>{t("Skipped")}: {run.skipped_count}</p>
      <p>{t("Cancelled")}: {run.cancelled_count}</p>
      <p>{t("Remaining")}: {run.remaining}</p>
      <p className="text-charcoal/50 dark:text-white/50">{when}</p>
      <p className="flex gap-3 font-semibold text-accent">
        <Link to={`/reach?tab=campaigns&run=${run.id}`}>{t("View details")}</Link>
        <button type="button" onClick={() => void downloadRun(run.id, "pdf")}>
          {t("Report")}
        </button>
      </p>
    </div>
  );
}

export function CampaignRunHistory({ focus }: { focus: string | null }) {
  const { t } = useLocale();
  const [runs, setRuns] = useState<CampaignRun[]>([]);
  const [detail, setDetail] = useState<CampaignRun | null>(null);
  const [people, setPeople] = useState<{ customer: string; contact: string; status: string; failure_reason: string | null }[]>([]);

  useEffect(() => {
    void apiGet<{ rows: CampaignRun[] }>("/api/v1/reach/campaign-runs?limit=50").then((body) => setRuns(body.rows)).catch(() => setRuns([]));
  }, [focus]);

  useEffect(() => {
    if (!focus) return;
    void apiGet<CampaignRun>(`/api/v1/reach/campaign-runs/${focus}`).then(setDetail).catch(() => setDetail(null));
    void apiGet<{ rows: { customer: string; contact: string; status: string; failure_reason: string | null }[] }>(
      `/api/v1/reach/campaign-runs/${focus}/recipients`,
    )
      .then((body) => setPeople(body.rows))
      .catch(() => setPeople([]));
  }, [focus]);

  return (
    <section className="rounded-card border border-line bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <h2 className="text-sm font-semibold">{t("Campaign history")}</h2>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-start text-sm">
          <thead className="text-xs uppercase text-charcoal/50">
            <tr>
              <th className="py-2 pe-3">{t("Campaign")}</th>
              <th className="py-2 pe-3">{t("Run")}</th>
              <th className="py-2 pe-3">{t("Channel")}</th>
              <th className="py-2 pe-3">{t("Status")}</th>
              <th className="py-2 pe-3">{t("Accepted by provider")}</th>
              <th className="py-2 pe-3">{t("Delivered")}</th>
              <th className="py-2">{t("Report")}</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.id} className="border-t border-line">
                <td className="py-2 pe-3">{run.campaign_name}</td>
                <td className="py-2 pe-3">{run.run_number}</td>
                <td className="py-2 pe-3">{run.channel}</td>
                <td className="py-2 pe-3">{run.status}</td>
                <td className="py-2 pe-3">{run.accepted_count}</td>
                <td className="py-2 pe-3">{run.delivered_count}</td>
                <td className="py-2">
                  <button type="button" className="font-semibold text-accent" onClick={() => void downloadRun(run.id, "pdf")}>
                    PDF
                  </button>
                  {" · "}
                  <button type="button" className="font-semibold text-accent" onClick={() => void downloadRun(run.id, "csv")}>
                    CSV
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {detail ? (
        <div className="mt-4 text-sm">
          <p className="font-semibold">
            {detail.campaign_name} · {t("Run")} {detail.run_number}
          </p>
          <p>
            {t("Started")}: {detail.started_at ? formatDateTime(detail.started_at) : "—"}
          </p>
          <p>
            {t("Eligible")}: {detail.eligible_recipients}. {t("Excluded")}: {detail.excluded_recipients}.
          </p>
          <button
            type="button"
            className="mt-2 text-sm font-semibold text-accent"
            onClick={() => void apiPost(`/api/v1/reach/campaign-runs/${detail.id}/cancel`, {})}
          >
            {t("Cancel remaining")}
          </button>
          <ul className="mt-2 space-y-1">
            {people.map((person) => (
              <li key={`${person.customer}-${person.contact}`}>
                {person.customer} · {person.contact} · {person.status}
                {person.failure_reason ? ` · ${person.failure_reason}` : ""}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
