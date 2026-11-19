import { readFileSync } from "node:fs";

const report = JSON.parse(readFileSync(process.env.TEMP + "/axiz-lh/cafe-mobile-2.json", "utf8"));
const items = report.audits["network-requests"].details.items.filter((item) => item.transferSize > 20000 || item.url.includes("axizpos"));
for (const item of items) {
  console.log(JSON.stringify({
    url: item.url,
    type: item.resourceType,
    kb: Math.round(item.transferSize / 1024),
    status: item.statusCode,
    mime: item.mimeType,
  }));
}
