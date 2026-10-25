type BrandVariant = "wordmark" | "mark";
/** light backgrounds use the ink logo. dark backgrounds use the white logo. auto follows the register theme. */
type BrandTone = "auto" | "light" | "dark";

const FILES = {
  wordmark: { light: "logo.svg", dark: "logo-white.svg" },
  mark: { light: "fav-icon.svg", dark: "fav-icon-white.svg" },
} as const;

function brandSrc(file: string): string {
  const base = import.meta.env.BASE_URL || "/";
  return `${base.endsWith("/") ? base : `${base}/`}brand/${file}`;
}

/** The company wordmark, or the A mark used as the favicon. */
export function BrandLogo({
  variant = "wordmark",
  tone = "auto",
  className = "",
  alt = "QIOS",
}: {
  variant?: BrandVariant;
  tone?: BrandTone;
  className?: string;
  alt?: string;
}) {
  const files = FILES[variant];
  if (tone === "light") {
    return <img src={brandSrc(files.light)} alt={alt} className={`object-contain ${className}`} />;
  }
  if (tone === "dark") {
    return <img src={brandSrc(files.dark)} alt={alt} className={`object-contain ${className}`} />;
  }
  return (
    <span className={`inline-flex items-center ${className}`}>
      <img src={brandSrc(files.light)} alt={alt} className="h-full max-h-full w-auto max-w-full object-contain dark:hidden" />
      <img src={brandSrc(files.dark)} alt="" aria-hidden="true" className="hidden h-full max-h-full w-auto max-w-full object-contain dark:block" />
    </span>
  );
}
