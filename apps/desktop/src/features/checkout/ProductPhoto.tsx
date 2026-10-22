import { useEffect, useState } from "react";

/** A product photo from the API's media URL; renders nothing when there is none or it cannot load (offline). */
export function ProductPhoto({ src, className = "" }: { src: string | null | undefined; className?: string }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [src]);
  if (!src || failed) return null;
  return <img src={src} alt="" loading="lazy" decoding="async" onError={() => setFailed(true)} className={className} />;
}
