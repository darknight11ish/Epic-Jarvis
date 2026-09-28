/**
 * Brain -> Memory -> "Bring in old chats" (history-import.js,
 * brain/history_import.rs; JARVIS-API.md section 85).
 *
 * Every answer here is REAL: tests/fixtures/history-import-cases.json is
 * jarvis_history_import.view() in named situations, written by
 * tools/gen_history_import_cases.py. Nothing is hand-made.
 *
 * What must hold:
 * - the PC's own sentence is shown, with counts only;
 * - "Bring in chats from ChatGPT, Claude or Gemini" starts one run, and is
 *   greyed on a stale link (rule 4) - Rust refuses too;
 * - while a run is going the page asks the PC where it is, shows Stop, and
 *   Stop is never held (it only does less);
 * - new cards make "Waiting for you" read again - nothing is decided here;
 * - an older backend, a refusal or a failure is a sentence, never JSON.
 *
 * The CONTROL checks read the Rust and the permissions.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { HISTORY_IMPORT, importView, POLL_MS } from "../src/history-import.js";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const CASES = JSON.parse(read("tests/fixtures/history-import-cases.json")).cases;

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const noRaw = (text) => {
  assert.doesNotMatch(text, /[{}]|HTTP \d|"available"|\bnull\b|undefined|\[object|NaN/,
    `raw data on the page: ${text.slice(0, 400)}`);
};

/* ── The card's logic, against the PC's real answers ──────────────────── */

await check("every real view is read as the PC sent it", async () => {
  for (const [name, answer] of Object.entries(CASES)) {
    const v = importView(answer);
    assert.equal(v.available, true, name);
    if (answer.here) assert.equal(v.words, answer.words, name);
    noRaw(v.words);
  }
  assert.equal(importView(CASES.running).running, true);
  assert.equal(importView(CASES.running).canStop, true);
  assert.equal(importView(CASES.running).canStart, false);
  assert.equal(importView(CASES.stopping).canStop, false, "stopping: not twice");
  assert.equal(importView(CASES.done).canStart, true);
  assert.equal(importView(CASES.done).waiting, 37);
  assert.equal(importView(CASES.queue_full).startLabel, HISTORY_IMPORT.again);
  assert.equal(importView(CASES.done).startLabel, HISTORY_IMPORT.start);
  assert.equal(importView(CASES.failed).tone, "warn");
});

await check("from another device: the PC-only sentence, and no Start", async () => {
  const v = importView(CASES.idle_not_here);
  assert.equal(v.words, HISTORY_IMPORT.notHere);
  assert.equal(v.canStart, false);
});

await check("an older PC or an unreadable answer is a sentence", async () => {
  const old = importView({ available: false, why: HISTORY_IMPORT.missing });
  assert.equal(old.words, HISTORY_IMPORT.missing);
  assert.equal(old.canStart, false);
  assert.equal(importView(null).words, HISTORY_IMPORT.unreadable);
  assert.equal(importView({ ok: true }).words, HISTORY_IMPORT.unreadable);
});

/* ── The Brain window, in a browser ───────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();
const SIZE = { width: 1180, height: 1600 };

/**
 * brain.html on its Memory tab (the one it opens on), with history_import_*
 * answering from `script` (the uikit `historyImport` option): `status`
 * answers used in turn (the last repeats), `start` or `startFails`, and
 * `cancel`.
 */
async function brain(script, extra = {}) {
  const page = await K.open(browser, base, "brain.html", { historyImport: script, ...extra },
    SIZE);
  await page.waitForTimeout(300);
  return page;
}

const card = (page) => page.evaluate(() => {
  const $ = (id) => document.getElementById(id);
  return {
    words: $("history-import-words").innerText,
    note: $("history-import-note").innerText,
    how: $("history-import-how").innerText,
    startHidden: $("history-import-start").hidden,
    startDisabled: $("history-import-start").disabled,
    startLabel: $("history-import-start").innerText,
    stopHidden: $("history-import-stop").hidden,
    stopDisabled: $("history-import-stop").disabled,
    calls: [...window.__historyImport.calls],
    pendingReads: window.__calls.filter(([c, a]) => c === "brain_read" && a
      && (a.sections || []).includes("memory_pending")).length,
    all: $("history-import-card").innerText,
  };
});

/** Nothing to do: the Memory tab is what brain.html opens on, and it asks. */
async function reread(page) {
  await page.waitForTimeout(50);
}

await check("idle: the PC's sentence, the note, how to get the file, and Start", async () => {
  const page = await brain({ status: [CASES.idle] });
  await reread(page);
  const c = await card(page);
  assert.equal(c.words, CASES.idle.words);
  assert.equal(c.note, HISTORY_IMPORT.about, "the note is the PC's ABOUT, word for word");
  assert.equal(c.how, HISTORY_IMPORT.how);
  assert.equal(c.startHidden, false);
  assert.equal(c.startDisabled, false);
  assert.equal(c.startLabel, HISTORY_IMPORT.start);
  assert.equal(c.stopHidden, true);
  noRaw(c.all);
  assert.deepEqual(page.__errors, [], "no errors on the page");
  await page.close();
});

await check("Start: one run, then Stop shows, and the page follows it", async () => {
  const page = await brain({
    status: [CASES.idle, CASES.running, CASES.done],
    start: { ...CASES.looking, started_now: true },
  });
  await reread(page);
  await page.click("#history-import-start");
  await page.waitForTimeout(100);
  let c = await card(page);
  assert.equal(c.calls.filter((x) => x === "history_import_start").length, 1);
  assert.equal(c.words, CASES.looking.words);
  assert.equal(c.startHidden, true, "no second Start while one runs");
  assert.equal(c.stopHidden, false);
  await page.waitForTimeout(POLL_MS + 400);
  c = await card(page);
  assert.equal(c.words, CASES.running.words, "asked again while running");
  const before = c.pendingReads;
  await page.waitForTimeout(POLL_MS + 400);
  c = await card(page);
  assert.equal(c.words, CASES.done.words);
  assert.equal(c.stopHidden, true);
  assert.equal(c.startHidden, false);
  assert.ok(c.pendingReads > before, "new cards: Waiting for you read again");
  // Finished: no more asking.
  const n = c.calls.length;
  await page.waitForTimeout(POLL_MS + 300);
  assert.equal((await card(page)).calls.length, n, "no polling once finished");
  await page.close();
});

await check("Stop: sent at once, and says it is stopping", async () => {
  const page = await brain({ status: [CASES.running, CASES.stopping, CASES.cancelled],
                             cancel: { ...CASES.stopping, cancelling: true } });
  await reread(page);
  await page.click("#history-import-stop");
  await page.waitForTimeout(100);
  const c = await card(page);
  assert.ok(c.calls.includes("history_import_cancel"));
  assert.equal(c.words, CASES.stopping.words);
  assert.equal(c.stopDisabled, true, "not twice");
  await page.close();
});

await check("a stale link greys Start; Stop is never held", async () => {
  const page = await brain({ status: [CASES.idle] }, { link: { stale: true } });
  await reread(page);
  let c = await card(page);
  assert.equal(c.startDisabled, true);
  await page.close();
  const running = await brain({ status: [CASES.running], cancel: CASES.stopping },
    { link: { stale: true } });
  await reread(running);
  c = await card(running);
  assert.equal(c.stopHidden, false);
  assert.equal(c.stopDisabled, false, "Stop only does less: never held");
  await running.close();
});

await check("the picker closed without a file: nothing sent, nothing changed", async () => {
  const page = await brain({ status: [CASES.idle], start: { cancelled: true } });
  await reread(page);
  await page.click("#history-import-start");
  await page.waitForTimeout(100);
  const c = await card(page);
  assert.equal(c.words, CASES.idle.words);
  assert.equal(c.startHidden, false);
  await page.close();
});

await check("a refusal is the PC's sentence, as a toast; an old PC says update", async () => {
  const page = await brain({ status: [CASES.idle], startFails:
    "Jarvis is already bringing in chats. Stop it first, or let it finish." });
  await reread(page);
  await page.click("#history-import-start");
  await page.waitForTimeout(150);
  const toast = await page.evaluate(() => document.getElementById("toast").innerText);
  assert.match(toast, /already bringing in chats/);
  await page.close();
  const old = await brain({ status: [{ available: false, why: HISTORY_IMPORT.missing }] });
  await reread(old);
  const c = await card(old);
  assert.equal(c.words, HISTORY_IMPORT.missing);
  assert.equal(c.startHidden, true);
  await old.close();
});

await browser.close();
await close();

/* ── CONTROL: the Rust and the permissions ─────────────────────────────── */

await check("CONTROL: Start is held on a stale link in Rust, before and after the dialog", async () => {
  const rs = read("src-tauri/src/brain/history_import.rs");
  const start = rs.slice(rs.indexOf("pub async fn history_import_start"));
  const body = start.slice(0, start.indexOf("\n}\n"));
  assert.equal((body.match(/require_link_live\(&app\)\?/g) || []).length, 2);
  assert.ok(body.indexOf("require_link_live") < body.indexOf("pick("));
  const cancel = rs.slice(rs.indexOf("pub async fn history_import_cancel"));
  assert.ok(!cancel.slice(0, cancel.indexOf("\n}\n")).includes("require_link_live"),
    "cancel is never held");
  assert.match(rs, /"\/api\/memory\/import_chats\/start"/);
});

await check("CONTROL: only the Brain window has the three commands", async () => {
  const brainCaps = JSON.parse(read("src-tauri/capabilities/brain.json"));
  assert.ok(brainCaps.permissions.includes("brain-history-import"));
  for (const f of ["settings", "hud", "widget", "quickbar", "floating", "faces", "onboarding"]) {
    const caps = read(`src-tauri/capabilities/${f}.json`);
    assert.ok(!caps.includes("brain-history-import"), f);
  }
  const toml = read("src-tauri/permissions/surfaces.toml");
  const set = toml.slice(toml.indexOf('identifier = "brain-history-import"'));
  for (const c of ["status", "start", "cancel"]) {
    assert.ok(set.slice(0, 600).includes(`"allow-history-import-${c}"`), c);
  }
});

await check("CONTROL: the note in brain.html is HISTORY_IMPORT.about, word for word", async () => {
  const html = read("src/brain.html");
  assert.ok(html.includes(HISTORY_IMPORT.about));
  assert.ok(html.includes(HISTORY_IMPORT.start));
});

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join(", ")}`);
  process.exit(1);
}
console.log("\nall passed");
