/**
 * brain-settings-door.mjs - the Settings door in the Brain window.
 *
 * The owner asked (2026-10-05): "can you put a settings option in the direct
 * jarvis program? It shouldn't be limited to just right clicking the jarvis
 * tray icon".
 *
 * Before this, every door to Settings was either outside the program or
 * conditional, and none of them opened Settings at its TOP:
 *
 *   - the tray icon's "Settings and help…" row (tray.rs ID_SETTINGS);
 *   - the Jarvis bar's jump list / "open <a settings section>"
 *     (main.js openSettingsFromRoute, which always names a section);
 *   - the rail's "N hidden" button (brain.js `btn-rail-hidden-menus`), which
 *     is only on screen while at least one menu IS hidden, and which lands on
 *     "menu-visibility" rather than the top;
 *   - pull request #69's command palette, whose own `entry.settings` row
 *     hardcodes `place: "connection"` - a section again, not the top.
 *
 * So this suite guards the one thing that was missing: a plain, always-there
 * control that opens Settings the way the tray row does. It reads the two
 * files rather than driving a browser, so it runs under plain Node like
 * tests/menu-visibility.mjs and the source-reading halves of security.mjs.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (f) => readFileSync(join(HERE, "..", "src", f), "utf8");

const fails = [];
const check = async (name, fn) => {
  try {
    await fn();
    console.log(`ok    ${name}`);
  } catch (e) {
    fails.push(name);
    console.log(`FAIL  ${name}\n      ${e.message}`);
  }
};

const html = read("brain.html");
const js = read("brain.js");

/** The whole `<button …>…</button>` whose opening tag carries `id="ID"`. */
function button(id) {
  const open = new RegExp(`<button\\b[^>]*\\bid="${id}"[^>]*>`).exec(html);
  assert.ok(open, `no <button id="${id}"> in brain.html`);
  const end = html.indexOf("</button>", open.index);
  assert.ok(end > open.index, `the ${id} button is never closed`);
  return { tag: open[0], all: html.slice(open.index, end + "</button>".length) };
}

/** The body of `$("ID")?.addEventListener("click", …)` in brain.js. */
function clickHandler(id) {
  const at = js.indexOf(`$("${id}")`);
  assert.ok(at >= 0, `brain.js has no click listener for ${id}`);
  const body = js.indexOf("click", at);
  assert.ok(body > at && body - at < 80, `${id}'s listener is not a click listener`);
  // To the next top-level `});` at the same indent, which is where this one ends.
  const end = js.indexOf("\n});", body);
  assert.ok(end > body, `${id}'s listener is never closed`);
  return js.slice(at, end);
}

/* ── The door is in the window ───────────────────────────────────────────── */

await check("the Brain has a Settings button in its top bar", () => {
  const { tag } = button("open-settings");
  // It must be a real, ordinary button: no `hidden` in its own markup, so it
  // is on screen the moment the Brain opens. That is the whole point - the
  // rail's "N hidden" button a few lines below it IS hidden, and correctly so.
  assert.doesNotMatch(tag, /\bhidden\b/, "the Settings button starts hidden");
  assert.doesNotMatch(tag, /\bdisabled\b/, "the Settings button starts disabled");
});

await check("the Settings button is keyboard-reachable with a real name", () => {
  const { tag, all } = button("open-settings");
  // Reachable: a <button type="button"> with no `tabindex="-1"`. `disabled`
  // and `hidden` are checked above too, since both drop it from the tab order.
  assert.match(tag, /type="button"/, "the Settings door is not a plain button");
  assert.doesNotMatch(tag, /tabindex="-1"/, "the Settings door is skipped by Tab");
  // A real accessible name, from the visible label itself - not a title
  // attribute, not a glyph, and not nothing.
  const label = all.replace(new RegExp(`^${tag.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`), "")
    .replace("</button>", "")
    .replace(/<[^>]*>/g, "")
    .replace(/<!--[\s\S]*?-->/g, "")
    .trim();
  assert.equal(label, "Settings", `the door's accessible name is "${label}", not "Settings"`);
});

await check("the Settings button looks like the window's own controls", () => {
  // `btn ghost` is what Refresh and Reconnect in the same top bar use, so the
  // door needs no new CSS and no colour literal of its own (the reuse rule
  // scripts/check-tokens.py enforces). This is also what makes the new suite
  // fail loudly rather than silently if someone restyles it inline.
  const { tag } = button("open-settings");
  assert.match(tag, /class="[^"]*\bbtn\b[^"]*"/, "the Settings door is not a .btn");
  assert.match(tag, /class="[^"]*\bghost\b[^"]*"/, "the Settings door is not a .btn.ghost");
  assert.doesNotMatch(tag, /style=/, "the Settings door carries its own colours");
});

/* ── The door opens Settings the way every other door does ───────────────── */

await check("the Settings door reuses the existing command and place key", () => {
  const body = clickHandler("open-settings");
  // The same command the tray-to-rail button below it, the Jarvis bar and
  // plain-errors.js's own fix buttons all use. no new Tauri command, and so
  // no new capability or invoke grant.
  assert.match(body, /invoke\(\s*"open_fix_place"\s*,\s*\{\s*place:\s*"settings"\s*\}\s*\)/,
    "the door does not open Settings through open_fix_place");
  // "settings" is the only place plain_errors.rs's open_fix_place accepts for
  // the Settings window, and it is what opens the window itself. No place key
  // is written, so settings.js's goToPlace() has nothing to jump to and
  // Settings opens at the TOP - exactly where the tray row leaves it.
  const writes = /localStorage\.setItem/.test(body);
  assert.equal(writes, false, "the door leaves a place behind, so it lands on a section, not the top");
});

await check("the browser preview still reaches Settings", () => {
  // brain.html opens in a plain browser for the preview and the UI suites,
  // where there is no Tauri to invoke. Every other door in this file handles
  // that; a door that only works inside the packaged app is half a door.
  const body = clickHandler("open-settings");
  assert.match(body, /IS_TAURI/, "the door does not check whether Tauri is there");
  assert.match(body, /settings\.html/, "the door has no browser-preview fallback");
});

/* ── App lock: one gate, every door through it ───────────────────────────── */

await check("App lock covers this door, in Rust, for every door at once", () => {
  // The door must NOT try to re-check the lock itself: the check lives in
  // windows::show_settings (lock.rs may_open, Covered::Settings), which asks
  // Windows Hello and shows the window once the owner confirms. Every caller
  // of open_fix_place -> show_settings therefore gets the identical answer,
  // which is what keeps the lock from having a laxest door. This asserts the
  // door stays out of it AND that the single gate is still the one in Rust.
  // Comments stripped first: the door's own comment NAMES may_open and the
  // lock deliberately, to say why it does not call them. Only running code
  // counts - the same trap tests/security.mjs avoids on the Rust side.
  const code = clickHandler("open-settings")
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .replace(/\/\/[^\n]*/g, " ");
  assert.doesNotMatch(code, /Windows Hello|windows_hello|may_open|app_lock|verify_owner/,
    "the door re-implements the lock instead of going through Rust's one gate");

  const lock = readFileSync(join(HERE, "..", "src-tauri", "src", "lock.rs"), "utf8");
  assert.match(lock, /Covered::Settings => crate::windows::show_settings_unlocked\(app\)/,
    "the single lock gate no longer opens Settings for Covered::Settings");

  const win = readFileSync(join(HERE, "..", "src-tauri", "src", "windows.rs"), "utf8");
  const at = win.indexOf("pub fn show_settings(");
  assert.ok(at >= 0, "windows.rs has no show_settings");
  assert.match(win.slice(at, at + 400),
    /crate::lock::may_open\(app, crate::lock::Covered::Settings\)/,
    "show_settings no longer asks the app lock");
});

/* ── Kept honest: the conditional rail door is still conditional ─────────── */

await check("the rail's hidden-menus door is still only for hidden menus", () => {
  // Both doors live in this window now, so it is worth pinning the difference:
  // the rail one is gated on something being hidden and lands on
  // "menu-visibility"; the top-bar one is always there and lands at the top.
  const { tag } = button("btn-rail-hidden-menus");
  assert.match(tag, /title="Show or hide menus"/, "the rail door changed meaning");
  const wrap = html.slice(0, html.indexOf(`id="btn-rail-hidden-menus"`));
  assert.match(wrap.slice(wrap.lastIndexOf("<div")), /\bhidden\b/,
    "the rail door is no longer gated by its hidden wrapper");
  const railBody = clickHandler("btn-rail-hidden-menus");
  assert.match(railBody, /"menu-visibility"/, "the rail door no longer names its own place");
});

await browserlessClose();

function browserlessClose() {
  console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nthe Settings door is in the Brain");
  process.exit(fails.length ? 1 : 0);
}
