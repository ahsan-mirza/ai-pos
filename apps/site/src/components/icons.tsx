import type { ReactNode } from "react";

const PATHS = {
  utensils: (
    <>
      <path d="M4 3v8a3 3 0 0 0 3 3v7" />
      <path d="M7 3v8" />
      <path d="M10 3v8" />
      <path d="M17 3c-1.5 2-2 4-2 6a3 3 0 0 0 3 3v9" />
    </>
  ),
  coffee: (
    <>
      <path d="M5 8h11v5a4 4 0 0 1-4 4H9a4 4 0 0 1-4-4V8z" />
      <path d="M16 9h2a3 3 0 0 1 0 6h-2" />
      <path d="M8 3v2" />
      <path d="M12 3v2" />
    </>
  ),
  bag: (
    <>
      <path d="M6 8h12l-1 12H7L6 8z" />
      <path d="M9 8V6a3 3 0 0 1 6 0v2" />
    </>
  ),
  boxes: (
    <>
      <path d="M3 7h8v6H3z" />
      <path d="M13 7h8v6h-8z" />
      <path d="M8 14h8v5H8z" />
    </>
  ),
  shirt: (
    <>
      <path d="M8 4l4 2 4-2 4 3-2 3h-2v10H8V10H6L4 7l4-3z" />
    </>
  ),
  phone: (
    <>
      <rect x="7" y="2" width="10" height="20" rx="2" />
      <path d="M11 18h2" />
    </>
  ),
  card: (
    <>
      <rect x="2" y="5" width="20" height="14" rx="2" />
      <path d="M2 10h20" />
      <path d="M6 15h4" />
    </>
  ),
  warehouse: (
    <>
      <path d="M3 10l9-6 9 6" />
      <path d="M5 10v10h14V10" />
      <path d="M10 20v-6h4v6" />
    </>
  ),
  chart: (
    <>
      <path d="M4 19V5" />
      <path d="M4 19h16" />
      <path d="M8 15l3-4 3 2 4-6" />
    </>
  ),
  users: (
    <>
      <circle cx="9" cy="8" r="3" />
      <path d="M3 19c1-3 3-4.5 6-4.5s5 1.5 6 4.5" />
      <circle cx="17" cy="9" r="2" />
      <path d="M17 14.5c2 .4 3.2 1.5 4 3.5" />
    </>
  ),
  stores: (
    <>
      <path d="M3 10l2-5h14l2 5" />
      <path d="M4 10v9h16v-9" />
      <path d="M9 19v-5h6v5" />
    </>
  ),
  key: (
    <>
      <circle cx="8" cy="14" r="4" />
      <path d="M11.5 12.5L20 4" />
      <path d="M16 6l2 2" />
      <path d="M18 8l2 2" />
    </>
  ),
  spark: (
    <>
      <path d="M12 3l1.6 5.2L19 10l-5.4 1.8L12 17l-1.6-5.2L5 10l5.4-1.8L12 3z" />
      <path d="M18 15l.6 1.8L20.5 17.5 18.6 18.1 18 20l-.6-1.9-1.9-.6 1.9-.7L18 15z" />
    </>
  ),
  tag: (
    <>
      <path d="M3 12V4h8l10 10-8 8L3 12z" />
      <circle cx="7.5" cy="7.5" r="1" />
    </>
  ),
  setup: (
    <>
      <path d="M4 20V9l8-5 8 5v11" />
      <path d="M9 20v-6h6v6" />
    </>
  ),
  till: (
    <>
      <rect x="3" y="4" width="18" height="12" rx="2" />
      <path d="M7 20h10" />
      <path d="M12 16v4" />
      <path d="M7 8h4" />
    </>
  ),
  growth: (
    <>
      <path d="M4 18l6-6 3 3 7-8" />
      <path d="M14 7h6v6" />
    </>
  ),
  receipt: (
    <>
      <path d="M6 3h12v18l-2-1.5L14 21l-2-1.5L10 21l-2-1.5L6 21V3z" />
      <path d="M9 8h6" />
      <path d="M9 12h6" />
    </>
  ),
  package: (
    <>
      <path d="M3 8l9-4 9 4-9 4-9-4z" />
      <path d="M3 8v8l9 4 9-4V8" />
      <path d="M12 12v8" />
    </>
  ),
  zap: (
    <>
      <path d="M13 2L4 14h7l-1 8 9-12h-7l1-8z" />
    </>
  ),
  folder: (
    <>
      <path d="M3 7h6l2 2h10v10H3V7z" />
    </>
  ),
  layers: (
    <>
      <path d="M12 3l9 5-9 5-9-5 9-5z" />
      <path d="M3 13l9 5 9-5" />
    </>
  ),
  check: <path d="M5 12l5 5L20 7" />,
} as const;

export type MarkName = keyof typeof PATHS;

export function Mark({ name, className = "h-6 w-6" }: { name: MarkName; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      {PATHS[name] as ReactNode}
    </svg>
  );
}

export function IconBadge({ name }: { name: MarkName }) {
  return (
    <span className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
      <Mark name={name} />
    </span>
  );
}
