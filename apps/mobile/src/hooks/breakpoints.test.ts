/// <reference types="jest" />
import {
  breakpointOf,
  columnsFit,
  directoryColumns,
  FONT_SCALE_CAP,
  gridColumns,
  gridTrackPercent,
  masterDetail,
  modalMaxHeight,
  safeBottom,
  scaledLineHeight,
  scaledSize,
  sheetMaxHeight,
} from "@/hooks/breakpoints";
import { touchTarget } from "@/theme/tokens";

const devices = [
  { id: "ios-se", width: 320, height: 568, platform: "ios" },
  { id: "ios-phone", width: 393, height: 852, platform: "ios" },
  { id: "ios-large", width: 440, height: 956, platform: "ios" },
  { id: "ios-phone-landscape", width: 852, height: 393, platform: "ios" },
  { id: "ipad", width: 768, height: 1024, platform: "ios" },
  { id: "ipad-landscape", width: 1024, height: 768, platform: "ios" },
  { id: "android-small", width: 360, height: 640, platform: "android" },
  { id: "android-phone", width: 412, height: 915, platform: "android" },
  { id: "android-large", width: 480, height: 1000, platform: "android" },
  { id: "android-tablet", width: 800, height: 1280, platform: "android" },
  { id: "android-tablet-landscape", width: 1280, height: 800, platform: "android" },
  { id: "foldable-inner", width: 768, height: 900, platform: "android" },
] as const;

describe("responsive layout", () => {
  it("keeps phone directories to one column and gives tablets more", () => {
    expect(directoryColumns(320)).toBe(1);
    expect(directoryColumns(393)).toBe(1);
    expect(directoryColumns(440)).toBe(1);
    expect(directoryColumns(768)).toBe(2);
    expect(directoryColumns(1024)).toBe(3);
  });

  it("uses master-detail only when the window is wide enough", () => {
    expect(masterDetail(667)).toBe(false);
    expect(masterDetail(412)).toBe(false);
    expect(masterDetail(768)).toBe(true);
    expect(masterDetail(852)).toBe(true);
  });

  it("fits every representative device without a grid track overflowing", () => {
    for (const device of devices) {
      const columns = gridColumns(device.width);
      expect(gridTrackPercent(columns) * columns).toBe(100);
      expect(columnsFit(device.width, columns, 12)).toBe(true);
      expect(breakpointOf(device.width)).toBeDefined();
      expect(sheetMaxHeight(device.height, 47, 34)).toBeLessThanOrEqual(device.height);
      expect(modalMaxHeight(device.height, 47, 34)).toBeLessThan(device.height);
    }
  });

  it("drops the bottom inset inside tabs and keeps it on stack screens", () => {
    expect(safeBottom(true, 34)).toBe(0);
    expect(safeBottom(true, 48)).toBe(0);
    expect(safeBottom(false, 34)).toBe(34);
    expect(safeBottom(false, 48)).toBe(48);
  });

  it("grows text with the system scale and keeps the line taller than the glyphs", () => {
    expect(touchTarget).toBeGreaterThanOrEqual(44);
    expect(scaledSize(15, 1)).toBe(15);
    expect(scaledSize(15, 3)).toBe(Math.round(15 * FONT_SCALE_CAP));
    const font = scaledSize(15, 2);
    const line = scaledLineHeight(22, 15, 2);
    expect(line).toBeGreaterThanOrEqual(Math.ceil(font * 1.25));
  });
});
