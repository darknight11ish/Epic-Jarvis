/**
 * Accounts on the desktop (ease-of-use audit row 15, "Security G3");
 * JARVIS-API.md section 44; src/account-secrets.js,
 * src/account-secrets-settings.js, src-tauri/src/account_secrets.rs,
 * token_store.rs.
 *
 * What must hold:
 * - all four secrets show, in the same order, each with its own box, help
 *   line and status;
 * - a value typed here goes to save_account_secret and nowhere else, the
 *   box is emptied at once, and the value is never shown again;
 * - a secret already set as an environment variable on this PC shows that,
 *   and its box is disabled - saving here would do nothing until it is
 *   removed there, so the page does not pretend otherwise;
 * - Remove only shows once something is saved, and calls
 *   forget_account_secret with that secret's name alone;
 * - CONTROL: the three powers sit with the Settings window only, and the
 *   phone has no such page (deep config editing stays off it).
 */
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { LABEL, readAccountSecrets, SECRETS, statusLine } from "../src/account-secrets.js";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const readRepo = (p) => readFileSync(join(HERE, "..", "..", p), "utf8");

/**
 * Every file under `dirs` (relative to the repo root) whose text matches
 * `pattern`.
 *
 * This used to shell out to `grep -rl`, which does not exist on Windows - so
 * the check could only ever FAIL there, printing "'grep' is not recognized",
 * and never took the honest "this machine cannot run it" route. Node reads
 * the files itself; no Unix tool is required, on any platform.
 */
function filesMatching(dirs, pattern, exts = /\.(kt|kts|java|xml|json|md|txt|toml|gradle|pro|properties)$/) {
  const hits = [];
  const walk = (dir) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === ".git" || entry.name === "build" || entry.name === ".gradle") continue;
        walk(full);
      } else if (exts.test(entry.name)) {
        let text;
        try { text = readFileSync(full, "utf8"); } catch { continue; } // unreadable is not a match
        if (pattern.test(text)) hits.push(full);
      }
    }
  };
  for (const d of dirs) walk(d);
  return hits;
}

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

// A fake value, built by concatenation so nothing here is shaped like a real one.
const FAKE = "hunter" + "2" + "hunter" + "2";

function allNone() {
  return { secrets: SECRETS.map((name) => ({ name, env_set: false, saved: false })) };
}

/* ── The words ────────────────────────────────────────────────────────── */

await check("readAccountSecrets always returns the four, in order, even from an odd answer", () => {
  const rows = readAccountSecrets({ secrets: [{ name: "home_token", env_set: true }] });
  assert.deepEqual(rows.map((r) => r.name), [...SECRETS]);
  assert.equal(rows.find((r) => r.name === "home_token").envSet, true);
  assert.equal(rows.find((r) => r.name === "imap_user").saved, null);
  assert.deepEqual(readAccountSecrets(null).map((r) => r.name), [...SECRETS]);
  assert.deepEqual(readAccountSecrets(undefined).map((r) => r.saved), [null, null, null, null]);
});

await check("statusLine never claims a value, and says which source wins", () => {
  assert.match(statusLine({ envSet: true, envVar: "JARVIS_IMAP_USER" }), /JARVIS_IMAP_USER/);
  assert.equal(statusLine({ envSet: false, saved: true }), "Saved in Windows Credential Manager on this PC.");
  assert.equal(statusLine({ envSet: false, saved: false }), "Not set.");
  assert.equal(statusLine({ envSet: false, saved: null }), "Could not check whether one is saved.");
});

/* ── Settings ─────────────────────────────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();

/** The bridge for the three account-secrets commands, on top of uikit's. */
function asBridge(scenario) {
  const core = window.__TAURI__.core;
  const invoke = core.invoke;
  window.__as = JSON.parse(JSON.stringify(scenario));
  window.__asCalls = [];
  core.invoke = async (cmd, args) => {
    const w = window.__as;
    switch (cmd) {
      case "get_account_secrets":
        return JSON.parse(JSON.stringify(w.view));
      case "save_account_secret": {
        window.__asCalls.push({ cmd, name: args.name, valueLength: String(args.value).length });
        window.__asValueSeen = args.value;
        const row = w.view.secrets.find((x) => x.name === args.name);
        row.saved = true;
        return { ok: true, said: "Saved in Windows Credential Manager on this PC." };
      }
      case "forget_account_secret": {
        window.__asCalls.push({ cmd, name: args.name });
        const row = w.view.secrets.find((x) => x.name === args.name);
        row.saved = false;
        return { ok: true, said: "Removed from Windows Credential Manager on this PC." };
      }
      default:
        return invoke(cmd, args);
    }
  };
}

async function settings(view) {
  const page = await K.open(browser, base, "settings.html", {}, { width: 820, height: 1800 });
  await page.addInitScript(asBridge, { view });
  await page.reload();
  await page.waitForTimeout(500);
  return page;
}

await check("Settings: all four secrets show, in order, each with its own help", async () => {
  const page = await settings(allNone());
  const text = await page.locator("#account-secrets").innerText();
  const boxes = await page.locator("#as-body [data-secret]").evaluateAll((els) => els.map((e) => e.dataset.secret));
  const errors = page.__errors;
  await page.close();
  assert.deepEqual(boxes, [...SECRETS]);
  const lower = text.toLowerCase();
  for (const name of SECRETS) {
    assert.ok(lower.includes(LABEL[name].toLowerCase()), `missing the ${name} label`);
  }
  assert.match(text, /Not set\./);
  assert.deepEqual(errors, []);
});

await check("Settings: a value goes to save_account_secret only, the box empties, never shown", async () => {
  const page = await settings(allNone());
  await page.locator("#as-imap_password").fill(FAKE);
  await page.locator('#as-body [data-secret="imap_password"] button', { hasText: "Save" }).click();
  await page.waitForTimeout(500);
  const box = await page.locator("#as-imap_password").inputValue();
  const html = await page.content();
  const calls = await page.evaluate(() => window.__asCalls);
  const seen = await page.evaluate(() => window.__asValueSeen);
  const others = await page.evaluate(() => window.__calls.filter(([c]) => c !== "save_account_secret")
    .map(([, a]) => JSON.stringify(a || {})).join(" "));
  const line = await page.locator('#as-body [data-secret="imap_password"]').innerText();
  await page.close();
  assert.deepEqual(calls, [{ cmd: "save_account_secret", name: "imap_password", valueLength: FAKE.length }]);
  assert.equal(seen, FAKE);
  assert.equal(box, "", "the value stayed in the box");
  assert.ok(!html.includes(FAKE), "the value is on the page");
  assert.ok(!others.includes(FAKE), "the value went to another command");
  assert.match(line, /Saved in Windows Credential Manager on this PC\./);
});

await check("Settings: a secret already set as an environment variable disables its box", async () => {
  const view = allNone();
  view.secrets.find((x) => x.name === "home_token").env_set = true;
  const page = await settings(view);
  const inputDisabled = await page.locator("#as-home_token").isDisabled();
  const saveDisabled = await page
    .locator('#as-body [data-secret="home_token"] button', { hasText: "Save" })
    .isDisabled();
  const line = await page.locator('#as-body [data-secret="home_token"]').innerText();
  const others = await page.locator('#as-body [data-secret="imap_user"] input').isDisabled();
  await page.close();
  assert.equal(inputDisabled, true);
  assert.equal(saveDisabled, true);
  assert.match(line, /JARVIS_HOME_TOKEN/);
  assert.equal(others, false, "an unrelated secret's box was disabled too");
});

await check("Settings: Remove only shows once saved, and names that one secret alone", async () => {
  const view = allNone();
  view.secrets.find((x) => x.name === "calendar_ics_url").saved = true;
  const page = await settings(view);
  const removeShown = await page.locator('#as-body [data-secret="calendar_ics_url"] button', { hasText: "Remove" }).isVisible();
  const removeHidden = await page.locator('#as-body [data-secret="imap_user"] button', { hasText: "Remove" }).isHidden();
  await page.locator('#as-body [data-secret="calendar_ics_url"] button', { hasText: "Remove" }).click();
  await page.waitForTimeout(400);
  const calls = await page.evaluate(() => window.__asCalls);
  await page.close();
  assert.equal(removeShown, true);
  assert.equal(removeHidden, true);
  assert.deepEqual(calls, [{ cmd: "forget_account_secret", name: "calendar_ics_url" }]);
});

await browser.close();
close();

/* ── CONTROL: the Rust, the powers, the phone ─────────────────────────── */

await check("CONTROL: a value is never returned by save_account_secret, and the store checks it", async () => {
  const rs = read("src-tauri/src/account_secrets.rs");
  const save = rs.slice(rs.indexOf("pub async fn save_account_secret"), rs.indexOf("pub async fn forget_account_secret"));
  assert.doesNotMatch(save.slice(save.indexOf("Ok(serde_json::json!")), /\bvalue\b[,)]/, "the value is in the answer");
  assert.match(save, /write_account_secret/);
  assert.match(save, /account_secret_problem/);
});

await check("CONTROL: the three powers sit with the Settings window only", async () => {
  const toml = read("src-tauri/permissions/surfaces.toml");
  const sets = toml.split("[[set]]");
  const settingsSet = sets.find((s) => s.includes('identifier = "settings-surface"'));
  for (const c of ["get-account-secrets", "save-account-secret", "forget-account-secret"]) {
    assert.ok(settingsSet.includes(`"allow-${c}"`), c);
    assert.equal(sets.filter((s) => s.includes(`"allow-${c}"`)).length, 1, `${c} is in another set`);
  }
  const build = read("src-tauri/build.rs");
  for (const c of ["get_account_secrets", "save_account_secret", "forget_account_secret"]) {
    assert.ok(build.includes(`"${c}"`), c);
  }
});

await check("CONTROL: the environment variable still wins on the backend (resolve_secret's own rule)", async () => {
  const py = readRepo("backend/jarvis_token_store.py");
  assert.match(py, /def resolve_secret/);
  const fn = py.slice(py.indexOf("def resolve_secret"));
  assert.match(fn.slice(0, fn.indexOf("\n\n\n")), /env\.get\(env_name/);
});

await check("CONTROL: there is no such page for the phone", async () => {
  // Nothing in either Android app names any of the four Credential Manager
  // targets or the account_secrets commands - a simple absence check, since
  // there is no Kotlin file for this feature to begin with (one-sided on
  // purpose: deep config editing stays off the phone, CLAUDE.md).
  const repoRoot = join(HERE, "..", "..");
  const hits = filesMatching(
    [join(repoRoot, "jarvis-client"), join(repoRoot, "jarvis-android")],
    /account_secret|Jarvis Backend\/IMAP|Jarvis Backend\/Calendar iCal|Jarvis Backend\/Home Assistant/
  ).map((p) => p.slice(repoRoot.length + 1));
  assert.deepEqual(hits, [], `the phone app references account secrets: ${hits.join(", ")}`);
});

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join(", ")}`);
  process.exit(1);
}
console.log("\nAccounts: four secrets, each into Credential Manager on this PC, the environment variable still wins, never shown again");
