import type { PaymentIntentStatus, PaymentMethod, SaleTender } from "@ai-pos/shared-types";
import type { RegisterCustomer } from "../../lib/tauri";
import { foreignValue } from "./fx";

export type TenderChoice = "cash" | "card" | "transfer" | "cheque" | "qr" | "bnpl" | "on_account" | "split" | "channel";

/** One guest's part of a split bill, collected guest by guest; each becomes its own tender. */
export interface GuestShare {
  method: "cash" | "card";
  amount: string;
  paid: boolean;
}

/** A sale carries at most 12 tenders, so a bill splits between at most 12 guests. */
export const MAX_GUESTS = 12;

/** Equal shares that add up to the total exactly; the odd cents go to the first guests. */
export function equalShares(totalCents: number, guests: number): number[] {
  const count = Math.max(1, Math.min(MAX_GUESTS, Math.floor(guests)));
  const base = Math.floor(totalCents / count);
  const extra = totalCents - base * count;
  return Array.from({ length: count }, (_, index) => base + (index < extra ? 1 : 0));
}

export function splitEqually(totalCents: number, guests: number, method: GuestShare["method"] = "card"): GuestShare[] {
  return equalShares(totalCents, guests).map((cents) => ({ method, amount: (cents / 100).toFixed(2), paid: false }));
}

export interface QrIntentDraft {
  id: string;
  amountCents: number;
  payload: string;
  status: "PENDING" | "PAID" | "EXPIRED" | "CANCELLED";
}
export type DepositMethod = "cash" | "card" | "transfer";

/** A card-terminal or pay-later payment the server is collecting; Charge unlocks once it is PAID. */
export interface ProviderIntentDraft {
  id: string;
  amountCents: number;
  status: PaymentIntentStatus;
  provider: string;
  simulated: boolean;
  customerUrl?: string | null;
  authCode?: string | null;
  cardLabel?: string | null;
  failure?: string | null;
}

/** A manager allowed a card taken on the standalone machine although the store's terminal is integrated. */
export interface ManualCardApproval {
  approvedById: string;
  approverName: string;
  note: string;
}

export interface PaymentDraft {
  choice: TenderChoice;
  /** Cash handed over, as typed. Only used for the change calculation. */
  cashReceived: string;
  /** Transfer reference, or the cheque number for cheque tenders. */
  reference: string;
  /** Deposit taken now on an on-account sale, as typed. */
  deposit: string;
  depositMethod: DepositMethod;
  chequeBank: string;
  /** yyyy-mm-dd written on the cheque; later than today makes it a post-dated cheque. */
  chequeDate: string;
  /** The QR payment shown to the customer; Charge unlocks once the server reports it paid. */
  qrIntent?: QrIntentDraft | null;
  /** Cash in a foreign currency: code and the rate in force when it was chosen. Change is given in business currency. */
  cashCurrency?: { code: string; rateMicros: number } | null;
  /** Loyalty points spent on this sale and their value; the chosen tender pays the rest. */
  loyalty?: { points: number; valueCents: number } | null;
  /** A store-credit voucher checked online; it pays up to its balance and the chosen tender pays the rest. */
  storeCredit?: { code: string; balanceCents: number } | null;
  /** A gift card checked online; it pays up to its balance and the chosen tender pays the rest. */
  giftCard?: { code: string; balanceCents: number } | null;
  /** A device the customer traded in for credit on this sale; its full value must be spent here. */
  tradeIn?: { id: string; number: string; amountCents: number } | null;
  /** Split between guests (equal or custom amounts), when the choice is "split". */
  guests?: GuestShare[] | null;
  /** The store's card terminal is integrated: card amounts are sent to it (or a manager approves a manual entry). */
  cardTerminal?: boolean;
  cardIntent?: ProviderIntentDraft | null;
  cardManual?: ManualCardApproval | null;
  bnplIntent?: ProviderIntentDraft | null;
}

export const emptyPayment: PaymentDraft = {
  choice: "cash",
  cashReceived: "",
  reference: "",
  deposit: "",
  depositMethod: "cash",
  chequeBank: "",
  chequeDate: "",
  qrIntent: null,
};

export const tenderOptions: { value: TenderChoice; label: string }[] = [
  { value: "cash", label: "Cash" },
  { value: "card", label: "Card" },
  { value: "transfer", label: "Bank transfer" },
  { value: "cheque", label: "Cheque / PDC" },
  { value: "qr", label: "QR payment" },
  { value: "bnpl", label: "Pay later (Tabby, Tamara)" },
  { value: "on_account", label: "On Account" },
  { value: "split", label: "Split between guests" },
  { value: "channel", label: "Paid on the delivery app" },
];

/** Banknote amounts a cashier is likely to be handed: the total rounded up to 5, 10, 50 and 100, at most three. */
export function quickCashAmounts(totalCents: number): number[] {
  if (totalCents <= 0) return [];
  const amounts = new Set<number>();
  for (const step of [500, 1000, 5000, 10000]) {
    const rounded = Math.ceil(totalCents / step) * step;
    if (rounded > totalCents) amounts.add(rounded);
  }
  return [...amounts].sort((left, right) => left - right).slice(0, 3);
}

export function parseCents(value: string): number | null {
  const trimmed = value.trim().replace(/,/g, "");
  if (trimmed === "") return null;
  if (!/^\d+(\.\d{1,2})?$/.test(trimmed)) return null;
  return Math.round(Number(trimmed) * 100);
}

export interface TenderPlan {
  paymentMethod: PaymentMethod;
  tenders: SaleTender[];
  paidCents: number;
  onAccountCents: number;
  changeCents: number | null;
  /** Why Charge is disabled; null when the plan is complete. */
  blocker: string | null;
  /** The account balance after this sale would exceed the limit; Charge needs a manager. */
  overLimitCents: number;
  /** The account is on credit hold; an on-account sale needs a manager. */
  holdReason: string | null;
  /** Loyalty points redeemed by this plan (0 when none). */
  loyaltyPoints?: number;
}

export function planTenders(draft: PaymentDraft, totalCents: number, customer: RegisterCustomer | null): TenderPlan {
  const loyalty = draft.loyalty ?? null;
  if (loyalty !== null && loyalty.points > 0 && customer !== null) {
    const value = Math.min(loyalty.valueCents, totalCents);
    const rest = planTenders({ ...draft, loyalty: null }, totalCents - value, customer);
    const loyaltyTender: SaleTender = { method: "loyalty", amount_cents: value, reference: `${loyalty.points} pts` };
    return {
      ...rest,
      paymentMethod: totalCents - value > 0 ? rest.paymentMethod : "loyalty",
      tenders: [loyaltyTender, ...rest.tenders],
      paidCents: rest.paidCents + value,
      blocker: totalCents - value > 0 ? rest.blocker : null,
      loyaltyPoints: loyalty.points,
    };
  }
  const tradeIn = draft.tradeIn ?? null;
  if (tradeIn !== null) {
    const rest = planTenders({ ...draft, tradeIn: null }, Math.max(0, totalCents - tradeIn.amountCents), customer);
    const tradeTender: SaleTender = {
      method: "trade_in",
      amount_cents: tradeIn.amountCents,
      reference: tradeIn.number,
      trade_in_id: tradeIn.id,
    };
    const covered = tradeIn.amountCents >= totalCents;
    return {
      ...rest,
      paymentMethod: covered ? "trade_in" : rest.paymentMethod,
      tenders: [tradeTender, ...rest.tenders],
      paidCents: rest.paidCents + tradeIn.amountCents,
      blocker:
        tradeIn.amountCents > totalCents
          ? "The trade-in is worth more than the sale. Add items, or pay the customer the difference as store credit instead."
          : covered
            ? null
            : rest.blocker,
    };
  }
  const giftCard = draft.giftCard ?? null;
  if (giftCard !== null && giftCard.balanceCents > 0 && totalCents > 0) {
    const value = Math.min(giftCard.balanceCents, totalCents);
    const rest = planTenders({ ...draft, giftCard: null }, totalCents - value, customer);
    const cardTender: SaleTender = {
      method: "gift_card",
      amount_cents: value,
      reference: giftCard.code,
      gift_card_code: giftCard.code,
    };
    return {
      ...rest,
      paymentMethod: totalCents - value > 0 ? rest.paymentMethod : "gift_card",
      tenders: [cardTender, ...rest.tenders],
      paidCents: rest.paidCents + value,
      blocker: totalCents - value > 0 ? rest.blocker : null,
    };
  }
  const voucher = draft.storeCredit ?? null;
  if (voucher !== null && voucher.balanceCents > 0 && totalCents > 0) {
    const value = Math.min(voucher.balanceCents, totalCents);
    const rest = planWithoutCredits(draft, totalCents - value, customer);
    const creditTender: SaleTender = {
      method: "store_credit",
      amount_cents: value,
      reference: voucher.code,
      store_credit_code: voucher.code,
    };
    return {
      ...rest,
      paymentMethod: totalCents - value > 0 ? rest.paymentMethod : "store_credit",
      tenders: [creditTender, ...rest.tenders],
      paidCents: rest.paidCents + value,
      blocker: totalCents - value > 0 ? rest.blocker : null,
    };
  }
  return planWithoutCredits(draft, totalCents, customer);
}

function planWithoutCredits(draft: PaymentDraft, totalCents: number, customer: RegisterCustomer | null): TenderPlan {
  const base = {
    paidCents: totalCents,
    onAccountCents: 0,
    changeCents: null,
    blocker: null,
    overLimitCents: 0,
    holdReason: null,
  };
  if (totalCents === 0) {
    return { ...base, paymentMethod: draft.choice === "on_account" || draft.choice === "split" ? "cash" : draft.choice, tenders: [] };
  }
  switch (draft.choice) {
    case "channel":
      return {
        ...base,
        paymentMethod: "channel",
        tenders: [{ method: "channel", amount_cents: totalCents, reference: draft.reference.trim() }],
      };
    case "split": {
      const guests = draft.guests ?? [];
      const amounts = guests.map((guest) => parseCents(guest.amount));
      const tenders: SaleTender[] = guests.flatMap((guest, index) =>
        (amounts[index] ?? 0) > 0 ? [{ method: guest.method, amount_cents: amounts[index]!, reference: `Guest ${index + 1}` }] : [],
      );
      const sum = amounts.reduce<number>((total, cents) => total + (cents ?? 0), 0);
      const unpaid = guests.findIndex((guest) => !guest.paid);
      const blocker =
        guests.length < 2
          ? "Split between at least two guests."
          : guests.length > MAX_GUESTS
            ? `A bill splits between at most ${MAX_GUESTS} guests.`
            : amounts.some((cents) => cents === null)
              ? "Enter every guest's share."
              : sum !== totalCents
                ? "The guests' shares must add up to the amount due."
                : unpaid >= 0
                  ? `Collect guest ${unpaid + 1}'s share.`
                  : null;
      return { ...base, paymentMethod: tenders[0]?.method ?? "card", tenders, blocker };
    }
    case "cash": {
      const foreign = draft.cashCurrency ?? null;
      if (foreign !== null) {
        const receivedForeign = parseCents(draft.cashReceived);
        const value = receivedForeign === null ? null : foreignValue(receivedForeign, foreign.rateMicros);
        const change = value === null ? null : value - totalCents;
        return {
          ...base,
          paymentMethod: "cash",
          tenders:
            receivedForeign !== null && change !== null && change >= 0
              ? [
                  {
                    method: "cash",
                    amount_cents: totalCents,
                    reference: "",
                    currency: foreign.code,
                    foreign_amount_cents: receivedForeign,
                    rate_micros: foreign.rateMicros,
                    change_cents: change,
                  },
                ]
              : [],
          changeCents: change,
          blocker: change === null || change < 0 ? `Enter the ${foreign.code} received.` : null,
        };
      }
      const received = parseCents(draft.cashReceived);
      const change = received === null ? null : received - totalCents;
      return {
        ...base,
        paymentMethod: "cash",
        tenders: [{ method: "cash", amount_cents: totalCents, reference: "" }],
        changeCents: change,
        blocker: change === null || change < 0 ? "Enter the cash received." : null,
      };
    }
    case "card": {
      const manual = draft.cardManual ?? null;
      if (!draft.cardTerminal || manual !== null) {
        const tender: SaleTender = { method: "card", amount_cents: totalCents, reference: manual ? "Manual entry" : "" };
        if (manual !== null && draft.cardTerminal) {
          tender.manual_override = { approved_by_id: manual.approvedById, note: manual.note };
        }
        return { ...base, paymentMethod: "card", tenders: [tender] };
      }
      const intent = draft.cardIntent ?? null;
      if (intent === null || intent.status !== "PAID") {
        return {
          ...base,
          paymentMethod: "card",
          tenders: [],
          blocker:
            intent === null || intent.status === "DECLINED" || intent.status === "EXPIRED" || intent.status === "CANCELLED"
              ? "Send the amount to the card terminal."
              : "Waiting for the card terminal.",
        };
      }
      if (intent.amountCents !== totalCents) {
        return { ...base, paymentMethod: "card", tenders: [], blocker: "The total changed after the card was approved." };
      }
      return {
        ...base,
        paymentMethod: "card",
        tenders: [
          {
            method: "card",
            amount_cents: totalCents,
            reference: (intent.cardLabel ?? intent.authCode ?? intent.id.slice(0, 8)).slice(0, 64),
            payment_intent_id: intent.id,
          },
        ],
      };
    }
    case "bnpl": {
      const intent = draft.bnplIntent ?? null;
      if (intent === null || intent.status !== "PAID") {
        return {
          ...base,
          paymentMethod: "bnpl",
          tenders: [],
          blocker: intent === null ? "Start the pay-later checkout on the customer's phone." : "Waiting for the customer to finish the pay-later checkout.",
        };
      }
      if (intent.amountCents !== totalCents) {
        return { ...base, paymentMethod: "bnpl", tenders: [], blocker: "The total changed after the pay-later plan was approved." };
      }
      return {
        ...base,
        paymentMethod: "bnpl",
        tenders: [{ method: "bnpl", amount_cents: totalCents, reference: intent.provider, payment_intent_id: intent.id }],
      };
    }
    case "transfer":
      return {
        ...base,
        paymentMethod: "transfer",
        tenders: [{ method: "transfer", amount_cents: totalCents, reference: draft.reference.trim() }],
        blocker: draft.reference.trim() === "" ? "Enter the transfer reference." : null,
      };
    case "qr": {
      const intent = draft.qrIntent ?? null;
      if (intent === null || intent.status !== "PAID") {
        return {
          ...base,
          paymentMethod: "qr",
          tenders: [],
          blocker: intent === null ? "Show the QR code to the customer." : "Waiting for the customer to pay by QR.",
        };
      }
      if (intent.amountCents !== totalCents) {
        return { ...base, paymentMethod: "qr", tenders: [], blocker: "The total changed after the QR was paid." };
      }
      return {
        ...base,
        paymentMethod: "qr",
        tenders: [{ method: "qr", amount_cents: totalCents, reference: intent.id.slice(0, 8), payment_intent_id: intent.id }],
      };
    }
    case "cheque": {
      const number = draft.reference.trim();
      const bank = draft.chequeBank.trim();
      const dated = /^\d{4}-\d{2}-\d{2}$/.test(draft.chequeDate) ? draft.chequeDate : "";
      return {
        ...base,
        paymentMethod: "cheque",
        tenders: [
          {
            method: "cheque",
            amount_cents: totalCents,
            reference: number,
            cheque: { cheque_number: number, bank, cheque_date: dated },
          },
        ],
        blocker: number === "" || bank === "" || dated === "" ? "Enter the cheque number, bank and date." : null,
      };
    }
    case "on_account": {
      if (customer === null || customer.customer_type !== "WHOLESALE") {
        return {
          ...base,
          paymentMethod: "on_account",
          tenders: [],
          blocker: "Attach a wholesale customer to sell on account.",
        };
      }
      const typed = draft.deposit.trim() === "" ? 0 : parseCents(draft.deposit);
      if (typed === null || typed > totalCents) {
        return { ...base, paymentMethod: "on_account", tenders: [], blocker: "The deposit cannot exceed the total." };
      }
      const onAccount = totalCents - typed;
      const tenders: SaleTender[] = [];
      if (typed > 0) {
        tenders.push({
          method: draft.depositMethod,
          amount_cents: typed,
          reference: draft.depositMethod === "transfer" ? draft.reference.trim() : "",
        });
      }
      if (onAccount > 0) tenders.push({ method: "on_account", amount_cents: onAccount, reference: "" });
      const projected = customer.current_balance_cents + onAccount;
      return {
        paymentMethod: onAccount > 0 ? "on_account" : draft.depositMethod,
        tenders,
        paidCents: typed,
        onAccountCents: onAccount,
        changeCents: null,
        blocker:
          typed > 0 && draft.depositMethod === "transfer" && draft.reference.trim() === ""
            ? "Enter the deposit's cheque or transfer reference."
            : null,
        overLimitCents: Math.max(0, projected - customer.credit_limit_cents),
        holdReason: onAccount > 0 && customer.credit_hold ? (customer.credit_hold_reason ?? "Account on credit hold") : null,
      };
    }
  }
}
