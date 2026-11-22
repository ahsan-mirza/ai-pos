export interface SyncState {
  tone: "synced" | "pending" | "offline" | "live";
  label: string;
  title: string;
}
