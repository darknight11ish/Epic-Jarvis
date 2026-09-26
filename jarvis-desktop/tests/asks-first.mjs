/**
 * "What asks first" on the desktop (the owner's decisions of 2026-09-26,
 * after the approvals audit; JARVIS-API.md section 32; src/asks-first.js,
 * src/asks-first-settings.js, src-tauri/src/asks_first.rs).
 *
 * What must hold:
 * - the words are the PC's own, word for word (tests/fixtures/
 *   asks-first-cases.json, made by the real jarvis_asks_first.py), and the
 *   phone's net/AsksFirst.kt says the same;
 * - Settings shows every group and row the PC sends, in its order;
 * - "Ask me first" is offered on the short safe list only; checking it
 *   (stricter) is sent at once, even on a stale link; unchecking it (looser)
 *   is sent only from the PC, on a live link, when no other loosening card
 *   waits - and while its card waits the switch stays on and says so;
 * - "Lights, plugs and fans without a card": ON is held on a stale link,
 *   OFF never is;
 * - CONTROL: the three commands sit with the Settings window only, Rust
 *   refuses an action off the list, and nothing in the app approves a card.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  DETAIL,
  LIGHTS_DETAIL,
  LIGHTS_LABEL,
  LIGHTS_WAITING,
  lightsView,
  MISSING,
  NOT_HERE,
  PHONE_LOOSEN,
  readAsksFirst,
  rowLine,
  SWITCH_LABEL,
  SWITCHABLE,
  switchView,
  TITLE,
  WAITING,
} from "../src/asks-first.js";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const CASES = JSON.parse(read("tests/fixtures/asks-first-cases.json"));
const C = CASES.cases;
const Wd = CASES.words;

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* ── The words ────────────────────────────────────────────────────────── */

await check("the words are the PC's own, and the phone says the same", async () => {
  assert.equal(TITLE, Wd.title);
  assert.equal(DETAIL, Wd.detail);
  assert.equal(MISSING, Wd.missing);
  assert.equal(SWITCH_LABEL, Wd.switch_label);
  assert.equal(WAITING, Wd.waiting);
  assert.equal(PHONE_LOOSEN, Wd.phone_loosen);
  assert.equal(LIGHTS_LABEL, Wd.lights_label);
  assert.equal(LIGHTS_DETAIL, Wd.lights_detail);
  assert.equal(LIGHTS_WAITING, Wd.lights_waiting);
  assert.deepEqual([...SWITCHABLE], CASES.switchable);
  const html = read("src/settings.html");
  assert.ok(html.includes(`<h2>${TITLE}</h2>`), "the heading");
  assert.ok(html.includes(DETAIL), "the note under the heading");
  const kt = read("../jarvis-client/app/src/main/java/com/jarvis/client/net/AsksFirst.kt")
    .replace(/"\s*\+\s*\n\s*"/g, "");
  for (const w of [TITLE, DETAIL, MISSING, SWITCH_LABEL, WAITING, PHONE_LOOSEN, LIGHTS_LABEL,
    LIGHTS_DETAIL, LIGHTS_WAITING]) {
    assert.ok(kt.includes(JSON.stringify(w).slice(1, -1)), `the phone says: ${w.slice(0, 50)}`);
  }
});

await check("readAsksFirst reads every real answer, and an older PC says so", async () => {
  for (const [name, raw] of Object.entries(C)) {
    const v = readAsksFirst(raw);
    assert.equal(v.available, true, name);
    assert.deepEqual(v.groups.map((g) => g.title), raw.groups.map((g) => g.title), name);
    assert.deepEqual(v.groups.flatMap((g) => g.rows.map((r) => r.id)),
      raw.groups.flatMap((g) => g.rows.map((r) => r.id)), name);
    const withSwitch = v.groups.flatMap((g) => g.rows).filter((r) => r.switch).map((r) => r.action);
    assert.ok(withSwitch.every((a) => SWITCHABLE.includes(a)), `${name}: switches only on the list`);
  }
  assert.equal(readAsksFirst({ available: false, why: "x" }).why, "x");
  assert.equal(readAsksFirst(null).why, MISSING);
  const forged = readAsksFirst({ groups: [{ title: "t", rows: [
    { id: "send_email", action: "send_email", title: "Send", says: "x", switch: { asks: true } }] }] });
  assert.equal(forged.groups[0].rows[0].switch, null, "a switch on an action off the list is dropped");
});

await check("the switch: stricter always, looser only from the PC, live, one card at a time", async () => {
  const pc = readAsksFirst(C.pc_shipped);
  const cal = pc.groups[0].rows.find((r) => r.action === "calendar_read");
  const sw = switchView(cal, pc, true);
  assert.deepEqual(sw, { checked: false, disabled: false, lines: [], loosens: false },
    "shipped: goes ahead without asking; checking it makes it stricter");
  assert.equal(switchView(cal, pc, false).disabled, false, "stricter is never held on a stale link");
  const strict = readAsksFirst(C.pc_stricter_lights_on);
  const cal2 = strict.groups[0].rows.find((r) => r.action === "calendar_read");
  assert.equal(switchView(cal2, strict, true).disabled, false, "on the PC, a live link: may loosen");
  assert.equal(switchView(cal2, strict, false).disabled, true, "a stale link: loosening is held");
  const phone = readAsksFirst(C.phone_cards_waiting);
  const cal3 = phone.groups[0].rows.find((r) => r.action === "calendar_read");
  const w = switchView(cal3, phone, true);
  assert.equal(w.checked, true, "its card waits: still asks");
  assert.equal(w.disabled, true);
  assert.deepEqual(w.lines, [WAITING]);
  const joplin = phone.groups[1].rows.find((r) => r.action === "create_joplin_note");
  assert.equal(switchView(joplin, phone, true).disabled, true, "not from the PC: cannot loosen");
  assert.ok(switchView(joplin, phone, true).lines.includes(NOT_HERE));
  const send = pc.groups.flatMap((g) => g.rows).find((r) => r.id === "send_email");
  assert.equal(switchView(send, pc, true), null, "sending email has no switch");
  assert.ok(rowLine(send).startsWith("Send an email - "));
});

await check("the lights switch: ON held on a stale link, OFF never, waiting said", async () => {
  const off = readAsksFirst(C.pc_shipped).lights;
  assert.deepEqual(lightsView(off, true), { show: true, checked: false, canChange: true, lines: [] });
  assert.equal(lightsView(off, false).canChange, false, "ON is held");
  const on = readAsksFirst(C.pc_stricter_lights_on).lights;
  assert.equal(lightsView(on, false).canChange, true, "OFF is never held");
  const waiting = readAsksFirst(C.phone_cards_waiting).lights;
  assert.deepEqual(lightsView(waiting, true).lines, [LIGHTS_WAITING]);
  assert.equal(lightsView(waiting, true).checked, true);
});

/* ── Settings ─────────────────────────────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();

function asksBridge(view) {
  const core = window.__TAURI__.core;
  const invoke = core.invoke;
  window.__asksCalls = [];
  window.__asksView = JSON.parse(JSON.stringify(view));
  core.invoke = async (cmd, args) => {
    if (cmd === "get_asks_first") {
      window.__asksCalls.push({ cmd });
      return JSON.parse(JSON.stringify(window.__asksView));
    }
    if (cmd === "set_asks_first" || cmd === "set_lights_without_card") {
      window.__asksCalls.push({ cmd, ...args });
      return { ok: true, message: "Done." };
    }
    return invoke(cmd, args);
  };
}

async function settings(view, data = {}) {
  const page = await K.open(browser, base, "settings.html", data, { width: 820, height: 2400 });
  await page.addInitScript(asksBridge, view);
  await page.reload();
  await page.waitForTimeout(700);
  return page;
}

await check("Settings: every group and row in the PC's words and order", async () => {
  const page = await settings(C.pc_shipped);
  const text = await page.locator("#asks-first").innerText();
  const ids = await page.locator("#af-groups li").evaluateAll((els) => els.map((e) => e.dataset.asks));
  const boxes = await page.locator("#af-groups input[type=checkbox]").evaluateAll(
    (els) => els.map((e) => e.id));
  const errors = page.__errors;
  await page.close();
  assert.deepEqual(ids, C.pc_shipped.groups.flatMap((g) => g.rows.map((r) => r.id)));
  for (const g of C.pc_shipped.groups) {
    assert.ok(text.includes(g.title), g.title);
    for (const r of g.rows) assert.ok(text.includes(`${r.title} - ${r.says}`), r.id);
  }
  assert.deepEqual(boxes.sort(), [...CASES.switchable.map((a) => `af-${a}`), "af-lights"].sort());
  assert.ok(text.includes(LIGHTS_LABEL));
  assert.deepEqual(errors, []);
});

await check("Settings: stricter is sent at once, even on a stale link", async () => {
  const page = await settings(C.pc_shipped, { link: { stale: true } });
  await page.locator("#af-calendar_read").click();
  await page.waitForTimeout(300);
  const calls = await page.evaluate(() => window.__asksCalls.filter((c) => c.cmd !== "get_asks_first"));
  await page.close();
  assert.deepEqual(calls, [{ cmd: "set_asks_first", action: "calendar_read", ask: true }]);
});

await check("Settings: looser from the PC on a live link is ONE request, and nothing is approved here", async () => {
  const page = await settings(C.pc_stricter_lights_on);
  await page.locator("#af-calendar_read").click();
  await page.waitForTimeout(300);
  const calls = await page.evaluate(() => window.__asksCalls.filter((c) => c.cmd !== "get_asks_first"));
  await page.close();
  assert.deepEqual(calls, [{ cmd: "set_asks_first", action: "calendar_read", ask: false }]);
});

await check("Settings: looser is greyed on a stale link, and while a card waits", async () => {
  let page = await settings(C.pc_stricter_lights_on, { link: { stale: true } });
  let off = await page.locator("#af-calendar_read").isDisabled();
  await page.close();
  assert.equal(off, true);
  page = await settings(C.phone_cards_waiting);
  off = await page.locator("#af-calendar_read").isDisabled();
  const checked = await page.locator("#af-calendar_read").isChecked();
  const text = await page.locator("#asks-first").innerText();
  await page.close();
  assert.equal(off, true);
  assert.equal(checked, true);
  assert.ok(text.includes(WAITING));
  assert.ok(text.includes(LIGHTS_WAITING));
});

await check("Settings: the lights setting - ON held on a stale link, OFF goes", async () => {
  let page = await settings(C.pc_shipped, { link: { stale: true } });
  const held = await page.locator("#af-lights").isDisabled();
  await page.close();
  assert.equal(held, true);
  page = await settings(C.pc_stricter_lights_on, { link: { stale: true } });
  await page.locator("#af-lights").click();
  await page.waitForTimeout(300);
  const calls = await page.evaluate(() => window.__asksCalls.filter((c) => c.cmd !== "get_asks_first"));
  await page.close();
  assert.deepEqual(calls, [{ cmd: "set_lights_without_card", enabled: false }]);
});

await check("Settings: a PC without it says what to do", async () => {
  const page = await settings({ available: false, why: MISSING });
  const state = await page.locator("#af-state").innerText();
  const hidden = await page.locator("#af-body").isHidden();
  await page.close();
  assert.equal(state, MISSING);
  assert.equal(hidden, true);
});

await browser.close();
close();

/* ── CONTROL ───────────────────────────────────────────────────────────── */

await check("CONTROL: Settings only; Rust refuses an action off the list; no approving here", async () => {
  const toml = read("src-tauri/permissions/surfaces.toml");
  const sets = toml.split("[[set]]");
  const settingsSet = sets.find((s) => s.includes('identifier = "settings-surface"'));
  for (const p of ["allow-get-asks-first", "allow-set-asks-first", "allow-set-lights-without-card"]) {
    assert.ok(settingsSet.includes(`"${p}"`), p);
    assert.equal(sets.filter((s) => s.includes(`"${p}"`)).length, 1, `${p} in one set only`);
  }
  const build = read("src-tauri/build.rs");
  for (const c of ["get_asks_first", "set_asks_first", "set_lights_without_card"]) {
    assert.ok(build.includes(`"${c}"`), c);
  }
  const rs = read("src-tauri/src/asks_first.rs");
  assert.match(rs, /if !SWITCHABLE\.contains\(&action\)/);
  assert.match(rs, /held_on_stale\(!ask\) && stale\(&app\)/);
  assert.doesNotMatch(rs, /api\/approve/);
  const js = read("src/asks-first-settings.js");
  assert.doesNotMatch(js, /decide_approval|approve/i);
});

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join(", ")}`);
  process.exit(1);
}
console.log("\nWhat asks first: the PC's words, stricter at once, looser on the PC only");
