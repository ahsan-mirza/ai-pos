/** Independent sidebar accordion state. Each section id is toggled on its own. */

export function toggleSection(open: ReadonlySet<string>, id: string): Set<string> {
  const next = new Set(open);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  return next;
}

/**
 * A route change opens the section that contains the page.
 * Every other section stays as the user left it.
 * Returns the same set when nothing needs to change.
 */
export function revealSection(open: ReadonlySet<string>, activeId: string | null): ReadonlySet<string> {
  if (activeId === null || open.has(activeId)) return open;
  const next = new Set(open);
  next.add(activeId);
  return next;
}
