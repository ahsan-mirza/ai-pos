import type { ChecklistItem } from "@ai-pos/shared-types";
import { Check, ChevronDown, ChevronUp, Trophy } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { apiPost } from "../../lib/api";
import { useCanManageSettings } from "../../lib/currency";
import { CHECKLIST_OPEN_KEY } from "../signup/WelcomeHandoff";
import { usePractice } from "./practice";

function readOpen(): boolean {
  return sessionStorage.getItem(CHECKLIST_OPEN_KEY) !== "0";
}

function StepRow({
  item,
  index,
  next,
  onGoLive,
  onSkip,
}: {
  item: ChecklistItem;
  index: number;
  next: boolean;
  onGoLive: () => void;
  onSkip: () => void;
}) {
  const marker = (
    <span
      className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border-2 text-xs font-semibold ${
        item.done ? "border-emerald-600 bg-emerald-600 text-white" : "border-charcoal/20 text-charcoal/50"
      }`}
      aria-hidden="true"
    >
      {item.done ? <Check size={12} /> : index + 1}
    </span>
  );
  const title = (
    <span className={`block text-sm font-medium ${item.done ? "text-charcoal/50 line-through" : ""}`}>{item.label}</span>
  );
  return (
    <li className={`rounded-xl px-2 py-2 ${next ? "bg-surface" : ""}`}>
      <div className="flex gap-3">
        {marker}
        <div className="min-w-0 flex-1">
          {title}
          {item.done ? null : <p className="mt-0.5 text-xs text-charcoal/60">{item.hint}</p>}
          {item.blocked ? <p className="mt-1 text-xs font-medium text-danger">{item.blocked}</p> : null}
          {item.done ? null : (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              {item.href === "#go-live" ? (
                <button
                  type="button"
                  onClick={onGoLive}
                  className={
                    next
                      ? "rounded-full bg-accent px-3 py-1 text-xs font-semibold text-white hover:bg-accent-hover"
                      : "text-xs font-semibold text-accent hover:underline"
                  }
                >
                  {item.action}
                </button>
              ) : (
                <Link
                  to={item.href}
                  className={
                    next
                      ? "rounded-full bg-accent px-3 py-1 text-xs font-semibold text-white hover:bg-accent-hover"
                      : "text-xs font-semibold text-accent hover:underline"
                  }
                >
                  {item.action}
                </Link>
              )}
              {item.secondary_href && item.secondary_label ? (
                <Link to={item.secondary_href} className="text-xs font-semibold text-charcoal/70 hover:underline">
                  {item.secondary_label}
                </Link>
              ) : null}
              {item.skippable ? (
                <button type="button" onClick={onSkip} className="text-xs text-charcoal/50 hover:text-charcoal hover:underline">
                  Skip inviting staff
                </button>
              ) : null}
              {item.skipped ? <span className="text-xs text-charcoal/50">Invite skipped</span> : null}
            </div>
          )}
        </div>
      </div>
    </li>
  );
}

/** Guided trial: floats bottom right for business-wide admins while the store is in practice mode. */
export function FirstWinChecklist() {
  const { practice, checklist, openGoLive, refresh } = usePractice();
  const canManage = useCanManageSettings();
  const [open, setOpen] = useState(readOpen);

  if (!practice || !canManage || checklist === null) return null;

  const done = checklist.items.filter((item) => item.done).length;
  const total = checklist.items.length;
  const next = checklist.items.find((item) => item.key === checklist.next_key) ?? null;
  const percent = total === 0 ? 0 : Math.round((done / total) * 100);
  const toggle = () => {
    sessionStorage.setItem(CHECKLIST_OPEN_KEY, open ? "0" : "1");
    setOpen(!open);
  };
  const skipInvite = () => {
    void apiPost("/api/v1/onboarding/skip", { key: "invite" }).then(() => refresh());
  };

  return (
    <section
      aria-label="Get your store ready"
      className="fixed bottom-4 right-4 z-40 w-[min(400px,calc(100vw-2rem))] overflow-hidden rounded-3xl border border-line bg-white shadow-2xl"
    >
      <div className="flex items-start gap-2 bg-charcoal px-4 py-3 text-white">
        <Trophy size={18} aria-hidden="true" className="mt-0.5 shrink-0 text-accent" />
        <button type="button" onClick={toggle} aria-expanded={open} className="min-w-0 flex-1 text-left">
          <span className="block text-sm font-semibold">Get your store ready</span>
          <span className="mt-0.5 block text-xs text-white/70">
            Explore AxizPOS, set up your business, and activate live operations when you're ready.
          </span>
          <span className="mt-1 block text-xs text-white/60">
            {done} of {total} steps completed
            {next ? ` · Next: ${next.label}` : ""}
          </span>
        </button>
        {next ? (
          next.href === "#go-live" ? (
            <button
              type="button"
              onClick={openGoLive}
              className="mt-0.5 shrink-0 rounded-full bg-accent px-3 py-1 text-xs font-semibold text-white hover:bg-accent-hover"
            >
              {next.action}
            </button>
          ) : (
            <Link
              to={next.href}
              className="mt-0.5 shrink-0 rounded-full bg-accent px-3 py-1 text-xs font-semibold text-white hover:bg-accent-hover"
            >
              {next.action}
            </Link>
          )
        ) : null}
        <button
          type="button"
          onClick={toggle}
          aria-label={open ? "Collapse setup guide" : "Expand setup guide"}
          className="rounded-full p-1 text-white/80 hover:bg-white/10 hover:text-white"
        >
          {open ? <ChevronDown size={18} aria-hidden="true" /> : <ChevronUp size={18} aria-hidden="true" />}
        </button>
      </div>
      <div
        className="h-1 bg-charcoal/10"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={done}
        aria-label="Setup progress"
      >
        <div className="h-full bg-accent transition-all" style={{ width: `${percent}%` }} />
      </div>
      {open ? (
        <ol className="max-h-[60vh] space-y-0.5 overflow-y-auto p-2">
          {checklist.items.map((item, index) => (
            <StepRow
              key={item.key}
              item={item}
              index={index}
              next={item.key === checklist.next_key}
              onGoLive={openGoLive}
              onSkip={skipInvite}
            />
          ))}
        </ol>
      ) : null}
    </section>
  );
}
