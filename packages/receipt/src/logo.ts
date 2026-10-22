/** Limits the API enforces on a receipt logo (app/schemas/receipt.py). */
export const LOGO_MAX_BYTES = 64 * 1024;
export const LOGO_MAX_HEIGHT = 320;
/** 384 dots fits 58 mm paper as well as 80 mm, so one logo serves every register. */
export const LOGO_TARGET_WIDTH = 384;

/** "dither" keeps photos and gradients readable; "threshold" keeps line-art logos crisp. */
export type LogoMode = "dither" | "threshold";

export interface PreparedLogo {
  dataUrl: string;
  width: number;
  height: number;
  bytes: number;
}

function readImage(file: Blob): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      URL.revokeObjectURL(url);
      resolve(image);
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("This file is not an image the browser can read. Use a PNG or JPEG."));
    };
    image.src = url;
  });
}

/** Luminance 0-255 per pixel, with transparency flattened onto white paper. */
function grayscale(rgba: Uint8ClampedArray): Float32Array {
  const out = new Float32Array(rgba.length / 4);
  for (let index = 0; index < out.length; index += 1) {
    const offset = index * 4;
    const alpha = (rgba[offset + 3] ?? 255) / 255;
    const luma = 0.299 * (rgba[offset] ?? 255) + 0.587 * (rgba[offset + 1] ?? 255) + 0.114 * (rgba[offset + 2] ?? 255);
    out[index] = 255 - alpha * (255 - luma);
  }
  return out;
}

/** 1 = black. Floyd–Steinberg spreads each pixel's rounding error onto its unvisited neighbours. */
export function toMonochrome(gray: Float32Array, width: number, height: number, mode: LogoMode): Uint8Array {
  const ink = new Uint8Array(width * height);
  const work = Float32Array.from(gray);
  const spread = (x: number, y: number, amount: number) => {
    if (x < 0 || x >= width || y >= height) return;
    const index = y * width + x;
    work[index] = (work[index] ?? 0) + amount;
  };
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const index = y * width + x;
      const value = work[index] ?? 255;
      const black = value < 128;
      ink[index] = black ? 1 : 0;
      if (mode !== "dither") continue;
      const error = value - (black ? 0 : 255);
      spread(x + 1, y, (error * 7) / 16);
      spread(x - 1, y + 1, (error * 3) / 16);
      spread(x, y + 1, (error * 5) / 16);
      spread(x + 1, y + 1, error / 16);
    }
  }
  return ink;
}

/** Bounding box of the inked pixels, so white margins around an uploaded logo do not waste paper. */
function inkBounds(ink: Uint8Array, width: number, height: number) {
  let top = height;
  let bottom = -1;
  let left = width;
  let right = -1;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      if (!ink[y * width + x]) continue;
      top = Math.min(top, y);
      bottom = Math.max(bottom, y);
      left = Math.min(left, x);
      right = Math.max(right, x);
    }
  }
  return bottom < 0 ? null : { top, left, width: right - left + 1, height: bottom - top + 1 };
}

function dataUrlBytes(dataUrl: string): number {
  const base64 = dataUrl.slice(dataUrl.indexOf(",") + 1);
  return Math.floor((base64.length * 3) / 4) - (base64.endsWith("==") ? 2 : base64.endsWith("=") ? 1 : 0);
}

/** Turns an uploaded image into the black-and-white PNG a thermal printer reproduces dot for dot. */
export async function prepareLogo(file: Blob, mode: LogoMode = "dither"): Promise<PreparedLogo> {
  const image = await readImage(file);
  const scale = Math.min(1, LOGO_TARGET_WIDTH / image.naturalWidth, LOGO_MAX_HEIGHT / image.naturalHeight);
  const width = Math.max(1, Math.round(image.naturalWidth * scale));
  const height = Math.max(1, Math.round(image.naturalHeight * scale));

  const source = document.createElement("canvas");
  source.width = width;
  source.height = height;
  const sourceCtx = source.getContext("2d");
  if (!sourceCtx) throw new Error("This browser cannot process images.");
  sourceCtx.drawImage(image, 0, 0, width, height);
  const ink = toMonochrome(grayscale(sourceCtx.getImageData(0, 0, width, height).data), width, height, mode);

  const box = inkBounds(ink, width, height);
  if (!box) throw new Error("The logo came out blank. Use an image with dark artwork on a light background.");
  const out = document.createElement("canvas");
  out.width = box.width;
  out.height = box.height;
  const outCtx = out.getContext("2d")!;
  const pixels = outCtx.createImageData(box.width, box.height);
  for (let y = 0; y < box.height; y += 1) {
    for (let x = 0; x < box.width; x += 1) {
      const black = ink[(box.top + y) * width + box.left + x] === 1;
      const offset = (y * box.width + x) * 4;
      const tone = black ? 0 : 255;
      pixels.data[offset] = tone;
      pixels.data[offset + 1] = tone;
      pixels.data[offset + 2] = tone;
      pixels.data[offset + 3] = 255;
    }
  }
  outCtx.putImageData(pixels, 0, 0);
  const dataUrl = out.toDataURL("image/png");
  const bytes = dataUrlBytes(dataUrl);
  if (bytes > LOGO_MAX_BYTES) {
    throw new Error(
      `The converted logo is ${Math.ceil(bytes / 1024)} KB; the limit is ${LOGO_MAX_BYTES / 1024} KB. Try "Line art" or a simpler image.`,
    );
  }
  return { dataUrl, width: box.width, height: box.height, bytes };
}
