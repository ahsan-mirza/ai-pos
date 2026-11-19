import { readFileSync } from "node:fs";
import { join } from "node:path";
import { createHash } from "node:crypto";
import {
  DEMO_BUSINESSES,
  POS_DEMO_BUSINESS_STORAGE_KEY,
  POS_INSTALLER_DOWNLOAD_PATH,
  POS_INSTALLER_FEED_PATH,
  PosInstallerError,
  formatInstallerSize,
  installerDigestMatches,
  loadPosInstallerRelease,
  planDemoOpen,
  posDemoHandoffDocument,
  posInstallerMessage,
  requestPosDemoHandoff,
  readPosInstallerBytes,
  readPosInstallerRelease,
  rememberPosDemoBusiness,
} from "@ai-pos/shared-types";
import { describe, expect, it } from "vitest";

const published = {
  version: "0.1.2",
  notes: null,
  pub_date: "2026-11-11T07:39:25Z",
  sha256: "9d50c61fcb2be7289061f2333b369cbe5ff959be3634849417c4848486129df7",
  path: "/api/download/installer/win",
};

function feed(status: number, body: unknown) {
  return async () => ({ ok: status >= 200 && status < 300, status, json: async () => body });
}

describe("POS demo connection file", () => {
  it("writes one ticket and nothing else the register could treat as a tenant", async () => {
    const ticket = "restaurant.abc123456789";
    const documentText = posDemoHandoffDocument(ticket);
    expect(JSON.parse(documentText)).toEqual({ version: 1, enrollment_ticket: ticket });
    expect(documentText).not.toContain("device_token");
    expect(documentText).not.toContain("tenant_id");
    const saved = await requestPosDemoHandoff("http://localhost:8000", "restaurant", async () => ({
      ok: true,
      status: 200,
      json: async () => ({ enrollment_ticket: ticket, expires_in: 600, business_code: "restaurant" }),
    }));
    expect(saved).toBe(documentText);
    await expect(requestPosDemoHandoff("http://localhost:8000", "restaurant", async () => ({
      ok: false,
      status: 404,
      json: async () => ({ error: { code: "demo_unavailable" } }),
    }))).rejects.toMatchObject({ failure: "unavailable" });
  });
});

describe("POS installer download", () => {
  it("keeps both actions on every business card and the shared-demo warning", () => {
    const page = readFileSync(join(process.cwd(), "../site/src/pages/ExplorePage.tsx"), "utf8");
    expect(DEMO_BUSINESSES.map((business) => business.code)).toEqual([
      "restaurant",
      "supermarket",
      "electronics",
      "fashion",
      "pharmacy",
    ]);
    expect(page).toContain("DEMO_BUSINESSES.map");
    expect(page).toContain("Explore Business Pro");
    expect(page).toContain("Download AxizPOS");
    expect(page).toContain("planDemoOpen");
    expect(page).toContain("grid-cols-1");
    expect(page).toContain("md:grid-cols-2");
    expect(page).toContain("flex-col");
    expect(page).toContain("sm:flex-row");
    expect(page).toContain("Each demo is a shared environment.");
    expect(page).toContain("Other visitors may create sales or update demo data.");
    expect(page).toContain("Windows 10 or Windows 11");
    expect(page).toContain("Download connection file");
    expect(page).toContain("does not contain a connection ticket");
    expect(page).not.toContain("enrollment_ticket=");
    expect(page).not.toContain("activation key");
    expect(page).not.toContain("access_token=");
  });

  it("still plans the Business Pro portal route without a credential in the address", () => {
    for (const business of DEMO_BUSINESSES) {
      const plan = planDemoOpen("http://localhost:5175", "http://localhost:5173/login", business.code);
      expect(plan).toEqual({ kind: "navigate", href: `http://localhost:5173/demo/${business.code}` });
      expect(plan.href).not.toContain("token");
    }
  });

  it("accepts the published release shape and rejects a foreign download URL", () => {
    const release = readPosInstallerRelease(published, "https://axizpos.com");
    expect(release).toEqual({
      version: "0.1.2",
      sha256: published.sha256,
      downloadUrl: "https://axizpos.com/api/download/installer/win",
    });
    expect(release?.downloadUrl).not.toContain("?");
    expect(readPosInstallerRelease({ ...published, path: "https://evil.example/setup.exe" }, "https://axizpos.com")).toBeNull();
    expect(readPosInstallerRelease({ ...published, path: "/api/download/installer/win?token=abc" }, "https://axizpos.com")).toBeNull();
    expect(readPosInstallerRelease({ ...published, version: "latest" }, "https://axizpos.com")).toBeNull();
    expect(readPosInstallerRelease({ ...published, sha256: "abcd" }, "https://axizpos.com")).toBeNull();
    expect(readPosInstallerRelease({ ...published, pub_date: "" }, "https://axizpos.com")).toBeNull();
    expect(readPosInstallerRelease(published, "http://downloads.example")).toBeNull();
    expect(readPosInstallerRelease(published, "http://localhost:8000")?.downloadUrl).toBe(
      "http://localhost:8000/api/download/installer/win",
    );
  });

  it("stores only the selected business code", () => {
    const saved: Record<string, string> = {};
    for (const business of DEMO_BUSINESSES) {
      expect(rememberPosDemoBusiness({ setItem: (key, value) => (saved[key] = value) }, business.code)).toBe(true);
      expect(saved[POS_DEMO_BUSINESS_STORAGE_KEY]).toBe(business.code);
    }
    expect(rememberPosDemoBusiness({ setItem: () => undefined }, "other")).toBe(false);
    expect(Object.keys(saved)).toEqual([POS_DEMO_BUSINESS_STORAGE_KEY]);
  });

  it("reports a missing release, a bad feed, and a network failure", async () => {
    await expect(loadPosInstallerRelease("https://axizpos.com", feed(404, {}))).rejects.toMatchObject({ failure: "missing" });
    await expect(loadPosInstallerRelease("https://axizpos.com", feed(500, {}))).rejects.toMatchObject({ failure: "unavailable" });
    await expect(loadPosInstallerRelease("https://axizpos.com", feed(200, { ...published, path: "/tmp/setup.exe" }))).rejects.toMatchObject({
      failure: "invalid",
    });
    const offline = async () => {
      throw new Error("network");
    };
    await expect(loadPosInstallerRelease("https://axizpos.com", offline)).rejects.toBeInstanceOf(PosInstallerError);
    expect(posInstallerMessage("missing")).toContain("No Windows installer");
    expect(posInstallerMessage("network")).toContain("internet connection");
    expect(posInstallerMessage("download")).not.toContain("downloads_dir");
  });

  it("reads the installer bytes and stops when the download breaks", async () => {
    const release = readPosInstallerRelease(published, "https://axizpos.com");
    expect(release).not.toBeNull();
    const payload = new Uint8Array([1, 2, 3, 4]);
    const ok = async (url: string) => {
      expect(url).toBe(release?.downloadUrl);
      expect(url).not.toContain(POS_INSTALLER_FEED_PATH);
      return {
        ok: true,
        status: 200,
        headers: { get: (name: string) => (name === "content-length" ? "4" : null) },
        body: {
          getReader: () => ({
            read: (() => {
              let sent = false;
              return async () => {
                if (sent) return { done: true };
                sent = true;
                return { done: false, value: payload };
              };
            })(),
          }),
        },
      };
    };
    const file = await readPosInstallerBytes(release!, ok, () => undefined);
    expect(file.size).toBe(4);
    expect(file.bytes).toEqual(payload);
    expect(formatInstallerSize(6279756)).toBe("6.0 MB");
    const broken = async () => ({
      ok: false,
      status: 404,
      headers: { get: () => null },
      body: null,
    });
    await expect(readPosInstallerBytes(release!, broken, () => undefined)).rejects.toMatchObject({ failure: "download" });
    const short = async () => ({
      ok: true,
      status: 200,
      headers: { get: () => "8" },
      body: { getReader: () => ({ read: async () => ({ done: true }) }) },
    });
    await expect(readPosInstallerBytes(release!, short, () => undefined)).rejects.toMatchObject({ failure: "invalid" });
    expect(installerDigestMatches(createHash("sha256").update(payload).digest("hex"), "nope")).toBe(false);
  });

  it("matches the live installer feed", async () => {
    const response = await fetch("https://axizpos.com/api/v1/downloads/latest.json");
    expect(response.status).toBe(200);
    const body: unknown = await response.json();
    const release = readPosInstallerRelease(body, "https://axizpos.com");
    expect(release?.downloadUrl).toBe(`https://axizpos.com${POS_INSTALLER_DOWNLOAD_PATH}`);
    expect(release?.version).toMatch(/^\d+\.\d+\.\d+$/);
    expect(release?.downloadUrl).not.toContain("token");
  });
});
