const MAX_EDGE = 1600;
const QUALITY = 0.82;

/**
 * Shrink a photo and encode it as WebP before it is uploaded.
 * The API stores product photos as WebP; sending WebP keeps the upload small.
 * A file the browser cannot decode is returned unchanged.
 */
export async function compressImageToWebp(file: File): Promise<File> {
  if (!file.type.startsWith("image/") || file.type === "image/svg+xml") return file;
  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(file);
  } catch {
    return file;
  }
  const scale = Math.min(1, MAX_EDGE / Math.max(bitmap.width, bitmap.height));
  const width = Math.max(1, Math.round(bitmap.width * scale));
  const height = Math.max(1, Math.round(bitmap.height * scale));
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) {
    bitmap.close();
    return file;
  }
  context.drawImage(bitmap, 0, 0, width, height);
  bitmap.close();
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/webp", QUALITY));
  if (!blob || blob.size === 0) return file;
  const stem = file.name.replace(/\.[^.]+$/, "") || "photo";
  return new File([blob], `${stem}.webp`, { type: "image/webp" });
}
