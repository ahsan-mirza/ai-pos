export interface SyncSnapshot {
  syncing: boolean;
  pending: number | null;
  failed: number | null;
  conflicts: number | null;
}

type Listener = (snapshot: SyncSnapshot) => void;

let depth = 0;
let pending: number | null = null;
let failed: number | null = null;
let conflicts: number | null = null;
const listeners = new Set<Listener>();

function snapshot(): SyncSnapshot {
  return { syncing: depth > 0, pending, failed, conflicts };
}

function emit(): void {
  const next = snapshot();
  for (const listener of listeners) listener(next);
}

/** Marks a catalogue download or a queue flush that still has work. Nested calls stay active until each one ends. */
export function beginSync(): () => void {
  depth += 1;
  emit();
  let ended = false;
  return () => {
    if (ended) return;
    ended = true;
    depth = Math.max(0, depth - 1);
    emit();
  };
}

export function noteSyncCounts(patch: { pending?: number; failed?: number; conflicts?: number }): void {
  if (patch.pending != null) pending = Math.max(0, patch.pending);
  if (patch.failed != null) failed = Math.max(0, patch.failed);
  if (patch.conflicts != null) conflicts = Math.max(0, patch.conflicts);
  emit();
}

export function subscribeSyncActivity(listener: Listener): () => void {
  listeners.add(listener);
  listener(snapshot());
  return () => listeners.delete(listener);
}
