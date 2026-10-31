import { isValidElement, type ReactNode } from "react";

/** What an action button means. The resting style stays neutral; the color shows on hover and keyboard focus. */
export type ActionIntent = "success" | "danger" | "warning" | "info" | "primary" | "neutral";

const RULES: readonly [ActionIntent, RegExp][] = [
  ["danger", /\b(reject|delete|remove|revoke|cancel|void|reverse)\b/i],
  ["warning", /\b(suspend|hold|disable|deactivate|flag|reopen|retry review|bounce|unmatch)\b/i],
  ["success", /\b(verify|activate|approve|confirm|complete)\b/i],
  ["info", /\b(view|receipt|details|preview|history|invoice|statement|ledger|pdf|trace)\b/i],
  ["primary", /\b(edit|update|configure|pricing|adjust)\b/i],
];

/** Classify a visible label. Danger is checked before success so "Confirm delete" stays red. */
export function actionIntentFromLabel(label: string): ActionIntent {
  const text = label.replace(/\s+/g, " ").trim();
  for (const [intent, pattern] of RULES) {
    if (pattern.test(text)) return intent;
  }
  return "neutral";
}

function nodeText(node: ReactNode): string {
  if (node == null || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(nodeText).join(" ");
  if (isValidElement(node)) {
    const props = node.props as { children?: ReactNode };
    return nodeText(props.children);
  }
  return "";
}

/** Label text plus the accessible name, so an icon button and a labelled button classify the same way. */
export function actionIntentFromNodes(children: ReactNode, ariaLabel?: string): ActionIntent {
  return actionIntentFromLabel(`${ariaLabel ?? ""} ${nodeText(children)}`);
}

const motion =
  "transition-[color,background-color,border-color] duration-200 ease-out motion-reduce:transition-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-40";

const shapeClass = {
  pill: "inline-flex items-center justify-center gap-2 rounded-full px-6 py-2.5 text-sm font-medium",
  icon: "inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full",
} as const;

const resting =
  "border-gray-200 bg-white text-charcoal dark:border-white/20 dark:bg-[#2D2A32] dark:text-white";

const hoverClass: Record<ActionIntent, string> = {
  neutral:
    "hover:border-gray-300 hover:bg-gray-100 focus-visible:ring-charcoal/30 dark:hover:border-white/30 dark:hover:bg-white/10",
  success:
    "hover:border-success hover:bg-success hover:text-white focus-visible:border-success focus-visible:bg-success focus-visible:text-white focus-visible:ring-success dark:hover:border-success dark:hover:bg-success dark:hover:text-white dark:focus-visible:border-success dark:focus-visible:bg-success dark:focus-visible:text-white",
  danger:
    "hover:border-danger hover:bg-danger hover:text-white focus-visible:border-danger focus-visible:bg-danger focus-visible:text-white focus-visible:ring-danger dark:hover:border-danger dark:hover:bg-danger dark:hover:text-white dark:focus-visible:border-danger dark:focus-visible:bg-danger dark:focus-visible:text-white",
  warning:
    "hover:border-warning-strong hover:bg-warning-strong hover:text-white focus-visible:border-warning-strong focus-visible:bg-warning-strong focus-visible:text-white focus-visible:ring-warning-strong dark:hover:border-warning-strong dark:hover:bg-warning-strong dark:hover:text-white dark:focus-visible:border-warning-strong dark:focus-visible:bg-warning-strong dark:focus-visible:text-white",
  info:
    "hover:border-info hover:bg-info hover:text-white focus-visible:border-info focus-visible:bg-info focus-visible:text-white focus-visible:ring-info dark:hover:border-info dark:hover:bg-info dark:hover:text-white dark:focus-visible:border-info dark:focus-visible:bg-info dark:focus-visible:text-white",
  primary:
    "hover:border-accent hover:bg-accent hover:text-white focus-visible:border-accent focus-visible:bg-accent focus-visible:text-white focus-visible:ring-accent dark:hover:border-accent dark:hover:bg-accent dark:hover:text-white dark:focus-visible:border-accent dark:focus-visible:bg-accent dark:focus-visible:text-white",
};

/** Hover and focus only, so an existing button can keep its size and resting border. */
export function actionHoverClass(intent: ActionIntent): string {
  return `${motion} ${hoverClass[intent]}`;
}

/** Resting ghost button. `intent` only changes hover and focus-visible. */
export function actionButtonClass(intent: ActionIntent, shape: keyof typeof shapeClass = "pill"): string {
  return `${shapeClass[shape]} border ${resting} ${hoverClass[intent]} ${motion}`;
}
