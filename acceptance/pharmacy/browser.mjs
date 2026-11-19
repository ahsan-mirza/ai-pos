import { chromium } from "playwright";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = path.dirname(fileURLToPath(import.meta.url));
const evidence = path.join(root, "evidence");
const web = process.env.ACCEPTANCE_WEB_URL;
const phase = process.env.BROWSER_PHASE || "main";
const staff = process.env.ACCEPTANCE_STAFF_PASSWORD;
const adminPassword = process.env.ACCEPTANCE_ADMIN_PASSWORD;
const results = [];

function record(name, passed, detail) {
  results.push({ name, status: passed ? "passed" : "failed", detail });
  console.log(`${passed ? "PASS" : "FAIL"} ${name}: ${detail}`);
}

async function shot(page, name) {
  await page.screenshot({ path: path.join(evidence, `${name}.png`), fullPage: true });
}

async function login(page, username, password) {
  await page.goto(`${web}/login`, { waitUntil: "domcontentloaded" });
  await page.locator("#identity").waitFor();
  await page.locator("#identity").fill(username);
  await page.locator("#password").fill(password);
  await page.getByRole("button", { name: "Sign In" }).click();
  await page.waitForURL((url) => !url.pathname.includes("login"), { timeout: 20000 });
  const later = page.getByRole("button", { name: "Decide later" });
  try {
    await later.waitFor({ timeout: 2000 });
    await later.click();
  } catch {
    // Onboarding is already complete for this acceptance tenant.
  }
}

async function logout(page) {
  const dialog = page.getByRole("dialog");
  if (await dialog.count()) {
    await dialog.getByRole("button", { name: "Close" }).click();
    await dialog.first().waitFor({ state: "hidden", timeout: 10000 });
  }
  await page.getByRole("button", { name: /Account menu/ }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await page.waitForURL((url) => url.pathname.includes("login"), { timeout: 15000 });
}

async function openUsers(page) {
  await page.goto(`${web}/users`, { waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: "Pharmacy appointment" }).waitFor({ timeout: 20000 });
}

async function openLot(page, lot) {
  await page.goto(`${web}/inventory/batches`, { waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: "Purchase batches" }).waitFor({ timeout: 20000 });
  const rows = page.locator("section[aria-label='Purchase batches'] tbody tr[data-row-id]");
  await rows.first().waitFor({ timeout: 20000 });
  const count = await rows.count();
  for (let index = 0; index < count; index += 1) {
    await rows.nth(index).click();
    const marker = page.getByText(`Manufacturer lot ${lot}`);
    try {
      await marker.first().waitFor({ timeout: 2500 });
      return true;
    } catch {
      // This receipt is a different manufacturer lot.
    }
  }
  return false;
}

async function nominate(page, name, reason) {
  await page.getByLabel("Staff member").selectOption({ label: name });
  await page.getByLabel("Reason").fill(reason);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Nominate officer" }).click();
  await page.locator("li").filter({ hasText: name }).waitFor({ timeout: 15000 });
}

async function mainFlow(page) {
  await login(page, "clerk.a", staff);
  await openUsers(page);
  await shot(page, "01-pharmacy-tenant-users");
  await nominate(page, "Governance Officer 1", "Nominate the first governance officer");
  await shot(page, "02-officer-nominated");
  const confirmForNominator = page.getByRole("button", { name: "Confirm" });
  record("nominator-cannot-confirm-in-ui", (await confirmForNominator.count()) === 0, "Confirm is hidden for the nominator");
  await logout(page);

  await login(page, "clerk.b", staff);
  await openUsers(page);
  await page.getByLabel("Reason").fill("Confirm the first governance officer");
  await page.getByRole("button", { name: "Confirm" }).click();
  await page.locator("li").filter({ hasText: "Governance Officer 1" }).filter({ hasText: "active" }).waitFor({ timeout: 15000 });
  await shot(page, "03-officer-one-confirmed");
  record("officer-one-confirmed", true, "Clerk B confirmed Officer 1");
  await nominate(page, "Governance Officer 2", "Nominate the second governance officer");
  await logout(page);

  await login(page, "clerk.a", staff);
  await openUsers(page);
  await page.getByLabel("Reason").fill("Confirm the second governance officer");
  await page.getByRole("button", { name: "Confirm" }).click();
  await page.locator("li").filter({ hasText: "Governance Officer 2" }).filter({ hasText: "active" }).waitFor({ timeout: 15000 });
  await shot(page, "04-two-officers");
  record("two-officers", true, "Two active officers");
  const revoke = page.getByRole("button", { name: "Revoke" });
  record("revoke-hidden-while-two-officers", (await revoke.count()) === 0, "Revoke is hidden so the count cannot fall below two");
  await logout(page);

  await login(page, "admin", adminPassword);
  await page.goto(`${web}/users`, { waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: "Pharmacy appointment" }).waitFor({ timeout: 20000 });
  await shot(page, "05-super-admin-users");
  const nominateVisible = await page.getByRole("button", { name: "Nominate officer" }).count();
  record("super-admin-cannot-nominate-after-bootstrap", nominateVisible === 0, "Nomination form is closed");
  await page.goto(`${web}/roles`, { waitUntil: "domcontentloaded" });
  const superAdmin = page.getByRole("button", { name: /^Super Admin/ });
  const explanation = page.getByText("Pharmacist appointment is governed separately and is not one of them.");
  await superAdmin.waitFor({ timeout: 20000 });
  for (let attempt = 0; attempt < 3; attempt += 1) {
    await superAdmin.click();
    try {
      await explanation.waitFor({ timeout: 5000 });
      break;
    } catch (error) {
      if (attempt === 2) throw error;
    }
  }
  const permission = page.getByText("pharmacy:authorize_pharmacist");
  const permissionCount = await permission.count();
  let locked = permissionCount === 0;
  if (permissionCount > 0) {
    locked = await permission.locator("xpath=ancestor::label").locator("input[type=checkbox]").first().isDisabled();
  }
  await shot(page, "06-super-admin-role");
  record(
    "super-admin-cannot-edit-appointment-permission",
    locked,
    permissionCount === 0 ? "The permission is not on the role editor" : "The permission checkbox is disabled",
  );
  await logout(page);

  await login(page, "officer.one", staff);
  await openUsers(page);
  await page.getByLabel("Staff member").selectOption({ label: "Pharmacist Candidate 1" });
  await page.getByLabel("Reason").fill("Request pharmacist appointment");
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Request appointment" }).click();
  await page.locator("li").filter({ hasText: "Pharmacist Candidate 1" }).filter({ hasText: "pending" }).waitFor({ timeout: 15000 });
  await shot(page, "07-appointment-pending");
  record("requester-cannot-approve", (await page.getByRole("button", { name: "Approve" }).count()) === 0, "Approve is hidden for the requester");
  await logout(page);

  await login(page, "officer.two", staff);
  await openUsers(page);
  await page.getByLabel("Reason").fill("Approve pharmacist appointment");
  await page.getByRole("button", { name: "Approve" }).click();
  await page.locator("li").filter({ hasText: "Pharmacist Candidate 1" }).filter({ hasText: "active" }).waitFor({ timeout: 15000 });
  await shot(page, "08-pharmacist-approved");
  record("pharmacist-approved", true, "Officer 2 approved Candidate 1");
  await logout(page);

  await login(page, "admin", adminPassword);
  await page.goto(`${web}/inventory/purchase-orders`, { waitUntil: "domcontentloaded" });
  const pending = page.locator("tr[data-row-id]").filter({ hasText: "0 / 10" });
  await pending.first().waitFor({ timeout: 20000 });
  await pending.first().click();
  await page.getByRole("button", { name: "Receive goods (GRN)" }).click();
  await page.getByLabel("Manufacturer lot").fill("ACCEPT-LOT-A");
  const expiry = page.getByLabel("Expiry date for Acceptance Medicine A");
  await expiry.click();
  await expiry.fill("2027-06-01");
  await page.getByLabel("Receipt note").fill("ACCEPT-GRN-001");
  await shot(page, "09-receive-medicine-a");
  await page.getByRole("button", { name: "Post goods receipt" }).click();
  await page.getByText("Manufacturer lot ACCEPT-LOT-A").waitFor({ timeout: 20000 });
  await page.getByText(/unreleased/i).first().waitFor({ timeout: 15000 });
  await shot(page, "10-medicine-a-received");
  record("medicine-a-received-in-ui", true, "Goods receipt posted. Receipt number and manufacturer lot are separate.");
  await logout(page);

  await login(page, "pharmacist.one", staff);
  const opened = await openLot(page, "ACCEPT-LOT-A");
  record("unreleased-lot-visible", opened, opened ? "Batch drawer shows ACCEPT-LOT-A" : "Lot A was not found");
  if (opened) {
    await page.getByText(/unreleased/i).first().waitFor();
    await shot(page, "11-unreleased-lot");
    await page.getByRole("button", { name: "Release lot" }).click();
    const confirm = page.getByRole("button", { name: "Confirm" });
    record("release-blocked-without-reason", await confirm.isDisabled(), "Confirm stays disabled before a reason and confirmation");
    await page.getByLabel("Reason").fill("Pharmacist release of lot A");
    await page.getByRole("checkbox", { name: /confirm this release/i }).check();
    await shot(page, "12-release-confirmation");
    await confirm.click();
    await page.getByText("Manufacturer lot ACCEPT-LOT-A · released").waitFor({ timeout: 15000 });
    await shot(page, "13-released-lot");
    record("lot-a-released-in-ui", true, "Release confirmed in the batch drawer");
  }
  const quarantine = await openLot(page, "ACCEPT-LOT-B");
  if (quarantine) {
    await page.getByText(/quarantined/i).first().waitFor();
    await shot(page, "14-quarantine");
    record("quarantine-visible", true, "Lot B is quarantined in the batch drawer");
  } else {
    record("quarantine-visible", false, "Lot B was not found");
  }
  const recalled = await openLot(page, "ACCEPT-LOT-C");
  if (recalled) {
    await shot(page, "15-recalled-lot");
    record(
      "recalled-lot-has-no-release",
      (await page.getByRole("button", { name: "Release lot" }).count()) === 0,
      "Release is not offered for the recalled lot",
    );
  } else {
    record("recalled-lot-has-no-release", false, "Lot C was not found");
  }
}

async function afterFlow(page) {
  await login(page, "pharmacist.one", staff);
  const quarantine = await openLot(page, "ACCEPT-LOT-B");
  if (quarantine) {
    const clear = page.getByRole("button", { name: "Clear quarantine" });
    try {
      await clear.waitFor({ timeout: 10000 });
    } catch {
      // The button is absent, or the pharmacist authorization request did not finish.
    }
    if (await clear.count()) {
      await clear.click();
      await page.getByLabel("Reason").fill("Clear acceptance quarantine");
      await page.getByRole("checkbox", { name: /confirm this clearance/i }).check();
      await page.getByRole("button", { name: "Confirm" }).click();
      await page.getByText("Manufacturer lot ACCEPT-LOT-B · released").waitFor({ timeout: 15000 });
      await shot(page, "15b-quarantine-cleared");
      record("quarantine-cleared-in-ui", true, "Lot B cleared by the authorized pharmacist");
    } else {
      record("quarantine-cleared-in-ui", false, "Clear quarantine was not offered");
    }
  } else {
    record("quarantine-cleared-in-ui", false, "Lot B was not found");
  }
  const found = await openLot(page, "ACCEPT-FEFO-OLD");
  await shot(page, "16-fefo-lot");
  record("fefo-lot-visible", found, found ? "Sooner FEFO lot is in the drawer" : "FEFO lot was not opened");
  if (found) {
    const later = await openLot(page, "ACCEPT-FEFO-NEW");
    if (later) await shot(page, "16b-fefo-later-lot");
    record("fefo-later-lot-visible", later, later ? "Later FEFO lot is in the drawer" : "Later FEFO lot was not opened");
  }
  await logout(page);
  await login(page, "officer.one", staff);
  await openUsers(page);
  await page.getByLabel("Reason").fill("Revoke pharmacist appointment");
  const activePharmacist = page.locator("li").filter({ hasText: "Pharmacist Candidate 1" }).filter({ hasText: "active" });
  await page.getByRole("button", { name: "Revoke" }).click();
  await activePharmacist.waitFor({ state: "hidden", timeout: 15000 });
  const history = page.getByRole("heading", { name: "Authorization history" });
  await history.waitFor({ timeout: 15000 });
  const closed = page.locator("li").filter({ hasText: "Pharmacist Candidate 1" }).filter({ hasText: "revoked" });
  await closed.waitFor({ timeout: 15000 });
  const reason = await closed.innerText();
  await shot(page, "17-pharmacist-revoked");
  record("pharmacist-revoked-in-ui", true, "The active appointment left the list");
  record(
    "revoked-history-visible-in-ui",
    reason.includes("Revoke pharmacist appointment") && reason.includes("approved"),
    reason,
  );
  await logout(page);
  await page.evaluate(() => localStorage.setItem("ai-pos.store-code", "accept-grocery"));
  await login(page, "admin", adminPassword);
  await page.goto(`${web}/users`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1500);
  const pharmacy = await page.getByRole("heading", { name: "Pharmacy appointment" }).count();
  await shot(page, "18-grocery-users");
  record("grocery-has-no-pharmacy-governance", pharmacy === 0, "Pharmacy appointment heading is absent");
  await page.goto(pathToFileURL(path.join(evidence, "grocery-allocations.html")).href, { waitUntil: "domcontentloaded" });
  await shot(page, "19-grocery-allocations");
  record("grocery-allocation-report-visible", (await page.getByRole("heading", { name: "Grocery allocation report" }).count()) === 1, "Allocation report opened");
}

async function choose(page, label, option) {
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: label }).click();
  await page.getByRole("option", { name: option }).click();
}

async function portalFlow(page) {
  await login(page, "admin", adminPassword);
  await page.goto(`${web}/inventory/transfers`, { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "New transfer" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.waitFor();
  await choose(page, /From \(source\)/, /Acceptance Pharmacy/);
  await choose(page, /To \(destination\)/, /Acceptance Second Store/);
  await choose(page, "Product", /Acceptance Portal Transfer/);
  await dialog.getByLabel(/Qty/).fill("2");
  await dialog.getByRole("button", { name: "Request transfer" }).click();
  await page.getByRole("button", { name: "Ship from source" }).click();
  await page.getByRole("button", { name: "Receive at destination" }).click();
  await page.getByText("Received", { exact: true }).waitFor({ timeout: 20000 });
  await shot(page, "20-portal-transfer");
  await page.getByRole("button", { name: "Close" }).click();
  await page.goto(`${web}/inventory/batches`, { waitUntil: "domcontentloaded" });
  const batchRows = page.locator("section[aria-label='Purchase batches'] tbody tr[data-row-id]");
  await batchRows.first().waitFor({ timeout: 20000 });
  let unreleased = false;
  const rowCount = await batchRows.count();
  for (let index = 0; index < rowCount; index += 1) {
    await batchRows.nth(index).click();
    const marker = page.getByText("Manufacturer lot ACCEPT-UI-XFER · unreleased");
    try {
      await marker.waitFor({ timeout: 4000 });
      unreleased = true;
      break;
    } catch {
      // This receipt is a different lot. The drawer replaces its contents on the next row.
    }
  }
  await shot(page, "21-destination-unreleased");
  record("portal-destination-unreleased", unreleased, unreleased ? "Destination layer is unreleased" : "Unreleased destination layer was not opened");

  await page.goto(`${web}/inventory/transfers`, { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "New transfer" }).click();
  await choose(page, /From \(source\)/, /Acceptance Pharmacy/);
  await choose(page, /To \(destination\)/, /Acceptance Second Store/);
  await choose(page, "Product", /Acceptance Portal Transfer/);
  await page.getByRole("dialog").getByLabel(/Qty/).fill("99");
  await page.getByRole("button", { name: "Request transfer" }).click();
  const invalid = page.getByText(/available|could not|enough|insufficient/i);
  await invalid.first().waitFor({ timeout: 10000 });
  await shot(page, "22-invalid-transfer");
  record("portal-invalid-transfer-rejected", true, "An oversized transfer was rejected");
  await page.getByRole("button", { name: "Close" }).click();

  await page.getByRole("button", { name: "New transfer" }).click();
  await choose(page, /From \(source\)/, /Acceptance Pharmacy/);
  await choose(page, /To \(destination\)/, /Acceptance Second Store/);
  await choose(page, "Product", /Acceptance Portal Transfer/);
  await page.getByRole("dialog").getByLabel(/Qty/).fill("1");
  await page.getByRole("button", { name: "Request transfer" }).click();
  await page.getByRole("button", { name: "Cancel transfer" }).click();
  await shot(page, "23-transfer-cancelled");
  record("portal-transfer-cancelled", true, "The requested transfer was cancelled");
  await page.getByRole("button", { name: "Close" }).click();

  const returning = await openLot(page, "ACCEPT-UI-RET");
  if (!returning) {
    record("portal-supplier-return", false, "The return lot was not opened");
    return;
  }
  await page.getByRole("button", { name: "Return to supplier" }).click();
  await page.getByLabel("Reference").fill("PORTAL-RET-1");
  await page.getByLabel("Quantity to return").fill("1");
  await page.getByLabel("Reason").fill("Portal partial return");
  await page.getByRole("button", { name: "Confirm" }).click();
  await page.getByText("3 / 4").waitFor({ timeout: 15000 });
  await shot(page, "24-partial-supplier-return");
  await page.getByRole("button", { name: "Return to supplier" }).click();
  await page.getByLabel("Reference").fill("PORTAL-RET-2");
  await page.getByLabel("Quantity to return").fill("3");
  await page.getByLabel("Reason").fill("Portal full return");
  await page.getByRole("button", { name: "Confirm" }).click();
  await page.getByText("Returned to the supplier").waitFor({ timeout: 15000 });
  await shot(page, "25-full-supplier-return");
  record("portal-supplier-return", true, "Partial then full return left the history visible");
}

async function profilesFlow(page) {
  const tenants = [
    ["accept-electronics-wholesale", "electronics"],
    ["accept-wholesale-retail", "wholesale"],
    ["accept-retail-fashion", "fashion"],
    ["accept-grocery", "grocery"],
    ["accept-restaurant", "restaurant"],
    ["accept-cafe", "cafe"],
    ["accept-quick-service", "quick-service"],
  ];
  for (const [code, name] of tenants) {
    await page.goto(`${web}/login`, { waitUntil: "domcontentloaded" });
    await page.evaluate((value) => localStorage.setItem("ai-pos.store-code", value), code);
    await login(page, "admin", adminPassword);
    await page.goto(`${web}/users`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(1000);
    const pharmacy = await page.getByRole("heading", { name: "Pharmacy appointment" }).count();
    await page.goto(`${web}/inventory/batches`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(1000);
    const release = await page.getByRole("button", { name: "Release lot" }).count();
    await shot(page, `26-${name}-portal`);
    record(`${name}-portal-has-no-pharmacy-controls`, pharmacy === 0 && release === 0, `pharmacy heading ${pharmacy}, release buttons ${release}`);
    await logout(page);
  }
}

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.setDefaultTimeout(15000);
await mkdir(evidence, { recursive: true });
try {
  if (phase === "main") await mainFlow(page);
  else if (phase === "after") await afterFlow(page);
  else if (phase === "portal") await portalFlow(page);
  else if (phase === "profiles") await profilesFlow(page);
  else throw new Error(`Unknown phase ${phase}`);
} catch (error) {
  record(`${phase}-flow`, false, error instanceof Error ? error.message : String(error));
  await shot(page, `failure-${phase}`).catch(() => undefined);
} finally {
  await browser.close();
  const file = path.join(evidence, `browser-${phase}.json`);
  await writeFile(file, JSON.stringify(results, null, 2));
  if (results.some((item) => item.status === "failed")) process.exitCode = 1;
}
