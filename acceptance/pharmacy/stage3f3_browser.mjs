import { chromium } from "playwright";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(fileURLToPath(import.meta.url));
const evidence = path.join(root, "evidence", "stage-3f.3");
const web = process.env.ACCEPTANCE_WEB_URL;
const adminPassword = process.env.ACCEPTANCE_ADMIN_PASSWORD;
const results = [];

function record(name, passed, detail) {
  results.push({ name, status: passed ? "passed" : "failed", detail });
  console.log(`${passed ? "PASS" : "FAIL"} ${name}: ${detail}`);
}

async function login(page, tenant) {
  await page.goto(`${web}/login`, { waitUntil: "domcontentloaded" });
  await page.evaluate((code) => localStorage.setItem("ai-pos.store-code", code), tenant);
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.locator("#identity").waitFor();
  await page.locator("#identity").fill("admin");
  await page.locator("#password").fill(adminPassword);
  await page.getByRole("button", { name: "Sign In" }).click();
  await page.waitForURL((url) => !url.pathname.includes("login"), { timeout: 20000 });
  const later = page.getByRole("button", { name: "Decide later" });
  try {
    await later.waitFor({ timeout: 2000 });
    await later.click();
  } catch {
    // Onboarding is already complete.
  }
}

async function openReceipt(page, invoice) {
  await page.goto(`${web}/sales-insights`, { waitUntil: "domcontentloaded" });
  const blocked = page.getByText("Plan access could not be confirmed");
  if (await blocked.count()) {
    throw new Error("Sales insights is hidden because plan access could not be confirmed.");
  }
  await page.getByLabel("Period").selectOption("Last 7 days");
  await page.getByRole("button", { name: "Refresh" }).click();
  await page.getByRole("tab", { name: "Transactions" }).click();
  await page.getByPlaceholder("Receipt number").fill(invoice);
  const rowButton = page.getByRole("button", { name: "Return" }).first();
  await rowButton.waitFor({ timeout: 20000 });
  await rowButton.click();
  await page.getByRole("dialog").waitFor();
}

async function submitReturn(page, invoice, shotName) {
  await openReceipt(page, invoice);
  const response = page.waitForResponse(
    (item) => item.url().includes("/api/v1/returns") && item.request().method() === "POST",
    { timeout: 20000 },
  );
  await page.getByRole("button", { name: /^Refund / }).click();
  const posted = await response;
  await page.getByText("Return recorded").waitFor({ timeout: 20000 });
  await page.screenshot({ path: path.join(evidence, `${shotName}.png`), fullPage: true });
  record(shotName, posted.status() === 201 || posted.status() === 200, `POST /api/v1/returns ${posted.status()} invoice ${invoice}`);
  await page.getByRole("button", { name: "Done" }).click();
}

async function showClamp(page, invoice) {
  await openReceipt(page, invoice);
  const input = page.getByRole("dialog").locator("input[type='number']");
  await input.waitFor();
  const max = await input.getAttribute("max");
  await input.fill("9");
  const value = await input.inputValue();
  await page.screenshot({ path: path.join(evidence, "excess-clamp.png"), fullPage: true });
  record("excess-quantity-clamped", max === "1" && value === "1", `max=${max} value=${value}`);
  await page.getByRole("button", { name: "Cancel" }).click();
}

const invoices = JSON.parse(await readFile(path.join(evidence, "invoices.json"), "utf8"));
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
let failed = false;
try {
  await login(page, "pharmacy-accept");
  await submitReturn(page, invoices.pharmacy.valid.invoice, "pharmacy-return-valid");
  await submitReturn(page, invoices.pharmacy.recalled.invoice, "pharmacy-return-recalled");
  await submitReturn(page, invoices.pharmacy.supplier.invoice, "pharmacy-return-supplier");
  await showClamp(page, invoices.pharmacy.excess.invoice);
  await page.getByRole("button", { name: /Account menu/ }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await page.waitForURL((url) => url.pathname.includes("login"), { timeout: 15000 });
  await login(page, "accept-grocery");
  await submitReturn(page, invoices.grocery.invoice, "grocery-return");
} catch (error) {
  failed = true;
  record("portal-browser", false, error instanceof Error ? error.message : "browser failed");
  await page.screenshot({ path: path.join(evidence, "portal-browser-error.png"), fullPage: true }).catch(() => {});
} finally {
  await browser.close();
  await writeFile(path.join(evidence, "browser.json"), JSON.stringify(results, null, 2));
}
if (failed || results.some((item) => item.status !== "passed")) {
  process.exit(1);
}
