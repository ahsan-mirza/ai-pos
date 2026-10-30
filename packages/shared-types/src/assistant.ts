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

/** Screen the user had open when they asked. The assistant treats it as a hint and still answers from reports. */
export interface AssistantContextHint {
  module: string;
  store: string;
}
