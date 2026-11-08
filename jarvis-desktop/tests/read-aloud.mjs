/**
 * The automatic read-aloud switch on the PC (Wave-9, 2026-11-07).
 *
 *   node tests/read-aloud.mjs
 *
 * Three files, three jobs:
 *   - `src/read-aloud.js` - the words and the one reading rule for the PC's
 *     answer. Imported here and checked value by value.
 *   - `src/read-aloud-settings.js` - the Settings wiring: two Tauri commands,
 *     the same route the backend's own chat/Live sentences write.
 *   - `src-tauri/src/read_aloud.rs` - the two commands and their reading of a
 *     missing/unreadable backend. Pinned by source here; its own `#[cfg(test)]`
 *     module runs under `cargo test`.
 *
 * The behaviour this suite exists to keep (the owner's decisions of
 * 2026-11-07):
 *   1. ON by default, so nothing he hears today changes until he turns it off.
 *   2. A TYPED question is never read automatically; a VOICE answer is, unless
 *      this switch is off (`main.js` re-reads it at every voice turn).
 *   3. A missing or unreadable backend is said in words, never read as "off".
 *   4. One source of truth: the same GET/POST /api/read-aloud the backend's
 *      chat/Live commands use - no localStorage second copy.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  DEFAULT_ON,
  MISSING,
  READ_ALOUD_PATH,
  describeReadAloud,
  readReadAloud,
} from "../src/read-aloud.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
const TAURI = join(HERE, "..", "src-tauri", "src");

let passed = 0;
function check(name, fn) {
  fn();
  passed += 1;
  console.log(`ok   ${name}`);
}

check("the route is the backend's own, and the default is ON", () => {
  assert.equal(READ_ALOUD_PATH, "/api/read-aloud");
  assert.equal(DEFAULT_ON, true,
    "OFF by default would change what the owner hears today");
});

check("the switch's words say typed-silent, voice-spoken, private-never", () => {
  const on = describeReadAloud(true).toLowerCase();
  assert.match(on, /voice answer/);
  assert.match(on, /typed question is never read automatically/);
  assert.match(on, /private answer always stays on screen/);
  assert.match(on, /read out loud/);
  const off = describeReadAloud(false).toLowerCase();
  assert.match(off, /no voice answer is read aloud automatically/);
  assert.match(off, /still read that one answer when you tap them/);
  assert.match(off, /private answer still stays on screen/);
});

check("the PC's real answer is read word for word, either position", () => {
  const on = readReadAloud({ ok: true, enabled: true, default: true,
                             known: true, words: "Yes - read replies out loud is on." });
  assert.deepEqual([on.known, on.enabled, on.available], [true, true, true]);
  const off = readReadAloud({ ok: true, enabled: false, known: true });
  assert.deepEqual([off.known, off.enabled, off.available], [true, false, true]);
  assert.deepEqual(readReadAloud({ enabled: false, words: "x" }).enabled, false);
});

check("a missing module and an unreadable answer are said, never read as off", () => {
  const missing = readReadAloud({ available: false });
  assert.equal(missing.available, false);
  assert.equal(missing.known, false);
  assert.match(missing.why, /read-aloud switch yet/);
  assert.equal(missing.why, MISSING);
  const odd = readReadAloud({ enabled: "false" });   // a string is not a state
  assert.equal(odd.known, false);
  assert.match(odd.why, /not in a way this app can read/);
  assert.equal(odd.enabled, DEFAULT_ON, "an unreadable state must not read as off");
});

check("the Settings wiring uses the two commands and no second copy", () => {
  const js = readFileSync(join(SRC, "read-aloud-settings.js"), "utf8");
  assert.match(js, /invoke\("get_read_aloud"\)/);
  assert.match(js, /invoke\("set_read_aloud", \{ enabled: on \}\)/);
  assert.match(js, /box\.addEventListener\("change"/);
  // Painted from the PC's answer, never from the click, and told apart from a
  // save that failed (the same rule the Anti-Slop card states).
  assert.match(js, /paint\(readReadAloud\(reply\)\)/);
  assert.match(js, /show it as not saved|did not happen/);
  assert.doesNotMatch(js, /localStorage\.(get|set)Item/,
    "the switch grew a second, staler source of truth in this window");
  // The row exists on the Settings page and loads this module.
  const html = readFileSync(join(SRC, "settings.html"), "utf8");
  assert.match(html, /id="hud-read-replies"/);
  assert.match(html, /id="hud-read-replies-status"/);
  assert.match(html, /<script type="module" src="read-aloud-settings.js"><\/script>/);
  assert.match(html, /A\s+VOICE answer[\s\S]{0,400}TYPED question is never read automatically/);
});

check("the quickbar obeys the switch for voice answers and only those", () => {
  const main = readFileSync(join(SRC, "main.js"), "utf8");
  assert.match(main, /let readAloudOn = true;/);
  assert.match(main, /invokeStrict\("get_read_aloud"\)/);
  // Re-read at each voice turn start.
  const refreshes = main.match(/refreshReadAloud\(\)/g) || [];
  assert.ok(refreshes.length >= 4,
    `expected the function plus one call per voice turn, got ${refreshes.length}`);
  // A typed turn never queues speech: this window only speaks state.voiceTurn.
  assert.match(main, /if \(!readAloudOn\) \{[\s\S]{0,220}automatic speech stops/);
  assert.match(main, /function checkForSpeakableSentence\(\) \{\s*if \(!state\.voiceTurn/);
  assert.match(main, /if \(!state\.voiceTurn \|\| speechMuted\) return;/,
    "the typed path is no longer separately silent");
});

check("the Rust commands exist, call the one route, and need the boolean back", () => {
  const rs = readFileSync(join(TAURI, "read_aloud.rs"), "utf8");
  assert.match(rs, /pub\(crate\) const READ_ALOUD_PATH: &str = "\/api\/read-aloud";/);
  assert.match(rs, /pub async fn get_read_aloud\(app: AppHandle\)/);
  assert.match(rs, /pub async fn set_read_aloud\(app: AppHandle, enabled: bool\)/);
  assert.match(rs, /serde_json::json!\(\{ "enabled": enabled \}\)/);
  assert.match(rs, /v\.get\("enabled"\)\.is_some_and\(\|e\| e\.is_boolean\(\)\)/);
  assert.match(rs, /fn missing\(code: u16, body: &str\) -> bool/);
  const lib = readFileSync(join(TAURI, "lib.rs"), "utf8");
  assert.match(lib, /pub mod read_aloud;/);
  assert.match(lib, /read_aloud::get_read_aloud/);
  assert.match(lib, /read_aloud::set_read_aloud/);
  // The two capabilities, so a build cannot ship a dead switch.
  const surfaces = readFileSync(join(HERE, "..", "src-tauri", "permissions",
                                     "surfaces.toml"), "utf8");
  assert.match(surfaces, /identifier = "read-aloud-read"/);
  assert.match(surfaces, /identifier = "read-aloud-write"/);
  const caps = join(HERE, "..", "src-tauri", "capabilities");
  const settings = readFileSync(join(caps, "settings.json"), "utf8");
  assert.match(settings, /"read-aloud-read"/);
  assert.match(settings, /"read-aloud-write"/);
  const quickbar = readFileSync(join(caps, "quickbar.json"), "utf8");
  assert.match(quickbar, /"read-aloud-read"/);
});

console.log(`\n${passed} passed, 0 skipped, 0 failed`);
