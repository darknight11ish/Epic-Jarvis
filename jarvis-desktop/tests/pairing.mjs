/**
 * The pairing token on the desktop: where it is kept, what "Clear token"
 * means, and how the owner gets it onto the phone.
 *
 * Three things were wrong, each found in the 2026-09-23 audit:
 *
 * - "Clear token" saved the token as "", and the Rust lookup took "" as the
 *   token and stopped - never reaching the environment or the backend's own
 *   token file - so every request went out with no token and got 401.
 * - The typed token sat in jarvis-desktop.json as plain text. It now lives
 *   in Windows Credential Manager (token_store.rs). Since 2026-09-24 there
 *   is no plain-text fallback at all (CLAUDE.md rule 3): a token Credential
 *   Manager refuses is not saved, and Settings says so. The backend's own
 *   token moved into Credential Manager the same day (token-store.patch).
 * - The phone's pairing screen says "the token from the desktop", and the
 *   desktop never showed it. Settings now has "Show the token for my phone".
 *
 * The page checks run the real settings.html/settings.js against the shared
 * stub; the CONTROL checks read the Rust, because the rules that matter
 * (empty means unset, the reveal is settings-only) live there.
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
const status = (page) => page.locator("#connection-status").innerText();

/* ── Where the token came from ───────────────────────────────────────────── */

await check("a token typed here says it is in Windows Credential Manager", async () => {
  const page = await open({ apiSettings: { typedToken: "typed-one" } });
  const state = await page.locator("#token-state").innerText();
  const clearable = await page.locator("#clear-token").isEnabled();
  await page.close();
  assert.match(state, /Credential Manager/);
  assert.ok(clearable, "Clear token is disabled for a token typed here");
});

await check("Jarvis's own token is named as such, and Clear is not offered for it", async () => {
  const page = await open();
  const state = await page.locator("#token-state").innerText();
  const clearable = await page.locator("#clear-token").isEnabled();
  await page.close();
  assert.match(state, /Jarvis's own/);
  assert.ok(!clearable, "Clear token was offered for a token this page did not set");
  // The token itself is never on the page until asked for.
  const html = await (await open()).content();
  assert.ok(!html.includes("backend-made-token"), "the token is on the page unasked");
});

/* ── Clear token ─────────────────────────────────────────────────────────── */

await check("Clear token goes back to Jarvis's own token, and says so", async () => {
  const page = await open({ apiSettings: { typedToken: "typed-one" } });
  await page.locator("#clear-token").click();
  await page.waitForTimeout(250);
  const said = await status(page);
  const state = await page.locator("#token-state").innerText();
  const calls = await page.evaluate(() => window.__calls);
  await page.close();
  const sent = calls.find((c) => c[0] === "set_api_settings");
  assert.equal(sent[1].token, "", "Clear did not send the clear");
  assert.match(said, /Now using Jarvis's own/, `did not say what it fell back to: "${said}"`);
  assert.match(state, /Jarvis's own/);
});

await check("with nothing to fall back to, Clear says Jarvis may refuse this app", async () => {
  const page = await open({ apiSettings: { typedToken: "typed-one", backendFileToken: null } });
  await page.locator("#clear-token").click();
  await page.waitForTimeout(250);
  const said = await status(page);
  await page.close();
  assert.match(said, /No other token was found/);
});

await check("a token Credential Manager refuses is NOT saved, and Settings says so", async () => {
  const page = await open({ tokenSaveRefuses: "The token was NOT saved, because Windows Credential Manager refused: saving failed (Windows error 1312). Nothing was written to disk. Try again, or set the JARVIS_TOKEN environment variable instead." });
  await page.locator("#token").fill("a-new-token");
  await page.locator("#save-connection").click();
  await page.waitForTimeout(250);
  const said = await status(page);
  const tone = await page.locator("#connection-status").getAttribute("data-tone");
  const state = await page.locator("#token-state").innerText();
  await page.close();
  assert.match(said, /NOT saved/, `the refusal was not shown: "${said}"`);
  assert.equal(tone, "bad");
  assert.doesNotMatch(state, /set here/, "the page claims a token was set here");
});

await check("Jarvis's own token in Credential Manager is named as such", async () => {
  const page = await open({ apiSettings: { backendCmToken: "backend-cm-token", backendFileToken: null } });
  const state = await page.locator("#token-state").innerText();
  await page.close();
  assert.match(state, /Jarvis's own, kept in Windows Credential Manager/);
});

await check("Jarvis's own token still in the old file says to update the backend", async () => {
  const page = await open();
  const state = await page.locator("#token-state").innerText();
  await page.close();
  assert.match(state, /old plain-text file/);
  assert.match(state, /apply-patches/);
});

/* ── Showing it for the phone ────────────────────────────────────────────── */

await check("Show the token for my phone reveals it read-only, and Hide takes it away", async () => {
  const page = await open();
  assert.ok(await page.locator("#pairing-shown").isHidden(), "shown before it was asked for");
  await page.locator("#reveal-token").click();
  await page.waitForTimeout(250);
  const value = await page.locator("#pairing-token").inputValue();
  const readOnly = await page.locator("#pairing-token").getAttribute("readonly");
  await page.locator("#hide-token").click();
  const after = await page.locator("#pairing-token").inputValue();
  const hidden = await page.locator("#pairing-shown").isHidden();
  await page.close();
  assert.equal(value, "backend-made-token");
  assert.notEqual(readOnly, null, "the shown token is editable");
  assert.equal(after, "", "Hide left the token in the field");
  assert.ok(hidden);
});

await check("with no token anywhere, Show says why instead of showing a blank", async () => {
  const page = await open({ apiSettings: { backendFileToken: null } });
  await page.locator("#reveal-token").click();
  await page.waitForTimeout(250);
  const said = await status(page);
  const tone = await page.locator("#connection-status").getAttribute("data-tone");
  await page.close();
  assert.match(said, /no token yet/);
  assert.equal(tone, "bad");
});

/* ── Controls: the Rust ──────────────────────────────────────────────────── */

await check("CONTROL: an empty token is 'not set' in Rust, at every step", async () => {
  const rust = read("src-tauri/src/commands.rs");
  const pick = rust.slice(rust.indexOf("pub(crate) fn pick_token"));
  const body = pick.slice(0, pick.indexOf("\n}\n"));
  assert.match(body, /filter\(\|t\| !t\.is_empty\(\)\)/, "empty is not filtered before falling through");
  // Every source goes through the same `clean`, so none can stop the chain with "".
  assert.equal((body.match(/clean\(/g) || []).length, 4, "a source skips the empty check (four sources, four clean() calls)");
  assert.match(rust, /fn an_empty_saved_token_falls_through_to_the_backend_file/,
    "the Rust test for the lockout is gone");
});

await check("CONTROL: Clear never stores an empty token", async () => {
  const rust = read("src-tauri/src/commands.rs");
  const set = rust.slice(rust.indexOf("pub fn set_api_settings"));
  const body = set.slice(0, set.indexOf("\n}\n"));
  assert.match(body, /if token\.is_empty\(\) \{[\s\S]*?store\.delete\("token"\)/,
    "clearing does not delete the key");
  // CLAUDE.md rule 3: no plain-text copy, not even as a fallback.
  assert.doesNotMatch(body, /store\.set\("token"/, "the token is written to the settings file");
  assert.match(body, /Err\(e\) => \{\s*return Err\(/, "a refused token does not stop the save");
  // The token is dealt with before anything else is put in the store, so a
  // refused token cannot leave a half-saved change behind.
  assert.ok(body.indexOf("token_store::write(&token)") < body.indexOf('store.set("base"'),
    "the base is put in the store before the token is tried");
});

await check("CONTROL: the typed token goes to Windows Credential Manager", async () => {
  const rust = read("src-tauri/src/commands.rs");
  assert.match(rust, /token_store::write\(&token\)/);
  const store = read("src-tauri/src/token_store.rs");
  assert.match(store, /CredWriteW/);
  assert.match(store, /CredReadW/);
  const cargo = read("src-tauri/Cargo.toml");
  assert.match(cargo, /"Win32_Security_Credentials"/);
  const lib = read("src-tauri/src/lib.rs");
  const setup = lib.slice(lib.indexOf(".setup(|app|"));
  const migrate = setup.indexOf("commands::migrate_plain_token(&handle)");
  const hud = setup.indexOf("build_hud_window(&handle)");
  assert.ok(migrate > -1 && migrate < hud, "the old plain-text token is not moved before the HUD reads it");
});

await check("CONTROL: only the settings window can reveal the token", async () => {
  const toml = read("src-tauri/permissions/surfaces.toml");
  const sets = toml.split("[[set]]").slice(1);
  const holders = sets.filter((s) => s.includes('"allow-reveal-pairing-token"'))
    .map((s) => s.match(/identifier = "([^"]+)"/)[1]);
  assert.deepEqual(holders, ["settings-surface"]);
  const caps = ["brain", "faces", "hud", "onboarding", "quickbar", "widget"];
  for (const c of caps) {
    const json = read(`src-tauri/capabilities/${c}.json`);
    assert.ok(!json.includes("settings-surface"), `${c} holds settings-surface`);
    assert.ok(!json.includes("reveal-pairing-token"), `${c} can reveal the token`);
  }
});

await check("CONTROL: the HUD is re-given the token when it changes, not only when it has no base", async () => {
  const lib = read("src-tauri/src/lib.rs");
  assert.doesNotMatch(lib, /&& !JARVIS\.base\)/, "back to re-sending only when the page has no base");
  assert.match(lib, /JARVIS\.token !== \{token\}/, "configure_hud does not compare the token");
  const stream = read("src-tauri/src/stream.rs");
  const publish = stream.slice(stream.indexOf("pub(crate) fn publish_link"));
  assert.match(publish.slice(0, publish.indexOf("\n}\n")), /crate::configure_hud\(app\)/,
    "a link change does not re-configure the HUD");
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nPairing token holds");
process.exit(fails.length ? 1 : 0);
