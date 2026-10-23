import { useEffect, useId, useState } from "react";
import { motion } from "framer-motion";

const TYPES = ["Restaurant", "Supermarket", "Retail", "Cafe"] as const;
const MODES = [
  { id: "onsite", name: "On-site, in person", copy: "A specialist comes to the shop with a register." },
  { id: "virtual", name: "Virtual walkthrough", copy: "A screen share through the floor, the till, and go-live." },
] as const;
const TIMES = ["10:00", "13:00", "16:00"] as const;

function upcomingDays(): Date[] {
  const start = new Date();
  start.setDate(start.getDate() + 1);
  start.setHours(12, 0, 0, 0);
  return Array.from({ length: 5 }, (_, index) => {
    const day = new Date(start);
    day.setDate(start.getDate() + index);
    return day;
  });
}

export function DemoModal({ onClose }: { onClose: () => void }) {
  const titleId = useId();
  const days = useState(upcomingDays)[0];
  const [step, setStep] = useState(0);
  const [type, setType] = useState<(typeof TYPES)[number]>("Restaurant");
  const [mode, setMode] = useState<(typeof MODES)[number]["id"]>("virtual");
  const [day, setDay] = useState(0);
  const [time, setTime] = useState<(typeof TIMES)[number]>("10:00");
  const titles = ["Business type", "How you want the demo", "Date and time", "Request held on this page"];
  const chosenMode = MODES.find((item) => item.id === mode);
  const chosenDay = days[day] ?? days[0];

  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-40 grid place-items-center bg-[#04080e]/75 p-4" onClick={onClose} role="presentation">
      <motion.div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={(event) => event.stopPropagation()}
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        className="max-h-[min(640px,100%)] w-full max-w-xl overflow-auto rounded-2xl border border-white/10 bg-[#101826] p-5 shadow-none"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.16em] text-glow">Book a demo</p>
            <h2 id={titleId} className="mt-1 text-2xl font-semibold tracking-tight">
              {titles[step]}
            </h2>
          </div>
          <button type="button" onClick={onClose} className="rounded-full border border-white/15 px-3 py-1.5 text-sm">
            Close
          </button>
        </div>
        <p className="mt-2 text-sm text-mist">
          Step {step + 1} of {titles.length}
        </p>

        {step === 0 && (
          <div className="mt-4 grid grid-cols-2 gap-2">
            {TYPES.map((item) => (
              <button key={item} type="button" onClick={() => setType(item)} className={choice(type === item)}>
                {item}
              </button>
            ))}
          </div>
        )}

        {step === 1 && (
          <div className="mt-4 grid gap-2">
            {MODES.map((item) => (
              <button key={item.id} type="button" onClick={() => setMode(item.id)} className={choice(mode === item.id)}>
                <span className="block font-semibold">{item.name}</span>
                <span className="mt-1 block text-sm font-normal text-mist">{item.copy}</span>
              </button>
            ))}
          </div>
        )}

        {step === 2 && chosenDay && (
          <div className="mt-4">
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {days.map((date, index) => (
                <button key={date.toISOString()} type="button" onClick={() => setDay(index)} className={choice(day === index)}>
                  {date.toLocaleDateString("en-AE", { weekday: "short", day: "numeric", month: "short" })}
                </button>
              ))}
            </div>
            <div className="mt-2 grid grid-cols-3 gap-2">
              {TIMES.map((slot) => (
                <button key={slot} type="button" onClick={() => setTime(slot)} className={choice(time === slot)}>
                  {slot} GST
                </button>
              ))}
            </div>
          </div>
        )}

        {step === 3 && chosenDay && (
          <p className="mt-4 rounded-xl border border-white/10 bg-white/[0.03] p-4 text-sm leading-6 text-mist">
            {type} · {chosenMode?.name ?? "Virtual walkthrough"} ·{" "}
            {chosenDay.toLocaleDateString("en-AE", { weekday: "long", day: "numeric", month: "long" })} at {time} GST.
            This request stays in the browser. It is not sent to the console.
          </p>
        )}

        <div className="mt-5 flex justify-between">
          <button
            type="button"
            className="rounded-full border border-white/15 px-4 py-2 text-sm disabled:opacity-40"
            disabled={step === 0}
            onClick={() => setStep((current) => current - 1)}
          >
            Back
          </button>
          {step < titles.length - 1 ? (
            <button type="button" className="rounded-full bg-cyan-400 px-4 py-2 text-sm font-semibold text-ink" onClick={() => setStep((current) => current + 1)}>
              Continue
            </button>
          ) : (
            <button type="button" className="rounded-full bg-cyan-400 px-4 py-2 text-sm font-semibold text-ink" onClick={onClose}>
              Done
            </button>
          )}
        </div>
      </motion.div>
    </div>
  );
}

function choice(selected: boolean): string {
  return `rounded-xl border px-3 py-3 text-left text-sm ${
    selected ? "border-cyan-400 bg-cyan-400/15" : "border-white/10 bg-transparent"
  }`;
}
