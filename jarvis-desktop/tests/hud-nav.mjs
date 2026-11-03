/**
 * The F6 navigation and multi-window surface, held to the code it names.
 *
 *   node tests/hud-nav.mjs
 *
 * WHAT THIS PINS, without a browser and without a window:
 *
 *   - the areas the injected HUD chrome can switch are the areas the Rust
 *     table can send (one table, two languages - they cannot drift);
 *   - a chat window's labels are the fixed set `chat_windows.rs` declares, and
 *     the HUD capability really covers them (`chat-*`), because a window with
 *     no capability has no commands at all;
 *   - the SAME conversation in two windows is a focus, never a second window
 *     (the dedupe function and its map are in Rust and are unit-tested there;
 *     this file only checks the page asks for the right command);
 *   - this window, and only this window, opens the conversation it was asked
 *     for - through the page's EXISTING `/api/history/conversation?id=` read,
 *     not a new route;
 *   - navigation has no `ui.navigate` stream listener, because the backend
 *     publishes no such event (the F6 research correction): it rides the
 *     existing per-answer `X-Jarvis-Route` path, extended with
 *     `open_area`/`open_anchor`;
 *   - the Update button really runs both halves, and the version handshake
 *     reads the backend's real `version.app_version` block;
 *   - `/api/self` and `/api/conversations` are on the HUD's fixed read
 *     allowlist, so a page that asks cannot be refused by its own proxy.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
const TAURI = join(HERE, "..", "src-tauri");
const read = (file) => readFileSync(file, "utf8");

const BOOT = read(join(TAURI, "src", "hud_bootstrap.js"));
const NAV_RS = read(join(TAURI, "src", "hud_nav.rs"));
const CHAT_RS = read(join(TAURI, "src", "chat_windows.rs"));
const SELF_RS = read(join(TAURI, "src", "backend_self.rs"));
const STREAM_RS = read(join(TAURI, "src", "stream.rs"));
const PROXY_RS = read(join(TAURI, "src", "hud_proxy.rs"));
const LOCK_RS = read(join(TAURI, "src", "lock.rs"));
const MEMORY_RS = read(join(TAURI, "src", "window_memory.rs"));
const TRAY_RS = read(join(TAURI, "src", "tray.rs"));
const SETTINGS_JS = read(join(SRC, "settings.js"));
const SURFACES = read(join(TAURI, "permissions", "surfaces.toml"));
const HUD_CAP = read(join(TAURI, "capabilities", "hud.json"));
const SETTINGS_CAP = read(join(TAURI, "capabilities", "settings.json"));

let passed = 0;
function check(name, fn) {
  try {
    fn();
    passed += 1;
    console.log(`ok   ${name}`);
  } catch (error) {
    console.error(`FAIL ${name}`);
    console.error(error.message);
    process.exitCode = 1;
  }
}

/** The `("area", "kind:key")` pairs out of the Rust table. */
function areaAliases() {
  const start = NAV_RS.indexOf("pub const AREA_ALIASES");
  assert.notEqual(start, -1, "AREA_ALIASES is gone from hud_nav.rs");
  const block = NAV_RS.slice(start, NAV_RS.indexOf("];", start));
  const rows = [];
  for (const m of block.matchAll(/\("([^"]+)",\s*"([^"]+)"\)/g)) {
    rows.push([m[1], m[2]]);
  }
  return rows;
}

/** The `PAGE_AREAS` array out of the injected bootstrap. */
function pageAreas() {
  const start = BOOT.indexOf("var PAGE_AREAS = [");
  assert.notEqual(start, -1, "PAGE_AREAS is gone from hud_bootstrap.js");
  const block = BOOT.slice(start, BOOT.indexOf("];", start));
  return [...block.matchAll(/"([^"]+)"/g)].map((m) => m[1]);
}

check("the areas the page chrome switches are the areas the Rust table sends", () => {
  const chrome = new Set(pageAreas());
  const expected = new Set();
  for (const [, destination] of areaAliases()) {
    const [kind, key] = destination.split(":");
    if (kind === "view" || kind === "tab" || kind === "panel") expected.add(key);
  }
  // The four the table sends that are not page-only: settings and the Brain
  // window are handled by their own functions, not by `PAGE_AREAS`.
  for (const special of ["settings", "brain-window"]) {
    assert.ok(
      BOOT.includes(`area === "${special}"`),
      `the page chrome does not handle the "${special}" area`
    );
  }
  for (const area of expected) {
    assert.ok(chrome.has(area), `hud_nav.rs can send "${area}" but the chrome cannot switch it`);
  }
  for (const area of chrome) {
    assert.ok(
      BOOT.includes(`area === "${area}"`) || BOOT.includes(`"${area}"`),
      `the chrome lists "${area}" but does not act on it`
    );
  }
});

check("the unknown-area sentence is the one the Rust table words, and it is shown", () => {
  assert.match(
    NAV_RS,
    /Jarvis asked to open \\"\{area\}\\", but the desktop has no \\"\{area\}\\"/,
    "hud_nav.rs no longer says the plain 'the desktop has no X' sentence"
  );
  assert.match(BOOT, /channel === "notice"\) handleNotice\(payload\)/,
    "the HUD chrome does not listen for the shell's notice line");
  assert.match(BOOT, /function handleNotice/, "handleNotice is gone");
  assert.match(BOOT, /hudNavNote\(payload\.words\.trim\(\)\)/,
    "the notice is received but never shown");
});

check("the page asks for both window commands by their registered names", () => {
  assert.match(BOOT, /navInvoke\("new_chat_window"\)/, "no 'new chat window' command call");
  assert.match(
    BOOT,
    /navInvoke\("open_conversation_window",\s*\{\s*conversation:\s*conv\s*\}\)/,
    "no 'this chat in a new window' command call"
  );
  const labelBlock = CHAT_RS.slice(
    CHAT_RS.indexOf("pub const CHAT_LABELS"),
    CHAT_RS.indexOf("];", CHAT_RS.indexOf("pub const CHAT_LABELS"))
  );
  const ids = [...labelBlock.matchAll(/"chat-(\d+)"/g)].map((m) => Number(m[1]));
  assert.deepEqual(ids, [1, 2, 3, 4, 5, 6, 7, 8],
    "chat_windows.rs's fixed label set changed - lock.rs and window_memory.rs hold it too");
  assert.match(BOOT, /host\.current\(\)/,
    "the bootstrap no longer reads the page's own current conversation id");
});

check("a chat window's capability covers its labels, because a page without one has no commands", () => {
  assert.match(HUD_CAP, /"windows":\s*\[\s*"hud",\s*"chat-\*"\s*\]/,
    'hud.json must cover "chat-*" - the glob the capability format accepts');
  assert.match(HUD_CAP, /"hud-nav"/,
    "hud.json does not grant the hud-nav set the chrome's two commands live in");
  const hudNavSet = SURFACES.slice(
    SURFACES.indexOf('identifier = "hud-nav"'),
    SURFACES.indexOf('identifier = "version-handshake"')
  );
  for (const permission of [
    "allow-open-jarvis-area",
    "allow-new-chat-window",
    "allow-open-conversation-window",
  ]) {
    assert.match(hudNavSet, new RegExp(`"${permission}"`), `the hud-nav set lacks ${permission}`);
  }
});

check("the extra windows are remembered and locked like the HUD they are", () => {
  assert.match(MEMORY_RS, /crate::chat_windows::is_chat_window\(label\)/,
    "window_memory.rs does not track the extra chat windows");
  assert.match(MEMORY_RS, /crate::chat_windows::CHAT_LABELS/,
    "window_memory.rs does not skip the plugin's own restore for a chat window");
  assert.match(LOCK_RS, /crate::chat_windows::is_chat_window\(label\)/,
    "lock.rs does not treat a chat window as a covered window");
  assert.match(LOCK_RS, /crate::chat_windows::CHAT_LABELS/,
    "the capture sweep and the lock's hide loop do not include the chat windows");
});

check("the tray has the row, and it is handled rather than decorative", () => {
  assert.match(TRAY_RS, /ID_NEW_CHAT_WINDOW: &str = "new-chat-window"/, "the tray row is missing");
  assert.match(TRAY_RS, /ID_NEW_CHAT_WINDOW => \{/, "the tray row is declared but not handled");
  assert.match(TRAY_RS, /crate::chat_windows::open_for\(app, None\)/,
    "the tray row does not open a new chat window");
});

check("this window - and only this window - opens the conversation it was asked for", () => {
  assert.match(BOOT, /window\.__jarvisConversation/, "the injected conversation id is not read");
  assert.match(BOOT, /new URL\(window\.location\.href\)\.searchParams/,
    "the ?conversation= query string is not read");
  assert.match(BOOT, /\/api\/history\/conversation\?id=/, "the existing history read is not used");
  assert.match(BOOT, /host\.open\(doc\)/, "the page's own History host does not open the chat");
  assert.doesNotMatch(BOOT, /localStorage\.setItem\([^)]*conversation/,
    "the conversation id must not be written to this window's localStorage");
});

check("navigation rides the per-answer route field, and there is no dead stream listener", () => {
  // The research correction: the backend kept navigation on X-Jarvis-Route and
  // publishes no ui.navigate event. A listener for it would be a doorbell into
  // an empty room, so it must not exist.
  assert.doesNotMatch(STREAM_RS, /ui\.navigate/, "stream.rs listens for a frame nothing publishes");
  assert.doesNotMatch(NAV_RS, /pub fn on_event/, "hud_nav.rs still has a dead frame handler");
  // And the extension is on the route the page already reads.
  assert.match(BOOT, /route\.open_area/, "the route's open_area field is not read");
  assert.match(BOOT, /route\.open_anchor/, "the route's open_anchor field is not read");
  assert.match(BOOT, /shellInvoke\("open_jarvis_area"/, "the route does not reach the one table");
  assert.match(NAV_RS, /pub fn open_jarvis_area/,
    "the open_jarvis_area command is gone");
});

check("the Update press runs BOTH halves, and never claims it when it cannot", () => {
  // The owner's requirement: one Update click updates the desktop AND the
  // backend. The desktop-only command survives only for the PC where the
  // backend half cannot run, and that case says so and is not painted green.
  const handler = SETTINGS_JS.slice(
    SETTINGS_JS.indexOf('dom.updateInstall.addEventListener("click"'),
    SETTINGS_JS.indexOf('dom.updateRestart.addEventListener')
  );
  assert.notEqual(handler.length, 0, "the Install handler is gone");
  assert.match(handler, /invoke\("update_both",\s*\{\s*mode:\s*"responsive"\s*\}\)/,
    "Install does not run update_both (both halves)");
  assert.match(handler, /where\.blocked/, "Install does not check whether the backend half can run");
  assert.match(handler, /The BACKEND was NOT updated/,
    "the desktop-only fallback does not admit the backend was not updated");
  assert.match(handler, /loadVersionSync\(\)/, "the handler does not re-read the two versions");
  assert.match(SETTINGS_JS, /invoke\("shell_version_sync"\)/,
    "Settings never reads the version handshake");
});

check("the version handshake reads the backend's real version block, not just a string", () => {
  assert.match(SELF_RS, /"\/version\/app_version"/,
    "backend_self.rs does not read /version/app_version (the real /api/self shape)");
  assert.match(SELF_RS, /IN SYNC/, "the in-sync sentence is gone");
  assert.match(SELF_RS, /MISMATCH/, "the mismatch sentence is gone");
  assert.match(SELF_RS, /Finish the backend\s*\\?\s*update/, "the mismatch does not say what to do");
  assert.match(SETTINGS_CAP, /"version-handshake"/,
    "the Settings window does not hold the version handshake set");
  const set = SURFACES.slice(
    SURFACES.indexOf('identifier = "version-handshake"'),
    SURFACES.length
  );
  assert.match(set, /"allow-shell-version-sync"/, "the version-handshake set lacks its permission");
});

check("/api/self and /api/conversations are on the HUD's fixed read allowlist", () => {
  assert.match(PROXY_RS, /"\/api\/self"/, "/api/self is not an allowed HUD read");
  assert.match(PROXY_RS, /"\/api\/conversations"/, "/api/conversations is not an allowed HUD read");
  const start = PROXY_RS.indexOf("pub const HUD_GET_PATHS");
  const block = PROXY_RS.slice(start, PROXY_RS.indexOf("];", start));
  assert.match(block, /"\/api\/self"/, "/api/self is not in HUD_GET_PATHS");
});

if (process.exitCode) {
  console.error(`\n${passed} check(s) passed before the failure(s) above.`);
} else {
  console.log(`\nall ${passed} checks passed.`);
}


