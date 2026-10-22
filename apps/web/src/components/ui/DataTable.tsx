/**
 * The portal's data table. Implemented once in `@ai-pos/ui` and shared with the register app.
 *
 * Server mode: the page owns `usePagination()` and fetches `offset` + `limit` from the API (`apiGetPage`).
 * Client mode: pass every row; the table slices pages itself.
 */
export {
  DataTable,
  PaginationFooter,
  PAGE_SIZE_OPTIONS,
  usePagination,
  type ClientPagination,
  type DataTableColumn,
  type DataTablePagination,
  type DataTableProps,
  type ServerPagination,
} from "@ai-pos/ui";
