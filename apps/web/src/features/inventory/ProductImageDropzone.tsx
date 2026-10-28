import { ImagePlus, Star, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

const MAX_BYTES = 5 * 1024 * 1024;
const MAX_PHOTOS = 24;

export interface PendingProductPhoto {
  key: string;
  file: File;
}

function rejectReason(file: File): string | null {
  const type = file.type.toLowerCase();
  const name = file.name.toLowerCase();
  const allowed =
    type === "image/jpeg" ||
    type === "image/png" ||
    type === "image/webp" ||
    name.endsWith(".jpg") ||
    name.endsWith(".jpeg") ||
    name.endsWith(".png") ||
    name.endsWith(".webp");
  if (!allowed) return "Use a JPEG, PNG or WebP.";
  if (file.size > MAX_BYTES) return "Photos are limited to 5 MB.";
  return null;
}

/** Photos queued on a new product. The main one is uploaded first, so the register shows that picture. */
export function ProductImageDropzone({
  photos,
  mainKey,
  onChange,
}: {
  photos: PendingProductPhoto[];
  mainKey: string | null;
  onChange: (photos: PendingProductPhoto[], mainKey: string | null) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [previews, setPreviews] = useState<Record<string, string>>({});

  useEffect(() => {
    const urls: Record<string, string> = {};
    for (const photo of photos) urls[photo.key] = URL.createObjectURL(photo.file);
    setPreviews(urls);
    return () => {
      for (const url of Object.values(urls)) URL.revokeObjectURL(url);
    };
  }, [photos]);

  const add = (list: FileList | null) => {
    if (!list || list.length === 0) return;
    const next = [...photos];
    let main = mainKey;
    let problem: string | null = null;
    for (const file of Array.from(list)) {
      if (next.length >= MAX_PHOTOS) {
        problem = `Keep at most ${MAX_PHOTOS} photos.`;
        break;
      }
      const reason = rejectReason(file);
      if (reason) {
        problem = `${file.name}: ${reason}`;
        continue;
      }
      const key = crypto.randomUUID();
      next.push({ key, file });
      if (main === null || !next.some((photo) => photo.key === main)) main = key;
    }
    setError(problem);
    onChange(next, main);
    if (input.current) input.current.value = "";
  };

  const remove = (key: string) => {
    const next = photos.filter((photo) => photo.key !== key);
    const main = key === mainKey ? (next[0]?.key ?? null) : mainKey;
    setError(null);
    onChange(next, main);
  };

  return (
    <div className="mb-5">
      <p className="text-sm font-semibold">Photos</p>
      <p className="mb-2 text-xs text-charcoal/50">Add several photos. The main one is the picture shown on the register.</p>
      {photos.length > 0 ? (
        <ul className="mb-3 grid grid-cols-3 gap-2 sm:grid-cols-4">
          {photos.map((photo) => {
            const main = photo.key === mainKey;
            return (
              <li key={photo.key} className="relative overflow-hidden rounded-2xl border border-line bg-surface">
                <img src={previews[photo.key]} alt="" className="aspect-square w-full object-cover" />
                <div className="absolute inset-x-1 top-1 flex justify-between gap-1">
                  {main ? (
                    <span className="rounded-full bg-accent px-2 py-0.5 text-[10px] font-semibold text-white">Main</span>
                  ) : (
                    <span />
                  )}
                </div>
                <div className="absolute inset-x-1 bottom-1 flex justify-end gap-1">
                  {main ? null : (
                    <button
                      type="button"
                      aria-label="Use as the main photo"
                      title="Use as the main photo"
                      onClick={() => onChange(photos, photo.key)}
                      className="grid h-7 w-7 place-items-center rounded-full bg-white text-charcoal shadow"
                    >
                      <Star size={13} aria-hidden="true" />
                    </button>
                  )}
                  <button
                    type="button"
                    aria-label="Remove photo"
                    title="Remove photo"
                    onClick={() => remove(photo.key)}
                    className="grid h-7 w-7 place-items-center rounded-full bg-white text-accent shadow"
                  >
                    <Trash2 size={13} aria-hidden="true" />
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      ) : null}
      {photos.length < MAX_PHOTOS ? (
        <button
          type="button"
          onClick={() => input.current?.click()}
          onDragEnter={(event) => {
            event.preventDefault();
            setDragOver(true);
          }}
          onDragOver={(event) => {
            event.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragOver(false);
            add(event.dataTransfer.files);
          }}
          className={`flex w-full flex-col items-center gap-2 rounded-2xl border border-dashed px-4 py-6 text-center ${
            dragOver ? "border-accent bg-accent/5" : "border-line bg-surface"
          }`}
        >
          <ImagePlus size={22} aria-hidden="true" className="text-charcoal/40" />
          <span className="text-sm font-semibold">{photos.length === 0 ? "Drop photos here, or browse" : "Add more photos"}</span>
          <span className="text-xs text-charcoal/50">JPEG, PNG or WebP, up to 5 MB each</span>
        </button>
      ) : null}
      {error ? <p className="mt-2 text-sm text-danger">{error}</p> : null}
      <input
        ref={input}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        multiple
        hidden
        onChange={(event) => add(event.target.files)}
      />
    </div>
  );
}
