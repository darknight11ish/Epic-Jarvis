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
  // Since the ease-of-use audit's do-first table, row 4 ("Things you can
  // say"), the primer's own kbd chips are gone - Settings -> Shortcuts
  // teaches those, live (see the three checks below) - but the note-app
  // prefixes are not keyboard shortcuts, so they stay here: this is still
  // their only in-app explanation.
  const page = await K.open(browser, base, "index.html", {});
  assert.equal(await page.locator("#primer").isVisible(), true,
    "the window opens with nothing on screen at all");
  const text = await page.locator("#primer").innerText();
  for (const key of ["Set a timer for 10 minutes.", "What did I miss?", "right-click the "
    + "Jarvis icon", "#log", "#joplin"]) {
    assert.ok(text.includes(key), `the primer never mentions ${key}`);
  }
  await page.close();
});

await check("tapping a sayable line fills the box and never sends", async () => {
  const page = await K.open(browser, base, "index.html", {});
  const items = page.locator(".sayable-item");
  const first = await items.first().textContent();
  await items.first().click();
  const value = await page.locator("#prompt").inputValue();
  assert.equal(value, first, "the tap did not fill the box with its own sentence");
  const calls = await page.evaluate(() => window.__calls.map((c) => c[0]));
  assert.ok(!calls.includes("stream_chat"),
    "tapping a sayable line sent a turn instead of only filling the box");
  await page.close();
});

await check("Settings -> Shortcuts names the hotkeys Rust actually binds", async () => {
  // The first version of the bar's own primer said Alt+Shift+N attached the
  // clipboard. `hotkeys.rs` binds that to the Logseq note and Super+Shift+J
  // to the clipboard, so the primer built to stop the app lying was lying -
  // and no test could have caught it, because it checked the copy against
  // itself. This checks Settings -> Shortcuts (where the live list moved
  // to, row 4 above) against the action table instead.
  const rust = readFileSync(join(HERE, "..", "src-tauri", "src", "hotkeys.rs"), "utf8");
  const defaults = [...rust.matchAll(/default:\s*"([^"]+)"/g)]
    .map((m) => m[1].replace(/\bSuper\b/, "Win").replace(/\bControl\b/, "Ctrl")
      .split("+").map((p) => p.trim()).join(" + "));
  assert.ok(defaults.length >= 5, `only found ${defaults.length} default bindings`);

  const page = await K.open(browser, base, "settings.html", {});
  const shown = await page.evaluate(() =>
    [...document.querySelectorAll("#hotkey-rows .hotkey-key")]
      .map((k) => k.textContent.trim()));
  await page.close();

  for (const combo of defaults) {
    assert.ok(shown.includes(combo),
      `${combo} is a shipped binding and Shortcuts does not list it (it lists ${shown.join(", ")})`);
  }
});

await check("Settings -> Shortcuts follows a rebind instead of hardcoding one", async () => {
  // The bindings are configurable, so a fixed list in the markup would be
  // wrong from the first change - the same failure this page was built to fix.
  const page = await K.open(browser, base, "settings.html", {
    hotkeys: K.HOTKEYS.map((h) =>
      h.id === "toggle_quickbar" ? { ...h, accelerator: "Control+Alt+Backquote" } : h),
  });
  await page.waitForTimeout(400);
  const shown = await page.evaluate(() =>
    [...document.querySelectorAll("#hotkey-rows .hotkey")]
      .find((row) => row.querySelector(".hotkey-name")?.textContent === "Show or hide the "
        + "Jarvis bar")?.querySelector(".hotkey-key")?.textContent);
  await page.close();
  assert.equal(shown, "Ctrl + Alt + Backquote", `Shortcuts still shows "${shown}"`);
});

await check("a refused binding is marked in Settings -> Shortcuts, in words", async () => {
  const page = await K.open(browser, base, "settings.html", {
    hotkeys: K.HOTKEYS.map((h) =>
      h.id === "toggle_quickbar" ? { ...h, registered: false, error: "taken" } : h),
  });
  await page.waitForTimeout(400);
  const text = await page.evaluate(() =>
    [...document.querySelectorAll("#hotkey-rows .hotkey")]
      .find((row) => row.querySelector(".hotkey-name")?.textContent === "Show or hide the "
        + "Jarvis bar")?.querySelector(".hotkey-state")?.textContent);
  await page.close();
  // A state word that looks like the working ones and does nothing is worse
  // than no state word at all.
  assert.match(text, /in use/i, `said "${text}"`);
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
  // of them before the request had even left. Since 2026-09-25 the word is
  // the plain "Answering…" (plain-errors.js STATUSES), never "Streaming".
  assert.ok(!/"Streaming"/.test(main), "the developer word Streaming is back");
  const premature = main.match(/textContent = STATUSES\.answering/g) || [];
  assert.equal(premature.length, 1,
    `"Answering…" is set in ${premature.length} places; it belongs in exactly one`);
  assert.match(main, /if \(!state\.chunks\) dom\.cardStatusText\.textContent = STATUSES\.answering;/,
    "the label no longer waits for the first chunk");
  assert.ok(!/chunks · /.test(main), "the card counts chunks again");
});

/* ── The widget does not claim to have filed anything ────────────────────── */

await check("a capture says filed only when the PC says so", async () => {
  // It used to ask a model to call a tool that did not exist, so the widget
  // could only say "Sent". Now the words come from the backend's answer
  // (note-capture.patch), and the widget has no sentence of its own that
  // claims a note landed.
  const widget = read("src/widget.js");
  assert.ok(!/Filed to Joplin|Appended to Logseq|Sent to \$\{where\}/.test(widget),
    "the widget still writes its own claim about where the note went");
  assert.match(widget, /fileNote\(invokeStrict/, "the widget no longer uses the shared filer");
  const filer = read("src/note-capture.js");
  assert.match(filer, /capture_note_status/, "a waiting card is never followed up");
});

await check("the capture goes to the notes route, not a chat turn", async () => {
  const rust = read("src-tauri/src/commands.rs");
  const i = rust.indexOf("pub async fn capture_note(");
  const body = rust.slice(i, rust.indexOf("\n}\n", i));
  assert.match(body, /\/api\/notes\/capture/, "capture_note does not post to /api/notes/capture");
  assert.ok(!/\/api\/chat/.test(body), "capture_note still runs a chat turn");
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
  // Since backend/power-mode.patch the mode CAN be set, so the row no longer
  // says read-only - and the three modes are live items instead.
  assert.ok(!/format!\("Power: \{\}\{by\} · read-only"/.test(tray), "the power row still claims it cannot be set");
  assert.match(tray, /ID_POWER_STANDBY/, "there is no way to choose a power mode");
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
