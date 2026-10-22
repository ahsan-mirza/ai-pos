import type { ProductImage } from "@ai-pos/shared-types";
import { ImagePlus, Loader2, Star, Trash2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiDelete, apiGet, apiPatch, apiUpload } from "../../lib/api";
import { compressImageToWebp } from "../../lib/imageFile";
import { errorMessage } from "../users/api";

interface PhotoGalleryProps {
  /** `/api/v1/inventory/products/{id}/images` or `/api/v1/product-models/{id}/images`. */
  path: string;
  canManage: boolean;
  /** Model galleries: the colours a photo can be tagged with, so each colour's variants show their own photo. */
  colours?: string[];
  /** Shown when there are no photos of its own (a variant falls back to its model's photo). */
  fallbackUrl?: string | null;
  onChange?: () => void;
}

const ACCEPT = "image/jpeg,image/png,image/webp";

/** Upload, order and tag product photos. Each file is compressed to WebP here, then stored as WebP on the server. */
export function PhotoGallery({ path, canManage, colours = [], fallbackUrl = null, onChange }: PhotoGalleryProps) {
  const [images, setImages] = useState<ProductImage[] | null>(null);
  const [colour, setColour] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      setImages(await apiGet<ProductImage[]>(path));
    } catch (caught) {
      setError(errorMessage(caught, "Could not load photos."));
    }
  }, [path]);

  useEffect(() => {
    void load();
  }, [load]);

  const changed = async () => {
    await load();
    onChange?.();
  };

  const upload = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      for (const file of Array.from(files)) {
        const form = new FormData();
        form.append("file", await compressImageToWebp(file));
        if (colour) form.append("attribute_value", colour);
        await apiUpload<ProductImage>(path, form);
      }
      await changed();
    } catch (caught) {
      setError(errorMessage(caught, "Could not upload the photo."));
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  };

  const act = async (run: () => Promise<unknown>, failure: string) => {
    setBusy(true);
    setError(null);
    try {
      await run();
      await changed();
    } catch (caught) {
      setError(errorMessage(caught, failure));
    } finally {
      setBusy(false);
    }
  };

  const empty = images !== null && images.length === 0;
  return (
    <section>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-charcoal/50">Photos</h4>
        {canManage ? (
          <div className="flex items-center gap-2">
            {colours.length ? (
              <select
                aria-label="Colour for new photos"
                value={colour}
                onChange={(event) => setColour(event.target.value)}
                className="h-8 rounded-full border border-line bg-white px-3 text-xs"
              >
                <option value="">All colours</option>
                {colours.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            ) : null}
            <button
              type="button"
              disabled={busy}
              onClick={() => input.current?.click()}
              className="inline-flex h-8 items-center gap-1.5 rounded-full bg-charcoal px-3 text-xs font-semibold text-white disabled:opacity-50"
            >
              {busy ? <Loader2 size={14} className="animate-spin" aria-hidden="true" /> : <ImagePlus size={14} aria-hidden="true" />}
              Add photos
            </button>
            <input
              ref={input}
              type="file"
              accept={ACCEPT}
              multiple
              hidden
              onChange={(event) => void upload(event.target.files)}
            />
          </div>
        ) : null}
      </div>
      {empty ? (
        fallbackUrl ? (
          <div className="flex items-center gap-3 rounded-2xl bg-surface p-3 text-sm text-charcoal/60">
            <img src={fallbackUrl} alt="" className="h-16 w-16 rounded-xl object-cover" />
            Showing the model&apos;s photo. Add a photo here to show this variant on its own.
          </div>
        ) : (
          <p className="rounded-2xl bg-surface px-4 py-6 text-center text-sm text-charcoal/60">
            No photos yet. JPEG, PNG or WebP, up to 5 MB each.
          </p>
        )
      ) : (
        <ul className="grid grid-cols-3 gap-2 sm:grid-cols-4">
          {(images ?? []).map((image) => (
            <li key={image.id} className="group relative overflow-hidden rounded-2xl border border-line bg-surface">
              <img src={image.thumb_url} alt="" loading="lazy" className="aspect-square w-full object-cover" />
              <div className="absolute inset-x-1 top-1 flex justify-between gap-1">
                {image.is_primary ? (
                  <span className="rounded-full bg-accent px-2 py-0.5 text-[10px] font-semibold text-white">Cover</span>
                ) : (
                  <span />
                )}
                {image.attribute_value ? (
                  <span className="truncate rounded-full bg-white/90 px-2 py-0.5 text-[10px] font-semibold">
                    {image.attribute_value}
                  </span>
                ) : null}
              </div>
              {canManage ? (
                <div className="absolute inset-x-1 bottom-1 flex justify-end gap-1 opacity-0 transition group-focus-within:opacity-100 group-hover:opacity-100">
                  {!image.is_primary ? (
                    <button
                      type="button"
                      aria-label="Use as cover"
                      title="Use as cover"
                      disabled={busy}
                      onClick={() =>
                        void act(
                          () => apiPatch(`/api/v1/inventory/images/${image.id}`, { is_primary: true }),
                          "Could not change the cover.",
                        )
                      }
                      className="grid h-7 w-7 place-items-center rounded-full bg-white text-charcoal shadow"
                    >
                      <Star size={13} aria-hidden="true" />
                    </button>
                  ) : null}
                  <button
                    type="button"
                    aria-label="Delete photo"
                    title="Delete photo"
                    disabled={busy}
                    onClick={() =>
                      void act(() => apiDelete(`/api/v1/inventory/images/${image.id}`), "Could not delete the photo.")
                    }
                    className="grid h-7 w-7 place-items-center rounded-full bg-white text-accent shadow"
                  >
                    <Trash2 size={13} aria-hidden="true" />
                  </button>
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {error ? (
        <p role="alert" className="mt-2 text-sm text-accent">
          {error}
        </p>
      ) : null}
    </section>
  );
}
