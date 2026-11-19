import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const dir = join(process.env.TEMP, "axiz-31");
const groups = new Map();
for (const file of readdirSync(dir)) {
  if (!file.endsWith(".json")) continue;
  const report = JSON.parse(readFileSync(join(dir, file), "utf8"));
  const metrics = report.audits.metrics.details.items[0];
  const key = file.replace(/-\d+\.json$/, "");
  const row = {
    score: Math.round(report.categories.performance.score * 100),
    lcp: Math.round(metrics.largestContentfulPaint),
    observed: Math.round(metrics.observedLargestContentfulPaint),
    fcp: Math.round(metrics.firstContentfulPaint),
    si: Math.round(metrics.speedIndex),
    tbt: Math.round(report.audits["total-blocking-time"].numericValue),
    cls: Number(report.audits["cumulative-layout-shift"].numericValue.toFixed(3)),
    weight: Math.round(report.audits["total-byte-weight"].numericValue / 1024),
  };
  groups.set(key, [...(groups.get(key) ?? []), row]);
}
const median = (values) => {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.floor(sorted.length / 2)];
};
for (const [key, rows] of groups) {
  const summary = {
    runs: rows.length,
    score: median(rows.map((row) => row.score)),
    lcp: median(rows.map((row) => row.lcp)),
    observed: median(rows.map((row) => row.observed)),
    fcp: median(rows.map((row) => row.fcp)),
    si: median(rows.map((row) => row.si)),
    tbt: median(rows.map((row) => row.tbt)),
    cls: median(rows.map((row) => row.cls)),
    weight: median(rows.map((row) => row.weight)),
    lcpRuns: rows.map((row) => row.lcp).join(","),
  };
  console.log(key, JSON.stringify(summary));
}
