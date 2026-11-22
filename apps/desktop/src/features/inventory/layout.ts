/** Inventory workspace stays inside the register pane. The tab row is full width and does not widen it. */
export const inventoryWorkspaceClass = "flex min-h-full w-full min-w-0 max-w-full flex-col";

/** Panel body scrolls with the register pane. It stays inside the pane while the tab row scrolls sideways. */
export const inventoryContentClass = "flex min-w-0 max-w-full flex-col gap-4 p-4";

/** Tables scroll inside the pane. Cells wrap so a long SKU does not widen the window. */
export const inventoryTableFrameClass = "max-w-full min-w-0 overflow-x-auto rounded-xl ring-1 ring-zinc-200 dark:ring-zinc-800";
export const inventoryTableClass = "w-full min-w-0 text-left text-sm";
