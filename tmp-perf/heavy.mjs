import { readFileSync } from "node:fs";

const report = JSON.parse(readFileSync(process.env.TEMP + "/axiz-lh/cafe-mobile-2.json", "utf8"));
const items = report.audits["network-requests"].details.items
  .map((item) => ({ url: item.url.replace("http://localhost:4175", ""), kb: Math.round(item.transferSize / 1024) }))
  .sort((a, b) => b.kb - a.kb)
  .slice(0, 20);
for (const item of items) console.log(String(item.kb).padStart(6), item.url);
const node = report.audits["lcp-discovery-insight"]?.details.items.find((item) => item.type === "node");
console.log("lcp", node?.snippet?.slice(0, 240) || "no node");
