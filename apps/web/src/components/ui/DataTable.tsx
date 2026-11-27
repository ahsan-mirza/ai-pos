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
  RowActionsMenu,
  TableToolbar,
  usePagination,
  type ClientPagination,
  type DataTableColumn,
  type DataTablePagination,
  type DataTableProps,
  type RowActionItem,
  type ServerPagination,
  type TableFilter,
  type TableToolbarProps,
} from "@ai-pos/ui";
