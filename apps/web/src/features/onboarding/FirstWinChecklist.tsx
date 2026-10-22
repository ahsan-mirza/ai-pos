import type { ChecklistItem } from "@ai-pos/shared-types";
import { Check, ChevronDown, ChevronUp, Trophy } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useCanManageSettings } from "../../lib/currency";
import { CHECKLIST_OPEN_KEY } from "../signup/WelcomeHandoff";
import { usePractice } from "./practice";

function readOpen(): boolean {
  return sessionStorage.getItem(CHECKLIST_OPEN_KEY) !== "0";
}

function ItemRow({ item, onGoLive }: { item: ChecklistItem; onGoLive: () => void }) {
  const marker = (
    <span
      className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 ${
        item.done ? "border-emerald-600 bg-emerald-600 text-white" : "border-charcoal/20"
      }`}
      aria-hidden="true"
    >
      {item.done ? <Check size={12} /> : null}
    </span>
  );
  const body = (
    <span className="min-w-0">
      <span className={`block text-sm font-medium ${item.done ? "text-charcoal/50 line-through" : ""}`}>
        {item.label}
      </span>
      {item.done ? null : <span className="block text-xs text-charcoal/60">{item.hint}</span>}
    </span>
  );
  const className = "flex w-full gap-3 rounded-xl px-2 py-2 text-left hover:bg-surface";
  if (item.href === "#go-live") {
    return (
      <button type="button" onClick={onGoLive} className={className}>
        {marker}
        {body}
      </button>
    );
  }
  return (
    <Link to={item.href} className={className}>
      {marker}
      {body}
    </Link>
  );
}

/** "First win" checklist: floats bottom right for business-wide admins while the store is in practice mode. */
export function FirstWinChecklist() {
  const { practice, checklist, openGoLive } = usePractice();
  const canManage = useCanManageSettings();
  const [open, setOpen] = useState(readOpen);

  if (!practice || !canManage || checklist === null) return null;

  const done = checklist.items.filter((item) => item.done).length;
  const total = checklist.items.length;
  const toggle = () => {
    sessionStorage.setItem(CHECKLIST_OPEN_KEY, open ? "0" : "1");
    setOpen(!open);
  };

  return (
    <section
      aria-label="Getting started"
      className="fixed bottom-4 right-4 z-40 w-[min(340px,calc(100vw-2rem))] overflow-hidden rounded-3xl border border-line bg-white shadow-2xl"
    >
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        className="flex w-full items-center gap-3 bg-charcoal px-4 py-3 text-left text-white"
      >
        <Trophy size={18} aria-hidden="true" className="shrink-0 text-accent" />
        <span className="flex-1">
          <span className="block text-sm font-semibold">Your first win</span>
          <span className="block text-xs text-white/60">
            {done} of {total} done
          </span>
        </span>
        {open ? <ChevronDown size={18} aria-hidden="true" /> : <ChevronUp size={18} aria-hidden="true" />}
      </button>
      <div className="h-1 bg-charcoal/10" aria-hidden="true">
        <div className="h-full bg-accent transition-all" style={{ width: `${Math.round((done / total) * 100)}%` }} />
      </div>
      {open ? (
        <ul className="max-h-[60vh] space-y-0.5 overflow-y-auto p-2">
          {checklist.items.map((item) => (
            <li key={item.key}>
              <ItemRow item={item} onGoLive={openGoLive} />
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
