import { useEffect, useState } from "react";
import { version as packagedVersion } from "../../package.json";
import versionFile from "../../VERSION?raw";

const SEMVER = /^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$/;

/** First version line in apps/desktop/VERSION. Comments and blank lines are skipped. */
export function versionFromFile(raw: string): string | null {
  const line = raw
    .split(/\r?\n/)
    .map((item) => item.trim())
    .find((item) => item !== "" && !item.startsWith("#"));
  if (!line || !SEMVER.test(line)) return null;
  return line;
}

/**
 * The local VERSION file is the current source version.
 * The installed app version is used when that file cannot be read.
 */
export function chooseAppVersion(fileVersion: string | null, installed: string | null, packaged: string): string {
  return fileVersion ?? installed ?? packaged;
}

const fileVersion = versionFromFile(versionFile);

export function useAppVersion(): string {
  const [version, setVersion] = useState(() => chooseAppVersion(fileVersion, null, packagedVersion));

  useEffect(() => {
    let cancelled = false;
    void import("@tauri-apps/api/app")
      .then(({ getVersion }) => getVersion())
      .then((installed) => {
        if (!cancelled) setVersion(chooseAppVersion(fileVersion, installed, packagedVersion));
      })
      .catch(() => {
        if (!cancelled) setVersion(chooseAppVersion(fileVersion, null, packagedVersion));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return version;
}
