/**
 * "What Jarvis can reach" on the desktop (the Muse audit, 2026-09-25;
 * JARVIS-API.md section 24; src/reach.js, src/reach-settings.js,
 * src-tauri/src/reach.rs).
 *
 * What must hold:
 * - the words for the parts of the screen are the PC's own, word for word
 *   (tests/fixtures/reach-cases.json, made by the real jarvis_reach.py);
 * - Settings shows every row the PC sends, in its order, with its state,
 *   where it goes and whether it asks - the PC's words, unchanged - and the
 *   tools the AI model is offered;
 * - it is a read: get_reach is the only command it calls, and a stale link
 *   hides nothing and greys nothing (there is nothing to send);
 * - no secret is on the page (the PC leaves them out; this checks the page
 *   adds none - there is nothing it could add);
 * - CONTROL: get_reach sits with the Settings window only.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  DETAIL,
  EVERYTHING_ELSE,
  MISSING,
  readReach,
  rowLines,
  TITLE,
  TOOLS_NONE,
  TOOLS_TITLE,
} from "../src/reach.js";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const CASES = JSON.parse(read("tests/fixtures/reach-cases.json"));
const C = CASES.cases;

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* ── The words ────────────────────────────────────────────────────────── */

await check("the words for the screen are the PC's own", async () => {
  assert.equal(TITLE, CASES.title);
  assert.equal(DETAIL, CASES.detail);
  assert.equal(MISSING, CASES.missing);
  assert.equal(TOOLS_TITLE, CASES.tools_title);
  assert.equal(TOOLS_NONE, CASES.tools_none);
  assert.equal(EVERYTHING_ELSE, CASES.everything_else);
  const html = read("src/settings.html");
  assert.ok(html.includes(`<h2>${TITLE}</h2>`), "the heading");
  assert.ok(html.includes(DETAIL), "the note under the heading");
});

await check("readReach reads every real answer, and a PC without it says so", async () => {
  for (const [name, view] of Object.entries(C)) {
    const v = readReach(view);
    assert.equal(v.available, true, name);
    assert.deepEqual(v.rows.map((r) => r.id), CASES.ids, name);
    assert.equal(v.on, view.on, name);
    assert.deepEqual(v.tools.map((t) => t.id), view.tools.map((t) => t.id), name);
  }
  const every = readReach(C.everything_on);
  const web = every.rows.find((r) => r.id === "web_search");
  assert.deepEqual(rowLines(web, every), [
    `Goes to: ${web.where}`, `Asks you first: ${web.asks}`, web.line]);
  const off = readReach(C.nothing_set_up).rows.find((r) => r.id === "email_read");
  assert.deepEqual(rowLines(off, readReach(C.nothing_set_up)), [off.line], "an off row shows its line only");
  assert.equal(readReach({ available: false, why: "x" }).why, "x");
  assert.equal(readReach(null).available, false);
  assert.equal(readReach({ rows: [] }).why, MISSING);
});

/* ── Settings ─────────────────────────────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();

function reachBridge(view) {
  const core = window.__TAURI__.core;
  const invoke = core.invoke;
  window.__reachCalls = [];
  core.invoke = async (cmd, args) => {
    if (cmd === "get_reach") {
      window.__reachCalls.push(cmd);
      if (view === "old") throw new Error("not json");
      return JSON.parse(JSON.stringify(view));
    }
    return invoke(cmd, args);
  };
}

async function settings(view, data = {}) {
  const page = await K.open(browser, base, "settings.html", data, { width: 820, height: 1800 });
  await page.addInitScript(reachBridge, view);
  await page.reload();
  await page.waitForTimeout(700);
  return page;
}

await check("Settings: every row in the PC's words and order, and the tools offered", async () => {
  const page = await settings(C.everything_on);
  const text = await page.locator("#reach").innerText();
  const ids = await page.locator("#reach-rows li").evaluateAll((els) => els.map((e) => e.dataset.reach));
  const tools = await page.locator("#reach-tools li").allInnerTexts();
  const errors = page.__errors;
  await page.close();
  assert.deepEqual(ids, CASES.ids);
  for (const r of C.everything_on.rows) {
    assert.ok(text.includes(`${r.name} - ${r.state_words}`), r.id);
    assert.ok(text.includes(r.line), `${r.id}'s line`);
    if (r.on && r.where) assert.ok(text.includes(`Goes to: ${r.where}`), `${r.id}'s host`);
  }
  assert.deepEqual(tools, C.everything_on.tools.map((t) => t.name));
  assert.ok(text.includes(EVERYTHING_ELSE));
  assert.deepEqual(errors, []);
});

await check("Settings: nothing set up says so, and no tool is offered", async () => {
  const page = await settings(C.nothing_set_up);
  const none = await page.locator("#reach-tools-none").innerText();
  const listHidden = await page.locator("#reach-tools").isHidden();
  await page.close();
  assert.equal(none, TOOLS_NONE);
  assert.equal(listHidden, true);
});

await check("Settings: a PC without it says what to do", async () => {
  const page = await settings({ available: false, why: MISSING });
  const state = await page.locator("#reach-state").innerText();
  const hidden = await page.locator("#reach-body").isHidden();
  await page.close();
  assert.equal(state, MISSING);
  assert.equal(hidden, true);
});

await check("Settings: a read only - get_reach alone, and a stale link hides nothing", async () => {
  const page = await settings(C.everyday, { link: { stale: true } });
  const calls = await page.evaluate(() => window.__reachCalls);
  const shown = await page.locator("#reach-rows li").count();
  const refresh = await page.locator("#reach-refresh").isDisabled();
  await page.close();
  assert.ok(calls.length >= 1 && calls.every((c) => c === "get_reach"));
  assert.equal(shown, CASES.ids.length);
  assert.equal(refresh, false);
});

await browser.close();
close();

/* ── CONTROL ───────────────────────────────────────────────────────────── */

await check("CONTROL: get_reach sits with the Settings window only, and is a read", async () => {
  const toml = read("src-tauri/permissions/surfaces.toml");
  const sets = toml.split("[[set]]");
  const settingsSet = sets.find((s) => s.includes('identifier = "settings-surface"'));
  assert.ok(settingsSet.includes('"allow-get-reach"'));
  assert.equal(sets.filter((s) => s.includes('"allow-get-reach"')).length, 1);
  assert.ok(read("src-tauri/build.rs").includes('"get_reach"'));
  const rs = read("src-tauri/src/reach.rs");
  assert.match(rs, /\.get\(format!\("\{base\}\{REACH_PATH\}"\)\)/);
  assert.doesNotMatch(rs, /\.post\(/);
});

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join(", ")}`);
  process.exit(1);
}
console.log("\nWhat Jarvis can reach: the PC's words, every row, a read only");
