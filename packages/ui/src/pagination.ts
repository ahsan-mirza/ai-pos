export const PAGE_SIZE_OPTIONS = [10, 25, 50, 100] as const;
export const DEFAULT_PAGE_SIZE = 25;

export type PageItem = number | "ellipsis-start" | "ellipsis-end";

export function pageCount(totalRecords: number, pageSize: number): number {
  if (pageSize <= 0) return 1;
  return Math.max(1, Math.ceil(Math.max(0, totalRecords) / pageSize));
}

export function clampPage(page: number, totalPages: number): number {
  if (!Number.isFinite(page)) return 1;
  return Math.min(Math.max(1, Math.trunc(page)), Math.max(1, totalPages));
}

/** Zero-based row offset for a one-based page, as sent to the API (`offset` / `skip`). */
export function pageOffset(page: number, pageSize: number): number {
  return (Math.max(1, page) - 1) * pageSize;
}

/** "Showing {from} to {to} of {total}"; both bounds are 0 when there are no records. */
export function pageRange(page: number, pageSize: number, totalRecords: number): { from: number; to: number } {
  if (totalRecords <= 0) return { from: 0, to: 0 };
  const from = pageOffset(page, pageSize) + 1;
  return { from: Math.min(from, totalRecords), to: Math.min(from + pageSize - 1, totalRecords) };
}

/**
 * Page buttons with ellipses, always showing the first and last page and `siblings` pages either side of the
 * current one. The list keeps a constant length once there are enough pages, so the controls do not jump.
 */
export function pageWindow(currentPage: number, totalPages: number, siblings = 1): PageItem[] {
  const total = Math.max(1, totalPages);
  const current = clampPage(currentPage, total);
  const slots = siblings * 2 + 5;
  if (total <= slots) return Array.from({ length: total }, (_, index) => index + 1);

  const left = Math.max(current - siblings, 1);
  const right = Math.min(current + siblings, total);
  const showStart = left > 3;
  const showEnd = right < total - 2;
  const edge = siblings * 2 + 3;

  if (!showStart && showEnd) {
    return [...Array.from({ length: edge }, (_, index) => index + 1), "ellipsis-end", total];
  }
  if (showStart && !showEnd) {
    return [1, "ellipsis-start", ...Array.from({ length: edge }, (_, index) => total - edge + index + 1)];
  }
  return [
    1,
    "ellipsis-start",
    ...Array.from({ length: right - left + 1 }, (_, index) => left + index),
    "ellipsis-end",
    total,
  ];
}
