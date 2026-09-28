/**
 * "Widgets you describe" (the owner's choice of 2026-09-28, the SAFE
 * version; JARVIS-API.md section 87; src/widget-board.js, brain.js
 * paintWidgets, widget.js "Your widget", src-tauri/src/brain/widgets.rs;
 * backend jarvis_widgets.py).
 *
 * What must hold:
 * - the drawing rule is the PC's and the phone's, case for case
 *   (fixtures/widget-cases.json, tools/gen_widget_cases.py): an unknown
 *   block or button is left out, an unknown source is private, sizes are
 *   capped, and private words go while hidden;
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
  ACTIONS,
  DELETE_LABEL,
  EMPTY,
  hideView,
  HIDDEN_WORDS,
  LIMITS,
  MISSING,
  NEVER_HELD,
  PREVIEW_TITLE,
  PRIVATE_SOURCES,
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
  assert.deepEqual(calls, [{ cmd: "brain_widgets_add", draft: "dabcdef0123" },
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

await check("Brain: the words are hidden with the private lists", async () => {
  const page = await workTab({ widgets: { widgets: [ROW] }, security: { hidden: true } });
  const text = await page.locator("#widgets-card").innerText();
  await page.close();
  assert.doesNotMatch(text, /Morning|Good morning/);
  assert.match(text, /Hidden until Windows Hello/);
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
  await page.close();
  assert.equal(faceHidden, true);
  assert.ok(text.includes("<img src=x"), "the tag is shown as words");
  assert.equal(imgs, 0);
  assert.equal(pwned, false);
  assert.ok(text.includes("412 GB free of 931 GB"));
  assert.deepEqual(buttons, ["10-min timer", "Stop everything"]);
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
