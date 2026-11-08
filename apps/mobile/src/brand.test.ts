/// <reference types="jest" />
declare const __dirname: string;
declare function require(id: string): unknown;

const fs = require("node:fs") as {
  existsSync(file: string): boolean;
  readFileSync(file: string, encoding?: string): { subarray(start: number, end: number): { toString(encoding: string): string }; readUInt32BE(offset: number): number; readonly [index: number]: number | undefined } & string;
};
const path = require("node:path") as { resolve(...parts: string[]): string };

const root = path.resolve(__dirname, "..");

function pngSize(relativePath: string): { width: number; height: number; colorType: number } {
  const file = path.resolve(root, relativePath);
  expect(fs.existsSync(file)).toBe(true);
  const bytes = fs.readFileSync(file);
  expect(bytes.subarray(0, 8).toString("hex")).toBe("89504e470d0a1a0a");
  return { width: bytes.readUInt32BE(16), height: bytes.readUInt32BE(20), colorType: bytes[25] ?? 0 };
}

describe("AxizPOS brand assets", () => {
  const config = JSON.parse(fs.readFileSync(path.resolve(root, "app.json"), "utf8")) as {
    expo: {
      icon: string;
      ios: { icon: string };
      android: { adaptiveIcon: { backgroundColor: string; foregroundImage: string; backgroundImage: string; monochromeImage: string } };
      web: { favicon: string };
      plugins: unknown[];
    };
  };

  it("points Expo at the generated icon, splash and adaptive images", () => {
    expect(config.expo.icon).toBe("./assets/icon.png");
    expect(config.expo.ios.icon).toBe("./assets/icon.png");
    expect(config.expo.android.adaptiveIcon.foregroundImage).toBe("./assets/android-icon-foreground.png");
    expect(config.expo.android.adaptiveIcon.backgroundImage).toBe("./assets/android-icon-background.png");
    expect(config.expo.android.adaptiveIcon.monochromeImage).toBe("./assets/android-icon-monochrome.png");
    expect(config.expo.android.adaptiveIcon.backgroundColor).toBe("#FFFFFF");
    expect(config.expo.web.favicon).toBe("./assets/favicon.png");
    const splash = config.expo.plugins.find((plugin) => Array.isArray(plugin) && plugin[0] === "expo-splash-screen");
    expect(Array.isArray(splash) && splash[1]).toMatchObject({ backgroundColor: "#F7F8FA", image: "./assets/splash-icon.png" });
  });

  it("uses square store icons and a transparent adaptive foreground", () => {
    expect(pngSize("assets/icon.png")).toMatchObject({ width: 1024, height: 1024 });
    expect(pngSize("assets/android-icon-background.png")).toMatchObject({ width: 1024, height: 1024 });
    expect(pngSize("assets/splash-icon.png")).toMatchObject({ width: 1024, height: 1024 });
    const foreground = pngSize("assets/android-icon-foreground.png");
    expect(foreground).toMatchObject({ width: 1024, height: 1024, colorType: 6 });
    expect(pngSize("assets/favicon.png").width).toBe(48);
  });
});
