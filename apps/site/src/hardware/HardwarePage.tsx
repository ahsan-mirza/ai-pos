import { useEffect, useState, type ReactNode } from "react";
import { apiBaseUrl } from "../env";
import type { PublicWhatsApp } from "../whatsapp";
import { EnquiryForm } from "./EnquiryForm";
import {
  hardwareView,
  productJsonLd,
  publicPrice,
  readCategory,
  readList,
  readPackage,
  readPackageCard,
  readProduct,
  segmentProducts,
  stockLabel,
  type HardwareCategory,
  type HardwarePackage,
  type HardwarePackageCard,
  type HardwareProduct,
} from "./model";

const WHY = [
  ["One catalogue", "The website and the AxizPOS console read the same published hardware records."],
  ["Software stays on the billing plan", "A package can include an existing AxizPOS plan. The monthly amount is the plan price, not a second price list."],
  ["A quote before a purchase", "An enquiry records what you asked for. It does not open a store or take a payment."],
  ["Built for the counter", "Registers, printers, scanners, drawers, scales, and displays can be grouped into a package."],
];

async function loadJson(path: string): Promise<unknown> {
  const response = await fetch(`${apiBaseUrl}${path}`);
  if (!response.ok) throw new Error("catalogue");
  return response.json();
}

function photo(product: HardwareProduct): { src: string; alt: string } | null {
  const image = product.images.find((item) => item.is_primary) ?? product.images[0];
  return image ? { src: image.thumb_url || image.url, alt: image.alt || product.name } : null;
}

function Price({ fils, currency }: { fils: number | null; currency: string }) {
  const label = publicPrice(fils, currency);
  return <p className="text-lg font-semibold text-charcoal">{label ?? "Price on request"}</p>;
}

function ProductCard({ product }: { product: HardwareProduct }) {
  const image = photo(product);
  return (
    <article className="flex h-full flex-col overflow-hidden rounded-3xl border border-line bg-card">
      {image ? <img src={image.src} alt={image.alt} className="aspect-[4/3] w-full object-cover" /> : <div className="aspect-[4/3] bg-canvas" />}
      <div className="flex flex-1 flex-col gap-2 p-5">
        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-primary">{product.category_name}</p>
        <h3 className="text-lg font-semibold">{product.name}</h3>
        <p className="text-sm text-charcoal/60">{[product.brand, product.model_number].filter(Boolean).join(" · ")}</p>
        <p className="text-sm leading-6 text-charcoal/75">{product.short_description}</p>
        <Price fils={product.display_price_fils} currency={product.currency} />
        <p className="text-sm text-charcoal/70">{stockLabel(product.stock_status)}{product.warranty_months ? ` · ${product.warranty_months} month warranty` : ""}</p>
        {product.compatibility ? <p className="text-sm text-charcoal/70">{product.compatibility}</p> : null}
        <a className="mt-auto inline-flex text-sm font-medium text-primary" href={`/hardware/products/${product.slug}`}>
          View details
        </a>
      </div>
    </article>
  );
}

export function HardwarePage({ contact }: { contact: PublicWhatsApp }) {
  const path = window.location.pathname;
  const view = hardwareView(path);
  const [categories, setCategories] = useState<HardwareCategory[]>([]);
  const [products, setProducts] = useState<HardwareProduct[]>([]);
  const [featured, setFeatured] = useState<HardwareProduct[]>([]);
  const [packages, setPackages] = useState<HardwarePackageCard[]>([]);
  const [detailProduct, setDetailProduct] = useState<HardwareProduct | null>(null);
  const [detailPackage, setDetailPackage] = useState<HardwarePackage | null>(null);
  const [plans, setPlans] = useState<HardwarePackage["plan"][]>([]);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [status, setStatus] = useState<"loading" | "ready" | "unavailable">("loading");
  const [detailStatus, setDetailStatus] = useState<"loading" | "ready" | "missing">("loading");

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      loadJson("/api/v1/public/hardware/categories"),
      loadJson("/api/v1/public/hardware/products?limit=48"),
      loadJson("/api/v1/public/hardware/products?featured=true&limit=8"),
      loadJson("/api/v1/public/hardware/packages?limit=24"),
    ])
      .then(async ([categoryRows, productRows, featuredRows, packageRows]) => {
        if (cancelled) return;
        const nextPackages = readList(packageRows, readPackageCard);
        setCategories(readList(categoryRows, readCategory));
        setProducts(readList(productRows, readProduct));
        setFeatured(readList(featuredRows, readProduct));
        setPackages(nextPackages);
        const details = await Promise.all(
          nextPackages.slice(0, 8).map((item) => loadJson(`/api/v1/public/hardware/packages/${item.slug}`).then(readPackage).catch(() => null)),
        );
        if (!cancelled) setPlans(details.flatMap((item) => (item?.plan ? [item.plan] : [])));
        setStatus("ready");
      })
      .catch(() => {
        if (!cancelled) setStatus("unavailable");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (view.kind === "catalog") return;
    let cancelled = false;
    const path = view.kind === "product" ? `/api/v1/public/hardware/products/${view.slug}` : `/api/v1/public/hardware/packages/${view.slug}`;
    loadJson(path)
      .then((body) => {
        if (cancelled) return;
        if (view.kind === "product") {
          const product = readProduct(body);
          if (!product) {
            setDetailStatus("missing");
            return;
          }
          setDetailProduct(product);
          const linked = productJsonLd(product, `${window.location.origin}/hardware/products/${product.slug}`);
          document.title = `${product.name} | AxizPOS hardware`;
          document.querySelector('meta[name="description"]')?.setAttribute("content", product.short_description || product.name);
          document.querySelector('link[rel="canonical"]')?.setAttribute("href", `${window.location.origin}/hardware/products/${product.slug}`);
          document.getElementById("hardware-jsonld")?.remove();
          if (linked) {
            const script = document.createElement("script");
            script.id = "hardware-jsonld";
            script.type = "application/ld+json";
            script.textContent = JSON.stringify(linked);
            document.head.appendChild(script);
          }
        } else {
          const bundle = readPackage(body);
          if (!bundle) {
            setDetailStatus("missing");
            return;
          }
          setDetailPackage(bundle);
          document.title = `${bundle.name} | AxizPOS hardware`;
        }
        setDetailStatus("ready");
      })
      .catch(() => {
        if (!cancelled) setDetailStatus("missing");
      });
    return () => {
      cancelled = true;
    };
  }, [path]);

  const visible = products.filter((product) => {
    const words = query.trim().toLowerCase();
    const matchesQuery = !words || `${product.name} ${product.brand} ${product.sku} ${product.short_description}`.toLowerCase().includes(words);
    return matchesQuery && (!category || product.category_slug === category);
  });
  const bundles = packages.filter((item) => item.package_type === "all_in_one" || item.package_type === "hardware_software");
  const segments = segmentProducts(products);
  const uniquePlans = plans.filter((plan, index, all) => plan && all.findIndex((item) => item?.code === plan.code) === index);

  if (view.kind === "product") {
    return (
      <DetailShell>
        {detailStatus === "missing" ? <p>This product is not published.</p> : null}
        {detailProduct ? (
          <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_360px]">
            <div>
              <a className="text-sm text-charcoal/60" href="/hardware">Back to hardware</a>
              <h1 className="mt-3 text-4xl font-semibold">{detailProduct.name}</h1>
              <p className="mt-2 text-charcoal/60">{[detailProduct.brand, detailProduct.model_number].filter(Boolean).join(" · ")}</p>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                {detailProduct.images.map((image) => (
                  <img key={image.url} src={image.url} alt={image.alt || detailProduct.name} className="aspect-square w-full rounded-3xl object-cover" />
                ))}
              </div>
              <p className="mt-6 leading-7 text-charcoal/80">{detailProduct.full_description || detailProduct.short_description}</p>
              {detailProduct.specifications.length ? (
                <table className="mt-6 w-full text-sm">
                  <tbody>
                    {detailProduct.specifications.map((spec) => (
                      <tr key={spec.label} className="border-b border-line">
                        <th className="py-2 text-left font-medium">{spec.label}</th>
                        <td className="py-2 text-charcoal/75">{spec.value}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : null}
              {detailProduct.compatibility ? <p className="mt-4 text-sm leading-6">{detailProduct.compatibility}</p> : null}
              <p className="mt-4 text-sm">{stockLabel(detailProduct.stock_status)}{detailProduct.warranty_months ? ` · ${detailProduct.warranty_months} month warranty` : ""}</p>
              <Price fils={detailProduct.display_price_fils} currency={detailProduct.currency} />
              <h2 className="mt-8 text-xl font-semibold">Related products</h2>
              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                {products.filter((item) => item.category_slug === detailProduct.category_slug && item.slug !== detailProduct.slug).slice(0, 2).map((item) => (
                  <ProductCard key={item.slug} product={item} />
                ))}
              </div>
            </div>
            <EnquiryForm contact={contact} products={detailProduct ? [detailProduct, ...products] : products} packages={packages} productSlug={detailProduct.slug} />
          </div>
        ) : detailStatus === "loading" ? <p>Loading product…</p> : null}
      </DetailShell>
    );
  }

  if (view.kind === "package") {
    return (
      <DetailShell>
        {detailStatus === "missing" ? <p>This package is not published.</p> : null}
        {detailPackage ? (
          <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_360px]">
            <div>
              <a className="text-sm text-charcoal/60" href="/hardware">Back to hardware</a>
              <h1 className="mt-3 text-4xl font-semibold">{detailPackage.name}</h1>
              {detailPackage.images[0] ? <img src={detailPackage.images[0].url} alt={detailPackage.images[0].alt || detailPackage.name} className="mt-4 aspect-video w-full rounded-3xl object-cover" /> : null}
              <Price fils={detailPackage.display_price_fils} currency={detailPackage.currency} />
              <p className="mt-4 leading-7">{detailPackage.full_description || detailPackage.short_description}</p>
              <h2 className="mt-6 text-xl font-semibold">Included hardware</h2>
              <ul className="mt-3 space-y-2">
                {detailPackage.items.map((item) => (
                  <li key={`${item.slug}-${item.name}`} className="flex justify-between gap-3 text-sm">
                    <span>{item.name} × {item.quantity}{item.is_optional ? " · optional" : ""}</span>
                    <span>{publicPrice(item.display_price_fils, "AED") ?? ""}</span>
                  </li>
                ))}
              </ul>
              <h2 className="mt-6 text-xl font-semibold">Software plan</h2>
              {detailPackage.plan ? (
                <p className="mt-2 text-sm">{detailPackage.plan.name} · {publicPrice(detailPackage.plan.monthly_fils, "AED")} / month · {detailPackage.plan.included_registers} registers</p>
              ) : (
                <p className="mt-2 text-sm text-charcoal/60">This package does not include a software plan.</p>
              )}
              {detailPackage.savings_fils != null ? (
                <p className="mt-4 text-sm text-primary">The required hardware display prices add up to {publicPrice(detailPackage.component_value_fils, "AED")}, which is {publicPrice(detailPackage.savings_fils, "AED")} more than this package price.</p>
              ) : null}
            </div>
            <EnquiryForm contact={contact} products={products} packages={packages} packageSlug={detailPackage.slug} />
          </div>
        ) : detailStatus === "loading" ? <p>Loading package…</p> : null}
      </DetailShell>
    );
  }

  return (
    <div>
      <section className="bg-canvas px-4 py-16 sm:px-6 lg:px-8">
        <div className="mx-auto grid max-w-page items-center gap-8 lg:grid-cols-[minmax(0,1fr)_420px]">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">AxizPOS hardware</p>
            <h1 className="mt-3 text-4xl font-semibold tracking-tight sm:text-5xl">POS hardware for the counter you already run</h1>
            <p className="mt-4 max-w-xl text-lg leading-8 text-charcoal/75">Browse published terminals, printers, scanners, and complete packages. Prices appear only when AxizPOS has set a public price.</p>
          </div>
          <img src="/pos/terminal.png" alt="AxizPOS on a register with a customer display, receipt printer, phone, and barcode scanner." className="w-full" />
        </div>
      </section>
      {status === "unavailable" ? <p role="alert" className="mx-auto max-w-page px-4 py-6 text-sm">The hardware catalogue could not be loaded. You can still send an enquiry below.</p> : null}
      <section className="mx-auto max-w-page px-4 py-12 sm:px-6 lg:px-8">
        <h2 className="text-2xl font-semibold">Categories</h2>
        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {categories.map((item) => (
            <button key={item.slug} type="button" className="rounded-3xl border border-line bg-card p-4 text-left" onClick={() => setCategory(item.slug)}>
              {item.image_url ? <img src={item.image_url} alt={item.image_alt} className="mb-3 aspect-video w-full rounded-2xl object-cover" /> : null}
              <span className="font-medium">{item.name}</span>
              {item.description ? <span className="mt-1 block text-sm text-charcoal/65">{item.description}</span> : null}
            </button>
          ))}
        </div>
      </section>
      {featured.length ? (
        <section className="mx-auto max-w-page px-4 py-4 sm:px-6 lg:px-8">
          <h2 className="text-2xl font-semibold">Featured POS products</h2>
          <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {featured.map((product) => <ProductCard key={product.slug} product={product} />)}
          </div>
        </section>
      ) : null}
      {bundles.length ? (
        <section className="mx-auto max-w-page px-4 py-12 sm:px-6 lg:px-8">
          <h2 className="text-2xl font-semibold">All-in-one POS packages</h2>
          <div className="mt-6 grid gap-4 md:grid-cols-2">
            {bundles.map((item) => (
              <a key={item.slug} href={`/hardware/packages/${item.slug}`} className="rounded-3xl border border-line bg-card p-5">
                {item.thumb_url ? <img src={item.thumb_url} alt="" className="mb-3 aspect-video w-full rounded-2xl object-cover" /> : null}
                <h3 className="text-lg font-semibold">{item.name}</h3>
                <p className="mt-2 text-sm text-charcoal/70">{item.short_description}</p>
                <Price fils={item.display_price_fils} currency={item.currency} />
              </a>
            ))}
          </div>
        </section>
      ) : null}
      {uniquePlans.length ? (
        <section className="mx-auto max-w-page px-4 py-4 sm:px-6 lg:px-8">
          <h2 className="text-2xl font-semibold">Compatible software</h2>
          <ul className="mt-4 grid gap-3 sm:grid-cols-2">
            {uniquePlans.map((plan) => plan ? (
              <li key={plan.code} className="rounded-2xl border border-line bg-card px-4 py-3 text-sm">
                {plan.name} · {publicPrice(plan.monthly_fils, "AED")} / month · {plan.included_registers} registers
              </li>
            ) : null)}
          </ul>
        </section>
      ) : null}
      <section className="mx-auto max-w-page px-4 py-12 sm:px-6 lg:px-8">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h2 className="text-2xl font-semibold">All hardware</h2>
          <div className="flex flex-wrap gap-2">
            <input aria-label="Search hardware" className="h-11 rounded-xl border border-line px-3 text-sm" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search" />
            <select aria-label="Filter by category" className="h-11 rounded-xl border border-line px-3 text-sm" value={category} onChange={(event) => setCategory(event.target.value)}>
              <option value="">All categories</option>
              {categories.map((item) => <option key={item.slug} value={item.slug}>{item.name}</option>)}
            </select>
          </div>
        </div>
        <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {visible.map((product) => <ProductCard key={product.slug} product={product} />)}
        </div>
        {status === "ready" && visible.length === 0 ? <p className="mt-6 text-sm text-charcoal/60">No published products match this search.</p> : null}
      </section>
      {segments.length ? (
        <section className="mx-auto max-w-page px-4 py-4 sm:px-6 lg:px-8">
          <h2 className="text-2xl font-semibold">Hardware for your business</h2>
          <div className="mt-6 grid gap-4 md:grid-cols-2">
            {segments.map((segment) => (
              <div key={segment.title} className="rounded-3xl border border-line p-5">
                <h3 className="font-semibold">{segment.title}</h3>
                <ul className="mt-3 space-y-2 text-sm">
                  {segment.products.map((product) => (
                    <li key={product.slug}><a className="text-primary" href={`/hardware/products/${product.slug}`}>{product.name}</a></li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </section>
      ) : null}
      <section className="mx-auto max-w-page px-4 py-12 sm:px-6 lg:px-8">
        <h2 className="text-2xl font-semibold">Why AxizPOS</h2>
        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          {WHY.map(([title, body]) => (
            <div key={title} className="rounded-3xl border border-line bg-card p-5">
              <h3 className="font-semibold">{title}</h3>
              <p className="mt-2 text-sm leading-6 text-charcoal/70">{body}</p>
            </div>
          ))}
        </div>
      </section>
      <section id="enquire" className="mx-auto max-w-xl px-4 py-8 sm:px-6">
        <EnquiryForm contact={contact} products={products} packages={packages} />
      </section>
    </div>
  );
}

function DetailShell({ children }: { children: ReactNode }) {
  return <div className="mx-auto max-w-page px-4 py-12 sm:px-6 lg:px-8">{children}</div>;
}
