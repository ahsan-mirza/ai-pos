import { ImagePlus, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

const MAX_BYTES = 5 * 1024 * 1024;

export interface ProductPhotoChoice {
  file: File | null;
  removed: boolean;
}

function rejectReason(file: File): string | null {
  const type = file.type.toLowerCase();
  const name = file.name.toLowerCase();
  const allowed = type === "image/jpeg" || type === "image/png" || name.endsWith(".jpg") || name.endsWith(".jpeg") || name.endsWith(".png");
  if (!allowed) return "Use a PNG or JPG.";
  if (file.size > MAX_BYTES) return "Photos are limited to 5 MB.";
  return null;
}

/** One cover photo for the product form: drag a PNG or JPG, preview it, or clear it. */
export function ProductImageDropzone({
  currentUrl,
  onChange,
}: {
  currentUrl: string | null;
  onChange: (choice: ProductPhotoChoice) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [removed, setRemoved] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);

  useEffect(() => {
    if (file === null) {
      setPreview(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const shown = preview ?? (removed ? null : currentUrl);

  const choose = (next: File | null) => {
    if (next === null) {
      setFile(null);
      setRemoved(true);
      setError(null);
      onChange({ file: null, removed: true });
      if (input.current) input.current.value = "";
      return;
    }
    const reason = rejectReason(next);
    if (reason) {
      setError(reason);
      return;
    }
    setFile(next);
    setRemoved(false);
    setError(null);
    onChange({ file: next, removed: false });
  };

  const take = (list: FileList | null) => {
    const next = list?.[0];
    if (next) choose(next);
  };

  return (
    <div className="mb-5">
      <p className="mb-2 text-sm font-semibold">Photo</p>
      {shown ? (
        <div className="flex items-center gap-4 rounded-2xl border border-line bg-surface p-3">
          <img src={shown} alt="" className="h-20 w-20 rounded-xl object-cover" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">{file ? file.name : "Cover photo"}</p>
            <p className="text-xs text-charcoal/50">PNG or JPG, up to 5 MB. This is the image on the register.</p>
            <div className="mt-2 flex gap-2">
              <button type="button" onClick={() => input.current?.click()} className="text-sm font-semibold text-accent">
                Replace
              </button>
              <button type="button" onClick={() => choose(null)} className="inline-flex items-center gap-1 text-sm font-semibold text-charcoal/60">
                <Trash2 size={14} aria-hidden="true" /> Remove
              </button>
            </div>
          </div>
        </div>
      ) : (
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
            take(event.dataTransfer.files);
          }}
          className={`flex w-full flex-col items-center gap-2 rounded-2xl border border-dashed px-4 py-8 text-center ${
            dragOver ? "border-accent bg-accent/5" : "border-line bg-surface"
          }`}
        >
          <ImagePlus size={22} aria-hidden="true" className="text-charcoal/40" />
          <span className="text-sm font-semibold">Drop a photo here, or browse</span>
          <span className="text-xs text-charcoal/50">PNG or JPG, up to 5 MB</span>
        </button>
      )}
      {error ? <p className="mt-2 text-sm text-accent">{error}</p> : null}
      <input
        ref={input}
        type="file"
        accept="image/png,image/jpeg"
        hidden
        onChange={(event) => take(event.target.files)}
      />
    </div>
  );
}
