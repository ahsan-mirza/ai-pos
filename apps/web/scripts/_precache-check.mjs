import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../dist/sw.js", import.meta.url), "utf8");
const urls = [...source.matchAll(/"url":"([^"]+)"/g)].map((match) => match[1]);
console.log(urls.length);
console.log(urls.join("\n"));
