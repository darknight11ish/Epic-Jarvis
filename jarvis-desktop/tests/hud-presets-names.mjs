/**
 * The seven screen layouts say their plain-words names (2026-11-09, Gemini's
 * UI review §1.2 / rulings Q2-Q3; the owner's ruling: ONE Presets menu,
 * display names only, internal ids unchanged).
 *
 *   node tests/hud-presets-names.mjs
 *
 * WHAT IS PROVEN:
 *
 *   - the seven internal ids are unchanged and are exactly the layout
 *     contract's seven (`contract/hud-presets.json`), each once - so a saved
 *     document, `hud_layout.rs` and every existing test still see the ids they
 *     know;
 *   - the seven plain-words names are the ones the review asks for, once each,
 *     and none is its own internal label (so "Cockpit" can never be drawn next
 *     to "Just Talk" as if they were two layouts);
 *   - the one-line subtitles are short and say what the layout is for;
 *   - `layoutDisplayName()` answers for a built-in, for the owner's saved copy
 *     (its own name), and for an unknown id (never blank, never "undefined");
 *   - the menu is still exactly ONE Presets menu (`#hud-presets-menu`), still
 *     called Presets, and it draws the built-in rows with those names through
 *     that one helper - no second picker, no second way to switch a lane, and
 *     the retired `data-hud-layout` pill key never comes back;
 *   - §2.1's one-popover-at-a-time helper exists and this module registers its
 *     three popovers with it;
 *   - the REAL page draws the seven plain names (real headless Chromium, the
 *     page's API stubbed), and none of the internal labels is on screen;
 *   - the three served copies of hud-presets.js stay byte-identical.
 *
 * The browser half needs Playwright (the clone has it); the rest needs Node.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { launch, serve } from "./uikit.mjs";
import * as P from "../src/hud-presets.js";
import * as L from "../src/hud-layout.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const DESK = join(HERE, "..");
const SRC = join(DESK, "src");
const ROOT = join(DESK, "..");
const read = (file) => readFileSync(file);
const text = (file) => readFileSync(file, "utf8");

const js = text(join(SRC, "hud-presets.js"));
const CONTRACT = JSON.parse(text(join(ROOT, "contract", "hud-presets.json")));

let passed = 0;
let failed = 0;
async function check(name, fn) {
  try {
    await fn();
    passed += 1;
    console.log(`ok   ${name}`);
  } catch (error) {
    failed += 1;
    console.log(`FAIL ${name}\n     ${error && error.message ? error.message : error}`);
  }
}

/** The review's table, §1.2. The ids are the contract's; only the words are new. */
const NAMES = {
  cockpit: "Just Talk",
  second_brain: "Command Center",
  quiet: "Quiet Desk",
  telemetry: "System Monitor",
  studio: "Custom Grid",
  ambient: "Face Only",
  minimal: "Mini View",
};

/** The labels the ids used to be drawn as, and must never be drawn as again in
 *  the picker. */
const OLD_LABELS = ["Cockpit", "Second Brain & Planner", "Quiet", "Telemetry & Ops",
  "Studio", "Ambient", "Minimal"];

await check("the seven internal ids are unchanged and are the contract's own seven", () => {
  const ids = P.LAYOUT_CHOICES.map((row) => row.id);
  assert.equal(ids.length, 7, `the table lists ${ids.length} layouts, not seven`);
  assert.equal(new Set(ids).size, 7, `an id is listed twice: ${JSON.stringify(ids)}`);
  assert.deepEqual(ids.slice().sort(), CONTRACT.presets.map((p) => p.id).slice().sort(),
    `the table's ids are not the layout contract's: ${JSON.stringify(ids)}`);
  assert.deepEqual(ids.slice().sort(), L.PRESETS.map((p) => p.id).slice().sort(),
    "the table's ids are not hud-layout.js's built-in presets");
  // Every built-in the picker can draw has words, and every row is a built-in.
  for (const preset of L.PRESETS) {
    assert.ok(NAMES[preset.id], `the picker has no plain name for ${preset.id}`);
  }
});

await check("the seven plain-words names are the review's, once each, and none is the old label", () => {
  const rows = P.LAYOUT_CHOICES;
  assert.deepEqual(rows.map((row) => row.name),
    ["Just Talk", "Command Center", "Quiet Desk", "System Monitor", "Custom Grid",
      "Face Only", "Mini View"],
    "the display names are not the review's §1.2 table");
  assert.equal(new Set(rows.map((row) => row.name)).size, 7,
    "two layouts share one display name");
  for (const row of rows) {
    assert.equal(row.name, NAMES[row.id], `${row.id} is named "${row.name}"`);
    assert.notEqual(row.name, L.presetInfo(row.id).label,
      `${row.id} still reads its internal label "${row.name}"`);
    assert.ok(!OLD_LABELS.includes(row.name),
      `${row.id} is drawn as the old label "${row.name}"`);
    assert.ok(row.name.length <= 24, `${row.id}'s display name is too long for a row`);
  }
});

await check("each subtitle is one short line saying what the layout is for", () => {
  for (const row of P.LAYOUT_CHOICES) {
    assert.match(row.subtitle, /\.$/, `${row.id}'s subtitle is not a sentence`);
    const words = row.subtitle.trim().split(/\s+/).length;
    assert.ok(words >= 5 && words <= 9,
      `${row.id}'s subtitle is ${words} words, not the review's 5-9`);
    assert.equal(P.layoutSubtitle(row.id), row.subtitle);
  }
  assert.equal(P.layoutSubtitle("not-a-layout"), "",
    "an unknown id grew an invented subtitle");
});

await check("layoutDisplayName answers a built-in, a saved copy and an unknown id", () => {
  assert.equal(P.layoutDisplayName("cockpit"), "Just Talk");
  assert.equal(P.layoutDisplayName("second_brain"), "Command Center");
  assert.equal(P.layoutDisplayName(L.normalizeLayout(L.presetLayout("studio"))), "Custom Grid",
    "a saved built-in document is not drawn with its plain name");
  // The owner's own saved copy keeps the name they gave it - the only one it has.
  const mine = L.normalizeLayout({
    ...L.presetLayout("cockpit"),
    id: "custom-cockpit-1",
    name: "My layout",
    user_presets: [{ id: "custom-cockpit-1", name: "My layout", base_preset: "cockpit" }],
  });
  assert.equal(P.layoutDisplayName(mine), "My layout");
  assert.equal(P.layoutDisplayName({ id: "custom-quiet-2", name: "Evening" }), "Evening",
    "a saved copy outside this document's library lost its own name");
  // Nothing is ever blank or "undefined"; the id is the honest last answer.
  assert.equal(P.layoutDisplayName("not-a-layout"), "not-a-layout");
  assert.equal(P.layoutDisplayName(null), "Just Talk",
    "no layout at all should fall back to the shipped default's name");
});

await check("there is still exactly ONE Presets menu, and it draws the plain names", () => {
  assert.equal((js.match(/menu\.id = MENU_ID/g) || []).length, 1,
    "hud-presets.js no longer creates exactly one menu");
  assert.ok(!js.includes("hud-layout-menu"),
    "a second layout picker menu was added - the owner asked for one menu");
  assert.ok(!js.includes("data-hud-layout"),
    "the retired data-hud-layout pill key came back");
  assert.ok(js.includes('menu.setAttribute("aria-label", "Presets")'),
    "the one menu is no longer called Presets");
  assert.ok(js.includes('el(doc, "p", "hud-presets-title", "Presets")'),
    "the one menu's title is no longer Presets");
  // The built-in rows ask the ONE helper, and the internal id rides along as a
  // data attribute only (never as the visible label).
  assert.match(js, /const name = layoutDisplayName\(preset\.id\);/,
    "the built-in rows do not ask layoutDisplayName");
  assert.match(js, /const hint = layoutSubtitle\(preset\.id\)/,
    "the built-in rows do not carry their subtitle");
  assert.match(js, /row\.dataset\.layoutId = preset\.id;/,
    "the built-in row lost its internal id");
  // The one write path is unchanged: a click still commits the SAME saved
  // document through the SAME commit (one layout write, no new mechanism).
  assert.match(js, /presetLayout\(preset\.id\)[\s\S]{0,120}user_presets: userLayouts\(layout\)/,
    "a built-in click no longer builds the one saved document");
  assert.ok(js.includes("`Layout: ${name}.`); },"),
    "a built-in click no longer saves through the one commit");
});

await check("one popover at a time is one helper, and this module registers its three", () => {
  assert.equal(typeof P.closeHudPopovers, "function",
    "the §2.1 popover-closing helper is not exported");
  assert.deepEqual(P.closeHudPopovers(), [],
    "with no page open the helper must close nothing and never throw");
  assert.equal((js.match(/function registerPopover\(/g) || []).length, 1,
    "the popover registry has no single definition");
  assert.match(js, /registerPopover\(MENU_ID,/, "the Presets menu is not registered");
  assert.match(js, /registerPopover\(PANEL_ID,/, "the Current Models panel is not registered");
  assert.match(js, /registerPopover\(FACE_PANEL_ID,/, "the Faces panel is not registered");
  assert.equal((js.match(/closeHudPopovers\(/g) || []).length, 4,
    "expected one definition and the three open paths that call it");
});

/* ── the real page ─────────────────────────────────────────────────────────── */

/**
 * The cockpit layout is REALLY two columns since Wave 16 (Gemini ruling Q1):
 * the left rail is an off-canvas drawer, opened by the page's own
 * [☰ Controls] button. This page's default layout is cockpit, so a click on
 * #rail-presets lands on an element that is off the glass and Playwright
 * refuses it with "element is outside of the viewport". Open the drawer first,
 * exactly as a person reaches the rail - the same two-line `neededDrawer` shape
 * tests/hud.mjs uses for its drawer shells.
 */
async function openRail(page) {
  const opened = await page.evaluate(() => {
    const rail = document.getElementById("rail-left");
    if (!rail) return false;
    const r = rail.getBoundingClientRect();
    if (r.width > 1 && r.left >= -1) return false;   // a layout that keeps it on screen
    const toggle = document.getElementById("left-toggle");
    if (!toggle) return false;
    toggle.click();
    return true;
  });
  if (opened) await page.waitForTimeout(350);
  return opened;
}

await check("the real page draws the seven plain names, not the internal labels", async () => {
  const browser = await launch();
  const site = await serve();
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 820 } });
    const problems = [];
    page.on("pageerror", (error) => problems.push(String(error)));
    // The page's own API, stubbed: this test is about the menu's WORDS, and a
    // PC with no presets route must still draw its built-in layouts.
    await page.route("**/api/**", (route) => route.fulfill({
      status: 200,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ok: true, available: false, presets: [], personalities: [],
        pending: [], history: [] }),
    }));
    await page.goto(`${site.base}/jarvis_hud.html`);
    await page.waitForSelector("#hud-layout-badge", { timeout: 15000 });
    // The plain browser's own layout store answers AFTER the first paint (the
    // page's preview mirror paints three-column until then), so let the
    // cockpit document land before asking whether the rail is a drawer.
    await page.waitForFunction(() => Boolean(window.__jarvisHudLayout),
      null, { timeout: 5000 }).catch(() => {});
    await page.waitForTimeout(300);
    await openRail(page);
    await page.click("#rail-presets");
    await page.waitForSelector("#hud-presets-menu:not([hidden])", { timeout: 5000 });
    const drawn = await page.evaluate(() => [...document.querySelectorAll(
      "#hud-presets-menu [data-layout-id]")].map((button) => ({
      id: button.dataset.layoutId,
      // The row's own state word is appended to its visible label.
      text: button.textContent.trim().replace(/\s*\(current\)$/, ""),
      hint: button.title,
      label: button.getAttribute("aria-label") || "",
    })));
    assert.equal(drawn.length, 7, `the page drew ${drawn.length} layouts, not seven`);
    assert.deepEqual(drawn.map((row) => row.id).slice().sort(),
      CONTRACT.presets.map((p) => p.id).slice().sort(),
      `the page drew ids the contract does not have: ${JSON.stringify(drawn.map((r) => r.id))}`);
    assert.deepEqual(drawn.map((row) => row.text).slice().sort(),
      Object.values(NAMES).slice().sort(),
      `the page did not draw the plain names: ${JSON.stringify(drawn.map((r) => r.text))}`);
    for (const row of drawn) {
      assert.ok(!OLD_LABELS.includes(row.text),
        `the page still draws the internal label "${row.text}"`);
      assert.equal(row.hint, P.layoutSubtitle(row.id),
        `${row.id}'s subtitle is not the row's hint`);
      assert.ok(row.label.includes(NAMES[row.id]),
        `${row.id}'s accessible name does not say its plain name: ${row.label}`);
    }
    assert.deepEqual(problems, [], `the page raised: ${JSON.stringify(problems)}`);
  } finally {
    await browser.close();
    await site.close();
  }
});

await check("the three served copies stay byte-identical", () => {
  const files = [
    join(SRC, "hud-presets.js"),
    join(ROOT, "jarvis-backend", "hud-presets.js"),
    join(ROOT, "backend", "static", "hud-presets.js"),
  ];
  const first = read(files[0]);
  for (const file of files.slice(1)) {
    assert.ok(first.equals(read(file)), `${files[0]} and ${file} differ`);
  }
});

console.log(`\n${passed} passed, 0 skipped, ${failed} failed`);
if (failed) process.exitCode = 1;
