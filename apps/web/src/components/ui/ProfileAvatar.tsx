import { useEffect, useState } from "react";

function initialsOf(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

/** The user's photo when the API has one. Initials stay when the photo is missing or the file fails to load. */
export function ProfileAvatar({
  name,
  url,
  className = "h-9 w-9",
  tone = "accent",
}: {
  name: string;
  url?: string | null;
  className?: string;
  tone?: "accent" | "ink";
}) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [url]);
  if (url && !failed) {
    return (
      <img
        src={url}
        alt=""
        className={`${className} shrink-0 rounded-full object-cover ring-1 ring-accent/20`}
        onError={() => setFailed(true)}
      />
    );
  }
  const toneClass =
    tone === "ink"
      ? "bg-charcoal text-xs font-semibold text-white"
      : "bg-accent/10 text-[11px] font-bold text-accent ring-1 ring-accent/20";
  return (
    <span className={`${className} flex shrink-0 items-center justify-center rounded-full ${toneClass}`}>
      {initialsOf(name)}
    </span>
  );
}
