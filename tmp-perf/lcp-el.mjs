import { readFileSync } from "node:fs";

const report = JSON.parse(readFileSync(process.env.TEMP + "/axiz-final/retail-1.json", "utf8"));
for (const [id, audit] of Object.entries(report.audits)) {
  const text = JSON.stringify(audit.details ?? "");
  if (!/IMG|snippet|LCP/.test(text) || text.length < 20) continue;
  if (!/lcp|contentful|element/.test(id)) continue;
  console.log(id, text.slice(0, 500));
  console.log("---");
}
