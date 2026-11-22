import { useEffect, useState } from "react";
import { env } from "../../config/env";
import { inventoryApi, inventoryError, type CatalogueImage } from "./api";
import { compressImageToWebp } from "./imageFile";

function media(url: string): string {
  try {
    const parsed = new URL(url, env.apiBaseUrl);
    if (!parsed.pathname.startsWith("/media/")) return url;
    return `${env.apiBaseUrl}${parsed.pathname}${parsed.search}`;
  } catch {
    return url;
  }
}

/** Saved catalogue photos: view, set the main photo, reorder, replace by adding, and delete. */
export function SavedPhotoGallery({ productId }: { productId: string }) {
  const [images, setImages] = useState<CatalogueImage[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () => {
    void inventoryApi.productImages(productId).then(setImages).catch((caught) => setError(inventoryError(caught, "Could not load photos.")));
  };
  useEffect(load, [productId]);

  const run = async (action: () => Promise<unknown>, failure: string) => {
    setBusy(true);
    setError(null);
    try {
      await action();
      setImages(await inventoryApi.productImages(productId));
    } catch (caught) {
      setError(inventoryError(caught, failure));
    } finally {
      setBusy(false);
    }
  };

  const ordered = [...images].sort((left, right) => left.position - right.position);

  return (
    <section className="mb-4">
      <p className="text-sm font-semibold">Saved photos</p>
      <p className="mb-2 text-xs text-zinc-500">The main photo is the one shown on the register. JPEG, PNG or WebP, up to 5 MB.</p>
      {ordered.length === 0 ? <p className="text-sm text-zinc-500">No photos yet.</p> : null}
      <ul className="grid grid-cols-3 gap-2 sm:grid-cols-4">
        {ordered.map((image, index) => (
          <li key={image.id} className="relative overflow-hidden rounded-2xl border border-zinc-200">
            <img src={media(image.thumb_url || image.url)} alt="" className="aspect-square w-full object-cover" />
            <div className="absolute inset-x-1 bottom-1 flex justify-end gap-1">
              {image.is_primary ? <span className="rounded-full bg-orange-500 px-2 py-0.5 text-[0.625rem] font-semibold text-white">Main</span> : (
                <button type="button" disabled={busy} className="rounded-full bg-white px-2 py-0.5 text-[0.625rem] font-semibold" onClick={() => void run(() => inventoryApi.updateImage(image.id, { is_primary: true }), "Could not change the cover.")}>Main</button>
              )}
              {index > 0 ? <button type="button" disabled={busy} className="rounded-full bg-white px-2 py-0.5 text-[0.625rem]" onClick={() => void run(() => inventoryApi.updateImage(image.id, { position: ordered[index - 1]!.position }), "Could not reorder the photo.")}>Earlier</button> : null}
              {index < ordered.length - 1 ? <button type="button" disabled={busy} className="rounded-full bg-white px-2 py-0.5 text-[0.625rem]" onClick={() => void run(() => inventoryApi.updateImage(image.id, { position: ordered[index + 1]!.position }), "Could not reorder the photo.")}>Later</button> : null}
              <button type="button" disabled={busy} className="rounded-full bg-white px-2 py-0.5 text-[0.625rem] font-semibold" onClick={() => void run(() => inventoryApi.deleteImage(image.id), "Could not delete the photo.")}>Remove</button>
            </div>
          </li>
        ))}
      </ul>
      <label className="mt-2 inline-block text-sm font-semibold">
        Add or replace
        <input
          type="file"
          accept="image/jpeg,image/png,image/webp"
          multiple
          className="mt-1 block text-xs"
          disabled={busy}
          onChange={(event) => {
            const files = Array.from(event.target.files ?? []);
            event.target.value = "";
            if (files.length === 0) return;
            void run(async () => {
              for (const file of files) await inventoryApi.uploadProductImage(productId, await compressImageToWebp(file));
            }, "Could not upload the photo.");
          }}
        />
      </label>
      {error ? <p role="alert" className="mt-2 text-xs font-medium text-red-700">{error}</p> : null}
    </section>
  );
}
