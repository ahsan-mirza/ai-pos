import type { AssistantInfo, AssistantReply, AssistantToolResult, AssistantTurn } from "@ai-pos/shared-types";
import { SendHorizontal, Sparkles, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { ErrorNote } from "../../components/ui/Field";
import { apiGet, apiPost } from "../../lib/api";
import { errorMessage } from "../users/api";

interface Message {
  role: "user" | "assistant";
  content: string;
  language?: "en" | "ar";
  results?: AssistantToolResult[];
}

const STORAGE_KEY = "ai-pos.assistant.conversation";
const isArabic = (text: string) => /[\u0600-\u06FF]/.test(text);

function restore(): Message[] {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Message[]) : [];
  } catch {
    return [];
  }
}

export function AssistantPage() {
  const [info, setInfo] = useState<AssistantInfo | null>(null);
  const [messages, setMessages] = useState<Message[]>(restore);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    apiGet<AssistantInfo>("/api/v1/assistant")
      .then(setInfo)
      .catch((caught: unknown) => setError(errorMessage(caught, "The assistant is unavailable.")));
  }, []);

  useEffect(() => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(messages.slice(-30)));
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  const ask = async (text: string) => {
    const trimmed = text.trim();
    if (trimmed.length < 2 || busy) return;
    const history: AssistantTurn[] = messages.slice(-8).map((message) => ({ role: message.role, content: message.content.slice(0, 2000) }));
    setMessages((current) => [...current, { role: "user", content: trimmed }]);
    setQuestion("");
    setBusy(true);
    setError(null);
    try {
      const reply = await apiPost<AssistantReply>("/api/v1/assistant/ask", { question: trimmed.slice(0, 500), history });
      setMessages((current) => [...current, { role: "assistant", content: reply.answer, language: reply.language, results: reply.results }]);
    } catch (caught) {
      setError(errorMessage(caught, "Could not get an answer."));
    } finally {
      setBusy(false);
    }
  };

  const suggestions = info ? [...info.suggestions.en.slice(0, 3), ...info.suggestions.ar.slice(0, 3)] : [];

  return (
    <section className="flex h-[calc(100vh-9rem)] min-h-[520px] flex-col rounded-card border border-line bg-white">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-6 py-4">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-charcoal text-white">
            <Sparkles size={18} aria-hidden="true" />
          </span>
          <div>
            <h2 className="text-lg font-semibold">Ask your business</h2>
            <p className="text-xs text-charcoal/60">
              English or العربية · answers come only from your reports
              {info ? ` · ${info.provider === "builtin" ? "built-in assistant" : info.provider.replace("openai:", "")}` : ""}
            </p>
          </div>
        </div>
        {messages.length ? (
          <button
            type="button"
            onClick={() => setMessages([])}
            className="inline-flex items-center gap-1.5 rounded-full border border-line px-3 py-1.5 text-xs font-semibold hover:border-accent hover:text-accent"
          >
            <Trash2 size={13} aria-hidden="true" /> New conversation
          </button>
        ) : null}
      </header>

      <div className="flex-1 space-y-4 overflow-y-auto px-6 py-5">
        {messages.length === 0 ? (
          <div className="mx-auto max-w-xl py-8 text-center">
            <p className="text-sm text-charcoal/60">Ask about sales, profit, best sellers, staff, stock, expenses, customer balances or what you owe suppliers.</p>
            <div className="mt-5 flex flex-wrap justify-center gap-2">
              {suggestions.map((item) => (
                <button
                  key={item}
                  type="button"
                  dir={isArabic(item) ? "rtl" : "ltr"}
                  onClick={() => void ask(item)}
                  className="rounded-full bg-surface px-3.5 py-2 text-sm hover:bg-accent hover:text-white"
                >
                  {item}
                </button>
              ))}
            </div>
          </div>
        ) : null}
        {messages.map((message, index) =>
          message.role === "user" ? (
            <div key={index} className="flex justify-end">
              <p dir={isArabic(message.content) ? "rtl" : "ltr"} className="max-w-[75%] rounded-2xl rounded-br-md bg-charcoal px-4 py-2.5 text-sm text-white">
                {message.content}
              </p>
            </div>
          ) : (
            <div key={index} className="max-w-[90%] space-y-3">
              <p dir={message.language === "ar" ? "rtl" : "ltr"} className="rounded-2xl rounded-bl-md bg-surface px-4 py-3 text-sm leading-relaxed">
                {message.content}
              </p>
              {message.results?.map((result, at) => <ResultTable key={at} result={result} />)}
            </div>
          ),
        )}
        {busy ? <p className="text-sm text-charcoal/50">Reading the reports…</p> : null}
        <div ref={endRef} />
      </div>

      <div className="border-t border-line px-6 py-4">
        <ErrorNote message={error} />
        <form
          className="flex items-center gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            void ask(question);
          }}
        >
          <input
            aria-label="Your question"
            dir={isArabic(question) ? "rtl" : "ltr"}
            value={question}
            maxLength={500}
            placeholder="e.g. What were sales at each branch last week?  ·  كم بعنا اليوم؟"
            onChange={(event) => setQuestion(event.target.value)}
            className="flex-1 rounded-full bg-surface px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40"
          />
          <button
            type="submit"
            aria-label="Ask"
            disabled={busy || question.trim().length < 2}
            className="flex h-11 w-11 items-center justify-center rounded-full bg-accent text-white hover:bg-accent-hover disabled:opacity-40"
          >
            <SendHorizontal size={18} aria-hidden="true" />
          </button>
        </form>
      </div>
    </section>
  );
}

function ResultTable({ result }: { result: AssistantToolResult }) {
  const [open, setOpen] = useState(result.rows.length <= 6);
  if (result.rows.length === 0) return null;
  const rows = open ? result.rows : result.rows.slice(0, 6);
  return (
    <div className="overflow-hidden rounded-2xl border border-line">
      <div className="flex items-center justify-between bg-surface/60 px-4 py-2 text-xs">
        <span className="font-semibold">{result.title}</span>
        {result.period ? <span className="text-charcoal/50">{result.period}</span> : null}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="text-charcoal/50">
            <tr>
              {result.columns.map((column, index) => (
                <th key={column} className={`px-4 py-2 font-medium ${index > 0 ? "text-right" : ""}`}>
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index} className="border-t border-line">
                {row.map((cell, at) => (
                  <td key={at} className={`px-4 py-2 ${at > 0 ? "text-right tabular-nums" : "font-medium"}`}>
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
