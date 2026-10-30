import type { AssistantToolResult } from "@ai-pos/shared-types";

export interface AssistantMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  language?: "en" | "ar";
  results?: AssistantToolResult[];
}

export interface AssistantThread {
  id: string;
  title: string;
  updatedAt: string;
  messages: AssistantMessage[];
}

interface Stored {
  activeId: string;
  threads: AssistantThread[];
}

const LEGACY_KEY = "ai-pos.assistant.conversation";
const MAX_THREADS = 20;
const MAX_MESSAGES = 30;

function storageKey(tenant: string, userId: string): string {
  return `ai-pos.assistant.v3.${tenant}.${userId}`;
}

function previousKey(userId: string): string {
  return `ai-pos.assistant.v2.${userId}`;
}

function newId(): string {
  return crypto.randomUUID();
}

export function blankThread(): AssistantThread {
  return { id: newId(), title: "New conversation", updatedAt: new Date().toISOString(), messages: [] };
}

function titleFor(messages: AssistantMessage[]): string {
  const first = messages.find((message) => message.role === "user");
  const text = first?.content.trim() ?? "";
  return text ? text.slice(0, 80) : "New conversation";
}

function normalize(thread: AssistantThread): AssistantThread {
  const messages = thread.messages.slice(-MAX_MESSAGES).map((message) => ({
    ...message,
    id: message.id || newId(),
  }));
  return { ...thread, title: titleFor(messages), messages };
}

function fromLegacy(raw: string): AssistantThread | null {
  try {
    const parsed = JSON.parse(raw) as Partial<AssistantMessage>[];
    if (!Array.isArray(parsed) || parsed.length === 0) return null;
    const messages = parsed
      .filter((message) => message.role === "user" || message.role === "assistant")
      .map((message) => ({
        id: newId(),
        role: message.role as "user" | "assistant",
        content: String(message.content ?? ""),
        language: message.language,
        results: message.results,
      }));
    if (messages.length === 0) return null;
    return normalize({ id: newId(), title: titleFor(messages), updatedAt: new Date().toISOString(), messages });
  } catch {
    return null;
  }
}

export function loadAssistant(tenant: string, userId: string): Stored {
  try {
    const raw = sessionStorage.getItem(storageKey(tenant, userId));
    if (raw) {
      const parsed = JSON.parse(raw) as Stored;
      const threads = (parsed.threads ?? []).map(normalize).slice(0, MAX_THREADS);
      const active = threads.find((thread) => thread.id === parsed.activeId) ?? threads[0];
      if (active) return { activeId: active.id, threads };
    }
  } catch {
    // A corrupt tab store starts a fresh conversation rather than blocking the drawer.
  }
  const previous = sessionStorage.getItem(previousKey(userId));
  sessionStorage.removeItem(previousKey(userId));
  if (previous) {
    try {
      const parsed = JSON.parse(previous) as Stored;
      const threads = (parsed.threads ?? []).map(normalize).slice(0, MAX_THREADS);
      const active = threads.find((thread) => thread.id === parsed.activeId) ?? threads[0];
      if (active) return { activeId: active.id, threads };
    } catch {
      // The old tab store was not a conversation list. Fall through to a new thread.
    }
  }
  const legacy = sessionStorage.getItem(LEGACY_KEY);
  sessionStorage.removeItem(LEGACY_KEY);
  const imported = legacy ? fromLegacy(legacy) : null;
  const thread = imported ?? blankThread();
  return { activeId: thread.id, threads: [thread] };
}

export function saveAssistant(tenant: string, userId: string, stored: Stored): void {
  const threads = stored.threads
    .map(normalize)
    .filter((thread) => thread.messages.length > 0 || thread.id === stored.activeId)
    .slice(0, MAX_THREADS);
  const activeId = threads.some((thread) => thread.id === stored.activeId) ? stored.activeId : threads[0]?.id;
  if (!activeId) return;
  try {
    sessionStorage.setItem(storageKey(tenant, userId), JSON.stringify({ activeId, threads }));
    sessionStorage.removeItem(LEGACY_KEY);
  } catch {
    // The conversation still lives in memory for this visit.
  }
}
