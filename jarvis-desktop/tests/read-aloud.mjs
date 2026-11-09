/**
 * The automatic read-aloud switch on the PC (Wave-9, 2026-11-07).
 *
 *   node tests/read-aloud.mjs
 *
 * Six checks below are behavioural (Wave-10 Q5 / Wave-9 audit F2): the same
 * `createReadAloudStop` the quickbar subscribes is driven with a queue
 * mid-answer and a recording audio stub, and must empty the queue and stop the
 * sentence in flight - no browser, no DOM, no player.
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
  READ_ALOUD_KIND,
  READ_ALOUD_PATH,
  createReadAloudStop,
  describeReadAloud,
  readAloudFrameAction,
  readReadAloud,
  readStillFresh,
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

/* --------------------------------------------------------------------------
   Wave-10 Q5 / Wave-9 audit F2: OFF stops speech immediately, mid-answer.
   The same `createReadAloudStop` main.js subscribes is driven here with a queue
   mid-answer and a recording audio stub - no browser, no DOM, no player.
   -------------------------------------------------------------------------- */

/** The window's speech variables as plain test values. The io closures have
 *  exactly the shape `main.js` passes, so a pass here is a pass for that code. */
function midAnswerWindow() {
  const w = {
    readAloudOn: true,
    queue: ["First sentence.", "Second sentence.", "Third sentence."],
    ahead: { text: "Fourth sentence.", generation: 7, request: null },
    clipPlaying: true,
    speaking: true,
    generation: 7,
    settled: 0,
    synced: 0,
    afterStops: 0,
    paused: [],
  };
  w.audio = { onended: () => {}, onerror: () => {},
              pause() { w.paused.push(this); } };
  w.io = {
    setReadAloudOn: (on) => { w.readAloudOn = on; },
    bumpGeneration: () => { w.generation += 1; },
    dropQueue: () => { w.queue = []; w.ahead = null; },
    setClipPlaying: (value) => { w.clipPlaying = value; },
    takeAudio: () => { const audio = w.audio; w.audio = null; return audio; },
    settleClip: () => { w.settled += 1; },
    setSpeaking: (value) => { w.speaking = value; },
    sync: () => { w.synced += 1; },
    afterStop: () => { w.afterStops += 1; },
  };
  w.onFrame = createReadAloudStop(w.io);
  return w;
}

check("the switch's bus frame is understood, and only from a real boolean", () => {
  assert.equal(READ_ALOUD_KIND, "read_aloud");
  assert.equal(readAloudFrameAction({ kind: "read_aloud", data: { enabled: true } }), "on");
  assert.equal(readAloudFrameAction({ kind: "read_aloud", data: { enabled: false } }), "off");
  // Other kinds, a missing body and a STRING are not guessed at: an unreadable
  // state must never read as off, and a frame that is not the switch is ignored.
  assert.equal(readAloudFrameAction({ kind: "step", data: { enabled: false } }), null);
  assert.equal(readAloudFrameAction({ kind: "read_aloud" }), null);
  assert.equal(readAloudFrameAction({ kind: "read_aloud", data: { enabled: "false" } }), null);
  assert.equal(readAloudFrameAction(null), null);
});

check("OFF mid-answer empties the queue and stops the sentence being spoken", () => {
  const w = midAnswerWindow();
  const audio = w.audio;
  assert.equal(w.onFrame({ kind: "read_aloud", data: { enabled: false } }), "off");
  assert.equal(w.readAloudOn, false, "the window's rule still says ON");
  assert.deepEqual(w.queue, [], "queued answer sentences survived OFF");
  assert.equal(w.ahead, null, "a sentence made ahead survived OFF");
  assert.equal(w.speaking, false);
  assert.equal(w.clipPlaying, false);
  assert.deepEqual(w.paused, [audio], "the clip in flight was not paused");
  assert.equal(w.audio, null, "the stopped clip is still held as current");
  assert.equal(w.settled, 1, "the player's wait was left pending");
  assert.equal(w.synced, 1, "the link line was not repainted");
  assert.equal(w.afterStops, 1);
  // The generation bump is what stops a clip still being MADE from playing:
  // `drainSpeechQueue` compares the number it started with against this one.
  assert.notEqual(w.generation, 7, "a clip already requested can still play");
  // The audio's own handlers are detached so its `ended` cannot re-enter.
  assert.equal(audio.onended, null);
  assert.equal(audio.onerror, null);
});

check("ON sets the rule but touches nothing that is playing", () => {
  const w = midAnswerWindow();
  const queued = w.queue.slice();
  const audio = w.audio;
  assert.equal(w.onFrame({ kind: "read_aloud", data: { enabled: true } }), "on");
  assert.equal(w.readAloudOn, true);
  assert.deepEqual(w.queue, queued, "ON dropped queued speech");
  assert.equal(w.ahead && w.ahead.text, "Fourth sentence.");
  assert.deepEqual(w.paused, [], "ON paused the clip");
  assert.equal(w.audio, audio);
  assert.equal(w.speaking, true);
});

check("an OFF with nothing playing is harmless, and each OFF is its own stop", () => {
  const idle = midAnswerWindow();
  idle.speaking = false;
  idle.clipPlaying = false;
  idle.ahead = null;
  idle.queue = [];
  assert.equal(idle.onFrame({ kind: "read_aloud", data: { enabled: false } }), "off");
  assert.equal(idle.audio, null);
  assert.equal(idle.settled, 1);

  const w = midAnswerWindow();
  w.onFrame({ kind: "read_aloud", data: { enabled: false } });
  w.onFrame({ kind: "read_aloud", data: { enabled: false } });
  assert.equal(w.settled, 2, "the second OFF was ignored");
  assert.deepEqual(w.queue, []);
  assert.equal(w.readAloudOn, false);
});

check("a frame that is not the switch never silences Jarvis", () => {
  const w = midAnswerWindow();
  assert.equal(w.onFrame({ kind: "step", data: {} }), null);
  assert.equal(w.onFrame({ kind: "read_aloud", data: {} }), null);
  assert.equal(w.onFrame({ kind: "read_aloud", data: { enabled: "off" } }), null);
  assert.equal(w.readAloudOn, true);
  assert.equal(w.queue.length, 3);
  assert.deepEqual(w.paused, []);
});

check("a switch read that started before an event cannot overwrite it", () => {
  // main.js's wiring, in the same order: a GET captures the counter at its
  // start; an event bumps it and sets the rule; the GET's snapshot is older.
  let seq = 0;
  const w = midAnswerWindow();
  w.io.setReadAloudOn = (on) => { seq += 1; w.readAloudOn = on; };
  w.onFrame = createReadAloudStop(w.io);

  const readStartedAt = seq;              // refreshReadAloud() begins here
  w.onFrame({ kind: "read_aloud", data: { enabled: false } });   // OFF lands
  assert.equal(readStillFresh(readStartedAt, seq), false,
    "a stale GET would set readAloudOn back to true after the OFF");
  assert.equal(w.readAloudOn, false);

  const nextReadStartedAt = seq;          // the next turn's read begins after it
  assert.equal(readStillFresh(nextReadStartedAt, seq), true);
  assert.equal(readStillFresh(0, 0), true, "no event: the read stands");
});

console.log(`\n${passed} passed, 0 skipped, 0 failed`);
