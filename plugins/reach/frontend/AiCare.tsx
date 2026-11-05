import { useEffect, useState } from "react";
import { apiDelete, apiGet, apiPost, apiPut } from "../../../apps/web/src/lib/api";
import { errorMessage } from "../../../apps/web/src/features/users/api";

const button = "inline-flex h-[38px] items-center rounded-full bg-accent px-4 text-sm font-medium text-white disabled:opacity-50";
const ghost = "inline-flex h-[38px] items-center rounded-full border border-line bg-white px-4 text-sm font-medium";
const field = "h-10 w-full rounded-xl border border-line px-3 text-sm";

interface Agent {
  enabled: boolean;
  mode: string;
  name: string;
  greeting: string;
  language: string;
  tone: string;
  instructions: string;
  product_help: boolean;
  order_help: boolean;
  action_detection: boolean;
  handoff: boolean;
}

interface Knowledge {
  id: string;
  kind: string;
  title: string;
  body: string;
  status: string;
}

interface Conversation {
  id: string;
  phone: string;
  customer_name: string;
  status: string;
  handler: string;
  priority: string;
  language: string;
  intent: string;
  last_preview: string;
}

interface CareMessage {
  id: string;
  direction: string;
  author: string;
  body: string;
  status: string;
  created_at: string;
}

interface CareStats {
  conversations: number;
  human_handling: number;
  actions_waiting: number;
  replies: number;
}

interface CareAction {
  id: string;
  conversation_id: string;
  category: string;
  title: string;
  details: string;
  priority: string;
  confidence: number;
  status: string;
  consequential: boolean;
  result: string;
}

interface Detail {
  conversation: Conversation;
  customer: { matched: boolean; name?: string; phone?: string; balance_cents?: number; purchase_total_cents?: number };
  messages: CareMessage[];
  actions: CareAction[];
}

export function AgentPanel() {
  const [agent, setAgent] = useState<Agent | null>(null);
  const [knowledge, setKnowledge] = useState<Knowledge[]>([]);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [trial, setTrial] = useState("");
  const [answer, setAnswer] = useState("");
  const [error, setError] = useState("");
  const [stats, setStats] = useState<CareStats | null>(null);

  const load = () => {
    apiGet<Agent>("/api/v1/reach/ai/agent").then(setAgent).catch((err) => setError(errorMessage(err, "The agent could not be loaded.")));
    apiGet<Knowledge[]>("/api/v1/reach/ai/knowledge").then(setKnowledge).catch(() => undefined);
    apiGet<CareStats>("/api/v1/reach/ai/analytics").then(setStats).catch(() => undefined);
  };

  useEffect(load, []);

  if (!agent) return <p className="text-sm text-charcoal/60">{error || "Loading the agent."}</p>;

  const save = () => {
    setError("");
    apiPut<Agent>("/api/v1/reach/ai/agent", agent)
      .then(setAgent)
      .catch((err) => setError(errorMessage(err, "The agent could not be loaded.")));
  };

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <section className="rounded-card border border-line bg-white p-4">
        <h2 className="text-lg font-semibold">Agent</h2>
        <p className="mt-1 text-sm text-charcoal/60">Replies stay off until you enable them. Hybrid is the default. Refunds are never posted from here.</p>
        {stats ? (
          <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
            <div><dt className="text-charcoal/50">Conversations</dt><dd className="font-semibold">{stats.conversations}</dd></div>
            <div><dt className="text-charcoal/50">With staff</dt><dd className="font-semibold">{stats.human_handling}</dd></div>
            <div><dt className="text-charcoal/50">Actions waiting</dt><dd className="font-semibold">{stats.actions_waiting}</dd></div>
            <div><dt className="text-charcoal/50">Replies prepared</dt><dd className="font-semibold">{stats.replies}</dd></div>
          </dl>
        ) : null}
        <div className="mt-3 grid gap-3">
          <label className="grid gap-1 text-sm">Name<input className={field} value={agent.name} onChange={(event) => setAgent({ ...agent, name: event.target.value })} /></label>
          <label className="grid gap-1 text-sm">Greeting<input className={field} value={agent.greeting} onChange={(event) => setAgent({ ...agent, greeting: event.target.value })} /></label>
          <label className="grid gap-1 text-sm">Mode
            <select className={field} value={agent.mode} onChange={(event) => setAgent({ ...agent, mode: event.target.value })}>
              <option value="assist">Assist — suggest only</option>
              <option value="hybrid">Hybrid — send verified answers</option>
              <option value="autonomous">Autonomous support — same verified answers, still no refunds</option>
            </select>
          </label>
          <label className="grid gap-1 text-sm">Language
            <select className={field} value={agent.language} onChange={(event) => setAgent({ ...agent, language: event.target.value })}>
              <option value="auto">Detect English or Arabic</option>
              <option value="en">English</option>
              <option value="ar">Arabic</option>
            </select>
          </label>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <button type="button" className={button} onClick={save}>Save</button>
          <button type="button" className={ghost} onClick={() => apiPost<Agent>(agent.enabled ? "/api/v1/reach/ai/agent/disable" : "/api/v1/reach/ai/agent/enable", {}).then(setAgent)}>{agent.enabled ? "Disable replies" : "Enable replies"}</button>
        </div>
        {error ? <p className="mt-2 text-sm text-red-700">{error}</p> : null}
      </section>
      <section className="rounded-card border border-line bg-white p-4">
        <h2 className="text-lg font-semibold">Approved answers</h2>
        <p className="mt-1 text-sm text-charcoal/60">FAQs are quoted as written. Prices and stock still come from the catalog, not from this text. PDF files are not indexed.</p>
        <form
          className="mt-3 grid gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            apiPost("/api/v1/reach/ai/knowledge", { kind: "faq", title, body }).then(() => {
              setTitle("");
              setBody("");
              load();
            }).catch((err) => setError(errorMessage(err, "The agent could not be loaded.")));
          }}
        >
          <input className={field} placeholder="Title, such as Opening hours" value={title} onChange={(event) => setTitle(event.target.value)} />
          <textarea className="min-h-24 w-full rounded-xl border border-line px-3 py-2 text-sm" placeholder="Approved text" value={body} onChange={(event) => setBody(event.target.value)} />
          <button type="submit" className={button}>Add FAQ</button>
        </form>
        <ul className="mt-3 grid gap-2">
          {knowledge.map((item) => (
            <li key={item.id} className="rounded-xl border border-line px-3 py-2 text-sm">
              <div className="flex items-start justify-between gap-2">
                <span className="font-medium">{item.title}</span>
                <button type="button" className={ghost} onClick={() => apiDelete(`/api/v1/reach/ai/knowledge/${item.id}`).then(load)}>Delete</button>
              </div>
              <p className="mt-1 whitespace-pre-wrap text-charcoal/70">{item.body}</p>
            </li>
          ))}
        </ul>
      </section>
      <section className="rounded-card border border-line bg-white p-4 lg:col-span-2">
        <h2 className="text-lg font-semibold">Try a question</h2>
        <p className="mt-1 text-sm text-charcoal/60">This does not send a WhatsApp message.</p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <input className={`${field} max-w-lg`} value={trial} onChange={(event) => setTrial(event.target.value)} placeholder="Do you have USB-C Cable?" />
          <button type="button" className={button} onClick={() => apiPost<{ reply: string }>("/api/v1/reach/ai/agent/test", { body: trial }).then((found) => setAnswer(found.reply)).catch((err) => setError(errorMessage(err, "The agent could not be loaded.")))}>Ask</button>
        </div>
        {answer ? <p className="mt-3 whitespace-pre-wrap text-sm">{answer}</p> : null}
      </section>
    </div>
  );
}

export function ConversationsPanel() {
  const [rows, setRows] = useState<Conversation[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [draft, setDraft] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");

  const refresh = () => {
    apiGet<Conversation[]>("/api/v1/reach/ai/conversations").then(setRows).catch((err) => setError(errorMessage(err, "The agent could not be loaded.")));
  };

  useEffect(refresh, []);
  useEffect(() => {
    if (!selected) return;
    apiGet<Detail>(`/api/v1/reach/ai/conversations/${selected}`).then(setDetail).catch((err) => setError(errorMessage(err, "The agent could not be loaded.")));
  }, [selected]);

  return (
    <div className="grid gap-3 lg:grid-cols-[16rem_minmax(0,1fr)_16rem]">
      <aside className="max-h-[32rem] overflow-y-auto rounded-card border border-line bg-white">
        {rows.length === 0 ? <p className="p-3 text-sm text-charcoal/60">No WhatsApp conversations yet.</p> : null}
        {rows.map((row) => (
          <button key={row.id} type="button" className={`block w-full border-b border-line px-3 py-2 text-left text-sm ${selected === row.id ? "bg-accent/10" : ""}`} onClick={() => setSelected(row.id)}>
            <span className="block font-medium">{row.customer_name || row.phone}</span>
            <span className="block truncate text-charcoal/60">{row.last_preview}</span>
            <span className="text-xs text-charcoal/50">{row.handler === "human" ? "Staff" : "AI"} · {row.status}</span>
          </button>
        ))}
      </aside>
      <section className="rounded-card border border-line bg-white p-3">
        {!detail ? <p className="text-sm text-charcoal/60">Select a conversation.</p> : (
          <>
            <div className="mb-3 flex flex-wrap gap-2">
              <button type="button" className={ghost} onClick={() => apiPost(`/api/v1/reach/ai/conversations/${detail.conversation.id}/takeover`, {}).then(() => setSelected(detail.conversation.id))}>Take over</button>
              <button type="button" className={ghost} onClick={() => apiPost(`/api/v1/reach/ai/conversations/${detail.conversation.id}/resume`, {}).then(refresh)}>Resume AI</button>
              <button type="button" className={ghost} onClick={() => apiPost(`/api/v1/reach/ai/conversations/${detail.conversation.id}/resolve`, {}).then(refresh)}>Resolve</button>
            </div>
            <ol className="grid max-h-[24rem] gap-2 overflow-y-auto">
              {detail.messages.map((message) => (
                <li key={message.id} className={`max-w-[36rem] rounded-2xl px-3 py-2 text-sm ${message.direction === "note" ? "bg-amber-50" : message.author === "customer" ? "bg-charcoal/5" : "bg-accent/10"}`}>
                  <span className="text-xs text-charcoal/50">{message.author} · {message.status}{message.direction === "note" ? " · internal" : ""}</span>
                  <p className="whitespace-pre-wrap">{message.body}</p>
                </li>
              ))}
            </ol>
            <form className="mt-3 flex flex-wrap gap-2" onSubmit={(event) => {
              event.preventDefault();
              apiPost(`/api/v1/reach/ai/conversations/${detail.conversation.id}/reply`, { body: draft }).then(() => {
                setDraft("");
                apiGet<Detail>(`/api/v1/reach/ai/conversations/${detail.conversation.id}`).then(setDetail);
              }).catch((err) => setError(errorMessage(err, "The agent could not be loaded.")));
            }}>
              <input className={`${field} max-w-lg`} value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Reply as staff" />
              <button type="submit" className={button}>Send</button>
            </form>
          </>
        )}
        {error ? <p className="mt-2 text-sm text-red-700">{error}</p> : null}
      </section>
      <aside className="rounded-card border border-line bg-white p-3 text-sm">
        {!detail ? <p className="text-charcoal/60">Customer details appear here.</p> : (
          <>
            <h2 className="font-semibold">{detail.customer.name || "Unknown customer"}</h2>
            <p className="text-charcoal/60">{detail.customer.phone}</p>
            <p className="mt-2 text-charcoal/60">{detail.customer.matched ? "Matched to a customer record." : "No customer record for this number."}</p>
            {detail.customer.matched ? <p className="mt-2">Ledger balance: {detail.customer.balance_cents ?? 0} cents</p> : null}
            <p className="mt-2">Intent: {detail.conversation.intent || "—"}</p>
            <p>Priority: {detail.conversation.priority}</p>
            <form className="mt-3 grid gap-2" onSubmit={(event) => {
              event.preventDefault();
              apiPost(`/api/v1/reach/ai/conversations/${detail.conversation.id}/notes`, { body: note }).then(() => {
                setNote("");
                apiGet<Detail>(`/api/v1/reach/ai/conversations/${detail.conversation.id}`).then(setDetail);
              });
            }}>
              <textarea className="min-h-20 w-full rounded-xl border border-line px-3 py-2 text-sm" value={note} onChange={(event) => setNote(event.target.value)} placeholder="Internal note" />
              <button type="submit" className={ghost}>Add note</button>
            </form>
          </>
        )}
      </aside>
    </div>
  );
}

export function ActionsPanel() {
  const [rows, setRows] = useState<CareAction[]>([]);
  const [error, setError] = useState("");
  const load = () => apiGet<CareAction[]>("/api/v1/reach/ai/actions").then(setRows).catch((err) => setError(errorMessage(err, "The agent could not be loaded.")));
  useEffect(() => { load(); }, []);
  return (
    <section className="rounded-card border border-line bg-white p-4">
      <h2 className="text-lg font-semibold">Action Center</h2>
      <p className="mt-1 text-sm text-charcoal/60">A refund or reservation stays here until staff handle it in the existing sales tools. Completing a follow-up does not create a sale.</p>
      {rows.length === 0 ? <p className="mt-3 text-sm text-charcoal/60">No actions yet.</p> : null}
      <ul className="mt-3 grid gap-2">
        {rows.map((row) => (
          <li key={row.id} className="rounded-xl border border-line px-3 py-2 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-medium">{row.title}</span>
              <span>{row.priority} · {row.status}{row.consequential ? " · needs staff" : ""}</span>
            </div>
            <p className="mt-1 whitespace-pre-wrap text-charcoal/70">{row.details}</p>
            {row.result ? <p className="mt-1">{row.result}</p> : null}
            <div className="mt-2 flex flex-wrap gap-2">
              <button type="button" className={ghost} onClick={() => apiPost(`/api/v1/reach/ai/actions/${row.id}/approve`, {}).then(load)}>Approve</button>
              <button type="button" className={ghost} onClick={() => apiPost(`/api/v1/reach/ai/actions/${row.id}/reject`, {}).then(load)}>Reject</button>
              <button type="button" className={button} onClick={() => apiPost(`/api/v1/reach/ai/actions/${row.id}/execute`, {}).then(load).catch((err) => setError(errorMessage(err, "The agent could not be loaded.")))}>Complete</button>
            </div>
          </li>
        ))}
      </ul>
      {error ? <p className="mt-2 text-sm text-red-700">{error}</p> : null}
    </section>
  );
}
