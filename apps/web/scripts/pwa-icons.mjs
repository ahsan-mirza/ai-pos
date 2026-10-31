/** Rasterize the existing AxizPOS mark into the PWA icon set. Fills are inlined because the source SVG uses a style block. */
import { mkdir } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "public", "icons");
const mark = (size) => Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 114.15 90.86">
  <path fill="#f26a21" d="m61.46,42.93l-15.3,28.17c-1.09,2,.36,4.43,2.64,4.43h25.32c2.27,0,3.72-2.43,2.64-4.43l-15.3-28.17Z"/>
  <path fill="#2b2b2b" d="m109.15,75.54c3.79,0,6.2-4.05,4.39-7.39L77.71,2.16c-.73-1.34-2.07-2.16-3.53-2.16h-25.44c-1.45,0-2.8.83-3.53,2.16L.74,84.37c-1.57,2.89.39,6.49,3.53,6.49h18.97c1.45,0,2.8-.83,3.53-2.16l17.04-31.69s0,0,0,0l17.13-31.54c.56-1.04,1.49-1.04,2.05,0l25.77,47.46c.87,1.61,2.56,2.61,4.39,2.61h16Z"/>
</svg>`);

async function icon(file, size, ratio, background) {
  const logo = Math.round(size * ratio);
  const rendered = await sharp(mark(logo)).png().toBuffer();
  await sharp({ create: { width: size, height: size, channels: 4, background } })
    .composite([{ input: rendered, gravity: "centre" }])
    .png()
    .toFile(join(root, file));
}

const canvas = { r: 234, g: 234, b: 234, alpha: 1 };
const white = { r: 255, g: 255, b: 255, alpha: 1 };

await mkdir(root, { recursive: true });
await icon("icon-192.png", 192, 0.72, canvas);
await icon("icon-512.png", 512, 0.72, canvas);
await icon("icon-maskable-192.png", 192, 0.56, white);
await icon("icon-maskable-512.png", 512, 0.56, white);
await icon("apple-touch-icon.png", 180, 0.7, canvas);
await icon("favicon-32.png", 32, 0.8, canvas);
