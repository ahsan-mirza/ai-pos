export interface AssistantTurn {
  role: "user" | "assistant";
  content: string;
}

export interface AssistantToolResult {
  tool: string;
  title: string;
  period: string | null;
  columns: string[];
  rows: string[][];
}

export interface AssistantReply {
  answer: string;
  language: "en" | "ar";
  provider: string;
  results: AssistantToolResult[];
  suggestions: string[];
}

export interface AssistantInfo {
  provider: string;
  tools: string[];
  suggestions: Record<"en" | "ar", string[]>;
}
