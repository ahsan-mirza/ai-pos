import type { CSSProperties } from "react";
import { IMAGE_SETS } from "./image-sets";

type KnownSrc = keyof typeof IMAGE_SETS;

export function ResponsiveImage({
  src,
  alt,
  width,
  height,
  sizes,
  loading,
  fetchPriority,
  className,
  style,
  id,
}: {
  src: string;
  alt: string;
  width: number;
  height: number;
  sizes: string;
  loading?: "eager" | "lazy";
  fetchPriority?: "high" | "low" | "auto";
  className?: string;
  style?: CSSProperties;
  id?: string;
}) {
  const set = IMAGE_SETS[src as KnownSrc];
  const img = (
    <img
      src={src}
      alt={alt}
      width={width}
      height={height}
      loading={loading}
      fetchPriority={fetchPriority}
      decoding={fetchPriority === "high" ? "sync" : "async"}
      className={className}
      style={style}
    />
  );
  if (!set) return img;
  return (
    <picture id={id} className="site-picture">
      <source type="image/avif" srcSet={set.avif} sizes={sizes} />
      <source type="image/webp" srcSet={set.webp} sizes={sizes} />
      {img}
    </picture>
  );
}
