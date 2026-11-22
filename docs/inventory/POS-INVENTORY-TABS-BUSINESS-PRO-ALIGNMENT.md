# POS inventory tabs — Business Pro alignment

Date: 21 November 2026.

Final status: **PASSED WITH LIMITATIONS**

The Windows POS Inventory & Stock tabs now use the same underline navigation as Business Pro. Inventory APIs, stock behaviour, permissions, and Business Pro were left unchanged. Nothing was deployed.

## Components changed

- `apps/desktop/src/features/inventory/InventoryTabNavigation.tsx` renders the register tab row through `AxizTabs` from `@ai-pos/ui`. It does not keep its own selection.
- `apps/desktop/src/features/inventory/InventoryPage.tsx` passes the existing tab id into that row. The same `inventoryTabs` list and the same panel switch decide what opens.
- `apps/desktop/src/features/inventory/layout.ts` keeps the workspace inside the pane. The tab strip is full width. Panel content stays in a padded column that cannot widen the window.
- Tests: `InventoryTabNavigation.test.tsx`, `layout.test.ts`, and `packages/ui/src/AxizTabs.test.tsx`.

`AxizTabs` itself was not restyled. Business Pro inventory already uses it.

## Styling removed

The POS row no longer uses:

- a filled orange active pill (`bg-primary-500 text-white`)
- rounded outlined inactive pills (`rounded-xl`, `ring-1`)
- a wrapping row (`flex-wrap`, `gap-2`)

The shared tab row now provides:

- one horizontal line of labels
- transparent tab backgrounds
- no per-tab border and no pill fill
- a bottom divider on the row (`border-b` with `--tab-line`)
- a 2px underline in the brand orange (`--tab-underline`, measured `rgb(242, 106, 33)`, which is `#f26a21`)
- active label at font weight 600 in `--tab-text`
- inactive label at font weight 500 in `--tab-text-muted` (measured `rgba(34, 32, 38, 0.55)`)
- hover that changes the text colour only
- a colour transition, with motion reduced when the user asks for it

Measured on the register: tab height 48px, horizontal padding 12px, border radius 0, `flex-shrink: 0`, `white-space: nowrap`. The underline sits on the bottom edge of the active label and does not take clicks (`pointer-events: none` on the underline). The whole tab button is the target.

The sidebar and the top status bar were not changed.

## Navigation

The open section is still the page’s existing state. `InventoryTabNavigation` receives `activeTab` and calls `onChange`. There is no second selected-tab store.

The row only shows tabs `inventoryTabs` already returns for the profile, capabilities, and permissions. A cashier with no inventory permission still gets an empty list. Models and Batches appear for the electronics profile because that profile already lists them. Markdowns and Size & color matrix are not POS tabs, so they are not shown.

Choosing a tab still mounts the same panel as before. Filters, pagination, and API calls stay inside those panels. The register does not put the inventory section in the URL, so application back navigation does not change the tab. That was already the case.

## Horizontal scrolling

The tab list uses `overflow-x: auto`, `flex-nowrap`, and `min-w-0`. Each tab uses `whitespace-nowrap` and `shrink-0`. The scrollbar is hidden with `no-scrollbar`. `overscroll-x-contain` keeps a sideways gesture from chaining into the page.

The class list includes `overflow-y: hidden`. The design-token stylesheet computes that cross axis as `clip` when the row scrolls sideways, so a vertical wheel over the tabs still reaches the page. The inventory body stays in the register’s existing vertical scroller (`main` is `overflow-y: auto`).

`AxizTabs` calls `scrollIntoView` when the selection changes. At 1024×768, choosing Transfers moved that label to the right edge and opened the transfer form. When the row is wider than the pane, the shared previous/next controls appear (`‹` / `›`, 32px). They are not shown when every label fits.

## Responsive results

Captured in the register shell. Sidebar and header stayed in place. The default electronics profile showed 14 tabs.

| Window | Tab row width | Content width | Result |
| --- | ---: | ---: | --- |
| 1024×768 | 48px | 912px of 1194px | One row. Later tabs scroll. Next control visible. |
| 1280×800 | 48px | 1168px of 1194px | One row. Transfers sits just past the edge, with the next control. |
| 1366×768 | 48px | 1286px of 1286px | Every label fits. No edge control. |
| 1920×1080 | 48px | 1840px of 1840px | Every label fits. No edge control. |

Labels are not shrunk and are not ellipsized. A label that does not fit is scrolled, not wrapped onto a second line.

## Touch targets

Each tab is 48px tall, which meets the 44px minimum and the 48–52px target. Padding is 12px on each side. The button, not only the word, receives the click. Focus styling is the shared `focus-visible` outline in `--tab-focus`. Arrow keys, Home, End, Enter, and Space are handled by `AxizTabs`.

## Screenshots

Taken from the register shell after the change. No earlier pill-row capture was made in this pass. The previous row was the orange pill buttons in `InventoryPage`.

- `docs/inventory/evidence/pos-inventory-tabs/after-1024x768.png`
- `docs/inventory/evidence/pos-inventory-tabs/after-1024x768-transfers.png`
- `docs/inventory/evidence/pos-inventory-tabs/after-1280x800.png`
- `docs/inventory/evidence/pos-inventory-tabs/after-1366x768.png`
- `docs/inventory/evidence/pos-inventory-tabs/after-1920x1080.png`
- `docs/inventory/evidence/pos-inventory-tabs/measurements.json`

The Transfers capture shows the orange underline under Transfers, the row scrolled so that tab is on screen, and the existing transfer form underneath.

## Tests

```text
pnpm --filter @ai-pos/desktop exec vitest run src/features/inventory
```

5 files, 23 tests, all passed. That includes the existing tab permission tests, the layout tests, and the new navigation tests for the underline row, the active tab, and the supplied labels only.

```text
pnpm --filter @ai-pos/ui exec vitest run src/AxizTabs.test.tsx
```

1 file, 17 tests, all passed. Added coverage for bringing the active tab into view and for the next control when the row is wider than the pane.

## Remaining limitations

- Inventory sections are still local page state. Back and forward do not change the tab, because the register never routed these sections.
- Screenshots and the click-through used an offline register preview so the PIN screen did not block the shell. Live stock numbers were not loaded. The preview entry was removed afterward.
- A physical touch swipe and a hardware keyboard were not used. The row is a native horizontal scroller with a 48px target, and keyboard behaviour is covered by the `AxizTabs` tests.
- When the labels are only slightly wider than the pane, the shared next control reserves 32px, so the last word sits partly out of view until the row is scrolled. That is the Business Pro overflow control, not a second line of tabs.
- Markdowns and Size & color matrix stay absent on the POS. They are not in the POS tab list.
