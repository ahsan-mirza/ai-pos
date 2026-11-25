const MAX_BYTES = 8 * 1024 * 1024;
const MAX_EDGE = 2000;

export function sniffBill(bytes: Uint8Array): "jpeg" | "png" | "webp" | null {
  if (bytes.length >= 3 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff) return "jpeg";
  if (bytes.length >= 8 && bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4e && bytes[3] === 0x47) return "png";
  if (
    bytes.length >= 12 &&
    bytes[0] === 0x52 &&
    bytes[1] === 0x49 &&
    bytes[2] === 0x46 &&
    bytes[3] === 0x46 &&
    bytes[8] === 0x57 &&
    bytes[9] === 0x45 &&
    bytes[10] === 0x42 &&
    bytes[11] === 0x50
  ) {
    return "webp";
  }
  return null;
}

export interface PreparedBill {
  fileName: string;
  contentType: "image/webp" | "image/jpeg";
  originalBytes: number;
  compressedBytes: number;
  dataBase64: string;
  previewUrl: string;
}

/** Preview copy. The API decodes the bytes again and stores its own compressed file. */
export async function prepareBill(file: File): Promise<PreparedBill> {
  if (file.size === 0) throw new Error("The bill image could not be processed. Try another image.");
  if (file.size > MAX_BYTES) throw new Error("The attachment exceeds the permitted size.");
  const bytes = new Uint8Array(await file.arrayBuffer());
  if (sniffBill(bytes) === null) throw new Error("Unsupported bill format. Upload a JPG, PNG or WebP image.");
  if (typeof createImageBitmap !== "function") throw new Error("The bill image could not be processed. Try another image.");
  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(file);
  } catch {
    throw new Error("The bill image could not be processed. Try another image.");
  }
  const scale = Math.min(1, MAX_EDGE / Math.max(bitmap.width, bitmap.height));
  const width = Math.max(1, Math.round(bitmap.width * scale));
  const height = Math.max(1, Math.round(bitmap.height * scale));
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (context === null) throw new Error("The bill image could not be processed. Try another image.");
  context.drawImage(bitmap, 0, 0, width, height);
  bitmap.close();
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/webp", 0.85));
  const encoded = blob ?? (await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.85)));
  if (encoded === null) throw new Error("The bill image could not be processed. Try another image.");
  const contentType = encoded.type === "image/jpeg" ? "image/jpeg" : "image/webp";
  const encodedBytes = new Uint8Array(await encoded.arrayBuffer());
  let binary = "";
  for (let index = 0; index < encodedBytes.length; index += 0x8000) {
    binary += String.fromCharCode(...encodedBytes.subarray(index, index + 0x8000));
  }
  return {
    fileName: file.name || "bill",
    contentType,
    originalBytes: file.size,
    compressedBytes: encoded.size,
    dataBase64: btoa(binary),
    previewUrl: URL.createObjectURL(encoded),
  };
}
