/**
 * Tailscale reachability, owned by the desktop.
 *
 * The backend has always supported binding off loopback via `JARVIS_HUD_BIND`
 * (docs/INSTALL.md §3.2), but only as a manual environment variable someone
 * set themselves before launching Python by hand. A supervised backend is
 * launched by Rust, so nothing the owner typed ever reached it — the desktop
 * had to grow its own setting and thread it through.
 *
 * Two things matter here, and the second is where a bug would actually bite:
 * the field has to round-trip through `get_api_settings`/`set_api_settings`,
 * and the one dangerous value — `0.0.0.0`, which would hand the backend to
 * the whole network rather than just the tailnet — has to be refused rather
 * than saved quietly.
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

const VIEW = { width: 760, height: 1400 };
const open = (data = {}) => K.open(browser, base, "settings.html", data, VIEW);

/* ── It renders what Rust reports ────────────────────────────────────────── */

await check("the field loads blank when nothing is configured", async () => {
  const page = await open();
  const value = await page.locator("#bind-address").inputValue();
  await page.close();
  assert.equal(value, "");
});

await check("the field loads a configured Tailscale address", async () => {
  const page = await open({ apiSettings: { bindAddress: "100.64.12.3" } });
  const value = await page.locator("#bind-address").inputValue();
  await page.close();
  assert.equal(value, "100.64.12.3");
});

/* ── Saving ───────────────────────────────────────────────────────────────── */

await check("saving sends the trimmed address to set_api_settings", async () => {
  const page = await open();
  await page.locator("#bind-address").fill("  100.64.12.3  ");
  await page.locator("#save-connection").click();
  await page.waitForTimeout(250);
  const calls = await page.evaluate(() => window.__calls);
  await page.close();
  const saved = calls.find((c) => c[0] === "set_api_settings");
  assert.ok(saved, "set_api_settings was never called");
  assert.equal(saved[1].bindAddress, "100.64.12.3");
});

await check("leaving it blank clears a previously-saved address", async () => {
  const page = await open({ apiSettings: { bindAddress: "100.64.12.3" } });
  await page.locator("#bind-address").fill("");
  await page.locator("#save-connection").click();
  await page.waitForTimeout(250);
  const calls = await page.evaluate(() => window.__calls);
  const after = await page.locator("#bind-address").inputValue();
  await page.close();
  const saved = calls.find((c) => c[0] === "set_api_settings");
  assert.equal(saved[1].bindAddress, "");
  assert.equal(after, "", "the field did not stay cleared after reload");
});

await check("saving a normal address reports success, not an error tone", async () => {
  const page = await open();
  await page.locator("#bind-address").fill("100.64.12.3");
  await page.locator("#save-connection").click();
  await page.waitForTimeout(250);
  const status = await page.locator("#connection-status").innerText();
  const tone = await page.locator("#connection-status").getAttribute("data-tone");
  await page.close();
  assert.notEqual(tone, "bad", `saving a good address was reported as an error: "${status}"`);
});

/* ── The one value this exists to stop ───────────────────────────────────── */

for (const spelling of ["0.0.0.0", "0"]) await check(`a wildcard address (${spelling}) is refused, and the page says so`, async () => {
  // The exact failure this whole feature exists to prevent: a value that
  // would open the backend to the whole network being saved without a word.
  const page = await open({
    bindAddressRefuses: [spelling],
    bindAddressRefusalMessage:
      "refusing to bind every network interface (0.0.0.0) — set this computer's own Tailscale or NordVPN Meshnet address instead",
  });
  await page.locator("#bind-address").fill(spelling);
  await page.locator("#save-connection").click();
  await page.waitForTimeout(250);
  const status = await page.locator("#connection-status").innerText();
  const tone = await page.locator("#connection-status").getAttribute("data-tone");
  const calls = await page.evaluate(() => window.__calls);
  await page.close();
  assert.match(status, /every network interface/, `did not explain the refusal: "${status}"`);
  assert.equal(tone, "bad", "a refused address was reported in the success tone");
  // The stub only ever records the attempted call; it never applies it when
  // it throws. Confirm the app did not treat the throw as a success.
  const saved = calls.find((c) => c[0] === "__savedApiSettings" && c[1].bindAddress === spelling);
  assert.ok(saved, "the attempt was never made");
});

await check("an address an older version saved, and this one refuses, is flagged in red", async () => {
  // sidecar.rs does not start the backend with it; the field must not look
  // like it works when it is being ignored.
  const page = await open({ apiSettings: { bindAddress: "0",
    bindAddressProblem: "refusing to bind every network interface (0.0.0.0)" } });
  await page.waitForTimeout(250);
  const status = await page.locator("#connection-status").innerText();
  const tone = await page.locator("#connection-status").getAttribute("data-tone");
  await page.close();
  assert.match(status, /not being used/, `the problem was not shown: "${status}"`);
  assert.equal(tone, "bad");
});

/* ── Explaining itself ───────────────────────────────────────────────────── */

await check("the note explains this is Tailscale-only, never the whole network", async () => {
  const page = await open();
  const note = await page.locator("#bind-address").locator(
    "xpath=../following-sibling::p[contains(@class,'note')][1]"
  ).innerText();
  await page.close();
  assert.match(note, /Tailscale/);
  assert.match(note, /whole internet|home Wi-Fi/i);
});

/* ── Controls ────────────────────────────────────────────────────────────── */

await check("CONTROL: Rust refuses the wildcard before it is persisted", async () => {
  const rust = read("src-tauri/src/commands.rs");
  assert.match(rust, /fn validate_bind_address/, "no validate_bind_address function");
  // Everything refusable is checked before ANYTHING is written - so a refused
  // address cannot leave a half-saved token (or base) behind either.
  const set = rust.slice(rust.indexOf("pub fn set_api_settings"));
  const body = set.slice(0, set.indexOf("\n}\n"));
  const check = body.indexOf("validate_bind_address(");
  const firstWrite = body.search(/store\.(set|delete)\(|token_store::(write|delete)\(/);
  assert.ok(check > -1 && firstWrite > -1 && check < firstWrite,
    "validation does not happen before the write");
  // It used to compare against the exact strings "0.0.0.0" and "::" only,
  // and "0", "0x0" and "000.000.000.000" bind every interface too.
  assert.doesNotMatch(rust, /addr == "0\.0\.0\.0"/,
    "back to an exact-string check, which the short spellings walk past");
  assert.match(rust, /fn binds_every_interface/, "no lenient-parser wildcard check");
});

await check("CONTROL: the shared case table covers the short wildcard spellings", async () => {
  // One table, three readers: the Rust unit tests (include_str!), the
  // backend's test_bind_wildcard.py (which binds a real socket to each
  // every_interface entry, so the table is checked against the OS), and this.
  const table = JSON.parse(read("tests/bind-address-cases.json"));
  for (const spelling of ["0.0.0.0", "0", "0x0", "0.0", "000.000.000.000", "::"]) {
    assert.ok(table.every_interface.includes(spelling), `the table lost ${spelling}`);
  }
  assert.ok(table.refused.includes("100.64.012.3"), "a leading-zero (octal) form is not refused");
  assert.ok(table.refused.includes("192.168.1.20"), "a home-network address is not refused");
  assert.ok(table.accepted.includes("100.64.12.3"), "a real Tailscale address is not accepted");
  const rust = read("src-tauri/src/commands.rs");
  assert.match(rust, /include_str!\("\.\.\/\.\.\/tests\/bind-address-cases\.json"\)/,
    "the Rust tests do not read the shared table");
  const py = readFileSync(join(HERE, "..", "..", "backend", "test_bind_wildcard.py"), "utf8");
  assert.match(py, /bind-address-cases\.json/, "the backend test does not read the shared table");
});

await check("CONTROL: a saved value is checked again before the backend is started with it", async () => {
  const sidecar = read("src-tauri/src/sidecar.rs");
  assert.match(sidecar, /validate_bind_address\(&bind\)[\s\S]{0,120}JARVIS_HUD_BIND/,
    "sidecar passes the stored bind address without re-checking it");
});

await check("CONTROL: a supervised backend is actually told to bind there", async () => {
  const sidecar = read("src-tauri/src/sidecar.rs");
  assert.match(sidecar, /JARVIS_HUD_BIND/,
    "sidecar::start() never sets JARVIS_HUD_BIND on the child process");
  assert.match(sidecar, /supervised_bind_address\(app\)/,
    "sidecar::start() does not read the configured bind address");
});

await check("CONTROL: an empty address is always accepted, since it means loopback-only", async () => {
  const rust = read("src-tauri/src/commands.rs");
  const fn = rust.slice(rust.indexOf("fn validate_bind_address"));
  const body = fn.slice(0, fn.indexOf("\n}\n") + 2);
  assert.match(body, /addr\.is_empty\(\)/, "empty is not special-cased");
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nTailscale reachability holds");
process.exit(fails.length ? 1 : 0);
