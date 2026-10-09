/**
 * Settings -> "When the phone does not answer" on the desktop (the owner's own
 * decision of 2026-10-08: "make this a setting for both options with 1 as the
 * default"; src/handoff-mode-rules.js, src/handoff-mode.js,
 * src-tauri/src/handoff.rs; backend/jarvis_handoff_mode.py;
 * docs/CAPTCHA-HANDOFF-DESIGN.md section 5).
 *
 * What must hold:
 * - the two values, the default and every word are the PC's own
 *   (tests/fixtures/handoff-cases.json, written by tools/gen_handoff_cases.py);
 * - "Stop early" is the DEFAULT, and it is the quick cut-off (about a minute),
 *   with the 15-minute ceiling shared by both choices;
 * - a damaged settings file reads as "Stop early" - never as the longer offer;
 * - choosing "Keep offering it" is the loosening one (it raises a card on the PC
 *   with Windows Hello and waits for a live link); "Stop early" is neither;
 * - the page really is wired: the card, the two choices and the Rust command,
 *   and the desktop still never asks for a picture or passes input on.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  DEFAULT_MODE,
  HANDOFF_MODE,
  HANDOFF_MODE_WORDS,
  MODE_HELP,
  MODE_LABELS,
  MODE_PATH,
  MODES,
  isLoosening,
  modeBody,
  modeView,
} from "../src/handoff-mode-rules.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..");
const read = (p) => readFileSync(join(ROOT, p), "utf8");
const CASES = JSON.parse(read("tests/fixtures/handoff-cases.json"));
const VIEW = CASES.mode_route_get.body;

const fails = [];
const check = (name, fn) => {
  try { fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

check("the two values, the default and every word are the PC's", () => {
  assert.deepEqual(MODES, CASES.modes);
  assert.equal(DEFAULT_MODE, CASES.mode_default);
  assert.equal(DEFAULT_MODE, "stop_early", "the default is the quick cut-off");
  assert.equal(CASES.mode_patient, "keep_offering");
  assert.deepEqual(HANDOFF_MODE_WORDS, CASES.mode_words);
  assert.equal(HANDOFF_MODE.title, CASES.mode_words.title);
});

check("the default is the quick cut-off: about a minute, with a 15-minute ceiling", () => {
  const v = modeView(VIEW);
  assert.equal(v.mode, DEFAULT_MODE);
  assert.equal(v.idleSeconds, 60, "about a minute with nobody looking");
  assert.equal(v.ceilingSeconds, 900, "the 15-minute ceiling both choices share");
  assert.equal(v.line, CASES.mode_words.stop_early_detail);
  assert.equal(v.patient, undefined, "the view carries the mode, not a second flag");
  assert.equal(v.mode === "keep_offering", false);
});

check("'Keep offering it' is the other value, and its line says what it costs", () => {
  const v = modeView({ ...VIEW, mode: "keep_offering", patient: true });
  assert.equal(v.mode, "keep_offering");
  assert.equal(v.line, CASES.mode_words.keep_offering_detail);
  assert.match(v.line, /15 minutes/);
  assert.match(v.line, /asks for your approval/);
});

check("a card waiting is said plainly, and nothing has changed yet", () => {
  const v = modeView({ ...VIEW, waiting: true });
  assert.equal(v.waiting, true);
  assert.equal(v.line, CASES.mode_words.waiting);
  assert.equal(v.mode, DEFAULT_MODE, "still stopping early while the card waits");
  assert.equal(v.lastWords, "");
});

check("a damaged file reads as 'Stop early', in the PC's words", () => {
  const v = modeView({ ...VIEW, why: CASES.mode_words.damaged });
  assert.equal(v.mode, DEFAULT_MODE);
  assert.equal(v.line, CASES.mode_words.damaged);
  assert.equal(v.why, CASES.mode_words.damaged);
});

check("anything not the PC's shape is 'could not read it', never a guess", () => {
  for (const bad of [undefined, null, {}, [], "stop_early", { mode: "forever" },
                     { mode: 1 }, { mode: null }]) {
    const v = modeView(bad);
    assert.equal(v.available, false, JSON.stringify(bad));
    assert.equal(v.mode, DEFAULT_MODE, JSON.stringify(bad));
    assert.equal(v.line, HANDOFF_MODE.unread, JSON.stringify(bad));
  }
});

check("how the last card ended rides along in the PC's own words", () => {
  const v = modeView({ ...VIEW, last: { message: CASES.mode_words.off_now } });
  assert.equal(v.lastWords, CASES.mode_words.off_now);
  assert.equal(modeView({ ...VIEW, last: null }).lastWords, "");
  assert.equal(modeView({ ...VIEW, last: { message: 7 } }).lastWords, "");
});

check("the body carries one of the two names and nothing else", () => {
  assert.deepEqual(JSON.parse(modeBody("stop_early")), { mode: "stop_early" });
  assert.deepEqual(JSON.parse(modeBody("keep_offering")), { mode: "keep_offering" });
  for (const bad of ["", "on", "off", "patient", "stop", "STOP_EARLY", "stop_early ",
                     null, 1, undefined]) {
    assert.equal(modeBody(bad), null, `${bad}`);
  }
});

check("choosing 'Keep offering it' is the loosening one", () => {
  assert.equal(isLoosening("keep_offering"), true);
  assert.equal(isLoosening("stop_early"), false);
  assert.equal(isLoosening("anything else"), false);
});

check("the labels and the lines are one copy, from the PC's table", () => {
  for (const id of MODES) {
    assert.equal(MODE_LABELS[id], CASES.mode_words[id]);
    assert.equal(MODE_HELP[id], CASES.mode_words[`${id}_detail`]);
  }
});

check("the route is the setting's own - a sibling of the hand-off, not one of its routes", () => {
  assert.equal(CASES.routes.mode, MODE_PATH);
  assert.equal(MODE_PATH, "/api/chatbot/handoff_mode");
  assert.ok(!MODE_PATH.startsWith("/api/chatbot/handoff/"));
});

check("the Rust command carries only a choice, and only the loosening waits", () => {
  const rs = read("src-tauri/src/handoff.rs");
  assert.match(rs, /const PATH: &str = "\/api\/chatbot\/handoff_mode"/);
  assert.match(rs, /MODES: &\[&str\] = &\["stop_early", "keep_offering"\]/);
  // Only "set" + not stop_early may be held on a stale link (rule 4).
  assert.match(rs, /action == "set" && mode\.as_deref\(\) != Some\("stop_early"\) && look::stale\(&app\)/);
  assert.match(rs, /pub async fn handoff_mode\(/);
  // Registered, or the page could never reach it.
  assert.match(read("src-tauri/src/lib.rs"), /handoff::handoff_mode,/);
});

check("the Settings page really carries the card, the choices and the script", () => {
  const html = read("src/settings.html");
  assert.match(html, /<section class="card" id="handoff">/);
  assert.match(html, /id="ho-choices" role="radiogroup"/);
  assert.match(html, /<a href="#handoff">When the phone does not answer<\/a>/);
  assert.match(html, /<script type="module" src="handoff-mode.js"><\/script>/);
  const js = read("src/handoff-mode.js");
  assert.match(js, /TAURI\.core\.invoke\("handoff_mode", \{ action: "read" \}\)/);
  assert.match(js, /TAURI\.core\.invoke\("handoff_mode", \{ action: "set", mode \}\)/);
  // The loosening one waits for a live link; the quick cut-off never does.
  assert.match(js, /input\.disabled = busy \|\| \(isLoosening\(id\) && looseningBlocked\)/);
});

check("CONTROL: this settings page still never pictures a window or passes input", () => {
  for (const f of ["src/handoff-mode.js", "src/handoff-mode-rules.js",
                   "src-tauri/src/handoff.rs"]) {
    const text = read(f);
    assert.ok(!/\/api\/chatbot\/handoff\/(?:start|frame|input|end)\b/.test(text), f);
    assert.ok(!/screenshot|\.mouse|keyboard\.type/.test(text), f);
  }
});

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join("; ")}`);
  process.exit(1);
}
console.log("\nall passed");
