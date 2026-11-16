// Rewrites the thin HTML entries from the SEO page list. Head tags are injected at build time.
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { SEO_PAGES } from "../apps/site/src/seo.ts";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "apps", "site");

for (const page of SEO_PAGES) {
  const relative = page.path === "/" ? "index.html" : `${page.path.slice(1)}/index.html`;
  const file = join(root, relative);
  mkdirSync(dirname(file), { recursive: true });
  const locale = page.locale ?? "en";
  const dir = locale === "ar" ? "rtl" : "ltr";
  writeFileSync(
    file,
    `<!doctype html>
<html lang="${locale}" dir="${dir}" data-page="${page.id}" data-lang="${locale}">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <!-- site-seo -->
    <link rel="icon" type="image/svg+xml" href="/brand/fav-icon.svg" media="(prefers-color-scheme: light)" />
    <link rel="icon" type="image/svg+xml" href="/brand/fav-icon-white.svg" media="(prefers-color-scheme: dark)" />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
`,
  );
}

console.log(`Wrote ${SEO_PAGES.length} marketing HTML entries.`);
