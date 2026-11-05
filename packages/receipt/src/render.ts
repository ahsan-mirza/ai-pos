import QRCode from "qrcode";
import { packBits, receiptOps, type ReceiptDoc, type ReceiptOp } from "./doc";

const FONT = "Archivo, 'Segoe UI', Tahoma, sans-serif";
const ARABIC_FONT = "'Noto Naskh Arabic', Tahoma, sans-serif";
const PADDING = 12;

/** Printable dots across the paper: 576 for 80 mm, 384 for 58 mm. */
export const PAPER_DOTS = { "80mm": 576, "58mm": 384 } as const;

function arabicScript(text: string): boolean {
  return /[\u0600-\u06FF]/.test(text);
}

function font(size: number, bold?: boolean, arabic = false): string {
  return `${bold ? 700 : 400} ${size}px ${arabic ? ARABIC_FONT : FONT}`;
}

/** Word-wraps each paragraph; explicit line breaks in the text are kept. */
function wrap(ctx: CanvasRenderingContext2D, text: string, width: number): string[] {
  const lines: string[] = [];
  for (const paragraph of text.split(/\r?\n/)) {
    const words = paragraph.split(/\s+/).filter(Boolean);
    let current = "";
    const pushWide = (word: string) => {
      let chunk = "";
      for (const char of word) {
        const nextChunk = chunk + char;
        if (chunk && ctx.measureText(nextChunk).width > width) {
          lines.push(chunk);
          chunk = char;
        } else {
          chunk = nextChunk;
        }
      }
      current = chunk;
    };
    for (const word of words) {
      if (ctx.measureText(word).width > width) {
        if (current) lines.push(current);
        pushWide(word);
        continue;
      }
      const next = current ? `${current} ${word}` : word;
      if (ctx.measureText(next).width <= width || current === "") {
        current = next;
      } else {
        lines.push(current);
        current = word;
      }
    }
    lines.push(current);
  }
  return lines.length > 0 ? lines : [""];
}

function loadImage(src: string): Promise<HTMLImageElement | null> {
  return new Promise((resolve) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => resolve(null);
    image.src = src;
  });
}

/** Lays the ops out top to bottom; draws only when `paint` is set, so the same pass also measures height. */
function layout(
  ctx: CanvasRenderingContext2D,
  ops: ReceiptOp[],
  width: number,
  paint: boolean,
  images: Map<string, HTMLImageElement>,
): number {
  const inner = width - PADDING * 2;
  let y = PADDING;
  ctx.fillStyle = "#000";
  ctx.strokeStyle = "#000";
  ctx.textBaseline = "top";
  for (const op of ops) {
    if (op.kind === "gap") {
      y += op.height;
    } else if (op.kind === "image") {
      const image = images.get(op.src);
      if (!image || image.naturalWidth === 0) continue;
      const scale = Math.min(1, inner / image.naturalWidth, op.maxHeight / image.naturalHeight);
      const drawWidth = Math.round(image.naturalWidth * scale);
      const drawHeight = Math.round(image.naturalHeight * scale);
      if (paint) {
        ctx.imageSmoothingEnabled = scale < 1;
        ctx.drawImage(image, Math.round((width - drawWidth) / 2), y, drawWidth, drawHeight);
      }
      y += drawHeight;
    } else if (op.kind === "rule") {
      y += 8;
      if (paint) {
        ctx.lineWidth = 2;
        ctx.setLineDash(op.dashed ? [6, 6] : []);
        ctx.beginPath();
        ctx.moveTo(PADDING, y);
        ctx.lineTo(width - PADDING, y);
        ctx.stroke();
        ctx.setLineDash([]);
      }
      y += 10;
    } else if (op.kind === "band") {
      const height = op.size + 16;
      const rtl = Boolean(op.rtl) || arabicScript(op.text);
      ctx.font = font(op.size, true, rtl);
      ctx.direction = rtl ? "rtl" : "ltr";
      if (paint) {
        ctx.fillStyle = "#000";
        ctx.fillRect(PADDING, y, inner, height);
        ctx.fillStyle = "#fff";
        ctx.textAlign = "center";
        ctx.fillText(op.text, width / 2, y + 8);
        ctx.fillStyle = "#000";
      }
      ctx.direction = "ltr";
      y += height + 6;
    } else if (op.kind === "qr") {
      const matrix = QRCode.create(op.data, { errorCorrectionLevel: "M" }).modules;
      const cell = Math.max(1, Math.floor(Math.min(op.size, inner) / matrix.size));
      const left = Math.round((width - cell * matrix.size) / 2);
      if (paint) {
        for (let row = 0; row < matrix.size; row += 1) {
          for (let column = 0; column < matrix.size; column += 1) {
            if (matrix.get(row, column)) ctx.fillRect(left + column * cell, y + row * cell, cell, cell);
          }
        }
      }
      y += cell * matrix.size;
    } else if (op.kind === "row") {
      const valueRtl = arabicScript(op.right);
      ctx.font = font(op.size, op.bold, valueRtl);
      ctx.direction = "ltr";
      const valueWidth = ctx.measureText(op.right).width;
      const labelRtl = Boolean(op.rtl) || arabicScript(op.left);
      ctx.font = font(op.size, op.bold, labelRtl);
      ctx.direction = labelRtl ? "rtl" : "ltr";
      const lines = wrap(ctx, op.left, Math.max(inner - valueWidth - 16, inner / 3));
      if (paint) {
        if (op.rtl) {
          ctx.textAlign = "right";
          lines.forEach((line, index) => ctx.fillText(line, width - PADDING, y + index * (op.size + 6)));
          ctx.font = font(op.size, op.bold, valueRtl);
          ctx.direction = valueRtl ? "rtl" : "ltr";
          ctx.textAlign = "left";
          ctx.fillText(op.right, PADDING, y);
        } else {
          ctx.textAlign = "left";
          lines.forEach((line, index) => ctx.fillText(line, PADDING, y + index * (op.size + 6)));
          ctx.font = font(op.size, op.bold, valueRtl);
          ctx.direction = valueRtl ? "rtl" : "ltr";
          ctx.textAlign = "right";
          ctx.fillText(op.right, width - PADDING, y);
        }
      }
      ctx.direction = "ltr";
      y += lines.length * (op.size + 6);
    } else {
      const rtl = Boolean(op.rtl) || arabicScript(op.text);
      ctx.font = font(op.size, op.bold, rtl);
      ctx.direction = rtl ? "rtl" : "ltr";
      const align = op.align ?? "left";
      const lines = wrap(ctx, op.text, inner);
      if (paint) {
        ctx.textAlign = align;
        const x = align === "center" ? width / 2 : align === "right" ? width - PADDING : PADDING;
        lines.forEach((line, index) => ctx.fillText(line, x, y + index * (op.size + 6)));
      }
      ctx.direction = "ltr";
      y += lines.length * (op.size + 6);
    }
  }
  return Math.ceil(y + PADDING);
}

export interface RenderedReceipt {
  width: number;
  height: number;
  canvas: HTMLCanvasElement;
  bits: () => number[];
}

/** Draws the slip exactly as the thermal printer receives it; the admin preview uses the same pass. */
export async function renderReceipt(doc: ReceiptDoc, width: number): Promise<RenderedReceipt> {
  return renderOps(receiptOps(doc), width);
}

/** Draws any slip built from receipt ops (kitchen tickets use this without the money lines). */
export async function renderOps(ops: ReceiptOp[], width: number): Promise<RenderedReceipt> {
  await Promise.all([
    document.fonts?.load(font(22, true))?.catch(() => undefined),
    document.fonts?.load(font(22, true, true))?.catch(() => undefined),
  ]);
  const images = new Map<string, HTMLImageElement>();
  for (const op of ops) {
    if (op.kind !== "image" || images.has(op.src)) continue;
    const image = await loadImage(op.src);
    if (image) images.set(op.src, image);
  }
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = 10;
  const measure = canvas.getContext("2d");
  if (!measure) throw new Error("This device cannot draw receipts (no canvas).");
  const height = layout(measure, ops, width, false, images);
  canvas.height = height;
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, width, height);
  layout(ctx, ops, width, true, images);
  return {
    width,
    height,
    canvas,
    bits: () => packBits(ctx.getImageData(0, 0, width, height).data, width, height),
  };
}
