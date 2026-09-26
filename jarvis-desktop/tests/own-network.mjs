/**
 * The Jarvis address: the owner's own networks only (CLAUDE.md, decided
 * 2026-09-26).
 *
 * Settings used to accept any address of the right shape, so a public
 * tunnel (`https://abc.ngrok-free.app`) was saved, and the pairing token went
 * through it with every request. Now an address off the owner's own
 * networks - this PC, the home network, Tailscale, NordVPN Meshnet - is
 * refused in one plain sentence, and one saved before the rule is not used:
 * the page says so in red, and the link line says it the way it says any
 * other connection error.
 *
 * The verdicts and the sentence come from the shared case table,
 * tests/fixtures/own-network-cases.json, which tools/gen_own_network_cases.py
 * writes from the backend's own rule (backend/jarvis_local_http.py). The Rust
 * that applies it is tested against the same table in commands.rs
 * (own_network_tests), and the phone's OwnNetworkTest reads a byte-identical
 * copy.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const CASES = JSON.parse(read("tests/fixtures/own-network-cases.json"));
const say = (address) => CASES.message.replace("{address}", address);
const REFUSED = CASES.origins.filter((c) => !c.own).map((c) => c.url);
const ALLOWED = CASES.origins.filter((c) => c.own).map((c) => c.url);

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* ── No browser: the table, the words, the link line ─────────────────────── */

await check("the table is the one the phone reads, byte for byte", async () => {
  const phone = readFileSync(join(HERE, "..", "..", "jarvis-client", "app", "src", "test",
    "resources", "contract", "own-network-cases.json"), "utf8");
  assert.equal(phone, read("tests/fixtures/own-network-cases.json"));
});

await check("the table holds the tricky cases the rule exists for", async () => {
  const verdict = Object.fromEntries(CASES.hosts.map((c) => [c.host, c.own]));
  for (const h of ["100.63.255.255", "100.128.0.0", "172.15.255.255", "172.32.0.0", "0.0.0.0",
    "localhost.evil.com", "10.0.0.1.nip.io", "abc123.ngrok-free.app",
    "my-jarvis.trycloudflare.com", "169.254.1.1", "fe80::1", "8.8.8.8"]) {
    assert.equal(verdict[h], false, `${h} should be refused`);
  }
  for (const h of ["localhost", "127.0.0.1", "::1", "192.168.1.20", "10.0.0.1", "172.16.0.1",
    "100.64.0.0", "100.127.255.255", "homeassistant.local", "desktop.tail1234.ts.net",
    "marioirelan11-alps.nord", "DESKTOP.TAIL1234.TS.NET", "desktop.tail1234.ts.net."]) {
    assert.equal(verdict[h], true, `${h} should be allowed`);
  }
  assert.ok(REFUSED.some((u) => u.startsWith("https://")), "https:// is refused too");
  assert.ok(CASES.tricky.some((c) => c.url.includes("@") && !c.own), "a user-name trick");
});

await check("the refusal is ONE sentence, so the link line shows all of it", async () => {
  const link = await import("../src/jarvis-link.js");
  const url = "https://abc123.ngrok-free.app";
  const words = link.linkWords({ connected: false, stale: true, error: say(url) });
  assert.equal(words.tone, "bad");
  assert.equal(words.canAct, false, "approving must be blocked");
  // linkWords shows the reason's first sentence; all of it must survive.
  assert.ok(words.text.startsWith(`Offline — Jarvis's address ${url} is not on your own networks`),
    words.text);
  assert.match(words.text, /a name ending in \.nord\)\. Approving is blocked/, words.text);
});

/* ── Settings ────────────────────────────────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();
const VIEW = { width: 760, height: 1400 };
const open = (data = {}) => K.open(browser, base, "settings.html", data, VIEW);
const refusals = Object.fromEntries(REFUSED.map((u) => [u, say(u)]));

await check("the field says which addresses are accepted, and why", async () => {
  const page = await open();
  const note = await page.locator("#base-note").innerText();
  await page.close();
  assert.match(note, /own networks/);
  assert.match(note, /Tailscale/);
  assert.match(note, /NordVPN Meshnet/);
  assert.match(note, /ngrok/);
});

for (const url of ["https://abc123.ngrok-free.app", "http://100.128.0.0:4719",
  "http://localhost.evil.com:4719"]) {
  await check(`saving ${url} is refused in the shared words`, async () => {
    const page = await open({ baseRefusals: refusals });
    await page.locator("#base").fill(url);
    await page.locator("#save-connection").click();
    await page.waitForTimeout(250);
    const status = await page.locator("#connection-status").innerText();
    const tone = await page.locator("#connection-status").getAttribute("data-tone");
    await page.close();
    assert.equal(status.trim(), say(url));
    assert.equal(tone, "bad");
  });
}

await check("CONTROL: an address on the owner's own networks saves", async () => {
  const page = await open({ baseRefusals: refusals });
  await page.locator("#base").fill(ALLOWED.find((u) => u.includes(".ts.net")));
  await page.locator("#save-connection").click();
  await page.waitForTimeout(250);
  const tone = await page.locator("#connection-status").getAttribute("data-tone");
  const status = await page.locator("#connection-status").innerText();
  await page.close();
  assert.notEqual(tone, "bad", status);
  assert.match(status, /^Saved/);
});

await check("an address saved before the rule is flagged in red, and said to be unused", async () => {
  const url = "https://abc123.ngrok-free.app";
  const page = await open({ apiSettings: { base: url, baseProblem: say(url) } });
  await page.waitForTimeout(250);
  const field = await page.locator("#base").inputValue();
  const status = await page.locator("#connection-status").innerText();
  const tone = await page.locator("#connection-status").getAttribute("data-tone");
  await page.close();
  assert.equal(field, url, "the field must show the refused address, so it can be changed");
  assert.match(status, /not being used/);
  assert.ok(status.includes(say(url)), status);
  assert.match(status, /Nothing is sent to it/);
  assert.equal(tone, "bad");
});

await browser.close();
close();

/* ── Controls: the Rust that does the refusing ───────────────────────────── */

await check("CONTROL: validate_base asks the own-network rule, tested on the shared table", async () => {
  const rust = read("src-tauri/src/commands.rs");
  const fn = rust.slice(rust.indexOf("fn validate_base"));
  assert.match(fn.slice(0, fn.indexOf("\n}\n")), /own_network_problem\(base\)/);
  assert.match(rust, /include_str!\("\.\.\/\.\.\/tests\/fixtures\/own-network-cases\.json"\)/);
});

await check("CONTROL: a refused configured address is never used, and the stream says why", async () => {
  const rust = read("src-tauri/src/commands.rs");
  const fn = rust.slice(rust.indexOf("pub(crate) fn base_from"));
  const body = fn.slice(0, fn.indexOf("\n}\n"));
  assert.match(rust, /pub fn jarvis_base\(app: &AppHandle\) -> String \{\s*base_from\(configured_base\(app\)\)\s*\}/);
  assert.match(body, /validate_base\(&base\)\.is_ok\(\)/, "jarvis_base does not check");
  // The owner's decision of 2026-09-26: nothing over the network while a
  // refused address is saved - not to it, and not to this PC instead.
  assert.match(body, /Some\(_\) => String::new\(\)/, "a refused address falls back to something");
  assert.match(body, /None => DEFAULT_BASE/, "an unset address no longer means this PC");
  const headers = rust.slice(rust.indexOf("pub fn jarvis_headers("));
  assert.match(headers.slice(0, headers.indexOf("\n}\n")), /require_base_allowed\(app\)\?;/,
    "requests to Jarvis are not refused while a refused address is saved");
  const stream = read("src-tauri/src/stream.rs");
  const loop = stream.slice(stream.indexOf("pub fn spawn"));
  const problem = loop.indexOf("commands::base_problem(&app)");
  const connect = loop.indexOf("connect_once(");
  assert.ok(problem > -1 && problem < connect, "the stream connects before checking");
});

if (fails.length) {
  console.log(`\n${fails.length} failed`);
  process.exit(1);
}
console.log("\nall passed");
