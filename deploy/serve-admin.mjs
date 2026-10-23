/** Serves the built admin portal and falls back to index.html so client routes keep working. */
import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize, sep } from "node:path";

const root = process.env.ADMIN_ROOT || "/var/www/ai-pos-admin";
const host = process.env.HOST || "127.0.0.1";
const port = Number(process.env.PORT || 4173);

const types = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".ico": "image/x-icon",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".webp": "image/webp",
  ".woff2": "font/woff2",
};

function safeFile(pathname) {
  const decoded = decodeURIComponent(pathname.split("?")[0]);
  const relative = normalize(decoded).replace(/^(\.\.(\/|\\|$))+/, "");
  const file = join(root, relative);
  if (file !== root && !file.startsWith(root + sep)) return null;
  return file;
}

createServer((request, response) => {
  const path = request.url || "/";
  let file = safeFile(path);
  if (file === null) {
    response.writeHead(403);
    response.end();
    console.log(`${request.method} ${path} 403`);
    return;
  }
  if (!existsSync(file) || statSync(file).isDirectory()) file = join(root, "index.html");
  if (!existsSync(file)) {
    response.writeHead(404);
    response.end("not found");
    console.log(`${request.method} ${path} 404`);
    return;
  }
  response.writeHead(200, { "Content-Type": types[extname(file)] || "application/octet-stream" });
  createReadStream(file).pipe(response);
  console.log(`${request.method} ${path} 200`);
}).listen(port, host, () => {
  console.log(`admin portal listening on http://${host}:${port}`);
});
