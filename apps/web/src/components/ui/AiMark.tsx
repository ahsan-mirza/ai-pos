import { Sparkles } from "lucide-react";

/** The mark in front of an AI feature name, in navigation and on its buttons. */
export function AiMark({ size = 14, className = "text-accent" }: { size?: number; className?: string }) {
  return <Sparkles size={size} aria-hidden="true" className={`shrink-0 ${className}`} />;
}

const AI_LABELS = new Set(["AI assistant", "AI insights", "Kitchen agent"]);

export function isAiFeature(label: string): boolean {
  return AI_LABELS.has(label);
}
