export interface ScrollBox {
  scrollHeight: number;
  clientHeight: number;
  scrollTop: number;
}

/** Page keys move a bounded content region. Inputs keep their own keys. */
export function nextScrollTop(box: ScrollBox, key: string): number | null {
  const max = Math.max(0, box.scrollHeight - box.clientHeight);
  const page = Math.max(1, Math.floor(box.clientHeight * 0.9));
  if (key === "Home") return 0;
  if (key === "End") return max;
  if (key === "PageDown") return Math.min(max, box.scrollTop + page);
  if (key === "PageUp") return Math.max(0, box.scrollTop - page);
  return null;
}

export function scrollGeometry(box: ScrollBox): { overflows: boolean; footerClear: boolean; endReachesLast: boolean } {
  const overflows = box.scrollHeight > box.clientHeight;
  const max = Math.max(0, box.scrollHeight - box.clientHeight);
  return {
    overflows,
    footerClear: box.scrollTop >= 0 && box.scrollTop <= max,
    endReachesLast: box.scrollTop + box.clientHeight >= box.scrollHeight - 1,
  };
}

export const TOUCH_MIN_PX = 44;

/** The register page scrolls on an ancestor. Page keys should move that element. */
export function scrollingBox(node: HTMLElement): HTMLElement {
  let current: HTMLElement | null = node;
  while (current) {
    if (typeof getComputedStyle === "function") {
      const overflow = getComputedStyle(current).overflowY;
      if ((overflow === "auto" || overflow === "scroll") && current.scrollHeight > current.clientHeight + 1) return current;
    }
    current = current.parentElement;
  }
  return node;
}
