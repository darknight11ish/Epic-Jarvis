/**
 * The Simple layout (the owner, 2026-11-10): "also add a simple layout and have
 * it at the top of layout presets for jarvis hud on the desktop. have this be
 * simple with just the essential tools and not too much customization or
 * options".
 *
 *   node tests/hud-simple-layout.mjs
 *
 * WHAT IS PROVEN, without needing the desktop shell:
 *
 *   1. Simple is the FIRST built-in row - first in `LAYOUT_CHOICES`, first in
 *      `PRESETS`, first in `contract/hud-presets.json`, and first on the real
 *      page's Built-in layouts list;
 *   2. it is the ESSENTIALS ONLY: the four protected cards (Stop everything,
 *      the Atlas bar, approvals, voice controls) plus the conversation and
 *      its ask box. Every rail card, the Galaxy/Memory/Reminders stage tabs and
 *      the Focus presets list are named and OFF, so the first Edit HUD visit
 *      cannot put them back;
 *   3. it is NOT a silent new default: `DEFAULT_PRESET_ID` stays `cockpit`, so
 *      an old, unknown or unreadable document still means the everyday layout
 *      (nobody who already picked a layout is moved);
 *   4. the real page applies it: the `simple` preset id is on `<html>`, the
 *      one-column shell and the comfortable density are on `<body>`, both side
 *      rails are off the glass, the essential controls are visible, and the
 *      Presets menu marks Simple as `(current)` - no page errors;
 *   5. SELECTING it changes what it claims, not just an injected document: a
 *      page that boots on Cockpit, with nothing saved, is switched by clicking
 *      Simple (the FIRST row of the ONE Presets menu); the click saves the
 *      Simple document through the page's own store, and the next boot is
 *      Simple - one column, no side panels, the six essentials.
 *
 * The browser half needs Playwright (the clone has it); the rest needs Node.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { launch, serve } from "./uikit.mjs";
import * as L from "../src/hud-layout.js";
import * as P from "../src/hud-presets.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const DESK = join(HERE, "..");
const ROOT = join(DESK, "..");
const text = (file) => readFileSync(file, "utf8");

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

const CONTRACT = JSON.parse(text(join(ROOT, "contract", "hud-presets.json")));

/* ── 1. The row the owner sees is the first one ──────────────────────────── */

await check("Simple is the first built-in row, in every list that draws one", () => {
  assert.equal(L.PRESETS[0].id, "simple");
  assert.equal(P.LAYOUT_CHOICES[0].id, "simple");
  assert.equal(CONTRACT.presets[0].id, "simple");
  assert.equal(P.layoutDisplayName("simple"), "Simple");
  assert.equal(P.layoutChoice("simple").name, "Simple",
    "the row's plain name is not the owner's word");
  // The seven existing rows keep their own order after it; none was renamed.
  assert.deepEqual(L.PRESETS.slice(1).map((preset) => preset.id),
    ["cockpit", "studio", "ambient", "quiet", "telemetry", "second_brain", "minimal"]);
});

/* ── 2. Essentials only ───────────────────────────────────────────────────── */

const ESSENTIALS = ["emergency_stop", "bar_launcher", "approvals", "voice_controls",
  "conversation", "composer"];
const HEAVY = ["nav", "lanes", "systems", "galaxy", "reminders", "memory",
  "calendar", "waiting", "telemetry", "tools", "brain_stats", "budget", "voice_stats"];

await check("Simple draws exactly the essential cards", () => {
  const doc = L.presetLayout("simple");
  const onGlass = doc.cards.filter((card) => card.visible).map((card) => card.id);
  assert.deepEqual(onGlass, ESSENTIALS,
    `Simple draws ${JSON.stringify(onGlass)}`);
  assert.equal(doc.shell_template, "single-stage-bento");
  assert.equal(doc.density, "comfortable");
  assert.equal(doc.default_stage_tab, "talk");
});

await check("every heavy surface is named and off, so Edit HUD cannot bring it back", () => {
  const doc = L.presetLayout("simple");
  for (const id of HEAVY) {
    const card = doc.cards.find((entry) => entry.id === id);
    assert.ok(card, `Simple does not NAME ${id}, so hud-edit.js would re-add it visible`);
    assert.equal(card.visible, false, `Simple still shows ${id}`);
  }
  // All registry cards are present in the document: a missing one is re-added
  // VISIBLE by hud-edit.js's withRegistryCards, which would quietly undo the
  // whole point of the simple layout.
  assert.deepEqual([...doc.cards.map((card) => card.id)].sort(),
    L.CARD_REGISTRY.map((card) => card.id).sort(),
    "Simple does not name every registry card");
  // And the composition is a fixed point: saving then reading it back keeps it.
  assert.deepEqual(L.normalizeLayout(doc), doc);
  assert.deepEqual(L.presetLayout("simple"), doc);
});

await check("Simple is a normal one-column chat, not a corner mode", () => {
  const doc = L.presetLayout("simple");
  assert.deepEqual([...L.rightColumn(doc).cards], [],
    "Simple still has a right-rail card");
  assert.deepEqual([...L.visibleCards(doc, "left_rail")], ["bar_launcher"],
    "Simple's left rail carries more than the protected Jarvis bar");
  assert.equal(L.returnPillFor(doc), null,
    "Simple is not Face Only / Mini View and must not claim their return pill");
});

/* ── 3. It does not become the silent default ────────────────────────────── */

await check("Cockpit is still the default, and an old/unknown document still means it", () => {
  assert.equal(L.DEFAULT_PRESET_ID, "cockpit");
  assert.equal(L.presetLayout("not-a-layout").base_preset, "cockpit");
  for (const bad of [undefined, null, "", "nonsense", 7, {}]) {
    assert.equal(L.migrateLegacyLayout(bad).base_preset, "cockpit",
      `an unknown legacy value now becomes ${L.migrateLegacyLayout(bad).base_preset}`);
  }
  // A saved document that NAMES a layout keeps it, Simple included.
  const saved = L.normalizeLayout({ ...L.presetLayout("simple"), updated_at: 12 });
  assert.equal(saved.base_preset, "simple");
  assert.equal(saved.id, "simple");
});

await check("the three repeated copies of the renderer and page agree", () => {
  for (const name of ["hud-layout.js", "hud-presets.js"]) {
    const first = text(join(DESK, "src", name));
    for (const other of [join(ROOT, "jarvis-backend", name),
      join(ROOT, "backend", "static", name)]) {
      assert.equal(first, text(other), `${name} differs from ${other}`);
    }
  }
  const page = text(join(DESK, "src", "jarvis_hud.html"));
  for (const other of [join(ROOT, "jarvis-backend", "jarvis_hud.html"),
    join(ROOT, "backend", "jarvis_hud.html")]) {
    assert.equal(page, text(other), `jarvis_hud.html differs from ${other}`);
  }
});

/* ── 4. The real page ─────────────────────────────────────────────────────── */

const simpleDoc = L.presetLayout("simple");

/** What the real page is showing: the layout attributes, the essential
 *  controls, both rails, and every heavy surface. Both browser checks use this
 *  one measure, so "the page is in Simple" means the same thing in each. */
async function measure(page) {
  return page.evaluate(() => {
    const box = (id) => {
      const el = document.getElementById(id);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      const s = getComputedStyle(el);
      return { shown: s.display !== "none" && s.visibility !== "hidden"
        && r.width > 1 && r.height > 1, x: Math.round(r.x), w: Math.round(r.width) };
    };
    const hidden = (sel) => {
      const el = document.querySelector(sel);
      if (!el) return true;
      const s = getComputedStyle(el);
      const r = el.getBoundingClientRect();
      // Nothing to see: not rendered, or parked off the glass in a closed
      // drawer (a page-owned panel inside the right rail is exactly that).
      return s.display === "none" || s.visibility === "hidden"
        || r.width < 2 || r.height < 2
        || r.x >= innerWidth - 1 || r.right <= 1;
    };
    return {
      preset: document.documentElement.getAttribute("data-hud-preset"),
      shell: document.body.dataset.hudShell,
      htmlShell: document.documentElement.getAttribute("data-hud-shell"),
      density: document.body.dataset.hudDensity,
      htmlDensity: document.documentElement.getAttribute("data-hud-density"),
      badge: (document.getElementById("hud-layout-badge") || {}).textContent || "",
      input: box("input"), mic: box("mic"), send: box("send"), stop: box("hud-stop"),
      leftRail: box("rail-left"), rightRail: box("rail-right"),
      approvals: Boolean(document.getElementById("approvals")),
      heavyHidden: ["#rail-nav", "#rail-lanes", "#rail-systems", "#rail-telemetry",
        "#rail-memory", "#rail-reminders", "#hud-stage-nav", "#hud-return-pill"]
        .map((sel) => ({ sel, hidden: hidden(sel) })),
    };
  });
}

await check("the real page applies Simple and keeps only its essential controls", async () => {
  const browser = await launch();
  const site = await serve();
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    const problems = [];
    page.on("pageerror", (error) => problems.push(String(error)));
    page.on("console", (message) => {
      if (message.type() !== "error") return;
      const words = message.text();
      if (/favicon|Failed to load resource|EventSource/.test(words)) return;
      problems.push(words);
    });
    // The page's own API, stubbed: this test is about the layout, and a PC with
    // no model must still draw the Simple document.
    await page.route("**/api/**", (route) => route.fulfill({
      status: 200,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ok: true, available: false, jarvis: false, ollama: false,
        presets: [], personalities: [], pending: [], history: [], items: [],
        events: [], nodes: [], links: [], cards: [] }),
    }));
    await page.goto(`${site.base}/jarvis_hud.html`);
    await page.waitForSelector("#hud-layout-badge", { timeout: 20000 });
    // Put the page in the layout the way the shell bootstrap does (the two
    // events the page's own layout script listens for).
    await page.evaluate((detail) => {
      window.__jarvisHudLayout = detail.doc;
      window.dispatchEvent(new CustomEvent("jarvis:hud-layout", { detail: detail.doc }));
      window.dispatchEvent(new CustomEvent("jarvis:hud-shell", { detail: detail.facts }));
    }, {
      doc: simpleDoc,
      facts: {
        shell_template: simpleDoc.shell_template,
        density: simpleDoc.density,
        default_stage_tab: simpleDoc.default_stage_tab,
        base_preset: simpleDoc.base_preset,
        name: simpleDoc.name,
      },
    });
    await page.waitForTimeout(500);

    const state = await measure(page);

    assert.equal(state.preset, "simple", "the page's data-hud-preset is not simple");
    assert.equal(state.shell, "single-stage-bento", "the one-column shell did not apply");
    assert.equal(state.density, "comfortable", "the density did not apply");
    assert.match(state.badge, /Simple/, "the Layout badge does not say Simple");
    for (const key of ["input", "mic", "send", "stop"]) {
      assert.ok(state[key] && state[key].shown,
        `the essential control #${key} is not on the glass: ${JSON.stringify(state[key])}`);
    }
    assert.ok(state.approvals, "the approvals card is not in the document");
    // Both rails are drawers, off the glass - one centred column, no empty column.
    assert.ok(state.leftRail && state.leftRail.x + state.leftRail.w <= 1,
      `the left rail is on the glass: ${JSON.stringify(state.leftRail)}`);
    assert.ok(state.rightRail && state.rightRail.x >= 1439,
      `the right rail is on the glass: ${JSON.stringify(state.rightRail)}`);
    for (const row of state.heavyHidden) {
      assert.equal(row.hidden, true, `${row.sel} is still on the glass in Simple`);
    }

    // The first row the owner sees in the ONE Presets menu is Simple, and when
    // Simple is active it is the one marked current.
    await page.click("#hud-layout-badge");
    await page.waitForSelector("#hud-presets-menu:not([hidden])", { timeout: 5000 });
    const rows = await page.evaluate(() => [...document.querySelectorAll(
      "#hud-presets-menu [data-layout-id]")].map((button) => ({
      id: button.dataset.layoutId,
      text: button.textContent.trim(),
      hint: button.title,
    })));
    assert.equal(rows[0].id, "simple", `the first built-in row is ${rows[0].id}`);
    assert.match(rows[0].text, /^Simple/, `the first row reads "${rows[0].text}"`);
    assert.match(rows[0].text, /\(current\)/,
      `Simple is active but its row does not say so: "${rows[0].text}"`);
    assert.equal(rows.filter((row) => /\(current\)/.test(row.text)).length, 1,
      `more than one row claims to be current: ${JSON.stringify(rows.map((r) => r.text))}`);
    assert.equal(rows[0].hint, P.layoutSubtitle("simple"),
      "the Simple row does not carry its one-line purpose");
    assert.deepEqual(problems, [], `the page raised: ${JSON.stringify(problems)}`);
  } finally {
    await browser.close();
    await site.close();
  }
});

/* ── 5. SELECTING it, not merely describing it ───────────────────────────── */

/** Open a HUD page with the same API stub the check above uses. */
async function openPage(browser, site) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const problems = [];
  page.on("pageerror", (error) => problems.push(String(error)));
  page.on("console", (message) => {
    if (message.type() !== "error") return;
    const words = message.text();
    if (/favicon|Failed to load resource|EventSource/.test(words)) return;
    problems.push(words);
  });
  // This test is about the layout; a PC with no model must still draw it.
  await page.route("**/api/**", (route) => route.fulfill({
    status: 200,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ok: true, available: false, jarvis: false, ollama: false,
      presets: [], personalities: [], pending: [], history: [], items: [],
      events: [], nodes: [], links: [], cards: [] }),
  }));
  await page.goto(`${site.base}/jarvis_hud.html`);
  await page.waitForSelector("#hud-layout-badge", { timeout: 20000 });
  return { page, problems };
}

await check("choosing Simple from the ONE Presets menu really switches the page to it", async () => {
  const browser = await launch();
  const site = await serve();
  try {
    // 1. A browser with nothing saved: the page's own boot path lands on the
    //    everyday layout, Cockpit - so a later Simple is a CHANGE, not a start.
    const { page, problems } = await openPage(browser, site);
    await page.waitForFunction(
      () => document.documentElement.getAttribute("data-hud-preset") === "cockpit",
      null, { timeout: 20000 },
    );
    const before = await measure(page);
    assert.equal(before.preset, "cockpit",
      `a fresh page starts on ${before.preset}, so "selecting Simple" proves nothing`);
    assert.equal(before.shell, "three-column", "the everyday layout did not apply its shell");
    assert.equal(await page.evaluate(() => localStorage.getItem("jarvis.web.hud_layout.v1")),
      null, "a fresh browser page already has a saved layout");

    // 2. The owner picks the FIRST row of the ONE Presets menu.
    await page.click("#hud-layout-badge");
    await page.waitForSelector("#hud-presets-menu:not([hidden])", { timeout: 5000 });
    const first = await page.evaluate(() => {
      const row = document.querySelector("#hud-presets-menu [data-layout-id]");
      return { id: row.dataset.layoutId, text: row.textContent.trim() };
    });
    assert.equal(first.id, "simple", `the first built-in row is ${first.id}`);
    assert.match(first.text, /^Simple/, `the first row reads "${first.text}"`);
    await page.click('#hud-presets-menu [data-layout-id="simple"]');

    // 3. The click SAVED the Simple document - through the page's own store,
    //    not through a hand-made dispatch. This is the layout the picker
    //    promises: one centred column, no side panels, six essential cards.
    await page.waitForFunction(() => {
      try {
        const saved = JSON.parse(localStorage.getItem("jarvis.web.hud_layout.v1") || "null");
        return Boolean(saved && saved.base_preset === "simple");
      } catch { return false; }
    }, null, { timeout: 5000 });
    const saved = await page.evaluate(
      () => JSON.parse(localStorage.getItem("jarvis.web.hud_layout.v1")));
    assert.equal(saved.base_preset, "simple", "the saved layout is not Simple");
    assert.equal(saved.shell_template, "single-stage-bento",
      "Simple saved a different shell, so it would not be one column");
    assert.equal(saved.density, "comfortable", "Simple saved a different density");
    assert.equal(saved.default_stage_tab, "talk", "Simple does not open on the conversation");
    assert.deepEqual(saved.cards.filter((card) => card.visible).map((card) => card.id),
      ESSENTIALS, "the saved Simple layout draws something other than the essentials");

    // 4. And a page that BOOTS from that save is Simple: this is the shell
    //    bootstrap's own path (the browser bridge loads the store and announces
    //    jarvis:hud-layout + jarvis:hud-shell), not a dispatch written here.
    await page.reload();
    await page.waitForSelector("#hud-layout-badge", { timeout: 20000 });
    await page.waitForFunction(
      () => document.documentElement.getAttribute("data-hud-preset") === "simple",
      null, { timeout: 20000 },
    );
    // The two drawers SLIDE (transition .18s). Wait for their destinations
    // instead of guessing a sleep: both rails must be off the glass before
    // anything is measured.
    await page.waitForFunction(() => {
      const off = (id, side) => {
        const el = document.getElementById(id);
        if (!el) return true;
        const s = getComputedStyle(el);
        if (s.display === "none" || s.visibility === "hidden") return true;
        const r = el.getBoundingClientRect();
        return side === "left" ? r.right <= 1 : r.left >= innerWidth - 1;
      };
      return off("rail-left", "left") && off("rail-right", "right");
    }, null, { timeout: 5000 });
    const after = await measure(page);
    assert.equal(after.preset, "simple", "the booted page is not in Simple");
    assert.equal(after.shell, "single-stage-bento", "the one-column shell did not apply");
    assert.equal(after.htmlShell, "single-stage-bento",
      "<html> and <body> disagree about the shell");
    assert.equal(after.density, "comfortable", "the comfortable density did not apply");
    assert.equal(after.htmlDensity, "comfortable",
      "<html> and <body> disagree about the density");
    assert.match(after.badge, /Simple/, `the Layout badge reads "${after.badge}"`);
    for (const key of ["input", "mic", "send", "stop"]) {
      assert.ok(after[key] && after[key].shown,
        `the essential control #${key} is not on the glass: ${JSON.stringify(after[key])}`);
    }
    assert.ok(after.approvals, "the approvals card is not in the document");
    assert.ok(after.leftRail && after.leftRail.x + after.leftRail.w <= 1,
      `the left rail is on the glass: ${JSON.stringify(after.leftRail)}`);
    assert.ok(after.rightRail && after.rightRail.x >= 1439,
      `the right rail is on the glass: ${JSON.stringify(after.rightRail)}`);
    for (const row of after.heavyHidden) {
      assert.equal(row.hidden, true, `${row.sel} is still on the glass in Simple`);
    }
    // The menu the owner comes back to marks Simple as the one current row.
    await page.click("#hud-layout-badge");
    await page.waitForSelector("#hud-presets-menu:not([hidden])", { timeout: 5000 });
    const rows = await page.evaluate(() => [...document.querySelectorAll(
      "#hud-presets-menu [data-layout-id]")].map((button) => ({
      id: button.dataset.layoutId, text: button.textContent.trim(),
    })));
    assert.equal(rows[0].id, "simple", `the first built-in row is ${rows[0].id}`);
    assert.match(rows[0].text, /\(current\)/,
      `Simple is active but its row does not say so: "${rows[0].text}"`);
    assert.equal(rows.filter((row) => /\(current\)/.test(row.text)).length, 1,
      `more than one row claims to be current: ${JSON.stringify(rows.map((r) => r.text))}`);
    assert.deepEqual(problems, [], `the page raised: ${JSON.stringify(problems)}`);
    await page.close();
  } finally {
    await browser.close();
    await site.close();
  }
});

console.log(`\n${passed} passed, 0 skipped, ${failed} failed`);
if (failed) process.exitCode = 1;
