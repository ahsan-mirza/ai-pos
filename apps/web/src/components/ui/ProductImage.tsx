import { useEffect, useState, type ReactNode } from "react";
import { mediaSrc } from "../../lib/media";

/** A stored product photo. `data-image-state` is `missing` when the product has no URL and `failed` when the file did not load. */
export function ProductImage({
  url,
  className,
  fallback,
}: {
  url: string | null | undefined;
  className?: string;
  fallback?: ReactNode;
}) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [url]);
  if (!url || failed) {
    return (
      <span data-image-state={url ? "failed" : "missing"} className="contents">
        {fallback ?? <span className={`${className ?? ""} grid place-items-center bg-surface`} />}
      </span>
    );
  }
  return (
    <img
      src={mediaSrc(url)}
      alt=""
      data-image-state="ready"
      className={className}
      onError={() => setFailed(true)}
    />
  );
}
