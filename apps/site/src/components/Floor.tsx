import { motion } from "framer-motion";
import { useState } from "react";
import { SectionHeading } from "./SectionHeading";

const STATUSES = [
  { id: "available", label: "Available", dot: "bg-emerald-400", border: "border-emerald-400/60" },
  { id: "seated", label: "Seated", dot: "bg-cyan-400", border: "border-cyan-400/60" },
  { id: "bill", label: "Bill ready", dot: "bg-amber-300", border: "border-amber-300/60" },
  { id: "reserved", label: "Reserved", dot: "bg-violet-400", border: "border-violet-400/60" },
] as const;

type StatusId = (typeof STATUSES)[number]["id"];

const INITIAL: StatusId[][] = [
  ["available", "seated", "available", "reserved"],
  ["seated", "bill", "available", "seated"],
  ["available", "available", "reserved", "bill"],
];

function nextStatus(current: StatusId): StatusId {
  const index = STATUSES.findIndex((item) => item.id === current);
  return STATUSES[(index + 1) % STATUSES.length]?.id ?? "available";
}

export function Floor() {
  const [tables, setTables] = useState(INITIAL);

  return (
    <section id="floor" className="mx-auto max-w-page px-5 py-24 lg:px-8">
      <SectionHeading kicker="Floor" title="Tap a table. Status moves with the service." />
      <ul className="mt-6 flex flex-wrap gap-4 text-sm text-mist">
        {STATUSES.map((status) => (
          <li key={status.id} className="flex items-center gap-2">
            <span className={`h-2 w-2 rounded-full ${status.dot}`} />
            {status.label}
          </li>
        ))}
      </ul>
      <div className="mt-6 grid gap-3">
        {tables.map((row, rowIndex) => (
          <div key={rowIndex} className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {row.map((status, column) => {
              const meta = STATUSES.find((item) => item.id === status) ?? STATUSES[0];
              const number = rowIndex * 4 + column + 1;
              return (
                <motion.button
                  key={`${rowIndex}-${column}`}
                  type="button"
                  whileHover={{ y: -4 }}
                  onClick={() =>
                    setTables((current) =>
                      current.map((line, r) =>
                        line.map((cell, c) => (r === rowIndex && c === column ? nextStatus(cell) : cell)),
                      ),
                    )
                  }
                  className={`rounded-2xl border bg-white/[0.03] p-4 text-left ${meta.border}`}
                >
                  <span className="text-xs text-mist">T{number}</span>
                  <strong className="mt-3 block">{meta.label}</strong>
                </motion.button>
              );
            })}
          </div>
        ))}
      </div>
    </section>
  );
}
