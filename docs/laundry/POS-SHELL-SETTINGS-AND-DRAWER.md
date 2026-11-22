# POS shell: Settings and Open drawer

Every business profile uses the same register shell. Settings is the sidebar gear. Open drawer is one button in the top navbar.

## Settings

`SidebarNav` is the only Settings entry. The laundry horizontal row no longer includes a Settings tab.

Every profile, including laundry, opens the shared store settings page at `#/settings/currency`. The layout is described in `POS-SETTINGS-WORKSPACE.md`. `#/laundry/settings` remains the laundry floor panel.

The gear uses the same active treatment as the other sidebar items.

## Open drawer

`HeaderBar` renders one `OpenDrawerButton` with `drawerButtonClass` after language and theme, on every page that uses the shell. The button still opens `CashDrawerModal`. No new drawer API was added.

The button is disabled while the shell is busy (checkout charge, repairs, returns) or while Orders holds it for an in-flight request. Checkout still has its own full-width drawer action in the tender footer. That control is part of the sale, not a second navbar button.

## Files

- `apps/desktop/src/components/shell/settingsEntry.ts` — gear destination, active state, navbar button class.
- `apps/desktop/src/components/shell/SidebarNav.tsx` — gear and page clicks.
- `apps/desktop/src/components/shell/HeaderBar.tsx` — shared drawer button.
- `apps/desktop/src/components/shell/ShellContext.tsx` — busy flag and drawer hold.
- `apps/desktop/src/components/shell/RegisterShell.tsx` — provides those flags.
- `apps/desktop/src/App.tsx` — `#/settings` on load and when the hash changes.
- `apps/desktop/src/features/laundry/laundryNav.ts` — Settings tab removed.
- Checkout, Orders, Repairs, Returns, and Laundry no longer pass their own navbar drawer button.

## Tests

From `apps/desktop`:

`pnpm exec vitest run src/components/shell/settingsEntry.test.ts src/features/laundry/laundryNav.test.tsx src/components/RegisterErrorBoundary.test.tsx src/lib/capabilities.test.ts`

11 passed in the shell, laundry navigation, and recovery files. 11 passed in `capabilities.test.ts`. 0 failed.

The laundry preview at `http://127.0.0.1:1421` was exercised in the browser. The horizontal row was Orders, Production, Services, Customers, Reports. The sidebar gear opened `#/laundry/settings`, stayed current after refresh, and Orders returned to `#/laundry/intake`. The navbar Open drawer button is 40px tall on the same row as language and theme, and it opened the existing cash-drawer dialog. The document did not scroll sideways.

Grocery, electronics, fashion, and restaurant were not switched in that preview. That window is the laundry tenant. Those profiles use the same `HeaderBar` and `SidebarNav`. `settingsEntry.test.ts` covers their gear destination and active state.

## Limitations

- The navbar drawer confirmation uses the button's own status line. Pages that previously printed that message in their own notice still do so only for the checkout tender button.
- Native Windows was not launched. The preview is the Vite register.
