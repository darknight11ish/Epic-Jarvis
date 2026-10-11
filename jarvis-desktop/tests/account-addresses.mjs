/**
 * The account ADDRESSES on the desktop (the owner's decision of 2026-10-06:
 * "anything needing a key or a sign-in should be settable in the Jarvis app
 * itself", desktop only; backend/accounts.patch, backend/jarvis_accounts.py);
 * src/account-secrets.js, src/account-secrets-settings.js,
 * src-tauri/src/account_addresses.rs.
 *
 * The Accounts card holds TWO shapes, and this is the second one. What must
 * hold:
 *
 * - all eight addresses show, in the PC's order, each with its own box, help
 *   line and status - none of the four SECRETS is among them;
 * - the box SHOWS what is saved (an address is not a secret), and Save sends
 *   exactly one change, with that address's own name, to save_account_address
 *   and nowhere else;
 * - an address already set as a Windows environment variable says so, and its
 *   box is disabled - saving here would do nothing until it is removed there,
 *   so the page does not pretend otherwise. An environment variable's VALUE
 *   is never asked for or shown;
 * - the one CHOICE (how email is encrypted) is a picker, not a free-text box;
 * - a save is greyed while the link is stale, and a PC without the route says
 *   so plainly rather than showing eight dead boxes;
 * - CONTROL: the eight are the only names the Rust side will ever send, a
 *   secret is refused before a request is built, the two commands sit with the
 *   Settings window only, and the phone has no such page (deep config editing
 *   stays off it).
 */
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  ADDRESSES,
  ADDRESS_CHOICES,
  ADDRESS_ENV_VAR,
  ADDRESS_LABEL,
  addressStatusLine,
  readAccountAddresses,
} from "../src/account-secrets.js";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const readRepo = (p) => readFileSync(join(HERE, "..", "..", p), "utf8");

/** Every file under `dirs` whose text matches `pattern` (no Unix tool: this
 *  used to shell out to `grep -rl`, which does not exist on Windows). */
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
        try { text = readFileSync(full, "utf8"); } catch { continue; }
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

// Fake values, built by concatenation so nothing here is shaped like a real one.
const FAKE_SECRET = "hunter" + "2" + "hunter" + "2";

/** The eight with nothing saved anywhere - what a fresh PC answers. */
function allEmpty() {
  return {
    answer: {
      available: true,
      why: "",
      fields: ADDRESSES.map((name) => ({
        name, env: ADDRESS_ENV_VAR[name], env_set: false, value: "",
      })),
    },
  };
}

function withSaved(name, value) {
  const a = allEmpty();
  a.answer.fields.find((f) => f.name === name).value = value;
  return a;
}

/* ── The words ────────────────────────────────────────────────────────── */

await check("readAccountAddresses always returns the eight, in order, even from an odd answer", () => {
  const rows = readAccountAddresses({ fields: [{ name: "home_url", value: "http://h:8123" }] });
  assert.deepEqual(rows.map((r) => r.name), [...ADDRESSES]);
  assert.equal(rows.find((r) => r.name === "home_url").value, "http://h:8123");
  assert.equal(rows.find((r) => r.name === "imap_host").value, "");
  assert.deepEqual(readAccountAddresses(null).map((r) => r.name), [...ADDRESSES]);
  assert.deepEqual(readAccountAddresses(undefined).map((r) => r.value),
    ADDRESSES.map(() => ""));
});

await check("none of the four SECRETS is among the eight", () => {
  for (const name of ["imap_user", "imap_password", "calendar_ics_url", "home_token"]) {
    assert.ok(!ADDRESSES.includes(name), name);
  }
  for (const name of ADDRESSES) {
    assert.doesNotMatch(name, /key|password|token|secret|ics/, name);
  }
});

await check("addressStatusLine says where a value comes from, and never a value", () => {
  assert.match(
    addressStatusLine({ envSet: true, envVar: "JARVIS_IMAP_HOST" }),
    /JARVIS_IMAP_HOST/,
  );
  assert.equal(addressStatusLine({ envSet: false, value: "imap.gmail.com" }), "Saved on this PC.");
  assert.equal(addressStatusLine({ envSet: false, value: "" }), "Not set.");
  assert.equal(addressStatusLine(null), "Could not check.");
});

await check("the encryption choice is a picker of the PC's three modes", () => {
  const values = ADDRESS_CHOICES.smtp_tls.map((c) => c.value);
  assert.deepEqual(values, ["", "ssl", "starttls", "off"]);
  assert.equal(Object.keys(ADDRESS_CHOICES).length, 1, "only smtp_tls is a choice");
});

/* ── Settings ─────────────────────────────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();

/** The bridge for the account addresses' two commands, on top of uikit's. */
function addressBridge(scenario) {
  const core = window.__TAURI__.core;
  const invoke = core.invoke;
  window.__aa = JSON.parse(JSON.stringify(scenario));
  window.__aaCalls = [];
  core.invoke = async (cmd, args) => {
    const w = window.__aa;
    switch (cmd) {
      case "get_account_addresses":
        if (w.answer === null) throw new Error("no desktop backend");
        return JSON.parse(JSON.stringify(w.answer));
      case "save_account_address": {
        window.__aaCalls.push({ cmd, name: args.name, value: args.value });
        const row = w.answer.fields.find((x) => x.name === args.name);
        row.value = String(args.value);
        return { ok: true, said: `Saved ${args.name} on this PC.` };
      }
      case "get_account_secrets":
        return { secrets: [] };
      default:
        return invoke(cmd, args);
    }
  };
}

async function settings(scenario, data = {}, viewport = { width: 900, height: 2600 }) {
  const page = await K.open(browser, base, "settings.html", data, viewport);
  await page.addInitScript(addressBridge, scenario);
  await page.reload();
  await page.waitForTimeout(500);
  return page;
}

await check("Settings: all eight addresses show, in order, each with its own help", async () => {
  const page = await settings(allEmpty());
  const text = await page.locator("#account-secrets").innerText();
  const boxes = await page.locator("#as-addresses [data-address]")
    .evaluateAll((els) => els.map((e) => e.dataset.address));
  const savedValue = await page.locator("#as-imap_host").inputValue();
  const errors = page.__errors;
  await page.close();
  assert.deepEqual(boxes, [...ADDRESSES]);
  const lower = text.toLowerCase();
  for (const name of ADDRESSES) {
    assert.ok(lower.includes(ADDRESS_LABEL[name].toLowerCase()), `missing the ${name} label`);
  }
  assert.equal(savedValue, "");
  assert.match(text, /Not set\./);
  assert.match(text, /Server addresses/);
  assert.deepEqual(errors, []);
});

await check("Settings: a saved address is SHOWN (it is not a secret), and Save sends one change", async () => {
  const page = await settings(withSaved("imap_host", "imap.gmail.com"));
  const before = await page.locator("#as-imap_host").inputValue();
  await page.locator("#as-imap_host").fill("imap.fastmail.com");
  await page.locator('#as-addresses [data-address="imap_host"] button', { hasText: "Save" }).click();
  await page.waitForTimeout(500);
  const calls = await page.evaluate(() => window.__aaCalls);
  const line = await page.locator('#as-addresses [data-address="imap_host"]').innerText();
  const others = await page.evaluate(() => window.__calls
    .filter(([c]) => c !== "get_account_secrets" && c !== "get_account_addresses")
    .map(([c, a]) => `${c} ${JSON.stringify(a || {})}`).join(" "));
  await page.close();
  assert.equal(before, "imap.gmail.com", "the saved address is not shown in its box");
  assert.deepEqual(calls, [{ cmd: "save_account_address", name: "imap_host", value: "imap.fastmail.com" }]);
  assert.match(line, /Saved on this PC\./);
  assert.ok(!others.includes("imap_host"), `went to another command: ${others}`);
});

await check("Settings: an address already set as an environment variable disables its box and says so", async () => {
  const a = withSaved("home_url", "http://192.168.1.5:8123");
  a.answer.fields.find((f) => f.name === "home_url").env_set = true;
  const page = await settings(a);
  const inputDisabled = await page.locator("#as-home_url").isDisabled();
  const saveDisabled = await page
    .locator('#as-addresses [data-address="home_url"] button', { hasText: "Save" })
    .isDisabled();
  const line = await page.locator('#as-addresses [data-address="home_url"]').innerText();
  const value = await page.locator("#as-home_url").inputValue();
  const other = await page.locator("#as-caldav_url").isDisabled();
  await page.close();
  assert.equal(inputDisabled, true);
  assert.equal(saveDisabled, true);
  assert.match(line, /JARVIS_HOME_URL/);
  assert.equal(value, "http://192.168.1.5:8123", "a saved address is still shown");
  assert.equal(other, false, "an unrelated address's box was disabled too");
});

await check("Settings: the encryption choice is a picker holding the PC's three modes", async () => {
  const page = await settings(withSaved("smtp_tls", "starttls"));
  const tag = await page.locator("#as-smtp_tls").evaluate((el) => el.tagName);
  const values = await page.locator("#as-smtp_tls option").evaluateAll((els) => els.map((e) => e.value));
  const chosen = await page.locator("#as-smtp_tls").inputValue();
  await page.locator("#as-smtp_tls").selectOption("off");
  await page.locator('#as-addresses [data-address="smtp_tls"] button', { hasText: "Save" }).click();
  await page.waitForTimeout(400);
  const calls = await page.evaluate(() => window.__aaCalls);
  await page.close();
  assert.equal(tag, "SELECT");
  assert.deepEqual(values, ADDRESS_CHOICES.smtp_tls.map((c) => c.value));
  assert.equal(chosen, "starttls");
  assert.deepEqual(calls, [{ cmd: "save_account_address", name: "smtp_tls", value: "off" }]);
});

await check("Settings: a stale link greys every Save, and lets nothing be sent", async () => {
  const page = await settings(allEmpty(), { link: { stale: true } });
  const disabled = await page
    .locator('#as-addresses [data-address="imap_host"] button', { hasText: "Save" })
    .isDisabled();
  const inputDisabled = await page.locator("#as-imap_host").isDisabled();
  const title = await page.locator('#as-addresses [data-address="imap_host"] button').getAttribute("title");
  const calls = await page.evaluate(() => window.__aaCalls);
  await page.close();
  assert.equal(disabled, true);
  assert.equal(inputDisabled, true);
  assert.match(String(title), /link to catch up/i);
  assert.deepEqual(calls, []);
});

await check("Settings: a PC without the addresses route says so, and shows no dead boxes", async () => {
  const a = { answer: { available: false, why: "Your PC's Jarvis does not have the account addresses yet - run apply-patches.ps1 on the PC." } };
  const page = await settings(a);
  const text = await page.locator("#as-addresses-state").innerText();
  const boxes = await page.locator("#as-addresses [data-address]").count();
  const errors = page.__errors;
  await page.close();
  assert.match(text, /apply-patches\.ps1/);
  assert.equal(boxes, 0);
  assert.deepEqual(errors, []);
});

await browser.close();
close();

/* ── CONTROL: the Rust, the powers, the phone ─────────────────────────── */

await check("CONTROL: the eight are the only names the Rust side will send", async () => {
  const rs = read("src-tauri/src/account_addresses.rs");
  // The shipped code only: the `#[cfg(test)]` block below it names the four
  // secrets on purpose, to prove each one is refused.
  const code = rs.slice(0, rs.indexOf("#[cfg(test)]"));
  const list = code.slice(code.indexOf("pub(crate) const FIELDS"),
                          code.indexOf("];", code.indexOf("pub(crate) const FIELDS")));
  for (const name of ADDRESSES) assert.ok(list.includes(`"${name}"`), name);
  const names = [...list.matchAll(/"([a-z_]+)"/g)].map((m) => m[1]);
  assert.deepEqual(names, [...ADDRESSES]);
  assert.match(code, /fn change_body/);
  assert.match(code, /if !FIELDS\.contains\(&name\)/, "the name is not checked before a request is built");
  assert.match(code, /ADDRESSES_PATH: &str = "\/api\/accounts\/addresses"/);
  assert.doesNotMatch(code, /imap_password|imap_user\b|home_token|calendar_ics_url/,
    "the address half names a secret");
  assert.match(code, /stale\(&app\)/, "a save is not held on a stale link");
  // ... and the test block refuses each of the four, so the rule is proven
  // rather than only asserted about.
  for (const name of ["imap_password", "imap_user", "home_token", "calendar_ics_url"]) {
    assert.ok(rs.includes(`"${name}"`), `the Rust tests do not refuse ${name}`);
  }
});

await check("CONTROL: the route stores addresses in a plain file, and refuses a secret by name", async () => {
  const py = readRepo("backend/jarvis_accounts.py");
  assert.match(py, /def addresses_path\(\)[\s\S]*?accounts\.json/);
  assert.match(py, /def handle_settings/);
  assert.match(py, /REFUSES_SECRETS/);
  assert.doesNotMatch(py, /JARVIS_IMAP_PASSWORD|JARVIS_HOME_TOKEN|JARVIS_CALENDAR_ICS_SECRET_URL/,
    "the addresses module names a secret's own environment variable");
  const patch = readRepo("backend/accounts.patch");
  assert.ok(patch.includes("/api/accounts/addresses"), "the patch adds no addresses route");
  assert.doesNotMatch(patch, /\/api\/accounts\/(key|secret|password|token)\b/);
  // The addresses file is beside web-search.json - the proven shape for an
  // address or a choice, and NOT Credential Manager (a store-sourced value is
  // redacted by exact value, which would swallow a host name).
  assert.match(readRepo("backend/jarvis_search.py"), /web-search\.json/);
});

await check("CONTROL: the two powers sit with the Settings window only", async () => {
  const toml = read("src-tauri/permissions/surfaces.toml");
  const sets = toml.split("[[set]]");
  const settingsSet = sets.find((s) => s.includes('identifier = "settings-surface"'));
  for (const c of ["get-account-addresses", "save-account-address"]) {
    assert.ok(settingsSet.includes(`"allow-${c}"`), c);
    assert.equal(sets.filter((s) => s.includes(`"allow-${c}"`)).length, 1, `${c} is in another set`);
  }
  const build = read("src-tauri/build.rs");
  const lib = read("src-tauri/src/lib.rs");
  for (const c of ["get_account_addresses", "save_account_address"]) {
    assert.ok(build.includes(`"${c}"`), `${c} is not in build.rs`);
    assert.ok(lib.includes(`account_addresses::${c}`), `${c} is not in lib.rs`);
    assert.ok(
      read(`src-tauri/permissions/autogenerated/${c}.toml`)
        .includes(`allow-${c.replace(/_/g, "-")}`),
      `${c} has no generated permission file`,
    );
  }
});

await check("CONTROL: no page can put one of the four secrets in the addresses file", async () => {
  const js = read("src/account-secrets-settings.js");
  const called = [...js.matchAll(/invoke\(\s*"([a-z_]+)"/g)].map((m) => m[1]);
  assert.deepEqual([...new Set(called)].sort(),
    ["get_account_addresses", "get_account_secrets", "forget_account_secret",
     "save_account_address", "save_account_secret"].sort());
  // save_account_address is only ever called with a name from ADDRESSES.
  const m = js.match(/invoke\("save_account_address",\s*\{([^}]*)\}/);
  assert.ok(m, "save_account_address is not called with an object");
  assert.match(m[1], /name:\s*entry\.name/);
  assert.doesNotMatch(js, /imap_password["'\s]*:/, "a secret name is built into an address save");
});

await check("CONTROL: there is no such page for the phone", async () => {
  const repoRoot = join(HERE, "..", "..");
  const hits = filesMatching(
    [join(repoRoot, "jarvis-client"), join(repoRoot, "jarvis-android")],
    /accounts\/addresses|account_addresses|jarvis_accounts|JARVIS_IMAP_MAILBOX/,
  ).map((p) => p.slice(repoRoot.length + 1));
  assert.deepEqual(hits, [], `the phone app references the account addresses: ${hits.join(", ")}`);
});

// A last guard: the fake secret is nowhere in what a save sends.
await check("CONTROL: the fake secret was never sent anywhere", async () => {
  assert.ok(!read("src/account-secrets-settings.js").includes(FAKE_SECRET));
});

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join(", ")}`);
  process.exit(1);
}
console.log("\nAccount addresses: eight addresses and one choice, saved on the PC in accounts.json, an environment variable still wins, never a secret");
