/** Present a stored timeline sentence without rewriting the event row. */

export interface PresentedEvent {
  /** English catalog key. Pass it through t(). */
  text: string;
  vars?: Record<string, string>;
}

const TEMPLATES: Array<{ pattern: RegExp; text: string; fields: string[] }> = [
  { pattern: /^Delivery promised for (\d{4}-\d{2}-\d{2})\.$/, text: "Delivery promised for {date}.", fields: ["date"] },
  { pattern: /^Added to dispatch plan ([A-Za-z0-9-]+)\.$/, text: "Added to dispatch plan {plan}.", fields: ["plan"] },
  { pattern: /^Removed from dispatch plan ([A-Za-z0-9-]+)\.$/, text: "Removed from dispatch plan {plan}.", fields: ["plan"] },
  { pattern: /^Dispatch plan ([A-Za-z0-9-]+) confirmed\.$/, text: "Dispatch plan {plan} confirmed.", fields: ["plan"] },
  { pattern: /^Dispatch plan ([A-Za-z0-9-]+) was cancelled\.$/, text: "Dispatch plan {plan} was cancelled.", fields: ["plan"] },
  { pattern: /^Order ([A-Za-z0-9-]+) created\.$/, text: "Order {number} created.", fields: ["number"] },
  {
    pattern: /^Order ([A-Za-z0-9-]+) confirmed and stock reserved\.$/,
    text: "Order {number} confirmed and stock reserved.",
    fields: ["number"],
  },
  { pattern: /^Delivery ([A-Za-z0-9-]+) left the branch\.$/, text: "Delivery {number} left the branch.", fields: ["number"] },
  { pattern: /^Pick list ([A-Za-z0-9-]+) prepared\.$/, text: "Pick list {number} prepared.", fields: ["number"] },
];

export function presentEvent(kind: string, summary: string, formatDate: (iso: string) => string): PresentedEvent | null {
  if (kind === "capacity_override") return null;
  for (const template of TEMPLATES) {
    const match = template.pattern.exec(summary);
    if (!match) continue;
    const vars: Record<string, string> = {};
    template.fields.forEach((field, index) => {
      const value = match[index + 1] ?? "";
      const shown = field === "date" ? formatDate(value) : value;
      vars[field] = `\u2066${shown}\u2069`;
    });
    return { text: template.text, vars };
  }
  return null;
}
