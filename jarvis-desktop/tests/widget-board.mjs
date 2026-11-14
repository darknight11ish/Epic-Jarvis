/**
 * "Widgets you describe" (the owner's choice of 2026-09-28, the SAFE
 * version; JARVIS-API.md section 86; src/widget-board.js, brain.js
 * paintWidgets, widget.js "Your widget", src-tauri/src/brain/widgets.rs;
 * backend jarvis_widgets.py).
 *
 * What must hold:
 * - the drawing rule is the PC's and the phone's, case for case
 *   (fixtures/widget-cases.json, tools/gen_widget_cases.py): an unknown
 *   block or button is left out, an unknown source is private, sizes are
 *   capped, and private words go while hidden;
 * - the ARRANGEMENT rule is the PC's and the phone's too (the fixture's
 *   `boards`): which block is drawn large, in what order the rest go, and the
 *   buttons last - four layouts, a closed list;
 * - the page draws with DOM calls only: a script or tag in a widget's words
 *   is shown as text, never run or parsed;
 * - the buttons are the five Quick Settings tile actions, in the phone's own
 *   words, and nothing else;
 * - the Brain: a preview is made from typed words, pasted words are sent as
 *   pasted, Add keeps ONE preview and Delete removes ONE widget, both held
 *   on a stale link, neither asks "are you sure?";
 * - the widget window: the chosen widget replaces the face, its buttons go
 *   through ONE widget_board_action, held on a stale link except Stop
 *   everything, and App lock hides its private words.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  ACCENTS,
  applyLook,
  ACTIONS,
  boardOf,
  CONTRASTS,
  DELETE_LABEL,
  EMPTY,
  hideView,
  HIDDEN_WORDS,
  LAYOUTS,
  LIMITS,
  LOOK_DEFAULT,
  lookOf,
  MISSING,
  NEVER_HELD,
  PREVIEW_TITLE,
  PRIVATE_SOURCES,
  SHADES,
  viewOf,
} from "../src/widget-board.js";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const readRepo = (p) => readFileSync(join(HERE, "..", "..", p), "utf8");
const CASES = JSON.parse(read("tests/fixtures/widget-cases.json"));

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* ── The rule, shared with the PC and the phone ────────────────────────── */

await check("the drawing rule matches the shared cases, word for word", async () => {
  assert.ok(Object.keys(CASES.cases).length >= 6);
  for (const [name, c] of Object.entries(CASES.cases)) {
    assert.deepEqual(viewOf(c.answer), c.view, `view: ${name}`);
    assert.deepEqual(hideView(viewOf(c.answer)), c.hidden, `hidden: ${name}`);
  }
});

await check("the four arrangements, and what each one draws, are the shared ones", async () => {
  assert.deepEqual(LAYOUTS, CASES.layouts);
  for (const [name, c] of Object.entries(CASES.cases)) {
    const view = viewOf(c.answer);
    for (const layout of CASES.layouts) {
      assert.deepEqual(boardOf(view && { ...view, layout }), c.boards[layout],
        `board ${layout}: ${name}`);
    }
    // boardOf uses the view's OWN layout: what the PC sent is what is drawn.
    if (view) assert.deepEqual(boardOf(view), c.boards[view.layout], `own: ${name}`);
  }
  // An arrangement this app does not know is drawn as the default, never
  // dropped - a newer PC must still leave a drawable widget.
  const future = { ok: true, name: "x", layout: "grid", blocks: [{ type: "title", text: "A" }] };
  assert.equal(viewOf(future).layout, "stack");
  assert.equal(boardOf(viewOf(future)).blocks.length, 1);
});

await check("the look's three closed lists are the PC's, id for id", async () => {
  assert.deepEqual(
    Object.entries(ACCENTS).map(([id, a]) => ({ id, label: a.label, color: a.hex })),
    CASES.accents, "the eight accents and their hexes");
  assert.deepEqual(
    Object.entries(SHADES).map(([id, s]) => ({ id, label: s.label, alpha: s.alpha,
      surface_alpha: s.surfaceAlpha })),
    CASES.shades, "the three shades and both alphas");
  assert.deepEqual(
    Object.entries(CONTRASTS).map(([id, c]) => ({ id, label: c.label, colors: c.colors })),
    CASES.contrasts, "the two contrasts and their four colours");
  assert.deepEqual(LOOK_DEFAULT, CASES.look_default, "the default look");
});

await check("the look defaults an absent key, and an unknown word falls back per key", async () => {
  // A widget from before the look: no keys at all - exactly today's drawing.
  const old = { ok: true, name: "x", layout: "stack", blocks: [] };
  assert.deepEqual(lookOf(old), CASES.look_default);
  const drawn = viewOf(old);
  assert.deepEqual({ accent: drawn.accent, shade: drawn.shade, contrast: drawn.contrast },
    CASES.look_default);
  assert.deepEqual(lookOf(null), CASES.look_default);
  // A newer PC's words this app does not know: the fixture's two cases.
  assert.deepEqual(lookOf(CASES.cases.newer_pc_look.answer), CASES.look_default);
  assert.deepEqual(lookOf(CASES.cases.half_right_look.answer),
    { accent: "amber", shade: "solid", contrast: "high" });
  // Each key falls back on its own, so one strange word never costs the other
  // two - and a word that is a JS built-in is not on a closed list either.
  assert.deepEqual(lookOf({ accent: "violet", shade: "frosted", contrast: "ultra" }),
    { accent: "violet", shade: "solid", contrast: "normal" });
  assert.deepEqual(lookOf({ accent: "constructor", shade: 7, contrast: "" }), CASES.look_default);
});

await check("hiding the private words keeps the look", async () => {
  const shown = viewOf(CASES.cases.looked_widget.answer);
  assert.deepEqual([shown.accent, shown.shade, shown.contrast], ["violet", "clear", "high"]);
  const hidden = hideView(shown);
  assert.deepEqual([hidden.accent, hidden.shade, hidden.contrast], ["violet", "clear", "high"]);
  assert.deepEqual(hidden, CASES.cases.looked_widget.hidden);
});

await check("applyLook sets the look's colours and alphas, and nothing else", async () => {
  // The smallest box `paint` and `applyLook` need: applyLook touches exactly
  // one thing, `box.style.setProperty`, so no DOM and no dependency is needed.
  const box = () => ({ style: { props: {},
    setProperty(name, value) { this.props[name] = value; } } });
  const looked = box();
  applyLook(looked, { accent: "violet", shade: "half", contrast: "high" });
  assert.deepEqual(looked.style.props, {
    "--board-accent": ACCENTS.violet.hex,
    "--board-bg": "#000000",
    "--board-bg-a": "0.749",
    "--board-surface": "#262626",
    "--board-surface-a": "0.624",
    "--board-text-hi": "#FFFFFF",
    "--board-text-muted": "#E0E0E0",
  });
  // Nothing but a colour or an alpha: no font, image, size or position.
  for (const name of Object.keys(looked.style.props)) {
    assert.match(name, /^--board-(bg|surface|text-hi|text-muted|accent)(-a)?$/, name);
  }
  // A box with no look, and a look with a word off the list, are the defaults.
  const plain = box();
  applyLook(plain, null);
  const normal = CONTRASTS.normal.colors;
  assert.deepEqual(plain.style.props, {
    "--board-accent": ACCENTS.cyan.hex,
    "--board-bg": normal.bg,
    "--board-bg-a": "1",
    "--board-surface": normal.surface,
    "--board-surface-a": "1",
    "--board-text-hi": normal.text_hi,
    "--board-text-muted": normal.text_muted,
  });
  const future = box();
  applyLook(future, { accent: "chartreuse", shade: "frosted", contrast: "ultra" });
  assert.deepEqual(future.style.props, plain.style.props);
});

await check("the five buttons, private sources and limits are the PC's", async () => {
  assert.deepEqual(Object.entries(ACTIONS).map(([id, label]) => ({ id, label })), CASES.actions);
  assert.deepEqual([...PRIVATE_SOURCES].sort(), CASES.private_sources);
  assert.equal(HIDDEN_WORDS, CASES.hidden_words);
  assert.equal(LIMITS.blocks, CASES.limits.blocks);
  assert.equal(LIMITS.items, CASES.limits.items);
  assert.deepEqual(NEVER_HELD, ["stop_everything", "brief_me"]);
  const tiles = readRepo("jarvis-client/app/src/main/java/com/jarvis/client/data/QuickTiles.kt");
  for (const [id, label] of Object.entries(ACTIONS)) {
    assert.ok(tiles.includes(`("${id}", "${label}"`), `the tile ${id} is not "${label}"`);
  }
  const rs = readRepo("jarvis-desktop/src-tauri/src/brain/widgets.rs");
  for (const [id, label] of Object.entries(ACTIONS)) assert.ok(rs.includes(`("${id}", "${label}")`));
  assert.ok(rs.includes(`PRIVATE_HIDDEN: &str = "${HIDDEN_WORDS}"`));
  const py = readRepo("backend/jarvis_widgets.py");
  assert.ok(py.includes(`MISSING = ("Your PC's Jarvis cannot make widgets yet`) ||
    readRepo("backend/jarvis_quick.py").includes(MISSING.slice(0, 40)));
  assert.ok(rs.includes(MISSING.slice(0, 40)));
});

await check("nothing from the PC is ever parsed as HTML", async () => {
  const src = read("src/widget-board.js");
  assert.doesNotMatch(src.replace(/\/\*[\s\S]*?\*\//g, ""), /innerHTML|outerHTML|insertAdjacentHTML|eval\(|new Function/);
});

/* ── The Brain ─────────────────────────────────────────────────────────── */

const W = "w0123456789";
const SHOW = CASES.cases.morning.answer;
const ROW = { id: W, name: "Morning", said: "A widget called “Morning” showing …",
  parts: ["Heading: Good morning", "Button: 10-min timer"] };
const DRAFT = { id: "dabcdef0123", name: "Desk", said: "A widget called “Desk”.",
  parts: ["Button: Stop everything"] };
const NO_CARD = "No approval card: a widget only shows what Jarvis already shows you.";

const { base, close } = await K.serve();
const browser = await K.launch();

async function workTab(data = {}) {
  const page = await K.open(browser, base, "brain.html", data, { width: 1180, height: 900 });
  await page.locator("#tab-work").click();
  await page.waitForTimeout(500);
  return page;
}

await check("Brain: the widgets and previews, with Delete, Add and Discard", async () => {
  const page = await workTab({ widgets: { widgets: [ROW], drafts: [DRAFT], noCard: NO_CARD } });
  const text = await page.locator("#widgets").innerText();
  const del = await page.locator(`#widgets .row-item[data-id='${W}'] button`).allInnerTexts();
  const pre = await page.locator("#widgets .row-item[data-id='dabcdef0123'] button").allInnerTexts();
  await page.close();
  assert.ok(text.includes("Morning") && text.includes("Heading: Good morning"));
  assert.ok(text.toLowerCase().includes(PREVIEW_TITLE.toLowerCase()), "the preview heading");
  assert.ok(text.includes(NO_CARD), "why there is no card");
  assert.deepEqual(del, [DELETE_LABEL]);
  assert.deepEqual(pre, ["Discard", "Add"]);
});

await check("Brain: typed words make ONE preview; pasted words are sent as pasted", async () => {
  const page = await workTab({ widgets: { draft: DRAFT } });
  await page.locator("#widgets-words").fill("  my next 3   reminders ");
  await page.locator("#widgets-make").click();
  await page.waitForTimeout(500);
  await page.locator("#widgets-words").focus();
  await page.evaluate(() => {
    const box = document.getElementById("widgets-words");
    box.dispatchEvent(new Event("paste"));
    box.value = "make a widget from this email";
  });
  await page.locator("#widgets-make").click();
  await page.waitForTimeout(500);
  const calls = await page.evaluate(() => window.__widgetCalls.filter((c) => c.cmd === "brain_widgets_draft"));
  const text = await page.locator("#widgets").innerText();
  await page.close();
  assert.deepEqual(calls, [
    { cmd: "brain_widgets_draft", words: "my next 3 reminders", pasted: false },
    { cmd: "brain_widgets_draft", words: "make a widget from this email", pasted: true }]);
  assert.ok(text.includes("Desk"));
});

await check("Brain: Add keeps ONE preview, Delete removes ONE widget - asking nothing", async () => {
  const page = await workTab({ widgets: { widgets: [ROW], drafts: [DRAFT] } });
  let asked = false;
  page.on("dialog", (d) => { asked = true; d.dismiss(); });
  await page.locator("#widgets .row-item[data-id='dabcdef0123']").getByRole("button", { name: "Add" }).click();
  await page.waitForTimeout(500);
  await page.locator(`#widgets .row-item[data-id='${W}']`).getByRole("button", { name: "Delete" }).click();
  await page.waitForTimeout(500);
  const calls = await page.evaluate(() => window.__widgetCalls.filter((c) => c.cmd !== "widget_board"));
  await page.close();
  assert.equal(asked, false);
  // Add carries the look showing under the preview, which - with no look of
  // the draft's own - is the default: cyan, solid, normal.
  assert.deepEqual(calls, [{ cmd: "brain_widgets_add", draft: "dabcdef0123", ...LOOK_DEFAULT },
    { cmd: "brain_widgets_delete", id: W }]);
});

await check("Brain: Add and Delete are held on a stale link", async () => {
  const page = await workTab({ widgets: { widgets: [ROW], drafts: [DRAFT] }, link: { stale: true } });
  const add = await page.locator("#widgets .row-item[data-id='dabcdef0123']").getByRole("button", { name: "Add" }).isDisabled();
  const del = await page.locator(`#widgets .row-item[data-id='${W}'] button`).isDisabled();
  await page.close();
  assert.equal(add, true);
  assert.equal(del, true);
});

/* The draft's own shape and look, as the PC sends it in GET /api/widgets (a
   row carries its `blocks`, which is what readList turns into a view). */
const LOOKED_DRAFT = {
  ...DRAFT,
  layout: "stack",
  accent: "amber",
  shade: "half",
  contrast: "high",
  blocks: [
    { type: "title", text: "Desk" },
    { type: "number", source: "todo_count", private: false, label: "To do", value: "2" },
    { type: "button", action: "timer" },
  ],
};

await check("Brain: the preview is drawn from the draft, and the pickers repaint it live", async () => {
  const page = await workTab({ widgets: { drafts: [LOOKED_DRAFT] } });
  const row = page.locator("#widgets .row-item[data-id='dabcdef0123']");
  const card = row.locator(".board-blocks");
  const start = await card.evaluate((n) => ({
    accent: n.style.getPropertyValue("--board-accent"),
    bg: n.style.getPropertyValue("--board-bg"),
    text: n.textContent,
  }));
  const labels = await row.locator(".widgets-look .board-pick-label").allInnerTexts();
  const accents = await row.locator("select").first().locator("option").allInnerTexts();
  const picked = await row.locator("select").first().inputValue();
  // The three pickers, then the owner changes all three.
  await page.locator("#widgets-look-accent-dabcdef0123").selectOption("violet");
  await page.locator("#widgets-look-shade-dabcdef0123").selectOption("clear");
  await page.locator("#widgets-look-contrast-dabcdef0123").selectOption("normal");
  const changed = await card.evaluate((n) => ({
    accent: n.style.getPropertyValue("--board-accent"),
    bg: n.style.getPropertyValue("--board-bg"),
    surface: n.style.getPropertyValue("--board-surface"),
    bgA: n.style.getPropertyValue("--board-bg-a"),
  }));
  const stillText = await card.locator(".board-value").first().innerText();
  await page.close();
  // The draft's own look is what it starts in: amber, half, high.
  assert.equal(start.accent, ACCENTS.amber.hex);
  assert.equal(start.bg, CONTRASTS.high.colors.bg);
  assert.ok(start.text.includes("Desk") && start.text.includes("2"), start.text);
  assert.deepEqual(labels, ["Colour", "See-through", "Contrast"]);
  // The pickers offer the PC's own list, in its own words.
  assert.deepEqual(accents, CASES.accents.map((a) => a.label));
  assert.equal(picked, "amber");
  // Changed, and repainted through the same `paint()`: colour and alpha are
  // the look's, the words are still the draft's own.
  assert.equal(changed.accent, ACCENTS.violet.hex);
  assert.equal(changed.bg, CONTRASTS.normal.colors.bg);
  assert.equal(changed.surface, CONTRASTS.normal.colors.surface);
  assert.equal(changed.bgA, "0.502");
  assert.equal(stillText, "2");
});

await check("Brain: Add sends the look the owner chose under the preview", async () => {
  const page = await workTab({ widgets: { drafts: [LOOKED_DRAFT] } });
  await page.locator("#widgets-look-accent-dabcdef0123").selectOption("lime");
  await page.locator("#widgets-look-shade-dabcdef0123").selectOption("clear");
  await page.locator("#widgets-look-contrast-dabcdef0123").selectOption("high");
  await page.locator("#widgets .row-item[data-id='dabcdef0123']").getByRole("button", { name: "Add" }).click();
  await page.waitForTimeout(500);
  const calls = await page.evaluate(() => window.__widgetCalls.filter((c) => c.cmd === "brain_widgets_add"));
  await page.close();
  assert.deepEqual(calls, [{ cmd: "brain_widgets_add", draft: "dabcdef0123",
    accent: "lime", shade: "clear", contrast: "high" }]);
});

await check("Brain: the words are hidden with the private lists", async () => {
  const page = await workTab({ widgets: { widgets: [ROW] }, security: { hidden: true } });
  const text = await page.locator("#widgets-card").innerText();
  await page.close();
  assert.doesNotMatch(text, /Morning|Good morning/);
  assert.match(text, /Hidden until Windows Hello/);
});

await check("Brain: a hidden draft row draws no preview of its own", async () => {
  // While the private lists are hidden the PC blanks the row's blocks, so the
  // shape is gone - and a preview of nothing would be a card of empty panels.
  const page = await workTab({ widgets: { drafts: [{ ...LOOKED_DRAFT, blocks: [] }] } });
  const previews = await page.locator("#widgets .widgets-preview-block").count();
  await page.close();
  assert.equal(previews, 0);
});

await check("Brain: a PC without widgets hides the form and says so", async () => {
  const page = await workTab({});
  const hidden = await page.locator("#widgets-form").isHidden();
  const text = await page.locator("#widgets").innerText();
  await page.close();
  assert.equal(hidden, true);
  assert.ok(text.includes(MISSING));
  assert.ok(!text.includes(EMPTY));
});

/* ── The widget window ─────────────────────────────────────────────────── */

async function widgetWindow(data, choice = W) {
  const p = await K.open(browser, base, "widget.html",
    { prefs: { expanded: true }, ...data }, { width: 320, height: 520 });
  await p.evaluate((id) => { try { localStorage.setItem("jarvis.widgetBoard", id); } catch (e) { /* none */ } }, choice);
  await p.reload();
  await p.waitForTimeout(700);
  return p;
}

const BOARD = { widgets: { widgets: [ROW], shows: { [W]: SHOW } } };

await check("widget window: the chosen widget replaces the face, drawn as text", async () => {
  const hostile = JSON.parse(JSON.stringify(SHOW));
  hostile.blocks[0].text = "<img src=x onerror=window.__pwned=1>";
  const page = await widgetWindow({ widgets: { widgets: [ROW], shows: { [W]: hostile } } });
  const faceHidden = await page.locator("#face-wrap").isHidden();
  const text = await page.locator("#board-blocks").innerText();
  const imgs = await page.locator("#board-blocks img").count();
  const pwned = await page.evaluate(() => window.__pwned === 1);
  const buttons = await page.locator("#board-blocks button").allInnerTexts();
  // "big" (the morning case's arrangement): ONE number drawn large, still
  // holding its label and its value, and still just text.
  const big = await page.locator("#board-blocks .board-big").count();
  const bigText = big ? await page.locator("#board-blocks .board-big").innerText() : "";
  await page.close();
  assert.equal(faceHidden, true);
  assert.ok(text.includes("<img src=x"), "the tag is shown as words");
  assert.equal(imgs, 0);
  assert.equal(pwned, false);
  assert.ok(text.includes("412 GB free of 931 GB"));
  assert.deepEqual(buttons, ["10-min timer", "Stop everything"]);
  assert.equal(big, 1, "exactly one block is drawn large");
  assert.ok(bigText.includes("Unread email") && bigText.includes("4"), bigText);
});

await check("widget window: the widget's own look is what it is drawn in", async () => {
  // The fixture's `looked_widget` (violet accent, see-through, high contrast,
  // its first number drawn large): the properties reach the box the widget is
  // painted into, and board.css really reads them - the big number takes the
  // accent, the muted text takes the lifted muted colour, and the card is the
  // contrast's background at the shade's alpha.
  const page = await widgetWindow({ widgets: { widgets: [ROW],
    shows: { [W]: CASES.cases.looked_widget.answer } } });
  const got = await page.evaluate(() => {
    const card = document.getElementById("board-blocks");
    const big = card.querySelector(".board-big .board-value");
    const label = card.querySelector(".board-label");
    return {
      accent: card.style.getPropertyValue("--board-accent"),
      bg: card.style.getPropertyValue("--board-bg"),
      bigColor: big ? getComputedStyle(big).color : "",
      labelColor: label ? getComputedStyle(label).color : "",
      background: getComputedStyle(card).backgroundColor,
    };
  });
  await page.close();
  assert.equal(got.accent, ACCENTS.violet.hex);
  assert.equal(got.bg, CONTRASTS.high.colors.bg);
  assert.equal(got.bigColor, "rgb(191, 166, 255)", "the big number wears the accent");
  assert.equal(got.labelColor, "rgb(224, 224, 224)", "the muted text is the high contrast's");
  // `color-mix` makes Chromium answer in its own colour space, so the card is
  // checked for its colour and its alpha rather than for a spelling.
  assert.match(got.background, /^(rgba?\(0, 0, 0|color\(srgb 0 0 0)/, got.background);
  assert.ok(got.background.includes("0.502"), `the card is see-through: ${got.background}`);
});

await check("widget window: ONE widget_board_action per press", async () => {
  const page = await widgetWindow(BOARD);
  await page.locator("#board-blocks button[data-action='timer']").click();
  await page.waitForTimeout(300);
  const calls = await page.evaluate(() => window.__widgetCalls.filter((c) => c.cmd === "widget_board_action"));
  await page.close();
  assert.deepEqual(calls, [{ cmd: "widget_board_action", action: "timer" }]);
});

await check("widget window: a stale link holds all but Stop everything", async () => {
  const page = await widgetWindow({ ...BOARD, link: { stale: true } });
  const timer = await page.locator("#board-blocks button[data-action='timer']").isDisabled();
  const stop = await page.locator("#board-blocks button[data-action='stop_everything']").isDisabled();
  await page.close();
  assert.equal(timer, true);
  assert.equal(stop, false);
});

await check("widget window: App lock hides the private words, keeps counts", async () => {
  const page = await widgetWindow({ ...BOARD, appLock: true });
  const text = await page.locator("#board-blocks").innerText();
  await page.close();
  assert.doesNotMatch(text, /Call mum/);
  assert.ok(text.includes(HIDDEN_WORDS));
  assert.ok(text.includes("412 GB free of 931 GB"));
});

await check("widget window: under App lock the tiles open the Jarvis bar and do not act; Stop everything still works", async () => {
  const { LOCKED_OPENS_BAR } = await import("../src/widget-board.js");
  const page = await widgetWindow({ ...BOARD, appLock: true });
  const timer = page.locator("#board-blocks button[data-action='timer']");
  assert.equal(await timer.isDisabled(), false, "pressable: it opens the bar");
  await timer.click();
  await page.waitForTimeout(300);
  const flashText = (await page.locator("#widget-flash").innerText()).trim();
  const opened = await page.evaluate(() => window.__barOpened || 0);
  await page.locator("#board-blocks button[data-action='stop_everything']").click();
  await page.waitForTimeout(300);
  const stopFlash = (await page.locator("#widget-flash").innerText()).trim();
  await page.close();
  assert.equal(flashText, LOCKED_OPENS_BAR);
  assert.equal(opened, 1, "the Jarvis bar was opened, nothing set");
  assert.equal(stopFlash, "Stop everything sent.");
});

await check("Rust: under App lock the acting tiles only open the Jarvis bar, before anything is sent", async () => {
  const rs = readRepo("jarvis-desktop/src-tauri/src/brain/widgets.rs");
  const { LOCKED_OPENS_BAR } = await import("../src/widget-board.js");
  assert.ok(rs.includes(`"${LOCKED_OPENS_BAR}"`), "the same words in both");
  const body = rs.slice(rs.indexOf("pub async fn widget_board_action"));
  const lock = body.indexOf("opens_bar_when_locked(action) && crate::lock::current(&app).app_lock");
  assert.ok(lock > 0 && lock < body.indexOf("match action"), "checked before any action");
  assert.ok(body.slice(lock, lock + 300).includes("show_quickbar"));
});

await check("widget window: a block paints no panel; a button's fill and a bar's track do", async () => {
  // The phone paints no panel behind a block (JarvisBoardWidget.kt `Part` has
  // no background); its panel colour is a button's fill (`PillButton`) and a
  // bar's track (`LinearProgressIndicator(backgroundColor = Surface1)`), and
  // nothing else. The same described widget must not be two pictures.
  const page = await widgetWindow(BOARD);
  const got = await page.evaluate(() => {
    const card = document.getElementById("board-blocks");
    const bg = (n) => (n ? getComputedStyle(n).backgroundColor : "");
    return {
      blocks: [...card.querySelectorAll(".board-part")].map(bg),
      button: bg(card.querySelector(".board-button")),
      track: bg(card.querySelector(".meter-track")),
    };
  });
  await page.close();
  assert.ok(got.blocks.length >= 3, `blocks measured: ${got.blocks.length}`);
  for (const one of got.blocks) assert.equal(one, "rgba(0, 0, 0, 0)", `a block paints ${one}`);
  assert.notEqual(got.button, "rgba(0, 0, 0, 0)", "a button keeps the panel colour");
  assert.notEqual(got.track, "rgba(0, 0, 0, 0)", "a bar keeps the panel colour");
});

await check("widget window: board mode gives the window's backdrop away; face mode keeps it", async () => {
  // Face mode: widgets exist, none is chosen, so the face is drawn and the
  // window paints its own colour exactly as it always has.
  const face = await K.open(browser, base, "widget.html",
    { prefs: { expanded: true }, widgets: { widgets: [ROW] } }, { width: 320, height: 560 });
  await face.evaluate(() => { try { localStorage.removeItem("jarvis.widgetBoard"); } catch (e) { /* none */ } });
  await face.reload();
  await face.waitForTimeout(700);
  const faceMode = await face.evaluate(() => {
    const shell = document.getElementById("widget-shell");
    return { boardMode: shell.classList.contains("board-mode"),
      shell: getComputedStyle(shell).backgroundColor,
      face: !document.getElementById("face-wrap").hidden };
  });
  await face.close();

  // Board mode: the widget is drawn, so the shell and the tray between the
  // desktop and the card paint no colour at all - the card's own alpha is
  // what the owner sees. Everything that is not the card keeps its fill.
  const page = await widgetWindow({ widgets: { widgets: [ROW],
    shows: { [W]: CASES.cases.looked_widget.answer } } });
  const boardMode = await page.evaluate(() => {
    const shell = document.getElementById("widget-shell");
    const cs = (sel) => getComputedStyle(document.querySelector(sel)).backgroundColor;
    return { boardMode: shell.classList.contains("board-mode"),
      shell: getComputedStyle(shell).backgroundColor,
      tray: getComputedStyle(document.getElementById("widget-tray")).backgroundColor,
      card: cs("#board-blocks"),
      bar: cs(".widget-bar"),
      rows: cs("#tray-solid") };
  });
  await page.close();
  assert.equal(faceMode.face, true, "face mode is drawing the face");
  assert.equal(faceMode.boardMode, false);
  assert.match(faceMode.shell, /^rgba\(4, 7, 12/, `face mode paints ${faceMode.shell}`);
  assert.equal(boardMode.boardMode, true);
  assert.equal(boardMode.shell, "rgba(0, 0, 0, 0)", "the shell gives way");
  assert.equal(boardMode.tray, "rgba(0, 0, 0, 0)", "the tray gives way");
  // The card is the shade itself (clear + high contrast = half see-through).
  assert.ok(boardMode.card.includes("0.502"), `the card's own alpha: ${boardMode.card}`);
  // The compact bar and the rows below the widget keep their own colour, so
  // they read as they do in every other state.
  assert.match(boardMode.bar, /^rgba\(4, 7, 12/, `the bar keeps ${boardMode.bar}`);
  assert.match(boardMode.rows, /^rgba\(4, 7, 12/, `the rows keep ${boardMode.rows}`);
});

await check("widget window: no widgets, no picker - the face as before", async () => {
  const page = await widgetWindow({ widgets: { widgets: [] } }, "");
  const board = await page.locator("#board").isHidden();
  const face = await page.locator("#face-wrap").isVisible();
  await page.close();
  assert.equal(board, true);
  assert.equal(face, true);
});

await check("CONTROL: registered, allowed on the right window only, held in Rust", async () => {
  const lib = readRepo("jarvis-desktop/src-tauri/src/lib.rs");
  for (const c of ["brain_widgets", "brain_widgets_draft", "brain_widgets_add",
    "brain_widgets_discard", "brain_widgets_delete", "widget_board", "widget_board_action"]) {
    assert.ok(lib.includes(`brain::widgets::${c},`), c);
  }
  const brain = JSON.parse(readRepo("jarvis-desktop/src-tauri/capabilities/brain.json"));
  const widget = JSON.parse(readRepo("jarvis-desktop/src-tauri/capabilities/widget.json"));
  assert.ok(brain.permissions.includes("brain-widgets") && !brain.permissions.includes("widget-board"));
  assert.ok(widget.permissions.includes("widget-board") && !widget.permissions.includes("brain-widgets"));
  const rs = readRepo("jarvis-desktop/src-tauri/src/brain/widgets.rs");
  for (const f of ["brain_widgets_add", "brain_widgets_delete"]) {
    const body = rs.slice(rs.indexOf(`pub async fn ${f}`));
    assert.ok(body.slice(0, 300).includes("require_link_live(&app)?"), f);
  }
});

await browser.close();
await close();
if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join(", ")}`);
  process.exit(1);
}
console.log("\nall passed");
