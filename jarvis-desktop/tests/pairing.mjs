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

// CONN-6 (audit 3): a Copy button put the token on the Windows clipboard,
// where Clipboard History (and cloud clipboard, on the owner's other
// devices) keeps it. The phone needs it typed, so there is no Copy for it.
await check("the shown token has no Copy button, is not selected, and nothing writes it to the clipboard", async () => {
  const page = await open();
  await page.evaluate(() => {
    window.__clipboardWrites = [];
    const record = (how, text) => window.__clipboardWrites.push({ how, text: String(text) });
    if (navigator.clipboard) {
      navigator.clipboard.writeText = async (text) => record("writeText", text);
      navigator.clipboard.write = async () => record("write", "(items)");
    }
    const exec = document.execCommand.bind(document);
    document.execCommand = (cmd, ...rest) => {
      if (/^(copy|cut)$/i.test(cmd)) record(cmd, String(window.getSelection()));
      return exec(cmd, ...rest);
    };
    document.addEventListener("copy", () => record("copy-event", String(window.getSelection())), true);
  });
  await page.locator("#reveal-token").click();
  await page.waitForTimeout(250);
  const shown = await page.locator("#pairing-shown").evaluate((el) => ({
    buttons: [...el.querySelectorAll("button")].map((b) => b.textContent.trim()),
  }));
  const selected = await page.locator("#pairing-token").evaluate((el) => el.selectionEnd - el.selectionStart);
  // Every button in the pairing block, pressed: none of them may copy it.
  for (const name of shown.buttons) {
    if (name !== "Hide") await page.locator("#pairing-shown button", { hasText: name }).click();
  }
  const note = await page.locator("#pairing .note").innerText();
  const writes = await page.evaluate(() => window.__clipboardWrites);
  await page.close();
  assert.deepEqual(shown.buttons, ["Hide"], `the pairing block has ${JSON.stringify(shown.buttons)}`);
  assert.equal(selected, 0, "the token is shown selected, one Ctrl+C from the clipboard");
  assert.ok(!writes.some((w) => w.text.includes("backend-made-token")),
    `the token was written to the clipboard: ${JSON.stringify(writes)}`);
  assert.match(note, /no Copy button on purpose/);
  assert.match(note, /clipboard history/);
});

await check("CONTROL: the only clipboard write left in Settings is the second card's pin command, which is not secret", async () => {
  const js = read("src/settings.js");
  const writes = [...js.matchAll(/clipboard\.writeText\(([^)]*)\)/g)].map((m) => m[1].trim());
  assert.deepEqual(writes, ["sc.pinCommand.value"]);
  // The one execCommand("copy") fallback is inside the pin command's handler.
  const pinHandler = js.slice(js.indexOf('sc.pinCopy.addEventListener("click"'));
  const pinBody = pinHandler.slice(0, pinHandler.indexOf("\n  });\n"));
  const execs = (js.match(/execCommand\(\s*["']copy/g) || []).length;
  assert.equal(execs, (pinBody.match(/execCommand\(\s*["']copy/g) || []).length,
    "a clipboard copy outside the pin command's Copy");
  assert.doesNotMatch(read("src/settings.html"), /id="copy-token"/);
  assert.match(read("src/settings.html"), /id="sc-pin-copy"/, "the pin command lost its Copy");
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

// CONN-3 (audit 3): the backend's own token was read Credential Manager
// first (the backend reads its old file first), and a backend this app
// started was handed that read-back token as HUD_TOKEN, pinning it.
await check("CONTROL: the backend's own token is read in the backend's order, and never passed back as HUD_TOKEN", async () => {
  const rust = read("src-tauri/src/commands.rs");
  const own = rust.slice(rust.indexOf("fn backend_token(app: &AppHandle)"));
  const body = own.slice(0, own.indexOf("\n}\n"));
  assert.match(body, /pick_backend_token\(token_from_config_dir\(app\), \|\| \{/,
    "backend_token no longer reads the old file first");
  assert.match(rust, /fn the_backends_old_file_beats_its_credential_manager_copy/, "the Rust order test is gone");
  const sidecar = read("src-tauri/src/sidecar.rs");
  const start = sidecar.slice(sidecar.indexOf("fn start(app: &AppHandle"));
  const startBody = start.slice(0, start.indexOf("\n}\n"));
  assert.doesNotMatch(startBody, /jarvis_token_for\(/, "the sidecar passes whatever token was picked");
  assert.match(startBody, /if commands::passes_as_hud_token\(source\) \{\s*command\.env\("HUD_TOKEN", token\);/);
  const passes = rust.slice(rust.indexOf("pub(crate) fn passes_as_hud_token("));
  const passBody = passes.slice(0, passes.indexOf("\n}\n"));
  assert.match(passBody, /TokenSource::BackendCredentialManager \| TokenSource::BackendFile => false/);
});

await check("CONTROL: Clear never stores an empty token", async () => {
  const rust = read("src-tauri/src/commands.rs");
  const set = rust.slice(rust.indexOf("pub fn set_api_settings"));
  const body = set.slice(0, set.indexOf("\n}\n"));
  // Setting or clearing, the plain key goes; "" clears Credential Manager.
  assert.match(body, /if token\.is_some\(\) \{\s*store\.delete\("token"\);/,
    "clearing does not delete the key");
  assert.match(body, /Some\(""\) => match token_store::delete\(\)/);
  // CLAUDE.md rule 3: no plain-text copy, not even as a fallback.
  assert.doesNotMatch(body, /store\.set\("token"/, "the token is written to the settings file");
  // CONN-7 (audit 3): the file first, THEN Credential Manager, and a refusal
  // rolls the file back - so a refused token leaves nothing half-saved, and
  // a failed save cannot leave an old plain copy on disk behind a new
  // Credential Manager token for the next start's migration to restore.
  assert.match(body, /save_file_then_token\(\s*\|\| store\.save\(\)/, "the file is not saved first");
  const order = rust.slice(rust.indexOf("pub(crate) fn save_file_then_token("));
  const orderBody = order.slice(0, order.indexOf("\n}\n"));
  assert.ok(orderBody.indexOf("save_file()") < orderBody.indexOf("credential_manager()"),
    "Credential Manager is written before the settings file");
  assert.match(orderBody, /if let Err\(e\) = credential_manager\(\) \{\s*roll_back_file\(\);/,
    "a refused token does not roll the file back");
  assert.match(rust, /fn a_failed_file_save_never_lets_the_old_token_come_back/, "the Rust test is gone");
});

await check("CONTROL: the typed token goes to Windows Credential Manager", async () => {
  const rust = read("src-tauri/src/commands.rs");
  assert.match(rust, /token_store::write\(token\)/);
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

await check("CONTROL: the HUD is re-configured on every link change, and never given the token (audit M2)", async () => {
  const lib = read("src-tauri/src/lib.rs");
  assert.doesNotMatch(lib, /&& !JARVIS\.base\)/, "back to re-sending only when the page has no base");
  // An empty token, compared and set every time, so a token some earlier
  // version left in the page is wiped; the real one stays in Rust.
  const configure = lib.slice(lib.indexOf("pub fn configure_hud("), lib.indexOf("// Global hotkeys"));
  assert.match(configure, /JARVIS\.token !== ''/, "configure_hud does not clear a token left in the page");
  assert.match(configure, /JARVIS\.set\(\{base\}, '', false\)/);
  assert.doesNotMatch(configure, /jarvis_token_for/, "configure_hud gives the page the token");
  const stream = read("src-tauri/src/stream.rs");
  const publish = stream.slice(stream.indexOf("pub(crate) fn publish_link"));
  assert.match(publish.slice(0, publish.indexOf("\n}\n")), /crate::configure_hud\(app\)/,
    "a link change does not re-configure the HUD");
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nPairing token holds");
process.exit(fails.length ? 1 : 0);
