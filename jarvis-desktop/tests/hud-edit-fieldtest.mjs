/**
 * hud-edit-fieldtest.mjs - the owner's field test of Edit HUD, end to end.
 *
 *     node tests/hud-edit-fieldtest.mjs
 *
 * THE OWNER'S WORDS (2026-10-28): "can you field test the edit hud and change
 * everything then revert back to make sure it all works?"
 *
 * WHAT THIS SUITE DOES, IN THE OWNER'S OWN ORDER. It drives the REAL HUD page
 * in a real Chromium - the page, its external `hud-edit.js`, and the shell's
 * own injected `hud_bootstrap.js`, exactly as `tests/hud.mjs` serves them - and
 * for each of two starting points it:
 *
 *   a. captures the saved layout as the app reads it, from the store BEHIND the
 *      two IPC commands (`get_hud_layout` / `set_hud_layout`, the settings
 *      store `hud-desktop.json` stands for), and checks the page's first paint
 *      is that document;
 *   b. enters Edit HUD through the real `#hud-edit-toggle` button;
 *   c. CHANGES EVERYTHING a user can change on a card: moves every movable
 *      card to a different region (the toolbar's "Move to" select), reorders
 *      every card that can move down (the arrow buttons), resizes every
 *      movable card - so all four of Small / Medium / Wide / Tall are used -
 *      folds every card, and hides every card that may be hidden. It also
 *      probes Undo (Ctrl+Z) once, because a field test of "change then revert"
 *      should not leave the app's own undo out;
 *   d. reloads the page and asserts every one of those changes is still there
 *      - the document the page adopts, the document in the store, and the
 *      rendered DOM (region, size, hidden, folded) - not merely that no error
 *      appeared;
 *   e. REVERTS, using a different real path for each starting point:
 *        A. a fresh install (the saved document is the Cockpit preset): the
 *           edit bar's real "Reset to preset" (`#hud-edit-reset`);
 *        B. the owner's own saved layout (id `custom-cockpit-1`, "Mine"): every
 *           original region, size, fold, visibility and place re-applied
 *           through the SAME controls - the fallback the brief names, and the
 *           only path a custom layout's own arrangement has;
 *    f. reloads again and asserts the layout is back to the document captured
 *       in (a).
 *
 * WHAT "EVERYTHING" MEANS HERE, HONESTLY. The card registry has 16 cards in
 * Cockpit; 12 are movable in H2 (the twelfth is the owner's Calendar, added
 * 2026-10-29) and 2 of those are protected (`approvals`, `bar_launcher`: they
 * may be resized and folded, never moved or hidden). So "everything" is: 10
 * cards moved to another region, 12 cards reordered / resized / folded, 10
 * cards hidden. The main stage, the composer, the Galaxy
 * view and the header stay put by design (`FIXED_IDS` in hud-edit.js) and this
 * suite does not pretend to move them.
 *
 * TWO THINGS COME OUT OF A REVERT, AND THEY ARE NOT THE SAME KIND OF THING.
 *
 * 1. A CHANGE OF NAME THAT IS BY DESIGN. The first edit of a BUILT-IN layout is
 *    deliberately made to the owner's own copy (`doAction` -> `ensureCustomCopy`,
 *    hud-edit.js:566-584; ruling 27): the saved document becomes `custom-cockpit-1`
 *    / "Cockpit (Custom)" and an entry is added to "My layouts". "Reset to
 *    preset" restores every CARD exactly but deliberately keeps that copy's name
 *    and place in the library, so the document is not byte-identical to the
 *    preset it started as. That is asserted as what the app does, with the
 *    reason beside it - it is not a failure, and scenario A passes with it.
 *
 * 2. A CHANGE THAT USED TO BE UNREVERSIBLE, AND NOW IS NOT (fixed 2026-10-28).
 *    This suite was written FOR that defect. Once a card was hidden, nothing on
 *    the page could show it again: the card's own Hide control (painted as a
 *    toggle - aria-pressed, a circle instead of a cross) always sent a fixed
 *    `visible: false` (hud-edit.js:676), while the one toggling path, the `h`
 *    key (hud-edit.js:709), needed focus on a shell that was `display: none`
 *    while hidden (.hud-card[hidden] in jarvis_hud.html). After a reload the
 *    only ways back were Undo / Discard changes (same editing session) or Reset
 *    to preset - and Reset replaces the arrangement of a layout that is not the
 *    base preset. So an owner's own saved layout could not be fully restored.
 *    The fix makes the control a real toggle and, while Edit HUD is on, paints a
 *    hidden card as a dimmed ghost (its header and its own Show control, with its
 *    body folded away) so it can be shown again; outside edit mode it stays
 *    hidden exactly as before. Scenario B's (e2) and (f) checks now pass, and the
 *    (d2) check in EVERY scenario drives both halves on the real page.
 *
 * WHAT THIS DOES *NOT* PROVE. See the note at the end of this file: a headless
 * Chromium is not the packaged Tauri window. The two IPC commands are stubbed
 * (their real Rust side is `hud_layout.rs`), so this proves the page's edit,
 * save and reload logic against the store's contract - not the Rust store, not
 * WebView2, and not a click with a real mouse (see the keyboard note below).
 *
 * RUNNING IT. Playwright is not a dependency of this package (tests/README.md
 * says why): `npm i -D playwright && npx playwright install chromium` first, or
 * copy an existing install into `node_modules`. Screenshots are written to
 * `<repo>/.dsh-scratch/MAXOUT-2026-10-28/hud-edit-fieldtest/` (gitignored), or
 * to `$JARVIS_HUD_FIELD_SHOTS` when that is set; a failed write is reported and
 * does not fail the suite.
 *
 * KEYBOARD, NOT POINTER, FOR THE CARD TOOLBARS. A card resized to Small or
 * Medium inside a 300px rail is narrower than its own toolbar, so the toolbar
 * spills into the neighbouring card and a MOUSE click can land on the other
 * card's button (measured; the `note` line counts them when it happens). The
 * edit buttons are real `<button>`s with a focus ring and the module is built
 * for keyboard use (ruling 27 / WCAG 2.5.7), so this suite activates a card's
 * controls the way the keyboard does - focus, then click - which cannot be
 * intercepted by paint order. The page's own `#hud-edit-*` bar buttons and a
 * VISIBLE card's "Move to" select are driven with real pointer actions. A hidden
 * card is a ghost in Edit HUD since the 2026-10-28 fix, so its "Move to" select
 * is now reachable the same way; the `change`-event road stays as a fallback and
 * the revert counts every card that needs it (it should be none).
 *
 * WHAT (d2) PROVES. On the real page, for a card the saved document says is
 * hidden: outside Edit HUD it is not painted; inside it is a dimmed ghost with a
 * Show control; a real POINTER click on that control shows the card, and the same
 * control hides it again; leaving Edit HUD hides it again. That is the whole fix
 * in one check, in both scenarios.
 *
 * WHAT THE TWO CHECKS THAT USED TO FAIL MEAN. They were the finding, not a broken
 * suite: `B (e2)` named the cause and `B (f)` its consequence in the saved
 * document. They pass since the fix, and are kept as the regression guard for the
 * hand-revert path.
 */
import assert from "node:assert/strict";
import { mkdirSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import * as K from "./uikit.mjs";
import { EDIT_REGIONS, MOVABLE_IDS, SIZES, applyAction } from "../src/hud-edit.js";
import {
  PROTECTED_IDS,
  effectiveCollapsed,
  normalizeLayout,
  presetLayout,
} from "../src/hud-layout.js";
import { ensureCustomCopy } from "../src/hud-presets.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const BOOT = readFileSync(join(HERE, "..", "src-tauri", "src", "hud_bootstrap.js"), "utf8");

/** Where the "PC's settings store" is kept for this run: one key, one document. */
const STORE_KEY = "test.pc.jarvis-desktop.hud_layout";
/** The backend the bootstrap is pointed at: nothing answers, on purpose. */
const BACKEND = "http://127.0.0.1:4719";
const VIEW = { width: 1600, height: 1000 };

const SHOTS = process.env.JARVIS_HUD_FIELD_SHOTS
  ? resolve(process.env.JARVIS_HUD_FIELD_SHOTS)
  : resolve(HERE, "..", "..", ".dsh-scratch", "MAXOUT-2026-10-28", "hud-edit-fieldtest");

const MOVABLE = new Set(MOVABLE_IDS);
const PROTECTED = new Set(PROTECTED_IDS);

const fails = [];
function check(name, fn) {
  return (async () => {
    try {
      await fn();
      console.log(`ok    ${name}`);
    } catch (error) {
      fails.push(name);
      console.log(`FAIL  ${name}\n      ${error && error.message ? error.message : error}`);
    }
  })();
}

/* ── a small vocabulary for the document ───────────────────────────────────── */

const cardOf = (doc, id) => doc.cards.find((card) => card.id === id);

/** The document WITHOUT its clock, for a deep-equal that still means "same". */
function withoutClock(doc) {
  const { updated_at: _clock, ...rest } = doc;
  return rest;
}

/** One line per card: the four facts that place a card, without its visibility. */
const placeLines = (doc) => doc.cards.map((card) => `${card.id} ${card.region}/${card.order} `
  + `${card.col_span}x${card.row_span} ${card.collapsed ? "folded" : "open"}`);

/** One line per card: the five facts a user changed, in a diffable form. */
const cardLines = (doc) => doc.cards.map((card) => `${card.id} ${card.region}/${card.order} `
  + `${card.col_span}x${card.row_span} ${card.visible ? "shown" : "hidden"} `
  + `${card.collapsed ? "folded" : "open"}`);

/** The size key a card's spans mean, or null when they are not one of the four. */
const sizeKey = (card) => SIZES.find(
  (size) => size.col_span === card.col_span && size.row_span === card.row_span)?.key || null;

/* ── the page, served and driven as tests/hud.mjs serves it ───────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();

/**
 * Open the HUD with the shell it really runs under: the harness's IPC bridge,
 * a durable store behind the two layout commands, and the real injected
 * bootstrap (which is what reads the saved layout and announces it).
 *
 * The store is localStorage here, and `jarvis-desktop.json` on the PC. It is
 * the same CONTRACT either way: `set_hud_layout({layout})` answers
 * `{layout, source}` and `get_hud_layout()` answers `{layout|null, source}`.
 * Seeded once, then never touched by the test again - every read after a
 * reload is the app reading back what it wrote, which is the whole point.
 */
async function openHud(original) {
  const page = await K.open(browser, base, "jarvis_hud.html", {}, VIEW);
  const errors = [];
  page.on("pageerror", (error) => errors.push(String(error)));
  await page.addInitScript(({ key, seed }) => {
    if (localStorage.getItem(key) === null) localStorage.setItem(key, seed);
    const tauri = window.__TAURI__;
    if (!tauri || !tauri.core || typeof tauri.core.invoke !== "function") return;
    const invoke = tauri.core.invoke;
    tauri.core.invoke = async (cmd, args) => {
      if (cmd === "get_hud_layout") {
        const raw = localStorage.getItem(key);
        return raw ? { layout: JSON.parse(raw), source: "saved" }
          : { layout: null, source: "none" };
      }
      if (cmd === "set_hud_layout") {
        // The document the Rust side would store, stored as it arrives.
        const doc = JSON.parse(JSON.stringify(args.layout));
        localStorage.setItem(key, JSON.stringify(doc));
        window.__hudLayout = doc;
        return { layout: doc, source: "saved" };
      }
      return invoke(cmd, args);
    };
  }, { key: STORE_KEY, seed: JSON.stringify(original) });
  await page.addInitScript(BOOT.replace("__JARVIS_BASE__", JSON.stringify(BACKEND)));
  page.__pageErrors = errors;
  await loadHud(page);
  return page;
}

/** Reload and wait until the page holds the layout the store gave it. */
async function loadHud(page) {
  await page.reload();
  await page.waitForFunction(() => Boolean(window.__jarvisHudEdit
    && window.__jarvisHudEdit.layout), null, { timeout: 20000 });
  await page.waitForTimeout(200);
}

const adopted = (page) => page.evaluate(
  () => JSON.parse(JSON.stringify(window.__jarvisHudEdit.layout)));
const stored = (page) => page.evaluate((key) => {
  const raw = localStorage.getItem(key);
  return raw ? JSON.parse(raw) : null;
}, STORE_KEY);
const rendered = (page) => page.evaluate(() => [...document.querySelectorAll("[data-hud-card]")].map(
  (el) => ({
    id: el.getAttribute("data-hud-card"),
    region: el.closest("[data-hud-region]")
      ? el.closest("[data-hud-region]").getAttribute("data-hud-region") : null,
    hidden: el.hidden,
    span: el.getAttribute("data-hud-span"),
    folded: el.classList.contains("hud-card-collapsed"),
    controls: el.querySelectorAll("[data-hud-edit-command]").length,
  })));

const settle = (page) => page.waitForTimeout(60);

/** Wait until the PC's store holds exactly what the page holds (the debounced save landed). */
const saved = (page) => K.until(page, "the store to hold the page's own layout", async () => {
  const [doc, store] = [await adopted(page), await stored(page)];
  return Boolean(store) && JSON.stringify(store) === JSON.stringify(doc);
}, { ms: 15000, every: 80 });

/**
 * Activate one of a card's own controls the way the keyboard does: focus it,
 * then click it. Asserts the control exists and is enabled first, so a
 * control that is missing or refused can never be counted as a change made.
 */
async function press(page, selector) {
  await page.evaluate((sel) => {
    const el = document.querySelector(sel);
    if (!el) throw new Error(`no control at ${sel}`);
    if (el.disabled) throw new Error(`the control at ${sel} is disabled`);
    el.focus();
    el.click();
  }, selector);
}

async function enterEdit(page) {
  assert.equal(await page.locator("#hud-edit-toggle").isVisible(), true,
    "#hud-edit-toggle is not on screen, so Edit HUD cannot be entered the way the owner does");
  assert.equal(await page.locator("#hud-edit-toggle").innerText(), "Edit HUD",
    "the toggle is not offering Edit HUD before edit mode");
  await page.click("#hud-edit-toggle");
  await page.waitForFunction(() => document.body.getAttribute("data-hud-edit") === "on",
    null, { timeout: 10000 });
  await page.waitForTimeout(150);
}

async function leaveEdit(page) {
  await page.click("#hud-edit-done");
  await page.waitForFunction(() => document.body.getAttribute("data-hud-edit") === "off",
    null, { timeout: 10000 });
  await page.waitForTimeout(150);
}

/** Best-effort screenshots: a write that fails is reported, never a suite failure. */
async function shot(page, name) {
  try {
    mkdirSync(SHOTS, { recursive: true });
    const file = join(SHOTS, `${name}.png`);
    await page.screenshot({ path: file });
    return file;
  } catch (error) {
    console.log(`note  could not write the ${name} screenshot: ${error.message}`);
    return null;
  }
}

/* ── the owner's "change everything" ──────────────────────────────────────── */

/**
 * Do everything the edit mode offers to every card that offers it, through the
 * controls on screen. Returns a summary of what the page actually changed, so
 * the checks can prove the DOCUMENT moved (not just that clicks happened).
 */
async function changeEverything(page, before) {
  const movables = before.cards.filter((card) => MOVABLE.has(card.id));
  const hideable = movables.filter((card) => !PROTECTED.has(card.id));

  // 1. every card that may move, moved to another region (the "Move to" select)
  for (const card of hideable) {
    const at = EDIT_REGIONS.indexOf(card.region);
    const target = EDIT_REGIONS[(at + 1) % EDIT_REGIONS.length];
    assert.notEqual(target, card.region, `no other region to move ${card.id} to`);
    await page.selectOption(`[data-hud-edit-region="${card.id}"]`, target);
    await settle(page);
  }
  const afterMoves = await adopted(page);

  // 2. every card that may move, one place down inside its region
  let arrowed = 0;
  for (const card of hideable) {
    const enabled = await page.evaluate((id) => {
      const button = document.querySelector(
        `[data-hud-edit-command="down"][data-hud-edit-card="${id}"]`);
      return Boolean(button && !button.disabled);
    }, card.id);
    if (!enabled) continue;
    await press(page, `[data-hud-edit-command="down"][data-hud-edit-card="${card.id}"]`);
    arrowed += 1;
    await settle(page);
  }
  const afterReorder = await adopted(page);

  // 3. every movable card resized to a different size, cycling all four
  const sizesUsed = new Set();
  for (let i = 0; i < movables.length; i += 1) {
    const card = movables[i];
    const current = cardOf(afterReorder, card.id);
    const now = sizeKey(current);
    let pick = null;
    for (let step = 0; step < SIZES.length; step += 1) {
      const candidate = SIZES[(i + step) % SIZES.length];
      if (candidate.key !== now) { pick = candidate; break; }
    }
    assert.ok(pick, `no size other than ${now} to give ${card.id}`);
    await press(page, `[data-hud-edit-card="${card.id}"][data-hud-edit-size="${pick.key}"]`);
    sizesUsed.add(pick.key);
    await settle(page);
  }
  // 3b. a size button the cycle above happened to skip is pressed on a card it
  //     meaningfully changes - so all four buttons are exercised for real, and
  //     no card ends on the size it started with.
  for (const size of SIZES) {
    if (sizesUsed.has(size.key)) continue;
    const doc = await adopted(page);
    const card = movables.find((entry) => sizeKey(cardOf(doc, entry.id)) !== size.key
      && sizeKey(entry) !== size.key);
    assert.ok(card, `no card left that ${size.key} would change`);
    await press(page, `[data-hud-edit-card="${card.id}"][data-hud-edit-size="${size.key}"]`);
    sizesUsed.add(size.key);
    await settle(page);
  }

  // Measured here, while every card is still on screen at its new size: with a
  // card narrower than its own toolbar, another card can paint over its
  // buttons. Not a check - this suite drives card controls by keyboard - but
  // the count is printed so the defect is on the record rather than hidden.
  const coveredAtSizes = await page.evaluate(() => {
    const out = [];
    for (const card of document.querySelectorAll("[data-hud-card]")) {
      if (card.hidden) continue;
      for (const control of card.querySelectorAll(
        "[data-hud-edit-command],[data-hud-edit-size],[data-hud-edit-region]")) {
        control.scrollIntoView({ block: "nearest" });
        const box = control.getBoundingClientRect();
        if (box.width < 2 || box.height < 2) continue;
        if (box.top < 0 || box.bottom > innerHeight) continue;
        const at = document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2);
        const owner = at && at.closest ? at.closest("[data-hud-card]") : null;
        if (owner && owner !== card) {
          out.push(`${card.getAttribute("data-hud-card")}.`
            + `${control.getAttribute("data-hud-edit-command") || "size"}`
            + ` <- ${owner.getAttribute("data-hud-card")}`);
        }
      }
    }
    return out;
  });

  // 4. every movable card folded
  for (const card of movables) {
    await press(page, `[data-hud-edit-command="collapse"][data-hud-edit-card="${card.id}"]`);
    await settle(page);
  }

  // 5. every card that may be hidden, hidden - last, so every card is still on
  //    screen at its final size for the measurement above. A hidden card is a
  //    ghost in Edit HUD since the 2026-10-28 fix, so its controls stay usable.
  for (const card of hideable) {
    await press(page, `[data-hud-edit-command="hide"][data-hud-edit-card="${card.id}"]`);
    await settle(page);
  }

  const changed = await adopted(page);
  return { changed, afterMoves, afterReorder, movables, hideable, arrowed, sizesUsed, coveredAtSizes };
}

/* ── the owner's "revert back", the two real paths ────────────────────────── */

/**
 * Choose a region in a card's own "Move to" select. A card that is on screen is
 * driven with the real pointer action; a card that is not (a layout can hide a
 * card without Edit HUD painting it, e.g. outside edit mode) is driven by setting
 * the select and firing the `change` event the same control sends. Since the
 * 2026-10-28 fix a hidden card is a ghost in Edit HUD, so the fallback should not
 * be needed there - the revert counts how many needed it, and reports it.
 */
async function chooseRegion(page, id, region, { mustBeReachable = false } = {}) {
  const visible = await page.locator(`[data-hud-edit-region="${id}"]`).isVisible();
  if (mustBeReachable) assert.equal(visible, true, `the "Move to" select for ${id} is not on screen`);
  if (visible) {
    await page.selectOption(`[data-hud-edit-region="${id}"]`, region);
    return true;
  }
  await page.evaluate(([cardId, want]) => {
    const select = document.querySelector(`[data-hud-edit-region="${cardId}"]`);
    if (!select) throw new Error(`no region select for ${cardId}`);
    select.value = want;
    select.dispatchEvent(new Event("change", { bubbles: true }));
  }, [id, region]);
  return false;
}

/** A: the edit bar's own "Reset to preset". */
async function revertWithReset(page) {
  await page.click("#hud-edit-reset");
  await page.waitForTimeout(600);
}

/**
 * B: re-apply every original fact through the same controls - region, size,
 * fold, visibility, then place. The place pass is an insertion sort with the
 * arrow buttons: walk each region's cards in the original order and move each
 * one up until it sits where it did.
 *
 * Returns what could NOT be restored, so a reachability regression is named
 * rather than hidden: before 2026-10-28 that was every hidden card, because the
 * only "show" control was one-way (see the note at the top of this file).
 */
async function revertByHand(page, original) {
  const want = original.cards.filter((card) => MOVABLE.has(card.id));
  const unreachable = [];

  for (const card of want) {
    const now = cardOf(await adopted(page), card.id);
    if (PROTECTED.has(card.id) || now.region === card.region) continue;
    if (!(await chooseRegion(page, card.id, card.region))) unreachable.push(`${card.id} (move)`);
    await settle(page);
  }
  for (const card of want) {
    const now = cardOf(await adopted(page), card.id);
    const target = sizeKey(card);
    assert.ok(target, `${card.id}'s saved size (${card.col_span}x${card.row_span}) is not one of the four buttons`);
    if (sizeKey(now) === target) continue;
    await press(page, `[data-hud-edit-card="${card.id}"][data-hud-edit-size="${target}"]`);
    await settle(page);
  }
  for (const card of want) {
    const now = cardOf(await adopted(page), card.id);
    if (Boolean(now.collapsed) === Boolean(card.collapsed)) continue;
    await press(page, `[data-hud-edit-command="collapse"][data-hud-edit-card="${card.id}"]`);
    await settle(page);
  }
  // visibility: the card's own control is the only per-card one there is. Since
  // 2026-10-28 it is a real toggle, so press it exactly as a user would - on
  // every card that should be shown.
  const stillHidden = [];
  for (const card of want) {
    if (PROTECTED.has(card.id) || !card.visible) continue;
    const now = cardOf(await adopted(page), card.id);
    if (now.visible) continue;
    await press(page, `[data-hud-edit-command="hide"][data-hud-edit-card="${card.id}"]`);
    await settle(page);
    if (!cardOf(await adopted(page), card.id).visible) stillHidden.push(card.id);
  }
  // place: an insertion sort per region, with the arrow buttons
  for (const region of EDIT_REGIONS) {
    const ordered = want.filter((card) => card.region === region)
      .sort((a, b) => a.order - b.order);
    for (let at = 0; at < ordered.length; at += 1) {
      for (let guard = 0; guard < ordered.length + 2; guard += 1) {
        const now = cardOf(await adopted(page), ordered[at].id);
        if (now.region !== region || now.order === at) break;
        await press(page,
          `[data-hud-edit-command="${now.order > at ? "up" : "down"}"][data-hud-edit-card="${ordered[at].id}"]`);
        await settle(page);
      }
    }
  }
  return { stillHidden, unreachable };
}

/* ── one scenario, end to end ─────────────────────────────────────────────── */

const shotsWritten = [];

async function fieldTest(label, original, revert) {
  console.log(`\n──────── ${label} ────────`);
  const page = await openHud(original);

  /* (a) the document the app reads back, captured from the store itself */
  await check(`${label} (a): the page opens on the saved document`, async () => {
    assert.deepEqual(await stored(page), original,
      "the store's document is not the one that was saved for this run");
    assert.deepEqual(await adopted(page), original,
      "the page did not adopt the saved document on load");
    assert.equal(await page.evaluate(() => document.body.getAttribute("data-hud-edit")), "off",
      "the HUD loaded already in edit mode");
  });
  shotsWritten.push(await shot(page, `${label}-1-before`));

  /* (b) Edit HUD, through the button the owner clicks */
  await check(`${label} (b): #hud-edit-toggle turns Edit HUD on`, async () => {
    await enterEdit(page);
    assert.equal(await page.locator("#hud-edit-toggle").getAttribute("aria-pressed"), "true",
      "the toggle does not say it is pressed");
    assert.equal(await page.locator("#hud-edit-toggle").innerText(), "Done",
      "the toggle does not offer Done while editing");
    assert.equal(await page.locator("#hud-edit-bar").isVisible(), true,
      "the editing banner (with Undo / Reset / Discard) is not on screen");
    assert.equal(await page.locator("#hud-edit-reset").isVisible(), true,
      "the edit bar's real Reset control is not on screen");
    const regions = await page.evaluate(() => [...document.querySelectorAll("[data-hud-region]")]
      .map((el) => el.getAttribute("data-hud-region")));
    assert.deepEqual(regions.sort(), [...EDIT_REGIONS].sort(),
      `the three card regions are not the page's: ${JSON.stringify(regions)}`);
  });

  /* (b2) the app's own Undo, on one change, before the big edit */
  await check(`${label} (b2): Ctrl+Z undoes one change, whole document and all`, async () => {
    const beforeUndo = await adopted(page);
    const card = beforeUndo.cards.find((entry) => MOVABLE.has(entry.id) && !PROTECTED.has(entry.id));
    await press(page, `[data-hud-edit-command="collapse"][data-hud-edit-card="${card.id}"]`);
    await settle(page);
    assert.notEqual(cardOf(await adopted(page), card.id).collapsed, card.collapsed,
      `folding ${card.id} did not change the document`);
    await page.keyboard.press("Control+z");
    await page.waitForTimeout(250);
    assert.deepEqual(await adopted(page), beforeUndo,
      "Ctrl+Z did not put the whole document back (it must, including a copy conversion)");
  });

  /* (c) change everything */
  let summary = null;
  await check(`${label} (c): every control changes the document`, async () => {
    summary = await changeEverything(page, await adopted(page));
    const { changed, movables, hideable, sizesUsed } = summary;

    assert.equal(movables.length, 12,
      `expected the 12 movable cards Cockpit carries, found ${movables.length}`);
    assert.equal(hideable.length, 10, `expected 10 hideable cards, found ${hideable.length}`);
    assert.equal(await page.evaluate(
      () => document.querySelectorAll("[data-hud-card]").length), 12,
      "not every movable card got an edit shell");

    for (const card of hideable) {
      const now = cardOf(changed, card.id);
      assert.notEqual(now.region, card.region, `${card.id} did not move to another region`);
      assert.equal(now.visible, false, `${card.id} is still shown after Hide`);
      assert.notEqual(now.collapsed, card.collapsed, `${card.id} was not folded`);
    }
    for (const card of movables) {
      const now = cardOf(changed, card.id);
      assert.notEqual(`${now.col_span}x${now.row_span}`, `${card.col_span}x${card.row_span}`,
        `${card.id} was not resized`);
    }
    assert.equal(sizesUsed.size, SIZES.length,
      `the size buttons were not all exercised: ${[...sizesUsed].join(",")}`);
    for (const card of movables) {
      const size = sizeKey(cardOf(changed, card.id));
      assert.ok(size, `${card.id} ended on a size that is not one of the four buttons`);
    }
    for (const card of movables.filter((entry) => PROTECTED.has(entry.id))) {
      assert.equal(cardOf(changed, card.id).visible, true,
        `protected ${card.id} was hidden, which the app must refuse`);
    }
    assert.ok(summary.arrowed >= 1, "no card had an enabled arrow button");

    const placesMoved = summary.afterMoves.cards.filter((card) => {
      const now = cardOf(summary.afterReorder, card.id);
      return now.region === card.region && now.order !== card.order;
    });
    assert.ok(placesMoved.length >= 1,
      "the arrow buttons changed no card's place inside its region");
  });

  await check(`${label} (c): the app saved the changed document exactly`, async () => {
    await saved(page);
    assert.deepEqual(await stored(page), summary.changed,
      "the store does not hold the document the page holds (the save was not exact)");
    assert.deepEqual(await stored(page), await adopted(page),
      "the store and the page disagree after the save");
  });

  // A measured note, not a check: with a card resized inside a 300px rail the
  // card is narrower than its own toolbar, so another card can paint over its
  // buttons. This suite drives card controls by keyboard for that reason; the
  // count is printed so the defect is on the record rather than hidden.
  const covered = summary.coveredAtSizes;
  console.log(`note  ${label}: ${covered.length} edit control(s) had another card's control painted over `
    + "them once every card was resized (pointer path only; this suite activates card controls by "
    + `keyboard, so no check depends on it)${covered.length ? `: ${covered.slice(0, 6).join(", ")}` : ""}`);
  shotsWritten.push(await shot(page, `${label}-2-changed-editing`));

  /* (d) reload: nothing lost */
  await check(`${label} (d): after a reload every change is still there`, async () => {
    await leaveEdit(page);
    await loadHud(page);
    const reloaded = await adopted(page);
    assert.deepEqual(reloaded, summary.changed,
      "the reloaded document is not the one the page saved");
    assert.deepEqual(await stored(page), summary.changed,
      "the store changed across the reload");
    for (const line of cardLines(summary.changed)) assert.ok(cardLines(reloaded).includes(line),
      `the reloaded layout has lost a card: ${line}`);
  });

  await check(`${label} (d): the rendered HUD shows every saved change`, async () => {
    const rows = await rendered(page);
    assert.equal(rows.length, 12, `the reloaded page drew ${rows.length} editable cards`);
    for (const card of summary.changed.cards.filter((entry) => MOVABLE.has(entry.id))) {
      const row = rows.find((entry) => entry.id === card.id);
      assert.ok(row, `${card.id} has no card on the page at all`);
      assert.equal(row.region, card.region, `${card.id} is drawn in the wrong region`);
      assert.equal(row.hidden, !card.visible, `${card.id}'s visibility did not survive the reload`);
      assert.equal(row.span, `${card.col_span}x${card.row_span}`,
        `${card.id} is drawn at the wrong size (${row.span})`);
      assert.equal(row.folded, effectiveCollapsed(card, 0),
        `${card.id}'s folded state did not survive the reload`);
    }
    assert.deepEqual(page.__pageErrors, [],
      `the page threw while editing: ${page.__pageErrors.join(" | ")}`);
  });
  shotsWritten.push(await shot(page, `${label}-3-changed-reloaded`));

  /* (d2) a hidden card is reachable again: the fix, driven on the real page */
  await check(`${label} (d2): a hidden card can be shown again in Edit HUD`, async () => {
    // The widest hidden card is used for the real pointer click: a 12-column
    // card's own toolbar fits inside it, so the click cannot land on a
    // neighbouring card's control. That separate narrow-card overlap is measured
    // in the `note` above and is not what this check is about.
    const hiddenCards = summary.changed.cards.filter((card) => MOVABLE.has(card.id)
      && !PROTECTED.has(card.id) && card.visible === false)
      .sort((a, b) => b.col_span - a.col_span || a.id.localeCompare(b.id));
    const target = hiddenCards[0];
    assert.ok(target, "the changed layout has no hidden card to show again");
    const shell = `[data-hud-card="${target.id}"]`;
    const control = `${shell} [data-hud-edit-command="hide"]`;

    // Outside Edit HUD the card is exactly as hidden as it has always been.
    assert.equal(await page.locator(shell).isVisible(), false,
      `${target.id} is painted outside Edit HUD although the saved layout hides it`);

    await enterEdit(page);
    try {
      const ghost = await page.evaluate((sel) => {
        const card = document.querySelector(sel);
        const body = card.querySelector(".hud-card-body");
        const word = card.querySelector(".hud-card-hidden-word");
        const button = card.querySelector('[data-hud-edit-command="hide"]');
        return {
          painted: card.getBoundingClientRect().height > 1,
          hiddenAttribute: Boolean(card.hidden),
          ghost: card.classList.contains("hud-card-hidden"),
          bodyShown: getComputedStyle(body).display !== "none",
          wordShown: Boolean(word && !word.hidden),
          pressed: button ? button.getAttribute("aria-pressed") : null,
          label: button ? (button.getAttribute("aria-label") || "") : "",
          enabled: Boolean(button && !button.disabled),
        };
      }, shell);
      assert.equal(ghost.painted, true, `${target.id}'s shell is not painted in Edit HUD`);
      assert.equal(ghost.hiddenAttribute, false,
        `${target.id}'s shell still carries the hidden attribute in Edit HUD`);
      assert.equal(ghost.ghost, true, `${target.id} is not marked as a hidden ghost`);
      assert.equal(ghost.bodyShown, false,
        `${target.id}'s card body is shown although the saved layout hides the card`);
      assert.equal(ghost.wordShown, true, `${target.id}'s ghost does not say it is hidden`);
      assert.equal(ghost.enabled, true, `${target.id}'s Show control is disabled`);
      assert.equal(ghost.pressed, "true",
        `${target.id}'s Hide control does not say the card is hidden (aria-pressed=${ghost.pressed})`);
      assert.match(ghost.label, /^Show /,
        `${target.id}'s control does not offer Show: "${ghost.label}"`);

      // The road a user has: a real pointer click on the control on screen.
      await page.locator(control).click({ timeout: 15000 });
      await settle(page);
      assert.equal(cardOf(await adopted(page), target.id).visible, true,
        `a real click on ${target.id}'s own Show control did not show it`);
      assert.equal(await page.locator(shell).isVisible(), true,
        `${target.id} is still a ghost after its Show control was pressed`);
      const after = await page.evaluate((sel) => {
        const card = document.querySelector(sel);
        const word = card.querySelector(".hud-card-hidden-word");
        return {
          ghost: card.classList.contains("hud-card-hidden"),
          wordShown: Boolean(word && !word.hidden),
        };
      }, shell);
      assert.equal(after.ghost, false,
        `${target.id} still carries the ghost mark after being shown`);
      assert.equal(after.wordShown, false,
        `${target.id} still says "hidden" after being shown`);
      // (c) folds every card, and a folded card's body is folded away BY THE
      // FOLD (.hud-card-collapsed .hud-card-body). So open the fold through the
      // card's own control before asking whether the BODY came back: the
      // question here is whether the hidden state's rule is still folding it,
      // which is exactly what the old defect left behind for ever.
      const folded = await page.evaluate((sel) => {
        const button = document.querySelector(`${sel} [data-hud-edit-command="collapse"]`);
        return Boolean(button && button.getAttribute("aria-pressed") === "true");
      }, shell);
      if (folded) {
        await press(page, `${shell} [data-hud-edit-command="collapse"]`);
        await settle(page);
      }
      assert.equal(await page.evaluate((sel) => getComputedStyle(
        document.querySelector(`${sel} .hud-card-body`)).display !== "none", shell), true,
        `${target.id}'s card body did not come back with the card`);
      if (folded) {
        // Put the fold back, so this check leaves the document as (c) did and
        // the revert below still restores it from the same starting point.
        await press(page, `${shell} [data-hud-edit-command="collapse"]`);
        await settle(page);
      }

      // ...and the same control is the toggle back, so nothing is one-way.
      await page.locator(control).click({ timeout: 15000 });
      await settle(page);
      assert.equal(cardOf(await adopted(page), target.id).visible, false,
        `pressing ${target.id}'s control a second time did not hide it again`);
    } finally {
      if (await page.evaluate(() => document.body.getAttribute("data-hud-edit") === "on")) {
        await leaveEdit(page);
      }
    }
    assert.equal(await page.locator(shell).isVisible(), false,
      `${target.id} stayed painted after Edit HUD ended`);
    assert.deepEqual(page.__pageErrors, [],
      `the page threw while showing a hidden card: ${page.__pageErrors.join(" | ")}`);
  });

  /* (e) revert, by this scenario's real path */
  let info = {};
  await check(`${label} (e): ${revert.what}`, async () => {
    await enterEdit(page);
    info = (await revert.run(page, original)) || {};
    await saved(page);
    const reverted = await adopted(page);
    assert.deepEqual(await stored(page), reverted,
      "the reverted document was not saved");
    (revert.assertAfterRevert || revert.assert)(reverted, original, info);
  });
  if (revert.after) await revert.after(page, original, info);
  const revertedDoc = await adopted(page);

  /* (f) reload: back to (a) */
  await check(`${label} (f): after a reload the layout is the one captured in (a)`, async () => {
    await leaveEdit(page);
    await loadHud(page);
    const reloaded = await adopted(page);
    assert.deepEqual(await stored(page), revertedDoc,
      "the store changed across the revert's reload");
    assert.deepEqual(cardLines(reloaded), cardLines(original),
      "the arrangement did not come back to the saved one");
    revert.assert(reloaded, original);
    const rows = await rendered(page);
    for (const card of original.cards.filter((entry) => MOVABLE.has(entry.id))) {
      const row = rows.find((entry) => entry.id === card.id);
      assert.ok(row, `${card.id} has no card on the page after the revert`);
      assert.equal(row.region, card.region, `${card.id} is drawn back in the wrong region`);
      assert.equal(row.hidden, !card.visible, `${card.id}'s visibility did not come back`);
      assert.equal(row.span, `${card.col_span}x${card.row_span}`, `${card.id}'s size did not come back`);
      assert.equal(row.folded, effectiveCollapsed(card, 0), `${card.id}'s fold did not come back`);
    }
  });
  shotsWritten.push(await shot(page, `${label}-4-reverted`));

  /* (g) the "Discard changes" control, asked once, honestly */
  if (revert.what.includes("Reset")) {
    await check(`${label} (g): "Discard changes" after a reload changes nothing`, async () => {
      await enterEdit(page);
      const before = await adopted(page);
      await page.click("#hud-edit-discard");
      await page.waitForTimeout(500);
      assert.deepEqual(await adopted(page), before,
        "Discard changes altered the layout after a reload");
      // It also leaves edit mode - and there is nothing to discard, because the
      // session's entry snapshot is made when Edit HUD is entered.
      assert.equal(await page.evaluate(() => document.body.getAttribute("data-hud-edit")), "off",
        "Discard changes did not leave edit mode");
      assert.deepEqual(await stored(page), before, "Discard changes wrote a different document");
    });
  }

  await page.close();
}

/* ── A: a fresh install - the saved document is the Cockpit preset ────────── */

const cockpit = presetLayout("cockpit");
assert.deepEqual(normalizeLayout(cockpit), cockpit,
  "the Cockpit preset this suite starts from is not a fixed point of the normalizer");

await fieldTest("A", cockpit, {
  what: 'the real "Reset to preset" restores every card, and keeps the owner\'s copy',
  run: (page) => revertWithReset(page),
  assert(reverted, original) {
    // Every card is exactly where it was: what the owner sees as "my HUD".
    assert.deepEqual(cardLines(reverted), cardLines(original),
      "Reset to preset did not restore every card's region, place, size, fold and visibility");
    for (const key of ["shell_template", "density", "default_stage_tab", "base_preset"]) {
      assert.equal(reverted[key], original[key], `Reset to preset changed ${key}`);
    }
    // The document ITSELF is the owner's copy now, on purpose (hud-edit.js:566-584,
    // ruling 27): the first edit of a built-in layout is made to a copy, and Reset
    // keeps a copy a copy - its name and its place in "My layouts" survive. This
    // is asserted as what the app does, so the report can say it plainly.
    assert.match(reverted.id, /^custom-/, "the first edit did not make the owner's own copy");
    assert.match(reverted.name, /\(Custom\)$/, "the owner's copy is not named as a copy");
    assert.deepEqual(reverted.user_presets.map((entry) => entry.id), [reverted.id],
      "the copy was not added to My layouts");
    assert.notEqual(reverted.id, original.id,
      "the saved document went back to the built-in's own id after a Reset");
  },
});

/* ── B: the owner's own saved layout - a full document round trip ─────────── */

/**
 * A document the app itself would have produced: Cockpit, edited by this
 * module's own reducer (so every order, span and fold is canonical), then made
 * the owner's own copy by the app's own `ensureCustomCopy`. It is deliberately
 * NOT the preset's arrangement - a region moved, a size changed, a card folded -
 * so that "Reset to preset" could not pass for a revert of it.
 */
function ownerSavedLayout() {
  let doc = presetLayout("cockpit");
  doc = applyAction(doc, { type: "moveCard", id: "telemetry", region: "left_rail", index: 1 }).layout;
  doc = applyAction(doc, { type: "moveCard", id: "waiting", region: "stage_top", index: 1 }).layout;
  doc = applyAction(doc, { type: "resizeCard", id: "nav", size: "S" }).layout;
  doc = applyAction(doc, { type: "toggleCollapsed", id: "systems" }).layout;
  return ensureCustomCopy(doc);
}

const mine = ownerSavedLayout();
assert.deepEqual(normalizeLayout(mine), mine,
  "the owner's saved layout this suite starts from is not a fixed point of the normalizer");
assert.notDeepEqual(placeLines(mine), placeLines(cockpit),
  "the owner's saved layout is the preset's own arrangement, so this scenario would prove nothing");

await fieldTest("B", mine, {
  what: "every region, place, size and fold re-applied through the same controls comes back",
  run: (page, original) => revertByHand(page, original),

  // What the hand re-apply DID restore, asked before the visibility question:
  // every region, place, size and fold, and the document's own identity.
  assertAfterRevert(reverted, original) {
    assert.deepEqual(placeLines(reverted), placeLines(original),
      "the hand re-apply did not restore every card's region, place, size and fold");
    for (const key of ["id", "name", "shell_template", "density", "default_stage_tab"]) {
      assert.equal(reverted[key], original[key], `the hand re-apply changed ${key}`);
    }
    assert.deepEqual(reverted.user_presets, original.user_presets,
      "the hand re-apply changed My layouts");
  },

  // The cause on its own, named: every hidden card must be showable again.
  async after(page, original, info) {
    await check("B (e2): a card hidden in Edit HUD can be shown again", async () => {
      assert.deepEqual(info.stillHidden, [],
        `${(info.stillHidden || []).length} card(s) could not be shown again: `
        + `${(info.stillHidden || []).join(", ")}. Since 2026-10-28 a card's Hide control is `
        + "a real toggle (onToolbarClick sends `setVisible` with no fixed value), and while "
        + "Edit HUD is on a hidden card is painted as a dimmed ghost whose own Show control "
        + "is reachable (`shell.hidden = !card.visible && !editing`, with the page's ghost "
        + "rule folding the card body away). If this fails, one of those two halves has "
        + "regressed: either the control stopped toggling, or a hidden card's shell stopped "
        + "being painted in edit mode.");
      if ((info.unreachable || []).length) {
        assert.fail(`controls the re-apply could not reach: ${info.unreachable.join(", ")}`);
      }
    });
  },

  // And the consequence, in the full document: what is still wrong after a reload.
  assert(reloaded, original) {
    const missing = reloaded.cards.filter((card) => {
      const want = original.cards.find((entry) => entry.id === card.id);
      return want && card.visible !== want.visible;
    }).map((card) => card.id);
    assert.deepEqual(missing, [],
      `after the revert these cards are still hidden: ${missing.join(", ")}`);
    assert.deepEqual(withoutClock(reloaded), withoutClock(original),
      "the reverted document is not the saved one (ignoring the save clock)");
    assert.ok(reloaded.updated_at >= original.updated_at, "the save clock went backwards");
  },
});

/* ── done ─────────────────────────────────────────────────────────────────── */

await browser.close();
if (close) await close();

const written = shotsWritten.filter(Boolean);
if (written.length) {
  console.log(`\nscreenshots (${written.length}):`);
  for (const file of written) console.log(`  ${file}`);
} else {
  console.log("\nnote  no screenshots were written (the shots directory was not writable)");
}

console.log(`\n${fails.length ? `${fails.length} failed` : "all passed"}`);
if (fails.length) {
  console.log(`failed: ${fails.join(", ")}`);
  process.exit(1);
}

/**
 * WHAT THIS SUITE DOES AND DOES NOT PROVE.
 *
 * IT DOES prove, against the real page and the real editor module, that:
 *   - every region move, place move, resize, fold and hide an owner can make in
 *     Edit HUD is written to the saved document and comes back after a reload -
 *     in the document AND on the page - for a fresh install and for an owner
 *     who already has a saved layout of their own;
 *   - the app's own "Reset to preset" restores every card of a built-in layout
 *     exactly (scenario A);
 *   - every region, place, size and fold of an owner's own layout can be put
 *     back by hand through the same controls (scenario B, which passes);
 *   - a hidden card can be shown again, in both scenarios: outside Edit HUD it is
 *     not painted, inside it is a dimmed ghost whose own Show control a REAL
 *     pointer click brings back (and the same control hides it again); the
 *     hand-revert then restores all nine hidden cards through that control
 *     (scenario B, (e2));
 *   - the copy conversion on the first edit of a built-in layout is by design
 *     (asserted, scenario A).
 *
 * IT DOES NOT prove:
 *   - that the ghost's dimmed look is right: the screenshots show it, no check
 *     measures a colour or a pixel;
 *   - that `hud_layout.rs` stores what it is given: the two IPC commands are
 *     stubbed here. The Rust store, its validation and the real
 *     `jarvis-desktop.json` write are a different test's business;
 *   - that the packaged Tauri window behaves the same: this is headless
 *     Chromium at one viewport, not WebView2 at the owner's DPI. Fonts, theme
 *     and the floating window's own hints are not exercised;
 *   - that a MOUSE click reaches every control: a card narrower than its own
 *     toolbar lets the neighbouring card paint over it (the `note` above counts
 *     it), and this suite drives card controls by keyboard for that reason.
 *     That is a real, separate UI defect, not something this suite can call
 *     fixed;
 *   - anything about the phone: Edit HUD is a desktop-window feature and the
 *     Android app has no equivalent (`docs/ARCHITECTURE.md` section 8).
 */
