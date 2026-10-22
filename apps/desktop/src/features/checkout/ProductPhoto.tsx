import { useEffect, useState, type ReactNode } from "react";

/** A product photo from the API's media URL; renders nothing when there is none or it cannot load (offline). */
export function ProductPhoto({ src, className = "" }: { src: string | null | undefined; className?: string }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [src]);
  if (!src || failed) return null;
  return <img src={src} alt="" loading="lazy" decoding="async" onError={() => setFailed(true)} className={className} />;
}

/** Top of a till card: the photo covers the frame, and a category icon shows until one loads. */
export function ProductPhotoFrame({
  src,
  icon,
  dimmed = false,
}: {
  src: string | null | undefined;
  icon: ReactNode;
  dimmed?: boolean;
}) {
  return (
    <span
      className={`relative -mx-4 -mt-4 mb-3 block aspect-[4/3] w-[calc(100%+2rem)] overflow-hidden bg-zinc-100 dark:bg-zinc-900 ${dimmed ? "opacity-60" : ""}`}
    >
      <span className="absolute inset-0 flex items-center justify-center text-zinc-400 dark:text-zinc-500">{icon}</span>
      <ProductPhoto src={src} className="absolute inset-0 h-full w-full object-cover" />
    </span>
  );
}
