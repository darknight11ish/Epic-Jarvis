/**
 * The information-architecture findings, pinned down.
 *
 * Every one of these is a thing the UI *said* that was not true, or a thing it
 * could do that no one could reach. Neither kind produces an error, a warning
 * or a failing build — which is exactly why they need a test each.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");

const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const OFFLINE = { connected: false, error: "connection refused. Is jarvis_hud.py running?" };

/* ── The primer: the window says what it can do before you use it ────────── */

await check("a first run shows what the bar can do", async () => {
  const page = await K.open(browser, base, "index.html", {});
  assert.equal(await page.locator("#primer").isVisible(), true,
    "the window opens with nothing on screen at all");
  const text = await page.locator("#primer").innerText();
  for (const key of ["Alt", "Space", "#log", "#joplin"]) {
    assert.ok(text.includes(key), `the primer never mentions ${key}`);
  }
  await page.close();
});

await check("the primer gets out of the way", async () => {
  const page = await K.open(browser, base, "index.html", { pending: [K.APPROVAL_RAISED] });
  // A gate is open: the primer is the least important thing on screen.
  assert.equal(await page.locator("#approval").isVisible(), true);
  assert.equal(await page.locator("#primer").isVisible(), false,
    "the primer is still taking space under an open gate");
  await page.close();
});

await check("the hotkeys are no longer only in the card footer", async () => {
  // The four-key strip used to live inside `#card`, which is `hidden` until an
  // answer has streamed: the only way to learn a hotkey was to already know one.
  const html = read("src/index.html");
  const footer = html.slice(html.indexOf('class="keys"'), html.indexOf('class="keys"') + 400);
  assert.ok(!/Alt<\/kbd>\+<kbd>Space/.test(footer),
    "the summon hotkey is still hidden inside the answer card");
});

/* ── Offline is a place you can leave ────────────────────────────────────── */

await check("the spotlight offers a way back when the link is down", async () => {
  const page = await K.open(browser, base, "index.html", { link: OFFLINE });
  assert.equal(await page.locator("#offline").isVisible(), true,
    "offline is still reported without being actionable");
  assert.match(await page.locator("#offline-text").innerText(), /not answering/i);
  await page.locator("#offline-retry").click();
  const calls = await page.evaluate(() => window.__calls.map((c) => c[0]));
  assert.ok(calls.includes("refresh_link"), "Reconnect does not reconnect");
  await page.close();
});

await check("the offline bar is absent while the link is up", async () => {
  const page = await K.open(browser, base, "index.html", {});
  assert.equal(await page.locator("#offline").isVisible(), false);
  await page.close();
});

await check("the widget offers a way back too", async () => {
  const page = await K.open(browser, base, "widget.html", { link: OFFLINE }, { width: 320, height: 420 });
  assert.equal(await page.locator("#widget-offline").isVisible(), true,
    "the widget reports offline and offers nothing");
  await page.locator("#widget-offline-retry").click();
  const calls = await page.evaluate(() => window.__calls.map((c) => c[0]));
  assert.ok(calls.includes("refresh_link"), "the widget's Reconnect does not reconnect");
  await page.close();
});

/* ── The badge does not name a model it has not been told ────────────────── */

await check("the route badge starts with no model name", async () => {
  const page = await K.open(browser, base, "index.html", {});
  assert.equal(await page.locator("#route-model").isVisible(), false,
    "the badge is asserting a model before the server has named one");
  assert.equal(await page.locator("#route-tier").innerText(), "Local");
  await page.close();
});

await check("no hard-coded model name survives in the source", async () => {
  // "qwen3:8b" was the default. It is a guess about someone else's machine.
  const main = read("src/main.js");
  const html = read("src/index.html");
  assert.ok(!/DEFAULT_ROUTE = \{[^}]*model: "/.test(main), "the default route names a model");
  assert.ok(!/CLOUD_ROUTE = \{[^}]*model: "/.test(main), "the cloud route names a model");
  assert.ok(/id="route-model"[^>]*><\/span>/.test(html), "the badge ships with a model in the markup");
});

/* ── "Thinking…" means thinking ──────────────────────────────────────────── */

await check("the card says Thinking until a token actually arrives", async () => {
  const main = read("src/main.js");
  // Both transports used to label the card "Streaming" before any token — one
  // of them before the request had even left.
  const premature = main.match(/textContent = "Streaming"/g) || [];
  assert.equal(premature.length, 1,
    `"Streaming" is set in ${premature.length} places; it belongs in exactly one`);
  assert.match(main, /if \(!state\.chunks\) dom\.cardStatusText\.textContent = "Streaming";/,
    "the label no longer waits for the first chunk");
});

/* ── The widget does not claim to have filed anything ────────────────────── */

await check("a capture says it was sent, never that it was filed", async () => {
  const widget = read("src/widget.js");
  assert.ok(!/Filed to Joplin|Appended to Logseq/.test(widget),
    "the widget still claims a note landed, which it cannot know");
  assert.match(widget, /Sent to \$\{where\}/, "the widget no longer says what it did");
});

await check("the capture shows Jarvis's own account of what it did", async () => {
  const rust = read("src-tauri/src/commands.rs");
  assert.match(rust, /fn assistant_reply/,
    "capture_note returns a raw body rather than the model's answer");
  assert.match(rust, /tool-execution receipt/,
    "nothing records WHY a 200 is not a receipt");
});

/* ── The tray ────────────────────────────────────────────────────────────── */

await check("the brief is reachable when nothing is pending", async () => {
  const tray = read("src-tauri/src/tray.rs");
  assert.ok(!/ID_WAITING,\s*\n\s*waiting_label\(&link\),\s*\n\s*link\.attention\.pending > 0/.test(tray),
    "the brief is still gated on pending > 0, which is when it is least reachable");
  assert.match(tray, /link\.attention\.known,/, "the row is not enabled on a known count");
  assert.match(tray, /rows\.waiting\.set_enabled/, "the row never re-enables as state changes");
});

await check("the permanently dead power row is gone", async () => {
  const tray = read("src-tauri/src/tray.rs");
  assert.ok(!/the server exposes no route yet/.test(tray),
    "a row that can never do anything is still spending a line of the menu");
  assert.match(tray, /read-only/, "the power row no longer says it cannot be set");
});

await check("the menu is sentence case and grouped", async () => {
  const tray = read("src-tauri/src/tray.rs");
  for (const gone of ['"Show HUD Window"', '"Toggle Spotlight"', '"Toggle Widget"', '"Status Check"']) {
    assert.ok(!tray.includes(gone), `${gone} is still Title Case`);
  }
  // Five groups: status / waiting / windows / machinery / quit.
  const menu = tray.slice(tray.indexOf("let menu = Menu::with_items"), tray.indexOf("app.state::<TrayHandles>"));
  const seps = (menu.match(/PredefinedMenuItem::separator/g) || []).length;
  assert.equal(seps, 4, `the menu has ${seps} separators; five groups need four`);
});

/* ── The widget can be used without a mouse ──────────────────────────────── */

await check("showing the widget gives it the keyboard", async () => {
  const windows = read("src-tauri/src/windows.rs");
  const show = windows.slice(windows.indexOf("pub fn toggle_widget"));
  assert.match(show.slice(0, 1600), /set_focus\(\)/,
    "the widget is skipTaskbar and focus:false, so nothing ever gives it the keyboard");
});

await check("Escape leaves the widget, and the field keeps its own Escape", async () => {
  const widget = read("src/widget.js");
  assert.match(widget, /invoke\("hide_widget"\)/, "there is no keyboard way out of the widget");
  assert.match(widget, /if \(event\.target === dom\.captureInput\) return;/,
    "Escape mid-note throws the writer out of the window");
});

await check("no hotkey answers an approval gate", async () => {
  // The one rule this window must not break: a gate is never one keystroke away.
  const widget = read("src/widget.js");
  const handler = widget.slice(widget.indexOf('window.addEventListener("keydown"'));
  const block = handler.slice(0, handler.indexOf("\n});"));
  assert.ok(!/decide\(/.test(block), "a keystroke answers a gate");
});

/* ── Controls ────────────────────────────────────────────────────────────── */

await check("CONTROL: the gate still opens and still needs two deliberate acts", async () => {
  const page = await K.open(browser, base, "index.html", { pending: [K.APPROVAL_RAISED] });
  assert.equal(await page.locator("#approval").isVisible(), true);
  await page.keyboard.press("Enter");
  const calls = await page.evaluate(() => window.__calls.map((c) => c[0]));
  assert.ok(!calls.includes("decide_approval"), "Enter answered a gate");
  await page.close();
});

await check("CONTROL: no page threw while any of this ran", async () => {
  for (const file of ["index.html", "widget.html"]) {
    const page = await K.open(browser, base, file, { link: OFFLINE });
    assert.deepEqual(page.__errors, [], `${file}: ${page.__errors.join(" | ")}`);
    await page.close();
  }
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nall IA findings held");
process.exit(fails.length ? 1 : 0);
