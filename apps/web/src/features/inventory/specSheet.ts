import { formatMoney, type BranchStock, type Product } from "@ai-pos/shared-types";
import { DEFAULT_PRIMARY, normalizeHex } from "../../lib/theme";

export interface SpecRow {
  label: string;
  value: string;
}

const escape = (value: string) =>
  value.replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]!);

/** Prints a one-page spec sheet; the browser's print dialog offers "Save as PDF". */
export function printSpecSheet(product: Product, specs: SpecRow[], branches: BranchStock[]) {
  const rows = specs.map((row) => `<tr><th>${escape(row.label)}</th><td>${escape(row.value)}</td></tr>`).join("");
  const stock = branches
    .map(
      (branch) =>
        `<tr><td>${escape(branch.store_code)} · ${escape(branch.store_name)}</td>` +
        `<td class="num">${branch.quantity_on_hand}</td><td class="num">${branch.quantity_reserved}</td>` +
        `<td>${escape(branch.aisle_shelf_location ?? "—")}</td></tr>`,
    )
    .join("");
  const subtitle = [product.brand, product.model_number].filter(Boolean).join(" · ");
  const primary = normalizeHex(getComputedStyle(document.documentElement).getPropertyValue("--primary")) ?? DEFAULT_PRIMARY;
  const html = `<!doctype html><html><head><meta charset="utf-8"><title>${escape(product.sku)} spec sheet</title>
<style>
  @page { margin: 18mm; }
  body { font-family: Archivo, Arial, sans-serif; color: #222026; }
  .tag { display: inline-block; border-radius: 999px; padding: 3px 10px; font-size: 11px; font-weight: 600;
    background: #F3F4F6; margin-right: 6px; }
  .tag.accent { background: ${primary}; color: #fff; }
  h1 { font-size: 26px; margin: 14px 0 4px; }
  .muted { color: #6b6a6e; font-size: 13px; }
  .price { font-size: 30px; font-weight: 700; margin: 18px 0; }
  h2 { font-size: 13px; text-transform: uppercase; letter-spacing: .08em; color: #6b6a6e; margin: 26px 0 8px; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { text-align: left; padding: 8px 0; border-bottom: 1px solid #DBDBDB; }
  th { width: 40%; font-weight: 500; color: #6b6a6e; }
  .num { text-align: right; font-variant-numeric: tabular-nums; }
  .bar { height: 4px; background: ${primary}; border-radius: 4px; margin-bottom: 18px; width: 64px; }
</style></head><body>
<div class="bar"></div>
<span class="tag">${escape(product.sku)}</span><span class="tag">${escape(product.category)}</span>
${product.sub_category ? `<span class="tag">${escape(product.sub_category)}</span>` : ""}
${product.is_serialized ? `<span class="tag accent">IMEI Tracked</span>` : ""}
<h1>${escape(product.name)}</h1>
<div class="muted">${escape(subtitle || "—")}</div>
<div class="price">${escape(formatMoney(product.price_cents, product.currency))}</div>
<h2>Specifications</h2><table>${rows}</table>
${branches.length ? `<h2>Branch stock</h2><table><tr><th>Branch</th><th class="num">On hand</th><th class="num">Reserved</th><th>Aisle / bin</th></tr>${stock}</table>` : ""}
<p class="muted" style="margin-top:28px">Generated ${escape(new Date().toLocaleString())}</p>
</body></html>`;

  const frame = document.createElement("iframe");
  frame.setAttribute("aria-hidden", "true");
  frame.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0;";
  document.body.appendChild(frame);
  const target = frame.contentWindow;
  if (!target) {
    frame.remove();
    return;
  }
  target.document.open();
  target.document.write(html);
  target.document.close();
  target.addEventListener("afterprint", () => frame.remove());
  setTimeout(() => frame.remove(), 120_000);
  setTimeout(() => {
    target.focus();
    target.print();
  }, 50);
}
