const MAX_EDGE = 1600;
const QUALITY = 0.82;
const LARGE_FILE = 32 * 1024;
const TINY_EDGE = 320;
const TINY_BLOB = 800;

/**
 * Shrink a photo and encode it as WebP before it is uploaded.
 * The API stores product photos as WebP; sending WebP keeps the upload small.
 * A file the browser cannot decode, or one that decodes to a blank thumbnail, is returned unchanged
 * so the server can encode the original.
 */
export async function compressImageToWebp(file: File): Promise<File> {
  if (!file.type.startsWith("image/") || file.type === "image/svg+xml") return file;
  if (typeof Image === "undefined") return file;
  let image: HTMLImageElement;
  try {
    image = await decodeImage(file);
  } catch {
    return file;
  }
  const longest = Math.max(image.naturalWidth, image.naturalHeight);
  if (longest < 2) return file;
  // Phone photos carry a tiny embedded preview. Encoding that preview stored a blank tile.
  if (file.size > LARGE_FILE && longest < TINY_EDGE) return file;
  const scale = Math.min(1, MAX_EDGE / longest);
  const width = Math.max(1, Math.round(image.naturalWidth * scale));
  const height = Math.max(1, Math.round(image.naturalHeight * scale));
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) return file;
  context.drawImage(image, 0, 0, width, height);
  const webp = await encode(canvas, "image/webp");
  if (usable(webp, file)) return asFile(file, webp, "webp", "image/webp");
  const jpeg = await encode(canvas, "image/jpeg");
  if (usable(jpeg, file)) return asFile(file, jpeg, "jpg", "image/jpeg");
  return file;
}

function decodeImage(file: File): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      URL.revokeObjectURL(url);
      resolve(image);
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("undecodable"));
    };
    image.src = url;
  });
}

function encode(canvas: HTMLCanvasElement, type: string): Promise<Blob | null> {
  return new Promise((resolve) => canvas.toBlob((blob) => resolve(blob), type, QUALITY));
}

function usable(blob: Blob | null, source: File): blob is Blob {
  if (!blob || blob.size === 0) return false;
  return !(source.size > LARGE_FILE && blob.size < TINY_BLOB);
}

function asFile(source: File, blob: Blob, extension: string, type: string): File {
  const stem = source.name.replace(/\.[^.]+$/, "") || "photo";
  return new File([blob], `${stem}.${extension}`, { type });
}
