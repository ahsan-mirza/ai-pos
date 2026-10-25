import type { KitchenActionIn, KitchenBrief, KitchenCard, KitchenKind } from "@ai-pos/shared-types";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AiMark } from "../../components/ui/AiMark";
import { ErrorNote, PrimaryButton } from "../../components/ui/Field";
import { apiGet, apiPost } from "../../lib/api";
import { message } from "../customers/api";

const groups: { kind: KitchenKind; label: string }[] = [
  { kind: "order", label: "Order" },
  { kind: "use_first", label: "Use first" },
  { kind: "push_today", label: "Push today" },
  { kind: "write_off", label: "Write off" },
  { kind: "cannot_make", label: "Cannot make" },
  { kind: "prep", label: "Prep for the next service" },
  { kind: "transfer", label: "Move from another branch" },
  { kind: "waste", label: "Waste" },
  { kind: "margin", label: "Menu margin" },
  { kind: "overstock", label: "Too much perishable stock" },
];

const tone: Record<KitchenCard["severity"], string> = {
  high: "bg-danger/10 text-danger",
  medium: "bg-amber-100 text-amber-800",
  low: "bg-charcoal/5 text-charcoal/70",
};

function actionLabel(card: KitchenCard): string | null {
  if (card.action === "draft_purchase") return "Draft purchase order";
  if (card.action === "draft_transfer") return "Draft transfer";
  if (card.action === "write_off") return "Write off";
  return null;
}

/** Computed brief for a restaurant or cafe: what to order, use first, move, or take off the menu. */
export function KitchenAgentPage() {
  const [brief, setBrief] = useState<KitchenBrief | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setBrief(await apiGet<KitchenBrief>("/api/v1/kitchen-agent"));
      setError(null);
    } catch (caught) {
      setError(message(caught, "Could not load the kitchen brief."));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const accept = async (card: KitchenCard) => {
    if (!card.action) return;
    setBusy(card.id);
    setNotice(null);
    const body: KitchenActionIn = {
      action: card.action,
      product_id: card.product_id,
      store_id: card.store_id,
      source_store_id: card.source_store_id,
      quantity: card.quantity,
      batch_item_id: card.batch_item_id,
      supplier_name: card.supplier_name,
    };
    try {
      const result = await apiPost<{ reference: string }>("/api/v1/kitchen-agent/actions", body);
      setNotice(card.action === "write_off" ? "Written off." : `Draft ${result.reference} created.`);
      await load();
    } catch (caught) {
      setError(message(caught, "Could not complete that action."));
    } finally {
      setBusy(null);
    }
  };

  const cards = brief?.cards ?? [];

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 p-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-semibold text-charcoal">
          <AiMark size={20} /> Kitchen agent
        </h1>
        <p className="mt-1 text-sm text-charcoal/70">
          What to order, use first, move, or take off the menu. Figures come from stock, recipes, and batch expiry.
        </p>
      </div>
      {error ? <ErrorNote message={error} /> : null}
      {notice ? <p className="text-sm font-medium text-charcoal">{notice}</p> : null}
      {brief && cards.length === 0 ? (
        <p className="rounded-2xl border border-line p-6 text-sm text-charcoal/70">Nothing needs attention right now.</p>
      ) : null}
      {groups.map((group) => {
        const rows = cards.filter((card) => card.kind === group.kind);
        if (rows.length === 0) return null;
        return (
          <section key={group.kind} className="flex flex-col gap-3">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-charcoal/50">{group.label}</h2>
            {rows.map((card) => {
              const label = actionLabel(card);
              return (
                <article key={card.id} className="rounded-2xl border border-line bg-white p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="font-semibold text-charcoal">{card.title}</h3>
                        <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${tone[card.severity]}`}>
                          {card.severity}
                        </span>
                      </div>
                      <p className="mt-1 text-sm text-charcoal/70">{card.body}</p>
                    </div>
                    {label ? (
                      <PrimaryButton disabled={busy === card.id} onClick={() => void accept(card)}>
                        <span className="inline-flex items-center gap-1.5">
                          <AiMark size={14} className="text-white" />
                          {busy === card.id ? "Working…" : label}
                        </span>
                      </PrimaryButton>
                    ) : card.href ? (
                      <Link className="text-sm font-semibold text-accent" to={card.href}>
                        Open
                      </Link>
                    ) : null}
                  </div>
                </article>
              );
            })}
          </section>
        );
      })}
    </div>
  );
}
