/**
 * The updater, and the line it must not cross.
 *
 * The owner's rule for this app is that nothing acts without a person: no
 * auto-approve, no approve-all, anywhere. An update replaces the executable,
 * which is the largest single change anything here can make to the machine, so
 * that rule applies to it more than to anything else — and the failure mode is
 * silent, because an updater that installed on its own would simply appear to
 * work.
 *
 * So the load-bearing test in this file is `a check never installs`. The rest
 * is whether the window tells the truth about what it found.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");

const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const VIEW = { width: 760, height: 1000 };
const open = (data = {}) => K.open(browser, base, "settings.html", data, VIEW);
const calls = (page) => page.evaluate(() => window.__calls.map((c) => c[0]));

const FOUND = { available: "0.2.0", notes: "Fixed the thing.", date: "2026-09-20" };

/* ── The rule ────────────────────────────────────────────────────────────── */

await check("a check never installs", async () => {
  const page = await open({ found: FOUND });
  await page.locator("#update-check").click();
  await page.waitForTimeout(300);
  const seen = await calls(page);
  await page.close();
  assert.ok(seen.includes("__checked"), "the check did not run");
  assert.ok(!seen.includes("__installed"),
    "checking installed something — this is the one thing that must never happen");
});

await check("nothing installs without a press, even with one available", async () => {
  // Open the window with an update already known, wait well past anything that
  // could be a debounce, and confirm the app just sits there.
  const page = await open({ update: { ...K.UPDATE_NONE, ...FOUND } });
  await page.waitForTimeout(1200);
  const seen = await calls(page);
  await page.close();
  assert.ok(!seen.includes("__installed"), "an update installed itself");
});

await check("CONTROL: the button does install, so the negatives mean something", async () => {
  const page = await open({ update: { ...K.UPDATE_NONE, ...FOUND } });
  await page.locator("#update-install").click();
  await page.waitForTimeout(300);
  const seen = await calls(page);
  await page.close();
  assert.ok(seen.includes("__installed"), "the Install button does not install");
});

await check("CONTROL: Rust keeps checking and installing as separate commands", async () => {
  // A flag on one command is how this rule gets lost in a later edit.
  const rust = read("src-tauri/src/update.rs");
  assert.match(rust, /pub async fn check_for_update/);
  assert.match(rust, /pub async fn install_update/);
  const checkFn = rust.slice(rust.indexOf("pub async fn check_for_update"),
                             rust.indexOf("pub fn set_update_check_on_start"));
  assert.ok(!/download_and_install/.test(checkFn),
    "the check path can install");
  const startup = rust.slice(rust.indexOf("pub fn spawn_startup_check"));
  assert.ok(!/download_and_install/.test(startup),
    "the startup check can install");
});

/* ── It tells the truth about what it found ──────────────────────────────── */

await check("no update says so, with the version", async () => {
  const page = await open();
  await page.waitForTimeout(300);
  const state = await page.locator("#update-state").innerText();
  const installVisible = await page.locator("#update-install").isVisible();
  await page.close();
  assert.match(state, /0\.1\.0/, `said "${state}"`);
  assert.equal(installVisible, false, "an Install button is offered with nothing to install");
});

await check("an available update names both versions", async () => {
  const page = await open({ update: { ...K.UPDATE_NONE, ...FOUND } });
  await page.waitForTimeout(300);
  const state = await page.locator("#update-state").innerText();
  const label = await page.locator("#update-install").innerText();
  await page.close();
  assert.match(state, /0\.2\.0/, `said "${state}"`);
  assert.match(state, /0\.1\.0/, "did not say what is running now");
  assert.match(label, /0\.2\.0/, `the button says "${label}"`);
});

await check("release notes are shown, but folded away", async () => {
  // Published text of arbitrary length, and not ours.
  const page = await open({ update: { ...K.UPDATE_NONE, ...FOUND } });
  await page.waitForTimeout(300);
  const open_ = await page.evaluate(() => document.getElementById("update-notes").open);
  // `textContent`, not `innerText`: a closed <details> renders nothing, so
  // innerText is empty even when the notes are there.
  const body = await page.evaluate(() =>
    document.getElementById("update-notes-body").textContent);
  await page.close();
  assert.equal(open_, false, "the notes push the button off the screen by default");
  assert.match(body, /Fixed the thing/);
});

await check("a build with no key says so instead of offering a dead button", async () => {
  const page = await open({ update: { ...K.UPDATE_NONE, supported: false } });
  await page.waitForTimeout(300);
  const state = await page.locator("#update-state").innerText();
  const disabled = await page.locator("#update-check").isDisabled();
  await page.close();
  assert.match(state, /no update key/i, `said "${state}"`);
  assert.equal(disabled, true, "a Check button that can only fail is still pressable");
});

await check("a failed install is reported, not swallowed", async () => {
  const page = await open({
    update: { ...K.UPDATE_NONE, ...FOUND },
    installFails: "signature verification failed",
  });
  await page.locator("#update-install").click();
  await page.waitForTimeout(300);
  const status = await page.locator("#update-status").innerText();
  const tone = await page.locator("#update-status").getAttribute("data-tone");
  await page.close();
  assert.match(status, /signature/i, `said "${status}"`);
  assert.equal(tone, "bad");
});

await check("a result found at startup is still there when Settings opens", async () => {
  // The window is opened LATER — after a startup check has already found
  // something. Without a cache, `update_status` rebuilt a blank answer and the
  // window said "the newest published" while the tray said 0.2.0.
  const page = await open({ update: { ...K.UPDATE_NONE, ...FOUND } });
  await page.waitForTimeout(300);
  const seen = await calls(page);
  const state = await page.locator("#update-state").innerText();
  await page.close();
  assert.ok(!seen.includes("__checked"),
    "opening Settings fired a network check of its own");
  assert.match(state, /0\.2\.0/, `said "${state}" without having checked`);
});

await check("CONTROL: Rust caches the result rather than rebuilding a blank one", async () => {
  const rust = read("src-tauri/src/update.rs");
  assert.match(rust, /pub struct UpdateState/, "there is no cache");
  const fn = rust.slice(rust.indexOf("pub fn update_status"), rust.indexOf("/// Checks now"));
  assert.match(fn, /state::<UpdateState>\(\)/, "update_status ignores the cache");
});

/* ── The startup check ───────────────────────────────────────────────────── */

await check("the startup check can be turned off", async () => {
  const page = await open();
  assert.equal(await page.locator("#update-auto").isChecked(), true,
    "being told is the point of the feature, so it should start on");
  await page.locator("#update-auto").uncheck();
  await page.waitForTimeout(200);
  const status = await page.locator("#update-status").innerText();
  await page.close();
  assert.match(status, /will not look/i, `said "${status}"`);
});

await check("CONTROL: only one endpoint, and it is the releases URL", async () => {
  // The whole network surface of this feature. If it grows, it should grow
  // visibly.
  const conf = JSON.parse(read("src-tauri/tauri.conf.json"));
  const endpoints = conf.plugins.updater.endpoints;
  assert.equal(endpoints.length, 1, `${endpoints.length} endpoints configured`);
  assert.match(endpoints[0], /^https:\/\/github\.com\//, endpoints[0]);
  assert.ok(!/\?|token|key=/i.test(endpoints[0]),
    "the endpoint carries a query string, so it is sending something");
});

await check("CONTROL: no page threw", async () => {
  const page = await open({ update: { ...K.UPDATE_NONE, ...FOUND } });
  await page.waitForTimeout(400);
  assert.deepEqual(page.__errors, [], page.__errors.join(" | "));
  await page.close();
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nthe updater holds its line");
process.exit(fails.length ? 1 : 0);
