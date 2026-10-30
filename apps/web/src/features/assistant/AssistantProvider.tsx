import type { AssistantContextHint, AssistantInfo, AssistantReply, AssistantTurn } from "@ai-pos/shared-types";
import { Permission } from "@ai-pos/shared-types";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { crumbsFor } from "../../components/layout/navigation";
import { env } from "../../config/env";
import { apiGet, apiPost } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useCapabilities } from "../../lib/capabilities";
import { useStoreScope } from "../../lib/storeScope";
import { errorMessage } from "../users/api";
import { blankThread, loadAssistant, saveAssistant, type AssistantMessage, type AssistantThread } from "./assistantStorage";

interface AssistantState {
  allowed: boolean;
  open: boolean;
  toggle: () => void;
  openDrawer: () => void;
  closeDrawer: () => void;
  info: AssistantInfo | null;
  messages: AssistantMessage[];
  threads: AssistantThread[];
  activeId: string | null;
  busy: boolean;
  error: string | null;
  moduleLabel: string;
  storeLabel: string;
  ask: (text: string) => Promise<void>;
  startNew: () => void;
  resume: (id: string) => void;
  clearCurrent: () => void;
}

const AssistantContext = createContext<AssistantState | null>(null);

export function AssistantProvider({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const { can, user } = useAuth();
  const { profile, has } = useCapabilities();
  const { storeId, stores } = useStoreScope();
  const allowed = can(Permission.PortalReportsRead);
  const [open, setOpen] = useState(false);
  const [info, setInfo] = useState<AssistantInfo | null>(null);
  const [threads, setThreads] = useState<AssistantThread[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [ownerId, setOwnerId] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sending = useRef(false);
  const returnFocus = useRef<HTMLElement | null>(null);
  const infoLoaded = useRef(false);

  const tenant = env.tenantDomain ?? "local";
  const moduleLabel = crumbsFor(pathname, { profile, has }).at(-1)?.label ?? "This page";
  const store = stores.find((row) => row.id === storeId);
  const storeLabel = store ? store.name : "All branches";

  useEffect(() => {
    infoLoaded.current = false;
    setInfo(null);
    if (!user) {
      setOwnerId(null);
      setThreads([]);
      setActiveId(null);
      setReady(false);
      return;
    }
    const loaded = loadAssistant(tenant, user.id);
    setOwnerId(`${tenant}:${user.id}`);
    setThreads(loaded.threads);
    setActiveId(loaded.activeId);
    setReady(true);
  }, [user?.id, tenant]);

  useEffect(() => {
    if (!ready || !user || !activeId || ownerId !== `${tenant}:${user.id}`) return;
    saveAssistant(tenant, user.id, { activeId, threads });
  }, [ready, user, activeId, threads, ownerId, tenant]);

  useEffect(() => {
    if (!allowed || !open || infoLoaded.current) return;
    infoLoaded.current = true;
    apiGet<AssistantInfo>("/api/v1/assistant")
      .then(setInfo)
      .catch((caught: unknown) => setError(errorMessage(caught, "The assistant is unavailable.")));
  }, [allowed, open, user?.id]);

  const openDrawer = useCallback(() => {
    returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setOpen(true);
  }, []);
  const closeDrawer = useCallback(() => {
    setOpen(false);
    const back = returnFocus.current;
    returnFocus.current = null;
    window.requestAnimationFrame(() => back?.focus());
  }, []);
  const toggle = useCallback(() => {
    setOpen((value) => {
      if (value) {
        const back = returnFocus.current;
        returnFocus.current = null;
        window.requestAnimationFrame(() => back?.focus());
        return false;
      }
      returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      return true;
    });
  }, []);

  const messages = threads.find((thread) => thread.id === activeId)?.messages ?? [];

  const updateThread = useCallback((id: string, change: (thread: AssistantThread) => AssistantThread) => {
    setThreads((current) => current.map((thread) => (thread.id === id ? change(thread) : thread)));
  }, []);

  const ask = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      const threadId = activeId;
      if (!threadId || trimmed.length < 2 || sending.current) return;
      const userMessage: AssistantMessage = { id: crypto.randomUUID(), role: "user", content: trimmed };
      const history: AssistantTurn[] = messages.slice(-8).map((message) => ({
        role: message.role,
        content: message.content.slice(0, 2000),
      }));
      const context: AssistantContextHint = { module: moduleLabel.slice(0, 80), store: storeLabel.slice(0, 80) };
      sending.current = true;
      setBusy(true);
      setError(null);
      updateThread(threadId, (thread) => ({
        ...thread,
        updatedAt: new Date().toISOString(),
        messages: [...thread.messages, userMessage].slice(-30),
      }));
      try {
        const reply = await apiPost<AssistantReply>("/api/v1/assistant/ask", {
          question: trimmed.slice(0, 500),
          history,
          context,
        });
        const answer: AssistantMessage = {
          id: crypto.randomUUID(),
          role: "assistant",
          content: reply.answer,
          language: reply.language,
          results: reply.results,
        };
        setThreads((current) =>
          current.map((thread) =>
            thread.id === threadId && thread.messages.some((message) => message.id === userMessage.id)
              ? { ...thread, updatedAt: new Date().toISOString(), messages: [...thread.messages, answer].slice(-30) }
              : thread,
          ),
        );
      } catch (caught) {
        setError(errorMessage(caught, "Could not get an answer."));
      } finally {
        sending.current = false;
        setBusy(false);
      }
    },
    [activeId, messages, moduleLabel, storeLabel, updateThread],
  );

  const startNew = useCallback(() => {
    if (messages.length === 0) return;
    const thread = blankThread();
    setThreads((current) => [thread, ...current.filter((item) => item.messages.length > 0)].slice(0, 20));
    setActiveId(thread.id);
    setError(null);
  }, [messages.length]);

  const resume = useCallback((id: string) => {
    setActiveId(id);
    setError(null);
  }, []);

  const clearCurrent = useCallback(() => {
    if (!activeId) return;
    const thread = blankThread();
    setThreads((current) => [thread, ...current.filter((item) => item.id !== activeId && item.messages.length > 0)].slice(0, 20));
    setActiveId(thread.id);
    setError(null);
  }, [activeId]);

  const value = useMemo<AssistantState>(
    () => ({
      allowed,
      open,
      toggle,
      openDrawer,
      closeDrawer,
      info,
      messages,
      threads,
      activeId,
      busy,
      error,
      moduleLabel,
      storeLabel,
      ask,
      startNew,
      resume,
      clearCurrent,
    }),
    [
      allowed,
      open,
      toggle,
      openDrawer,
      closeDrawer,
      info,
      messages,
      threads,
      activeId,
      busy,
      error,
      moduleLabel,
      storeLabel,
      ask,
      startNew,
      resume,
      clearCurrent,
    ],
  );

  return <AssistantContext.Provider value={value}>{children}</AssistantContext.Provider>;
}

export function useAssistant(): AssistantState {
  const context = useContext(AssistantContext);
  if (context === null) throw new Error("useAssistant must be used inside AssistantProvider.");
  return context;
}
