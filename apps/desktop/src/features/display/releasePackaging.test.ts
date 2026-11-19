import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const root = join(process.cwd(), "src-tauri");
const config = JSON.parse(readFileSync(join(root, "tauri.conf.json"), "utf8")) as {
  productName: string;
  identifier: string;
  bundle: {
    targets: string[];
    publisher: string;
    fileAssociations: { ext: string[] }[];
    windows: { certificateThumbprint?: string; signCommand: { args: string[] } };
  };
};

describe("AxizPOS Windows packaging", () => {
  it("keeps the installed data directory and requires a signing command", () => {
    const text = readFileSync(join(root, "tauri.conf.json"), "utf8");
    const hooks = readFileSync(join(process.cwd(), "build/installer.nsh"), "utf8");
    const signer = readFileSync(join(root, "sign-pos.ps1"), "utf8");
    expect(config.identifier).toBe("com.aipos.desktop");
    expect(config.productName).toBe("AxizPOS");
    expect(config.bundle.publisher).toBe("AxizPOS");
    expect(config.bundle.targets).toEqual(["nsis"]);
    expect(config.bundle.fileAssociations[0]?.ext).toEqual(["posdemo"]);
    expect(config.bundle.windows.certificateThumbprint).toBeUndefined();
    expect(text).not.toContain("BEGIN PRIVATE KEY");
    expect(signer).toContain("AXIZPOS_SIGN_THUMBPRINT");
    expect(signer).not.toMatch(/[0-9A-Fa-f]{40}/);
    expect(hooks).toContain("com.aipos.desktop");
    expect(hooks).toContain("Uninstall\\AxizPOS\"");
    expect(hooks).toContain("Uninstall\\AxizPOS POS Register");
    expect(hooks).toContain("Uninstall\\AI POS");
    expect(hooks).toContain('$3 == "AxizPOS"');
  });
});
