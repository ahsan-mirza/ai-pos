export type InstallerKind = "exe" | "msi";

export interface InstallerFile {
  name: string;
  kind: InstallerKind;
  size_bytes: number;
  sha256: string;
  /** Relative to /api/v1; fetched with the admin's token. */
  download_path: string;
}

export interface AppRelease {
  app: "pos";
  version: string;
  published_at: string;
  notes: string | null;
  files: InstallerFile[];
}

/** GET /api/v1/downloads (Super Admin only). Newest release first. */
export interface DownloadsList {
  releases: AppRelease[];
}
