/**
 * The Jarvis bar's own chrome (the owner's requests of 2026-10-10):
 *
 *   "any jarvis shortcut bar should be able to be hidden with a button on the
 *    bar itself"
 *   "i should be able to access settings on the desktop program easily too,
 *    there should be a settings symbol button"
 *
 * And the toggle half of the same day's requests, in Rust: "open jarvis bar in
 * the main desktop jarvis program should also hide it if it is clicked again
 * after it pops up" - the notification-area icon's left click now goes through
 * the one toggle every other route uses, instead of an unconditional show.
 *
 * WHY THIS TEST READS THE FILES INSTEAD OF DRIVING A BROWSER
 * The properties being checked are all structural: which control exists, which
 * command it names, and whether that command is granted to that window. The
 * Playwright suites (tests/a11y.mjs and friends) own what these things LOOK
 * like and how they behave against a live page. Reading the real files here
 * means this runs in CI with no browser and catches the failure that actually
 * bites in this app - a control wired to a command no window is allowed to
 * call, which is silent at runtime and invisible at compile time
 * (tools/check_invoke_grants.py's own reason for existing).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
const TAURI = join(HERE, "..", "src-tauri");

const read = (p) => readFileSync(p, "utf8");
const indexHtml = read(join(SRC, "index.html"));
const mainJs = read(join(SRC, "main.js"));
const widgetHtml = read(join(SRC, "widget.html"));
const widgetJs = read(join(SRC, "widget.js"));
const surfaces = read(join(TAURI, "permissions", "surfaces.toml"));
const widgetCap = read(join(TAURI, "capabilities", "widget.json"));
const trayRs = read(join(TAURI, "src", "tray.rs"));
const windowsRs = read(join(TAURI, "src", "windows.rs"));

const fails = [];
const check = (name, fn) => {
  try { fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/** The text of one `if (dom.x) { ... }` block, by the file it lives in. */
function blockFor(source, marker, span = 700) {
  const at = source.indexOf(marker);
  assert.notEqual(at, -1, `${marker} is not in the file`);
  return source.slice(at, at + span);
}

/* ── The bar's settings button ───────────────────────────────────────────── */

check("index.html has a settings button on the bar", () => {
  assert.match(indexHtml, /id="open-settings"/, "no #open-settings on the bar");
  assert.match(indexHtml, /<span class="sr-only">Jarvis settings<\/span>/,
    "the gear needs a name for a screen reader");
});

check("the gear calls the command this window already holds", () => {
  const block = blockFor(mainJs, "if (dom.openSettings)");
  assert.match(block, /invoke\("open_fix_place",\s*\{\s*place:\s*"settings"\s*\}\)/,
    "the gear must call open_fix_place with place: settings");
  assert.doesNotMatch(block, /invoke\("(open_settings|show_settings)"/,
    "there is no such command; a new name would be refused by the ACL");
});

check("main.js knows the gear's element", () => {
  assert.match(mainJs, /openSettings:\s*\$\("open-settings"\)/,
    "dom.openSettings must be looked up");
});

/* ── The bar's hide button ───────────────────────────────────────────────── */

check("index.html has a hide button on the bar", () => {
  assert.match(indexHtml, /id="hide-bar"/, "no #hide-bar on the bar");
  assert.match(indexHtml, /<span class="sr-only">Hide the Jarvis bar<\/span>/,
    "the hide button needs a name for a screen reader");
});

check("the hide button calls hide_quickbar - the same command Esc runs", () => {
  const block = blockFor(mainJs, "if (dom.hideBar)");
  assert.match(block, /invoke\("hide_quickbar"\)/,
    "the × must call hide_quickbar");
});

check("main.js knows the hide button's element", () => {
  assert.match(mainJs, /hideBar:\s*\$\("hide-bar"\)/,
    "dom.hideBar must be looked up");
});

/* ── Both grants really exist, for the window that calls them ────────────── */

check("the quickbar window is granted both commands", () => {
  // `quickbar-surface` is the set the quickbar's capability pulls in; both
  // permissions live in it (check_invoke_grants.py is the stronger check, and
  // this says so at the point a reader is looking).
  const quickbarSet = surfaces.slice(
    surfaces.indexOf('identifier = "quickbar-surface"'),
    surfaces.indexOf('identifier = "memory-used"'),
  );
  assert.match(quickbarSet, /"allow-hide-quickbar"/, "allow-hide-quickbar is not granted");
  assert.match(quickbarSet, /"allow-open-fix-place"/, "allow-open-fix-place is not granted");
});

/* ── The widget's gear, and the grant it needed ──────────────────────────── */

check("widget.html has a settings button on its own bar", () => {
  assert.match(widgetHtml, /id="btn-settings"/, "no #btn-settings on the widget bar");
  assert.match(widgetHtml, /<span class="sr-only">Jarvis settings<\/span>/,
    "the widget's gear needs a name for a screen reader");
});

check("the widget's gear calls open_fix_place", () => {
  const block = blockFor(widgetJs, "if (dom.btnSettings)", 500);
  assert.match(block, /invoke\("open_fix_place",\s*\{\s*place:\s*"settings"\s*\}\)/,
    "the widget's gear must call open_fix_place");
  assert.match(widgetJs, /btnSettings:\s*\$\("btn-settings"\)/,
    "dom.btnSettings must be looked up");
});

check("the widget's window is granted the command its own card already used", () => {
  // The widget's offline card has invoked open_fix_place since it was written
  // and every one of those taps was refused, because this surface never held
  // the permission. Both halves are checked: the set lists it, and the
  // capability pulls the set in.
  const widgetSet = surfaces.slice(
    surfaces.indexOf('identifier = "widget-surface"'),
    surfaces.indexOf('identifier = "settings-surface"'),
  );
  assert.match(widgetSet, /"allow-open-fix-place"/, "widget-surface does not grant it");
  assert.match(widgetCap, /"open-fix-place"/, "widget.json does not pull the set in");
});

/* ── The toggle: the tray icon no longer only shows ─────────────────────── */

check("the notification-area icon toggles the bar, it does not only show it", () => {
  const at = trayRs.indexOf("fn handle_tray_icon_event");
  assert.notEqual(at, -1, "handle_tray_icon_event is gone from tray.rs");
  const body = trayRs.slice(at, trayRs.indexOf("\n}\n", at));
  assert.match(body, /windows::toggle_quickbar\(app\)/,
    "the icon's left click must toggle (the owner's request of 2026-10-10)");
  assert.doesNotMatch(body, /windows::show_quickbar\(app\)/,
    "an unconditional show is what made a second click do nothing");
});

check("the menu row and the icon go through the same toggle", () => {
  const row = trayRs.slice(
    trayRs.indexOf("ID_TOGGLE_SPOTLIGHT =>"),
    trayRs.indexOf("ID_TOGGLE_WIDGET =>"),
  );
  assert.match(row, /windows::toggle_quickbar\(app\)/,
    "the tray menu's Show/Hide row must still toggle");
});

check("the toggle puts the caret in the bar itself, so every route agrees", () => {
  // The icon's click used to be the one route that did NOT (lib.rs emitted the
  // focus event for the hotkey only). windows.rs's toggle now does it for
  // everyone, and this is that line.
  const at = windowsRs.indexOf("pub fn toggle_quickbar");
  assert.notEqual(at, -1, "toggle_quickbar is gone from windows.rs");
  const body = windowsRs.slice(at, windowsRs.indexOf("\n}\n", at));
  assert.match(body, /focus_quickbar_input\(app\)/,
    "the toggle must place the caret, or the tray-summoned bar is not ready to type in");
  assert.match(windowsRs, /pub fn focus_quickbar_input/,
    "focus_quickbar_input must exist");
});

console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nall checks passed");
process.exit(fails.length ? 1 : 0);
