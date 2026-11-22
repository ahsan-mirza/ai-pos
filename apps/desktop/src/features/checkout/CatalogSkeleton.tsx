import type { CatalogDensity } from "../../components/RegisterLayout";
import { catalogueLayoutClass } from "./cataloguePresentation";
import type { CatalogueView } from "./cataloguePreference";

/** Product-card placeholders. No names, prices, or stock — those stay blank until a real catalogue arrives. */
export function CatalogSkeleton({ density, view = "grid" }: { density: CatalogDensity; view?: CatalogueView }) {
  const image = view === "list" ? "h-12 w-12" : "h-[var(--pos-product-image-height)]";
  const layout = catalogueLayoutClass(view);
  return (
    <ul className={layout} aria-busy="true" aria-label="Loading products" data-density={density}>
      {Array.from({ length: 8 }, (_, index) => (
        <li
          key={index}
          className="flex h-auto w-full min-w-0 flex-col overflow-hidden rounded-2xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-800/40"
        >
          <span className={`block w-full shrink-0 animate-pulse bg-zinc-200 motion-reduce:animate-none dark:bg-zinc-700 ${image}`} />
          <span className="space-y-2 px-3 py-2.5">
            <span className="block h-3 w-16 animate-pulse rounded bg-zinc-200 motion-reduce:animate-none dark:bg-zinc-700" />
            <span className="block h-10 animate-pulse rounded bg-zinc-200 motion-reduce:animate-none dark:bg-zinc-700" />
            <span className="flex items-center justify-between gap-2">
              <span className="block h-5 w-20 animate-pulse rounded bg-zinc-200 motion-reduce:animate-none dark:bg-zinc-700" />
              <span className="block h-7 w-16 animate-pulse rounded-full bg-zinc-200 motion-reduce:animate-none dark:bg-zinc-700" />
            </span>
          </span>
          <span className="h-[var(--pos-product-footer-height)] border-t border-zinc-200 dark:border-zinc-800" />
        </li>
      ))}
    </ul>
  );
}
