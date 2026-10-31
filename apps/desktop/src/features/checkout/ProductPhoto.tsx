import { useEffect, useState, type ReactNode } from "react";
import { displayPhoto, subscribePhotos } from "./productImages";

/** A product photo. Uses the copy saved on this till when one exists, and the category icon when it cannot load. */
export function ProductPhoto({ src, className = "" }: { src: string | null | undefined; className?: string }) {
  const [shown, setShown] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => subscribePhotos(() => setRevision((current) => current + 1)), []);
  useEffect(() => {
    let cancelled = false;
    setFailed(false);
    if (!src) {
      setShown(null);
      return;
    }
    void displayPhoto(src).then((url) => {
      if (!cancelled) setShown(url);
    });
    return () => {
      cancelled = true;
    };
  }, [src, revision]);
  if (!shown || failed) return null;
  return <img src={shown} alt="" loading="lazy" decoding="async" onError={() => setFailed(true)} className={className} />;
}

/** Top of a till card: every photo sits in the same frame. A category icon shows when there is no picture. */
export function ProductPhotoFrame({
  src,
  icon,
  dimmed = false,
  compact = false,
  flush = false,
}: {
  src: string | null | undefined;
  icon: ReactNode;
  dimmed?: boolean;
  compact?: boolean;
  /** The frame is already the full card width, so it does not cancel parent padding. */
  flush?: boolean;
}) {
  const inset = flush ? "w-full" : compact ? "-mx-3 -mt-3 w-[calc(100%+1.5rem)]" : "-mx-4 -mt-4 w-[calc(100%+2rem)]";
  return (
    <span
      className={`relative block shrink-0 overflow-hidden bg-zinc-100 dark:bg-zinc-900 ${flush ? "mb-0" : "mb-3"} ${inset} ${compact ? "aspect-video" : "aspect-[4/3]"} ${dimmed ? "opacity-60" : ""}`}
    >
      <span className="absolute inset-0 flex items-center justify-center text-zinc-400 dark:text-zinc-500">{icon}</span>
      <ProductPhoto
        src={src}
        className="absolute inset-0 block h-full w-full object-cover object-center"
      />
    </span>
  );
}
