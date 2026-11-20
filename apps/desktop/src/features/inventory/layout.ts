/** Inventory workspace stays inside the register pane at 1024×768. */
export const inventoryWorkspaceClass = "flex min-h-full w-full min-w-0 max-w-full flex-col gap-4 p-4";

/** Tabs wrap onto extra rows instead of being clipped past the window edge. */
export const inventoryTabListClass = "flex min-w-0 max-w-full flex-wrap gap-2";

/** Tables scroll inside the pane. Cells wrap so a long SKU does not widen the window. */
export const inventoryTableFrameClass = "max-w-full min-w-0 overflow-x-auto rounded-xl ring-1 ring-zinc-200 dark:ring-zinc-800";
export const inventoryTableClass = "w-full min-w-0 text-left text-sm";
