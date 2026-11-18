import { DataTable, type DataTableColumn } from "@ai-pos/ui";
import { useEffect, useState } from "react";
import { PageHeader } from "../../components/PageHeader";
import { ErrorNote, Field, GhostButton, PrimaryButton } from "../../components/ui";
import { api, errorText } from "../../lib/api";
import { when } from "../../lib/format";
import { ENQUIRY_STATUSES, type CatalogEnquiry } from "./types";

export function HardwareEnquiriesPage() {
  const [rows, setRows] = useState<CatalogEnquiry[]>([]);
  const [selected, setSelected] = useState<CatalogEnquiry | null>(null);
  const [status, setStatus] = useState("");
  const [query, setQuery] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");

  function load(enquiryId?: string) {
    const params = new URLSearchParams({ limit: "100" });
    if (status) params.set("status", status);
    if (query.trim()) params.set("q", query.trim());
    api
      .page<CatalogEnquiry>(`/hardware-catalog/enquiries?${params}`)
      .then((found) => {
        setRows(found.rows);
        if (enquiryId) setSelected(found.rows.find((row) => row.id === enquiryId) ?? null);
      })
      .catch((caught) => setError(errorText(caught, "Enquiries could not be loaded.")));
  }

  useEffect(() => {
    load();
  }, [status]);

  async function open(id: string) {
    try {
      setSelected(await api.get<CatalogEnquiry>(`/hardware-catalog/enquiries/${id}`));
    } catch (caught) {
      setError(errorText(caught, "The enquiry could not be opened."));
    }
  }

  async function updateStatus(next: string) {
    if (!selected) return;
    try {
      const row = await api.put<CatalogEnquiry>(`/hardware-catalog/enquiries/${selected.id}`, { status: next, reason: `Status ${next}` });
      setSelected(row);
      load(row.id);
    } catch (caught) {
      setError(errorText(caught, "The status could not be updated."));
    }
  }

  async function addNote() {
    if (!selected || note.trim().length < 1) return;
    try {
      const row = await api.post<CatalogEnquiry>(`/hardware-catalog/enquiries/${selected.id}/notes`, { body: note.trim(), reason: "Internal note" });
      setSelected(row);
      setNote("");
    } catch (caught) {
      setError(errorText(caught, "The note could not be saved."));
    }
  }

  const columns: DataTableColumn<CatalogEnquiry>[] = [
    { id: "ref", header: "Reference", cell: (row) => row.enquiry_reference },
    { id: "customer", header: "Customer", cell: (row) => row.customer_name },
    { id: "business", header: "Business", cell: (row) => row.business_name },
    { id: "interest", header: "Interest", cell: (row) => row.product_label || row.package_label || row.enquiry_type },
    { id: "status", header: "Status", cell: (row) => row.status },
    { id: "created", header: "Received", cell: (row) => when(row.created_at) },
    { id: "open", header: "Actions", cell: (row) => <GhostButton onClick={() => open(row.id)}>Open</GhostButton> },
  ];

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
      <div>
        <PageHeader title="Enquiries" description="Website quotation requests. Updating a status does not create a store." />
        <ErrorNote message={error} />
        <div className="mb-4 flex flex-wrap gap-2">
          <input aria-label="Search enquiries" value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") load(); }} placeholder="Search name, email, or reference" className="h-10 w-full max-w-sm rounded-xl border border-line px-3 text-sm" />
          <select aria-label="Enquiry status" value={status} onChange={(event) => setStatus(event.target.value)} className="h-10 rounded-xl border border-line px-3 text-sm">
            <option value="">All statuses</option>
            {ENQUIRY_STATUSES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </div>
        <DataTable aria-label="Hardware enquiries" columns={columns} data={rows} getRowId={(row) => row.id} emptyState={{ title: "No enquiries", description: "Requests from the website appear here." }} />
      </div>
      {selected ? (
        <aside className="rounded-2xl border border-line bg-card p-4 text-sm">
          <p className="font-semibold">{selected.enquiry_reference}</p>
          <p className="mt-2">{selected.customer_name}</p>
          <p>{selected.business_name}</p>
          <p>{selected.email}</p>
          <p>{selected.phone}</p>
          <p className="mt-2 text-charcoal/60">{selected.country} · {selected.business_type}</p>
          <p className="mt-2">Quantity {selected.quantity}</p>
          <p className="mt-2 whitespace-pre-wrap">{selected.message}</p>
          <label className="mt-4 block font-medium">
            Status
            <select aria-label="Update enquiry status" className="mt-1 h-10 w-full rounded-xl border border-line px-3" value={selected.status} onChange={(event) => updateStatus(event.target.value)}>
              {ENQUIRY_STATUSES.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <ul className="mt-4 space-y-2">
            {selected.notes.map((item) => (
              <li key={item.id} className="rounded-xl bg-surface px-3 py-2">
                <p>{item.body}</p>
                <p className="text-xs text-charcoal/50">{item.operator_name} · {when(item.created_at)}</p>
              </li>
            ))}
          </ul>
          <Field label="Internal note" multiline value={note} onChange={(event) => setNote(event.target.value)} />
          <PrimaryButton className="mt-3" onClick={addNote}>
            Add note
          </PrimaryButton>
        </aside>
      ) : null}
    </div>
  );
}
