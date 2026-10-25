// The shipped POS icons are rendered from packages/ui/assets/fav-icon.svg.
// This script draws the older geometric mark and would replace those files.
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { crc32, deflateSync } from "node:zlib";

const outDir = join(dirname(fileURLToPath(import.meta.url)), "..", "apps", "desktop", "src-tauri", "icons");

function chunk(type, data) {
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length, 0);
  const body = Buffer.concat([Buffer.from(type, "ascii"), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body) >>> 0, 0);
  return Buffer.concat([length, body, crc]);
}

function insideRoundedRect(x, y, size, radius) {
  const max = size - 1;
  if (x < 0 || y < 0 || x > max || y > max) return false;
  const left = x < radius;
  const right = x >= size - radius;
  const top = y < radius;
  const bottom = y >= size - radius;
  if (!left && !right) return true;
  if (!top && !bottom) return true;
  const cx = left ? radius : size - radius - 1;
  const cy = top ? radius : size - radius - 1;
  const dx = x - cx;
  const dy = y - cy;
  return dx * dx + dy * dy <= radius * radius;
}

function png(size) {
  const raw = Buffer.alloc((size * 4 + 1) * size);
  const radius = Math.round(size * 0.22);
  const markLeft = Math.round(size * 0.3);
  const markRight = Math.round(size * 0.7);
  const markTop = Math.round(size * 0.24);
  const markBottom = Math.round(size * 0.76);
  const lineY = Math.round(size * 0.46);

  for (let y = 0; y < size; y += 1) {
    const row = y * (size * 4 + 1);
    raw[row] = 0;
    for (let x = 0; x < size; x += 1) {
      const offset = row + 1 + x * 4;
      if (!insideRoundedRect(x, y, size, radius)) {
        raw[offset + 3] = 0;
        continue;
      }
      const inMark = x >= markLeft && x <= markRight && y >= markTop && y <= markBottom;
      const onLine = inMark && Math.abs(y - lineY) <= Math.max(1, Math.round(size * 0.025));
      if (onLine) {
        raw[offset] = 0x22;
        raw[offset + 1] = 0x20;
        raw[offset + 2] = 0x26;
      } else if (inMark) {
        raw[offset] = 0xff;
        raw[offset + 1] = 0xff;
        raw[offset + 2] = 0xff;
      } else {
        raw[offset] = 0xfd;
        raw[offset + 1] = 0x37;
        raw[offset + 2] = 0x06;
      }
      raw[offset + 3] = 255;
    }
  }

  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0);
  ihdr.writeUInt32BE(size, 4);
  ihdr[8] = 8;
  ihdr[9] = 6;
  const signature = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
  return Buffer.concat([
    signature,
    chunk("IHDR", ihdr),
    chunk("IDAT", deflateSync(raw)),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

function ico(images) {
  const header = Buffer.alloc(6);
  header.writeUInt16LE(0, 0);
  header.writeUInt16LE(1, 2);
  header.writeUInt16LE(images.length, 4);
  const directory = Buffer.alloc(16 * images.length);
  let offset = 6 + directory.length;
  const parts = [header, directory];
  images.forEach((image, index) => {
    const entry = index * 16;
    directory[entry] = image.size >= 256 ? 0 : image.size;
    directory[entry + 1] = image.size >= 256 ? 0 : image.size;
    directory.writeUInt16LE(1, entry + 4);
    directory.writeUInt16LE(32, entry + 6);
    directory.writeUInt32LE(image.png.length, entry + 8);
    directory.writeUInt32LE(offset, entry + 12);
    offset += image.png.length;
    parts.push(image.png);
  });
  return Buffer.concat(parts);
}

mkdirSync(outDir, { recursive: true });
const sizes = [32, 128, 256];
const images = sizes.map((size) => ({ size, png: png(size) }));
writeFileSync(join(outDir, "32x32.png"), images[0].png);
writeFileSync(join(outDir, "128x128.png"), images[1].png);
writeFileSync(join(outDir, "128x128@2x.png"), images[2].png);
writeFileSync(join(outDir, "icon.ico"), ico(images.slice(0, 2)));
console.log(`Wrote icons to ${outDir}`);
