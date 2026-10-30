import type { AssistantToolResult } from "@ai-pos/shared-types";
import { History, Plus, SendHorizontal, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { AiMark } from "../../components/ui/AiMark";
import { ErrorNote } from "../../components/ui/Field";
import { useAssistant } from "./AssistantProvider";
import type { AssistantMessage } from "./assistantStorage";

const isArabic = (text: string) => /[\u0600-\u06FF]/.test(text);

function RichText({ text }: { text: string }) {
  const chunks = text.split(/(\*\*[^*]+\*\*)/g);
  return (
    <>
      {chunks.map((chunk, index) =>
        chunk.startsWith("**") && chunk.endsWith("**") && chunk.length > 4 ? (
          <strong key={index}>{chunk.slice(2, -2)}</strong>
        ) : (
          <span key={index} className="whitespace-pre-wrap">
            {chunk}
          </span>
        ),
      )}
    </>
  );
}

function ResultTable({ result }: { result: AssistantToolResult }) {
  const [open, setOpen] = useState(result.rows.length <= 6);
  if (result.rows.length === 0) return null;
  const rows = open ? result.rows : result.rows.slice(0, 6);
  return (
    <div className="overflow-hidden rounded-xl border border-line">
      <div className="flex items-center justify-between gap-2 bg-surface/60 px-3 py-2 text-xs">
        <span className="font-semibold">{result.title}</span>
        {result.period ? <span className="text-charcoal/50">{result.period}</span> : null}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="text-charcoal/50">
            <tr>
              {result.columns.map((column, index) => (
                <th key={column} className={`px-3 py-2 font-medium ${index > 0 ? "text-right" : ""}`}>
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index} className="border-t border-line">
                {row.map((cell, at) => (
                  <td key={at} className={`px-3 py-2 ${at > 0 ? "text-right tabular-nums" : "font-medium"}`}>
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {result.rows.length > 6 ? (
        <button type="button" onClick={() => setOpen(!open)} className="w-full border-t border-line py-2 text-xs font-semibold text-accent">
          {open ? "Show fewer" : `Show all ${result.rows.length}`}
        </button>
      ) : null}
    </div>
  );
}

const iconAction =
  "flex h-8 w-8 items-center justify-center rounded-lg text-charcoal/60 outline-none hover:bg-charcoal/[0.05] hover:text-charcoal focus-visible:ring-2 focus-visible:ring-accent/40";

export function AssistantDrawer() {
  const assistant = useAssistant();
  const [draft, setDraft] = useState("");
  const [historyOpen, setHistoryOpen] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const scrollerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!assistant.open) return;
    const frame = window.requestAnimationFrame(() => inputRef.current?.focus());
    return () => window.cancelAnimationFrame(frame);
  }, [assistant.open]);

  useEffect(() => {
    if (!assistant.open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || document.querySelector(".modal-backdrop")) return;
      if (confirmClear) {
        setConfirmClear(false);
        return;
      }
      if (historyOpen) {
        setHistoryOpen(false);
        return;
      }
      assistant.closeDrawer();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [assistant.closeDrawer, confirmClear, historyOpen]);

  useEffect(() => {
    const el = scrollerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [assistant.messages, assistant.busy, assistant.open]);

  if (!assistant.allowed || !assistant.open) return null;

  const suggestions = assistant.info
    ? [...assistant.info.suggestions.en.slice(0, 4), ...assistant.info.suggestions.ar.slice(0, 3)]
    : [];
  const provider =
    assistant.info == null
      ? ""
      : assistant.info.provider === "builtin"
        ? "built-in"
        : assistant.info.provider.replace(/^openai:|^ollama:/, "");
  const past = assistant.threads.filter((thread) => thread.messages.length > 0);

  const send = () => {
    if (assistant.busy || draft.trim().length < 2) return;
    const text = draft;
    setDraft("");
    if (inputRef.current) inputRef.current.style.height = "auto";
    void assistant.ask(text);
  };

  return (
    <>
      <button
        type="button"
        aria-label="Close AI Assistant"
        className="drawer-backdrop absolute inset-0 z-10 hidden bg-charcoal/20 md:block lg:hidden"
        onClick={assistant.closeDrawer}
      />
      <section
        id="ai-assistant-drawer"
        role="dialog"
        aria-modal="false"
        aria-labelledby="ai-assistant-title"
        className="drawer-panel absolute inset-0 z-20 flex min-w-0 flex-col bg-white shadow-xl md:inset-y-0 md:left-auto md:right-0 md:w-[min(480px,92vw)] md:border-l md:border-line lg:w-[min(460px,40vw)]"
      >
        <header className="flex items-start gap-3 border-b border-line px-4 py-3">
          <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-accent/10 text-accent">
            <AiMark size={16} className="text-accent" />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id="ai-assistant-title" className="text-sm font-semibold text-charcoal">
              AI Assistant
            </h2>
            <p className="truncate text-xs text-charcoal/55">
              Ask your business
              {provider ? ` · ${provider}` : ""}
            </p>
            <p className="truncate text-[11px] text-charcoal/45">
              {assistant.moduleLabel} · {assistant.storeLabel}
            </p>
          </div>
          <button type="button" className={iconAction} aria-label="Conversation history" aria-pressed={historyOpen} onClick={() => setHistoryOpen((value) => !value)}>
            <History size={16} aria-hidden="true" />
          </button>
          <button
            type="button"
            className={iconAction}
            aria-label="New conversation"
            onClick={() => {
              setHistoryOpen(false);
              setConfirmClear(false);
              assistant.startNew();
            }}
          >
            <Plus size={16} aria-hidden="true" />
          </button>
          <button type="button" className={iconAction} aria-label="Close AI Assistant" onClick={assistant.closeDrawer}>
            <X size={16} aria-hidden="true" />
          </button>
        </header>

        {historyOpen ? (
          <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-3 py-3">
            <p className="px-2 pb-2 text-xs font-semibold uppercase tracking-wide text-charcoal/45">Conversations</p>
            {past.length === 0 ? <p className="px-2 py-6 text-sm text-charcoal/55">No earlier conversations in this session.</p> : null}
            <ul className="space-y-1">
              {past.map((thread) => (
                <li key={thread.id}>
                  <button
                    type="button"
                    onClick={() => {
                      assistant.resume(thread.id);
                      setHistoryOpen(false);
                    }}
                    className={`w-full rounded-xl px-3 py-2 text-left hover:bg-surface ${thread.id === assistant.activeId ? "bg-accent/10" : ""}`}
                  >
                    <span className="block truncate text-sm font-medium">{thread.title}</span>
                    <span className="text-[11px] text-charcoal/45">{new Date(thread.updatedAt).toLocaleString()}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <div ref={scrollerRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain px-4 py-4">
            {assistant.messages.length === 0 ? <Welcome suggestions={suggestions} onAsk={(text) => void assistant.ask(text)} /> : null}
            {assistant.messages.map((message) => (
              <MessageView key={message.id} message={message} />
            ))}
            {assistant.busy ? <p className="text-sm text-charcoal/50">Reading the reports…</p> : null}
          </div>
        )}

        <div className="border-t border-line px-4 py-3">
          {confirmClear ? (
            <div className="mb-3 rounded-xl border border-line bg-surface px-3 py-3 text-sm">
              <p>Clear this conversation? Other saved chats in this session stay.</p>
              <div className="mt-2 flex gap-2">
                <button
                  type="button"
                  className="rounded-full bg-charcoal px-3 py-1.5 text-xs font-semibold text-white"
                  onClick={() => {
                    assistant.clearCurrent();
                    setConfirmClear(false);
                  }}
                >
                  Clear
                </button>
                <button type="button" className="rounded-full px-3 py-1.5 text-xs font-semibold" onClick={() => setConfirmClear(false)}>
                  Cancel
                </button>
              </div>
            </div>
          ) : assistant.messages.length > 0 && !historyOpen ? (
            <button type="button" onClick={() => setConfirmClear(true)} className="mb-2 text-xs font-semibold text-charcoal/50 hover:text-accent">
              Clear conversation
            </button>
          ) : null}
          <ErrorNote message={assistant.error} />
          <form
            className="flex items-end gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              send();
            }}
          >
            <textarea
              ref={inputRef}
              aria-label="Your question"
              dir={isArabic(draft) ? "rtl" : "ltr"}
              rows={1}
              value={draft}
              maxLength={500}
              placeholder="Ask about your business..."
              disabled={assistant.busy}
              onChange={(event) => {
                setDraft(event.target.value);
                event.target.style.height = "auto";
                event.target.style.height = `${Math.min(event.target.scrollHeight, 128)}px`;
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  send();
                }
              }}
              className="max-h-32 min-h-11 flex-1 resize-none rounded-2xl bg-surface px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40 disabled:opacity-60"
            />
            <button
              type="submit"
              aria-label="Send"
              disabled={assistant.busy || draft.trim().length < 2}
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-accent text-white hover:bg-accent-hover disabled:opacity-40"
            >
              <SendHorizontal size={18} aria-hidden="true" />
            </button>
          </form>
        </div>
      </section>
    </>
  );
}

function Welcome({ suggestions, onAsk }: { suggestions: string[]; onAsk: (text: string) => void }) {
  return (
    <div className="py-2">
      <p className="text-sm font-semibold text-charcoal">How can I help your business?</p>
      <p className="mt-2 text-sm leading-relaxed text-charcoal/60">
        Ask about sales, revenue, profit, best-selling products, inventory and stock, purchase orders, suppliers, customer balances, expenses, or branch performance. Answers come only from your reports, in English or العربية.
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        {suggestions.map((item) => (
          <button
            key={item}
            type="button"
            dir={isArabic(item) ? "rtl" : "ltr"}
            onClick={() => onAsk(item)}
            className="inline-flex items-center gap-1.5 rounded-full bg-surface px-3 py-1.5 text-left text-sm hover:bg-accent hover:text-white"
          >
            <AiMark size={12} className="text-current" />
            {item}
          </button>
        ))}
      </div>
    </div>
  );
}

function MessageView({ message }: { message: AssistantMessage }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <p dir={isArabic(message.content) ? "rtl" : "ltr"} className="max-w-[85%] rounded-2xl rounded-br-md bg-charcoal px-3.5 py-2.5 text-sm text-white">
          {message.content}
        </p>
      </div>
    );
  }
  return (
    <div className="max-w-[95%] space-y-2">
      <div dir={message.language === "ar" ? "rtl" : "ltr"} className="rounded-2xl rounded-bl-md bg-surface px-3.5 py-3 text-sm leading-relaxed">
        <RichText text={message.content} />
      </div>
      {message.results?.map((result, index) => (
        <ResultTable key={`${result.tool}-${index}`} result={result} />
      ))}
    </div>
  );
}
