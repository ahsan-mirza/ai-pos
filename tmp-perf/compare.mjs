import { readFileSync } from "node:fs";

for (const name of ["axiz-home-fix.json", "axiz-cafe-fix.json"]) {
  const report = JSON.parse(readFileSync(process.env.TEMP + "/" + name, "utf8"));
  const metrics = report.audits.metrics.details.items[0];
  console.log(name, JSON.stringify({
    score: Math.round(report.categories.performance.score * 100),
    lcp: Math.round(metrics.largestContentfulPaint),
    observed: Math.round(metrics.observedLargestContentfulPaint),
    fcp: Math.round(metrics.firstContentfulPaint),
    tbt: Math.round(report.audits["total-blocking-time"].numericValue),
    cls: Number(report.audits["cumulative-layout-shift"].numericValue.toFixed(3)),
    weight: Math.round(report.audits["total-byte-weight"].numericValue / 1024),
  }));
  const heavy = report.audits["network-requests"].details.items
    .filter((item) => item.transferSize > 15000)
    .map((item) => `${Math.round(item.transferSize / 1024)} ${item.url.replace("http://localhost:4175", "").replace("https://axizpos.com", "LIVE")}`)
    .slice(0, 12);
  console.log(heavy.join("\n"));
  console.log("---");
}
