import type { StaffTimesheet, TimeEntry, TimesheetReport, User } from "@ai-pos/shared-types";
import { ChevronDown, ChevronRight, Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { ErrorNote, FilterSelect, GhostButton, PrimaryButton, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { apiGet, apiPost, apiPut } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { errorMessage, usersApi } from "../users/api";

const iso = (value: Date) => value.toISOString().slice(0, 10);
const weekStart = () => {
  const now = new Date();
  const monday = new Date(now);
  monday.setDate(now.getDate() - ((now.getDay() + 6) % 7));
  return iso(monday);
};
export const hours = (minutes: number) => `${Math.floor(minutes / 60)}h ${String(minutes % 60).padStart(2, "0")}m`;
const when = (value: string) =>
  new Date(value).toLocaleString(undefined, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const toLocal = (value: string | null) => {
  if (!value) return "";
  const date = new Date(value);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
};

export function TimesheetsTab({ onToast }: { onToast: (text: string) => void }) {
  const [from, setFrom] = useState(weekStart());
  const [to, setTo] = useState(iso(new Date()));
  const [report, setReport] = useState<TimesheetReport | null>(null);
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [editing, setEditing] = useState<{ entry: TimeEntry | null; person: StaffTimesheet | null } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setReport(await apiGet<TimesheetReport>(`/api/v1/timesheets?from=${from}&to=${to}`));
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "Could not load timesheets."));
    }
  }, [from, to]);

  useEffect(() => {
    void load();
  }, [load]);

  const approve = async (person: StaffTimesheet) => {
    const ids = person.entries.filter((entry) => entry.status === "CLOSED").map((entry) => entry.id);
    try {
      const result = await apiPost<{ approved: number }>("/api/v1/timesheets/approve", { entry_ids: ids });
      onToast(`${result.approved} entr${result.approved === 1 ? "y" : "ies"} approved for ${person.name}.`);
      void load();
    } catch (caught) {
      setError(errorMessage(caught, "Could not approve."));
    }
  };

  const staff = report?.staff ?? [];
  const totalMinutes = staff.reduce((sum, row) => sum + row.worked_minutes, 0);
  const overtime = staff.reduce((sum, row) => sum + row.overtime_minutes, 0);
  const pending = staff.reduce((sum, row) => sum + row.pending_approval, 0);

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-3">
        <article className="rounded-card bg-charcoal p-6 text-white">
          <p className="text-sm text-white/60">Hours worked</p>
          <p className="mt-4 text-3xl font-semibold tabular-nums">{hours(totalMinutes)}</p>
          <p className="mt-2 text-xs text-white/50">{staff.length} people clocked in this period</p>
        </article>
        <article className="rounded-card bg-accent p-6 text-white">
          <p className="text-sm text-white/80">Overtime</p>
          <p className="mt-4 text-3xl font-semibold tabular-nums">{hours(overtime)}</p>
          <p className="mt-2 text-xs text-white/80">Beyond {report?.daily_hours ?? 8} hours in a day</p>
        </article>
        <article className="rounded-card border border-line bg-white p-6">
          <p className="text-sm text-charcoal/60">Waiting for approval</p>
          <p className="mt-4 text-3xl font-semibold tabular-nums">{pending}</p>
          <p className="mt-2 text-xs text-charcoal/50">Only approved time reaches payroll</p>
        </article>
      </div>

      <div className="rounded-card border border-line bg-white p-6">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold">Timesheets</h2>
            <p className="text-sm text-charcoal/60">Clocked at the registers with each person's PIN. Correct mistakes with a note, then approve.</p>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <TextField label="From" type="date" value={from} onChange={(event) => setFrom(event.target.value)} />
            <TextField label="To" type="date" value={to} onChange={(event) => setTo(event.target.value)} />
            <GhostButton onClick={() => setEditing({ entry: null, person: null })}>
              <Plus size={15} aria-hidden="true" className="-ml-1 mr-1.5" /> Add time
            </GhostButton>
          </div>
        </div>
        <ErrorNote message={error} />
        <table className="w-full text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-charcoal/50">
            <tr>
              <th className="pb-2 font-medium">Person</th>
              <th className="pb-2 text-right font-medium">Days</th>
              <th className="pb-2 text-right font-medium">Worked</th>
              <th className="pb-2 text-right font-medium">Overtime</th>
              <th className="pb-2 pl-6 font-medium">Status</th>
              <th className="pb-2" />
            </tr>
          </thead>
          <tbody>
            {staff.map((person) => {
              const expanded = open.has(person.user_id);
              return [
                <tr key={person.user_id} className="border-t border-line">
                  <td className="py-3">
                    <button
                      type="button"
                      onClick={() =>
                        setOpen((current) => {
                          const next = new Set(current);
                          if (next.has(person.user_id)) next.delete(person.user_id);
                          else next.add(person.user_id);
                          return next;
                        })
                      }
                      className="flex items-center gap-1.5 text-left font-medium hover:text-accent"
                    >
                      {expanded ? <ChevronDown size={14} aria-hidden="true" /> : <ChevronRight size={14} aria-hidden="true" />}
                      {person.name}
                    </button>
                    <span className="block pl-5 text-xs text-charcoal/50">{person.role_name}</span>
                  </td>
                  <td className="py-3 text-right tabular-nums">{person.days_worked}</td>
                  <td className="py-3 text-right font-semibold tabular-nums">{hours(person.worked_minutes)}</td>
                  <td className={`py-3 text-right tabular-nums ${person.overtime_minutes ? "text-accent" : "text-charcoal/40"}`}>
                    {hours(person.overtime_minutes)}
                  </td>
                  <td className="py-3 pl-6 text-xs text-charcoal/60">
                    {person.open_entries ? <span className="mr-2 font-semibold text-accent">{person.open_entries} on the clock</span> : null}
                    {person.pending_approval ? `${person.pending_approval} to approve` : "All approved"}
                  </td>
                  <td className="py-3 text-right">
                    {person.pending_approval ? (
                      <button
                        type="button"
                        onClick={() => void approve(person)}
                        className="rounded-full bg-accent px-3 py-1.5 text-xs font-semibold text-white hover:bg-accent-hover"
                      >
                        Approve
                      </button>
                    ) : null}
                  </td>
                </tr>,
                expanded
                  ? person.entries.map((entry) => (
                      <tr key={entry.id} className="bg-surface/50 text-xs">
                        <td className="py-2 pl-6">
                          {when(entry.clock_in_at)} → {entry.clock_out_at ? new Date(entry.clock_out_at).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }) : "still clocked in"}
                          <span className="block text-charcoal/50">
                            {entry.store_code}
                            {entry.break_minutes ? ` · ${entry.break_minutes} min break` : ""}
                            {entry.edit_note ? ` · edited by ${entry.edited_by_name ?? "a manager"}: ${entry.edit_note}` : ""}
                          </span>
                        </td>
                        <td />
                        <td className="py-2 text-right tabular-nums">{hours(entry.worked_minutes)}</td>
                        <td className="py-2 text-right tabular-nums">{entry.overtime_minutes ? hours(entry.overtime_minutes) : ""}</td>
                        <td className="py-2 pl-6">
                          {entry.forgotten ? <span className="font-semibold text-accent">Forgot to clock out?</span> : entry.status === "APPROVED" ? `Approved by ${entry.approved_by_name ?? ""}` : entry.status === "OPEN" ? "On the clock" : "Closed"}
                        </td>
                        <td className="py-2 text-right">
                          {entry.status !== "APPROVED" ? (
                            <button type="button" onClick={() => setEditing({ entry, person })} className="font-semibold text-accent">
                              Correct
                            </button>
                          ) : null}
                        </td>
                      </tr>
                    ))
                  : null,
              ];
            })}
          </tbody>
        </table>
        {report && staff.length === 0 ? <p className="py-8 text-sm text-charcoal/60">Nobody clocked in during this period.</p> : null}
      </div>
      {editing ? (
        <EntryModal
          entry={editing.entry}
          person={editing.person}
          onClose={() => setEditing(null)}
          onSaved={(text) => {
            setEditing(null);
            onToast(text);
            void load();
          }}
        />
      ) : null}
    </div>
  );
}

function EntryModal({
  entry,
  person,
  onClose,
  onSaved,
}: {
  entry: TimeEntry | null;
  person: StaffTimesheet | null;
  onClose: () => void;
  onSaved: (text: string) => void;
}) {
  const { user } = useAuth();
  const [people, setPeople] = useState<User[]>([]);
  const [userId, setUserId] = useState(person?.user_id ?? "");
  const [clockIn, setClockIn] = useState(toLocal(entry?.clock_in_at ?? null));
  const [clockOut, setClockOut] = useState(toLocal(entry?.clock_out_at ?? null));
  const [breakMinutes, setBreakMinutes] = useState(String(entry?.break_minutes ?? 0));
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (entry) return;
    usersApi
      .list()
      .then(setPeople)
      .catch(() => setPeople([]));
  }, [entry]);

  const save = async () => {
    if (!clockIn || !clockOut || note.trim().length < 3) return setError("Enter both times and a note explaining the change.");
    const body = {
      clock_in_at: new Date(clockIn).toISOString(),
      clock_out_at: new Date(clockOut).toISOString(),
      break_minutes: Number(breakMinutes) || 0,
      note: note.trim(),
    };
    try {
      if (entry) {
        await apiPut(`/api/v1/timesheets/entries/${entry.id}`, body);
        onSaved("Time entry corrected.");
      } else {
        const chosen = people.find((row) => row.id === userId);
        if (!chosen) return setError("Choose the person.");
        await apiPost("/api/v1/timesheets/entries", { ...body, user_id: userId, store_id: chosen.store_id ?? user?.store_id });
        onSaved(`Time added for ${chosen.full_name}.`);
      }
    } catch (caught) {
      setError(errorMessage(caught, "Could not save the time entry."));
    }
  };

  return (
    <Modal
      title={entry ? `Correct ${person?.name ?? ""}'s time` : "Add time"}
      subtitle={entry ? "The original register times are replaced; your note is kept on the entry." : "For a shift someone forgot to clock."}
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton onClick={() => void save()}>Save</PrimaryButton>
        </>
      }
    >
      <div className="space-y-4">
        {entry ? null : (
          <FilterSelect
            label="Person"
            value={userId}
            options={people.filter((row) => row.store_id).map((row) => ({ value: row.id, label: row.full_name, hint: row.role.name }))}
            onChange={setUserId}
          />
        )}
        <div className="grid gap-4 md:grid-cols-2">
          <TextField label="Clocked in" type="datetime-local" value={clockIn} onChange={(event) => setClockIn(event.target.value)} />
          <TextField label="Clocked out" type="datetime-local" value={clockOut} onChange={(event) => setClockOut(event.target.value)} />
        </div>
        <TextField label="Unpaid break (minutes)" inputMode="numeric" value={breakMinutes} onChange={(event) => setBreakMinutes(event.target.value.replace(/\D/g, ""))} />
        <TextField label="Why" value={note} maxLength={255} placeholder="Left early, approved by me" onChange={(event) => setNote(event.target.value)} />
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}
