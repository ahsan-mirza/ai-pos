import { useEffect, useRef, useState } from "react";

const MAX_BYTES = 5 * 1024 * 1024;
const MAX_PHOTOS = 24;

export interface PendingPhoto {
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

/** Queues catalogue photos. The main photo is uploaded first so the register shows that picture. */
export function ProductPhotos({
  photos,
  mainKey,
  onChange,
}: {
  photos: PendingPhoto[];
  mainKey: string | null;
  onChange: (photos: PendingPhoto[], mainKey: string | null) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
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
      if (main === null) main = key;
    }
    setError(problem);
    onChange(next, main);
    if (input.current) input.current.value = "";
  };

  return (
    <div className="mb-5">
      <p className="text-sm font-semibold">Photos</p>
      <p className="mb-2 text-xs text-zinc-500">JPEG, PNG or WebP, up to 5 MB. The main photo is the picture shown on the register.</p>
      {photos.length > 0 ? (
        <ul className="mb-3 grid grid-cols-3 gap-2 sm:grid-cols-4">
          {photos.map((photo) => {
            const main = photo.key === mainKey;
            return (
              <li key={photo.key} className="relative overflow-hidden rounded-2xl border border-zinc-200">
                <img src={previews[photo.key]} alt="" className="aspect-square w-full object-cover" />
                <div className="absolute inset-x-1 bottom-1 flex justify-end gap-1">
                  {main ? <span className="rounded-full bg-orange-500 px-2 py-0.5 text-[0.625rem] font-semibold text-white">Main</span> : (
                    <button type="button" className="rounded-full bg-white px-2 py-0.5 text-[0.625rem] font-semibold" onClick={() => onChange(photos, photo.key)}>
                      Main
                    </button>
                  )}
                  <button
                    type="button"
                    className="rounded-full bg-white px-2 py-0.5 text-[0.625rem] font-semibold"
                    onClick={() => {
                      const remaining = photos.filter((item) => item.key !== photo.key);
                      onChange(remaining, photo.key === mainKey ? (remaining[0]?.key ?? null) : mainKey);
                    }}
                  >
                    Remove
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      ) : null}
      <button
        type="button"
        onClick={() => input.current?.click()}
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault();
          add(event.dataTransfer.files);
        }}
        className="flex h-28 w-full items-center justify-center rounded-2xl border border-dashed border-zinc-300 bg-zinc-50 text-sm text-zinc-600"
      >
        Drop photos here or browse files
      </button>
      <input ref={input} type="file" accept="image/jpeg,image/png,image/webp" multiple className="hidden" onChange={(event) => add(event.target.files)} />
      {error ? <p role="alert" className="mt-2 text-xs font-medium text-red-700">{error}</p> : null}
    </div>
  );
}
