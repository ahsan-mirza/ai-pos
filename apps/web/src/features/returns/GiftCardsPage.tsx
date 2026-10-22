import { Permission, formatMoney, type GiftCardIssue, type StoreCreditList, type StoreCreditVoucher } from "@ai-pos/shared-types";
import { Gift, Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { ErrorNote, GhostButton, PrimaryButton, SelectField, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { Toast } from "../../components/ui/Toast";
import { apiGet, apiPost } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useCurrency } from "../../lib/currency";
import { message, toCents } from "../customers/api";
import { storeOptions, useStores } from "../inventory/shared";

const filters = [
  { value: "open", label: "With balance" },
  { value: "all", label: "All" },
] as const;

const shortDate = (value: string) =>
  new Date(value).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });

function cardStatus(card: StoreCreditVoucher): { label: string; tone: string } {
  if (card.voided_at) return { label: "Voided", tone: "bg-gray-100 text-charcoal/50" };
  if (card.expires_at && new Date(card.expires_at).getTime() < Date.now()) {
    return { label: "Expired", tone: "bg-amber-100 text-amber-800" };
  }
  if (card.balance_cents === 0) return { label: "Spent", tone: "bg-gray-100 text-charcoal/50" };
  return { label: "Active", tone: "bg-emerald-100 text-emerald-800" };
}

/** Gift cards: sold at the till or issued here, owed as a liability (ledger 2410) until spent. */
export function GiftCardsPage() {
  const { user } = useAuth();
  const { currency } = useCurrency();
  const canManage = Boolean(user?.permissions.includes(Permission.GiftCardsManage));
  const [filter, setFilter] = useState<(typeof filters)[number]["value"]>("open");
  const [data, setData] = useState<StoreCreditList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [issuing, setIssuing] = useState(false);
  const [voiding, setVoiding] = useState<StoreCreditVoucher | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);

  const load = useCallback(async () => {
    try {
      setData(await apiGet<StoreCreditList>(`/api/v1/gift-cards?open_only=${filter === "open"}`));
      setError(null);
    } catch (caught) {
      setError(message(caught, "Could not load gift cards."));
    }
  }, [filter]);

  useEffect(() => {
    void load();
  }, [load]);

  const done = (text: string) => {
    setToast(text);
    setIssuing(false);
    setVoiding(null);
    void load();
  };

  const items = data?.items ?? [];
  const soldCents = items.filter((card) => card.issued_sale_id).reduce((sum, card) => sum + card.initial_cents, 0);

  return (
    <section className="space-y-4">
      <div className="grid gap-4 md:grid-cols-3">
        <article className="rounded-card bg-charcoal p-6 text-white">
          <p className="text-sm text-white/60">Outstanding gift cards</p>
          <p className="mt-4 text-3xl font-semibold tabular-nums">{data ? formatMoney(data.outstanding_cents, currency) : "—"}</p>
          <p className="mt-2 text-xs text-white/50">A liability until spent, not revenue (ledger 2410)</p>
        </article>
        <article className="rounded-card bg-accent p-6 text-white">
          <p className="text-sm text-white/80">Cards with a balance</p>
          <p className="mt-4 text-3xl font-semibold tabular-nums">{data?.open_count ?? "—"}</p>
          <p className="mt-2 text-xs text-white/80">Accepted at every branch</p>
        </article>
        <article className="rounded-card border border-line bg-white p-6">
          <p className="text-sm text-charcoal/60">Sold at the till (listed)</p>
          <p className="mt-4 text-3xl font-semibold tabular-nums">{data ? formatMoney(soldCents, currency) : "—"}</p>
          <p className="mt-2 text-xs text-charcoal/50">The rest were issued from the portal</p>
        </article>
      </div>

      <div className="rounded-card border border-line bg-white p-6">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold">Gift cards</h2>
            <p className="text-sm text-charcoal/60">
              Sold at the register or issued here for promotions and goodwill; customers spend them as a tender.
            </p>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <SegmentedControl label="Gift cards" value={filter} options={filters} onChange={setFilter} />
            {canManage ? (
              <PrimaryButton onClick={() => setIssuing(true)}>
                <Plus size={16} aria-hidden="true" className="-ml-1 mr-1.5" /> Issue cards
              </PrimaryButton>
            ) : null}
          </div>
        </div>
        <ErrorNote message={error} />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[860px] text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-charcoal/50">
              <tr>
                <th className="pb-3 font-medium">Card</th>
                <th className="pb-3 font-medium">Issued</th>
                <th className="pb-3 font-medium">Customer</th>
                <th className="pb-3 text-right font-medium">Value</th>
                <th className="pb-3 text-right font-medium">Balance</th>
                <th className="pb-3 pl-6 font-medium">Status</th>
                <th className="pb-3" />
              </tr>
            </thead>
            <tbody>
              {items.map((card) => {
                const status = cardStatus(card);
                return (
                  <tr key={card.id} className="border-t border-line align-top">
                    <td className="py-3">
                      <span className="block font-mono text-xs font-semibold">{card.code}</span>
                      <span className="block text-xs text-charcoal/50">
                        {card.issued_sale_id ? "Sold at the till" : card.note || "Issued in the portal"}
                      </span>
                    </td>
                    <td className="py-3">
                      <span className="block tabular-nums">{shortDate(card.issued_at)}</span>
                      <span className="block text-xs text-charcoal/50">{card.store_name}</span>
                    </td>
                    <td className="py-3 text-charcoal/70">{card.customer_name ?? "—"}</td>
                    <td className="py-3 text-right tabular-nums">{formatMoney(card.initial_cents, card.currency)}</td>
                    <td className={`py-3 text-right font-semibold tabular-nums ${card.usable ? "" : "text-charcoal/40"}`}>
                      {formatMoney(card.balance_cents, card.currency)}
                    </td>
                    <td className="py-3 pl-6">
                      <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${status.tone}`}>{status.label}</span>
                      <span className="mt-1 block text-xs text-charcoal/50">
                        {card.expires_at ? `Expires ${shortDate(card.expires_at)}` : "No expiry"}
                        {card.uses.length ? ` · used ${card.uses.length}×` : ""}
                      </span>
                    </td>
                    <td className="py-3 text-right">
                      {canManage && !card.voided_at && card.balance_cents > 0 ? (
                        <button
                          type="button"
                          onClick={() => setVoiding(card)}
                          className="text-xs font-semibold text-charcoal/60 hover:text-accent"
                        >
                          Void
                        </button>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {data !== null && items.length === 0 ? (
            <p className="flex items-center gap-2 py-8 text-sm text-charcoal/60">
              <Gift size={16} aria-hidden="true" /> No gift cards{filter === "open" ? " with a balance" : ""} yet. Sell one at the
              register or issue one here.
            </p>
          ) : null}
        </div>
      </div>

      {issuing ? <IssueDialog onClose={() => setIssuing(false)} onDone={done} /> : null}
      {voiding ? <VoidDialog card={voiding} onClose={() => setVoiding(null)} onDone={done} /> : null}
      {toast ? <Toast message={toast} onDismiss={dismissToast} /> : null}
    </section>
  );
}

function IssueDialog({ onClose, onDone }: { onClose: () => void; onDone: (text: string) => void }) {
  const { user } = useAuth();
  const { stores } = useStores();
  const [storeId, setStoreId] = useState(user?.store_id ?? "");
  const [amount, setAmount] = useState("");
  const [count, setCount] = useState("1");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!storeId && stores.length) setStoreId(stores.find((store) => !store.is_warehouse)?.id ?? stores[0]!.id);
  }, [storeId, stores]);

  const cents = toCents(amount);
  const quantity = Number(count);
  const valid = cents !== null && cents >= 100 && Number.isInteger(quantity) && quantity >= 1 && quantity <= 200 && note.trim().length >= 3;

  const submit = async () => {
    if (!valid || cents === null) return;
    setBusy(true);
    try {
      const body: GiftCardIssue = { store_id: storeId, amount_cents: cents, count: quantity, customer_id: null, note: note.trim() };
      const cards = await apiPost<StoreCreditVoucher[]>("/api/v1/gift-cards/issue", body);
      onDone(cards.length === 1 ? `Gift card ${cards[0]!.code} issued.` : `${cards.length} gift cards issued.`);
    } catch (caught) {
      setError(message(caught, "Could not issue the gift cards."));
      setBusy(false);
    }
  };

  return (
    <Modal
      title="Issue gift cards"
      subtitle="For promotions, goodwill or corporate orders. Each card gets its own code."
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={!valid || busy} onClick={() => void submit()}>
            {busy ? "Issuing…" : "Issue"}
          </PrimaryButton>
        </>
      }
    >
      <div className="space-y-4">
        {user?.store_id ? null : (
          <SelectField label="Issuing branch" value={storeId} options={storeOptions(stores)} onChange={setStoreId} />
        )}
        <div className="grid grid-cols-2 gap-3">
          <TextField label="Value per card" inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} />
          <TextField label="How many" type="number" min={1} max={200} value={count} onChange={(event) => setCount(event.target.value)} />
        </div>
        <TextField
          label="Reason"
          placeholder="e.g. Eid campaign prizes"
          value={note}
          onChange={(event) => setNote(event.target.value)}
          hint="Recorded in the audit trail."
        />
        <ErrorNote message={error} />
      </div>
    </Modal>
  );
}

function VoidDialog({
  card,
  onClose,
  onDone,
}: {
  card: StoreCreditVoucher;
  onClose: () => void;
  onDone: (text: string) => void;
}) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    try {
      await apiPost<StoreCreditVoucher>(`/api/v1/gift-cards/${encodeURIComponent(card.code)}/void`, { note: note.trim() });
      onDone(`Gift card ${card.code} voided.`);
    } catch (caught) {
      setError(message(caught, "Could not void the gift card."));
      setBusy(false);
    }
  };

  return (
    <Modal
      title={`Void ${card.code}`}
      subtitle={`The remaining ${formatMoney(card.balance_cents, card.currency)} can no longer be spent.`}
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Keep card</GhostButton>
          <PrimaryButton disabled={note.trim().length < 3 || busy} onClick={() => void submit()}>
            {busy ? "Voiding…" : "Void card"}
          </PrimaryButton>
        </>
      }
    >
      <TextField
        label="Reason"
        placeholder="e.g. Reported lost, reissued as GC-…"
        value={note}
        onChange={(event) => setNote(event.target.value)}
      />
      <ErrorNote message={error} />
    </Modal>
  );
}
