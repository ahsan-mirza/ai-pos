import { useCallback, useEffect, useRef, useState } from "react";
import { DEFAULT_PAGE_SIZE, pageOffset } from "./pagination";

export interface PaginationState {
  page: number;
  pageSize: number;
  /** Zero-based offset for the API request. */
  offset: number;
  setPage: (page: number) => void;
  /** Changing the page size returns to the first page. */
  setPageSize: (pageSize: number) => void;
}

/**
 * Page state for server-side tables. Any change in `resetKeys` (filters, search, store scope) returns to page 1,
 * so a narrower result set never strands the user on an empty page.
 */
export function usePagination({
  initialPageSize = DEFAULT_PAGE_SIZE,
  resetKeys = [],
}: { initialPageSize?: number; resetKeys?: readonly unknown[] } = {}): PaginationState {
  const [page, setPage] = useState(1);
  const [pageSize, setSize] = useState(initialPageSize);
  const signature = JSON.stringify(resetKeys);
  const previous = useRef(signature);

  useEffect(() => {
    if (previous.current === signature) return;
    previous.current = signature;
    setPage(1);
  }, [signature]);

  const setPageSize = useCallback((size: number) => {
    setSize(size);
    setPage(1);
  }, []);

  return { page, pageSize, offset: pageOffset(page, pageSize), setPage, setPageSize };
}
