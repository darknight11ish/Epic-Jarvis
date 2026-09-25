/**
 * Web search on the desktop (the owner's decisions of 2026-09-25;
 * JARVIS-API.md section 23; src/web-search.js, src/web-search-settings.js,
 * src-tauri/src/web_search.rs, token_store.rs).
 *
 * What must hold:
 * - the "why use this one" lines are the PC's own words, word for word, and
 *   Settings shows all four, which one is in use, what stands in the way of
 *   each, and Whoogle's reason for being left out;
 * - ONE change per tap: choosing a provider sends that provider only;
 *   turning "Ask before every web search" off asks the PC (a card there)
 *   and the box does not claim "off" before the PC says so;
 * - Test search says what happened in the PC's words, with the offer to
 *   switch - never a different provider quietly;
 * - a key typed here goes to save_search_key and nowhere else, the box is
 *   emptied at once, and the key is never shown again;
 * - on a stale link every change and the test are greyed - the key boxes
 *   are not (a key goes into this PC's Credential Manager, not the link);
 * - CONTROL: the Rust holds changes on a stale link, never returns a key,
 *   and the powers sit with the Settings window only; the phone has no way
 *   to send a key.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  keyLine,
  LABEL,
  PROVIDERS,
  readSearch,
  testWords,
  WHY,
  WHOOGLE_WHY,
} from "../src/web-search.js";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const readRepo = (p) => readFileSync(join(HERE, "..", "..", p), "utf8");
const CASES = JSON.parse(read("tests/fixtures/web-search-cases.json"));
const C = CASES.cases;

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

// A fake key, built by concatenation so nothing here is shaped like a real one.
const FAKE = "tv" + "ly-" + "page" + "0123456789";

/* ── The words ────────────────────────────────────────────────────────── */

await check("the four lines, the labels and Whoogle's reason are the PC's own words", async () => {
  assert.deepEqual([...PROVIDERS], CASES.providers);
  for (const p of PROVIDERS) {
    assert.equal(WHY[p], CASES.why[p], p);
    assert.equal(LABEL[p], CASES.labels[p], p);
  }
  assert.equal(WHOOGLE_WHY, CASES.left_out[0].why);
});

await check("readSearch reads every real answer, and a PC without it says so", async () => {
  const v = readSearch(C.default);
  assert.equal(v.available, true);
  assert.equal(v.provider, "searxng");
  assert.deepEqual(v.providers.map((p) => p.id), [...PROVIDERS]);
  assert.equal(v.address, "http://127.0.0.1:8888");
  assert.equal(v.askEveryTime, false);
  assert.equal(readSearch(C.damaged).provider, null);
  assert.match(readSearch(C.damaged).why, /damaged/);
  assert.equal(readSearch(C.brave_no_key_ask_every_time).askEveryTime, true);
  assert.equal(keyLine(readSearch(C.tavily_key_saved).providers.find((p) => p.id === "tavily")),
    "A key is saved on this PC.");
  assert.equal(readSearch({ available: false, why: "x" }).available, false);
  assert.equal(readSearch(null).available, false);
  const t = testWords(C.test_not_running.body);
  assert.equal(t.tone, "bad");
  assert.match(t.text, /SearXNG isn't running on this PC/);
  assert.match(t.text, /Switch web search to DuckDuckGo\?/);
  assert.equal(testWords(C.test_works.body).tone, "ok");
});

/* ── Settings ─────────────────────────────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();

/** The bridge for web search's five commands, on top of uikit's. */
function wsBridge(scenario) {
  const core = window.__TAURI__.core;
  const invoke = core.invoke;
  window.__ws = JSON.parse(JSON.stringify(scenario));
  window.__wsCalls = [];
  core.invoke = async (cmd, args) => {
    const w = window.__ws;
    switch (cmd) {
      case "get_web_search":
        return JSON.parse(JSON.stringify(w.view));
      case "set_web_search":
      case "test_web_search": {
        window.__wsCalls.push({ cmd, ...args });
        const link = await invoke("get_link_state");
        if (link.stale) throw new Error("The connection to Jarvis is catching up, so nothing can be sent until it does.");
        if (cmd === "test_web_search") return w.test;
        if (args.provider) {
          w.view.provider = args.provider;
          return { ok: true, said: `Web search now uses ${args.provider}.` };
        }
        if (args.askEveryTime === false) {
          w.view.waiting = true;
          return { ok: true, waiting: true, said: "Waiting for your approval." };
        }
        if (args.askEveryTime === true) {
          w.view.ask_every_time = true;
          return { ok: true, said: "Jarvis now asks before every web search." };
        }
        return { ok: true, said: "SearXNG address set." };
      }
      case "save_search_key": {
        window.__wsCalls.push({ cmd, provider: args.provider, keyLength: String(args.key).length });
        window.__wsKeySeen = args.key;
        const p = w.view.providers.find((x) => x.id === args.provider);
        p.key_saved = true;
        return { ok: true, said: "Saved your Tavily key in Windows Credential Manager on this PC." };
      }
      case "forget_search_key": {
        window.__wsCalls.push({ cmd, ...args });
        const p = w.view.providers.find((x) => x.id === args.provider);
        p.key_saved = false;
        return { ok: true, said: "Removed." };
      }
      default:
        return invoke(cmd, args);
    }
  };
}

async function settings(scenario, data = {}) {
  const page = await K.open(browser, base, "settings.html", data, { width: 820, height: 1800 });
  await page.addInitScript(wsBridge, scenario);
  await page.reload();
  await page.waitForTimeout(700);
  return page;
}

const PLAIN = { view: C.default, test: C.test_not_running.body };

await check("Settings: four providers with the PC's lines, which is in use, Whoogle left out", async () => {
  const page = await settings(PLAIN);
  const text = await page.locator("#web-search").innerText();
  const checked = await page.locator("#ws-providers input:checked").getAttribute("value");
  const errors = page.__errors;
  await page.close();
  for (const p of PROVIDERS) assert.ok(text.includes(CASES.why[p]), `missing the ${p} line`);
  assert.ok(text.includes(CASES.left_out[0].why), "Whoogle's reason");
  assert.match(text, /SearXNG is the default because/);
  assert.match(text, /Search with/i, "the choice lost its label");
  assert.match(text, /In use\. Ready\./);
  assert.equal(checked, "searxng");
  assert.match(text, /No Tavily key is saved on this PC/);
  assert.match(text, /The phone never asks for one/);
  assert.deepEqual(errors, []);
});

await check("Settings: choosing one sends that ONE change; Ask-less waits for the PC's card", async () => {
  const view = JSON.parse(JSON.stringify(C.default));
  view.ask_every_time = true;
  const page = await settings({ view, test: C.test_works.body });
  await page.locator('#ws-providers input[value="duckduckgo"]').check();
  await page.waitForTimeout(400);
  // click(), not uncheck(): the box is put back until the PC says it is off.
  await page.locator("#ws-ask").click();
  await page.waitForTimeout(400);
  const stillOn = await page.locator("#ws-ask").isChecked();
  const status = await page.locator("#ws-ask-status").innerText();
  const calls = await page.evaluate(() => window.__wsCalls);
  await page.close();
  assert.deepEqual(calls, [
    { cmd: "set_web_search", provider: "duckduckgo" },
    { cmd: "set_web_search", askEveryTime: false },
  ]);
  assert.equal(stillOn, true, "the box claimed off before the card was approved");
  assert.match(status, /Waiting for your approval card/);
});

await check("Settings: Test search says what happened, with the offer to switch", async () => {
  const page = await settings(PLAIN);
  await page.locator("#ws-test").click();
  await page.waitForTimeout(400);
  const said = await page.locator("#ws-test-status").innerText();
  const tone = await page.locator("#ws-test-status").getAttribute("data-tone");
  await page.close();
  assert.match(said, /SearXNG isn't running on this PC/);
  assert.match(said, /Switch web search to DuckDuckGo\?/);
  assert.equal(tone, "bad");
});

await check("Settings: a key goes to save_search_key only, the box empties, it is never shown", async () => {
  const page = await settings(PLAIN);
  await page.locator("#ws-key-tavily").fill(FAKE);
  await page.locator('#ws-keys [data-key="tavily"] button', { hasText: "Save key" }).click();
  await page.waitForTimeout(500);
  const box = await page.locator("#ws-key-tavily").inputValue();
  const html = await page.content();
  const calls = await page.evaluate(() => window.__wsCalls);
  const seen = await page.evaluate(() => window.__wsKeySeen);
  const others = await page.evaluate(() => window.__calls.filter(([c]) => c !== "save_search_key")
    .map(([, a]) => JSON.stringify(a || {})).join(" "));
  const line = await page.locator('#ws-keys [data-key="tavily"]').innerText();
  await page.close();
  assert.deepEqual(calls, [{ cmd: "save_search_key", provider: "tavily", keyLength: FAKE.length }]);
  assert.equal(seen, FAKE);
  assert.equal(box, "", "the key stayed in the box");
  assert.ok(!html.includes(FAKE), "the key is on the page");
  assert.ok(!others.includes(FAKE), "the key went to another command");
  assert.match(line, /A key is saved on this PC\./);
});

await check("Settings: on a stale link every change and the test are greyed; the key boxes are not", async () => {
  const page = await settings(PLAIN, { link: { stale: true } });
  const radios = await page.locator("#ws-providers input").evaluateAll((els) => els.map((e) => e.disabled));
  const ask = await page.locator("#ws-ask").isDisabled();
  const addr = await page.locator("#ws-address-save").isDisabled();
  const test = await page.locator("#ws-test").isDisabled();
  const key = await page.locator('#ws-keys [data-key="tavily"] button', { hasText: "Save key" }).isDisabled();
  await page.close();
  assert.ok(radios.length === 4 && radios.every(Boolean));
  assert.equal(ask, true);
  assert.equal(addr, true);
  assert.equal(test, true);
  assert.equal(key, false);
});

await browser.close();
close();

/* ── CONTROL: the Rust, the powers, the phone ─────────────────────────── */

await check("CONTROL: changes held on a stale link in Rust; a key is never returned", async () => {
  const rs = read("src-tauri/src/web_search.rs");
  const set = rs.slice(rs.indexOf("pub async fn set_web_search"), rs.indexOf("pub async fn test_web_search"));
  const test = rs.slice(rs.indexOf("pub async fn test_web_search"), rs.indexOf("fn provider_label"));
  assert.match(set, /if stale\(&app\)/);
  assert.match(test, /if stale\(&app\)/);
  const save = rs.slice(rs.indexOf("pub async fn save_search_key"), rs.indexOf("pub async fn forget_search_key"));
  assert.doesNotMatch(save.slice(save.indexOf("Ok(serde_json::json!")), /\bkey\b[,)]/, "the key is in the answer");
  assert.match(save, /write_search_key/);
});

await check("CONTROL: the five powers sit with the Settings window only", async () => {
  const toml = read("src-tauri/permissions/surfaces.toml");
  const sets = toml.split("[[set]]");
  const settingsSet = sets.find((s) => s.includes('identifier = "settings-surface"'));
  for (const c of ["get-web-search", "set-web-search", "test-web-search", "save-search-key", "forget-search-key"]) {
    assert.ok(settingsSet.includes(`"allow-${c}"`), c);
    assert.equal(sets.filter((s) => s.includes(`"allow-${c}"`)).length, 1, `${c} is in another set`);
  }
  const build = read("src-tauri/build.rs");
  for (const c of ["get_web_search", "set_web_search", "test_web_search", "save_search_key", "forget_search_key"]) {
    assert.ok(build.includes(`"${c}"`), c);
  }
});

await check("CONTROL: the phone has no way to send a key", async () => {
  const kt = readRepo("jarvis-client/app/src/main/java/com/jarvis/client/net/WebSearch.kt");
  assert.doesNotMatch(kt, /"key"\s*to|save_search_key|\/api\/search\/key/);
  assert.match(kt, /The phone never asks for one/);
});

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join(", ")}`);
  process.exit(1);
}
console.log("\nWeb search: the PC's words, one change per tap, the key only into Credential Manager, held on a stale link");
