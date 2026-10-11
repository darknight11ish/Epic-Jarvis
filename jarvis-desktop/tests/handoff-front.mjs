/**
 * Settings -> "When a captcha stops Jarvis" on the desktop (the owner's own
 * decision of 2026-10-09: "1 by default with the option for 2 in the settings
 * of Jarvis"; src/handoff-front-rules.js, src/handoff-front.js,
 * src-tauri/src/handoff.rs `handoff_front`; backend/jarvis_handoff_front.py).
 *
 * What must hold:
 * - the two values, the default and every word are the PC's own
 *   (tests/fixtures/handoff-cases.json, written by tools/gen_handoff_cases.py);
 * - "Leave it where it is" is the DEFAULT, and it raises no window at all;
 * - a damaged settings file reads as the default - never as "Bring it to the
 *   front";
 * - choosing "Bring it to the front" is the loosening one (it raises a card on
 *   the PC with Windows Hello and waits for a live link); the default is
 *   neither;
 * - the page really is wired: the card, the two choices, the Rust command and
 *   the ACL set - and the desktop still never pictures a window, passes input
 *   on, or raises anything itself.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  BRING_TO_FRONT,
  DEFAULT_FRONT,
  FRONT_HELP,
  FRONT_LABELS,
  FRONT_MODES,
  FRONT_PATH,
  HANDOFF_FRONT,
  HANDOFF_FRONT_WORDS,
  frontBody,
  frontView,
  isLoosening,
} from "../src/handoff-front-rules.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..");
const read = (p) => readFileSync(join(ROOT, p), "utf8");
const CASES = JSON.parse(read("tests/fixtures/handoff-cases.json"));
const VIEW = CASES.front_route_get.body;

const fails = [];
const check = (name, fn) => {
  try { fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

check("the two values, the default and every word are the PC's", () => {
  assert.deepEqual(FRONT_MODES, CASES.front_modes);
  assert.equal(DEFAULT_FRONT, CASES.front_default);
  assert.equal(DEFAULT_FRONT, "leave_in_place", "the default touches no window");
  assert.equal(CASES.front_looser, "bring_to_front");
  assert.equal(BRING_TO_FRONT, "bring_to_front");
  assert.deepEqual(HANDOFF_FRONT_WORDS, CASES.front_words);
  assert.equal(HANDOFF_FRONT.title, CASES.front_words.title);
});

check("the default raises nothing at all", () => {
  const v = frontView(VIEW);
  assert.equal(v.mode, DEFAULT_FRONT);
  assert.equal(v.raises, false);
  assert.equal(v.line, CASES.front_words.leave_in_place_detail);
  assert.equal(CASES.front_stuck_default, false, "the PC's own answer: raise nothing");
});

check("'Bring it to the front' is the other value, and it is what raises the window", () => {
  const v = frontView({ ...VIEW, mode: "bring_to_front", brings_to_front: true });
  assert.equal(v.mode, "bring_to_front");
  assert.equal(v.raises, true);
  assert.equal(v.line, CASES.front_words.bring_to_front_detail);
  assert.match(v.line, /screen/);
  assert.match(v.line, /keyboard/);
  assert.match(v.line, /asks for your approval/);
  assert.equal(CASES.front_stuck_chosen, true, "the PC's own answer: raise it");
});

check("while the phone is solving it, nothing is raised", () => {
  assert.equal(CASES.front_active_chosen, false);
  assert.equal(CASES.front_nothing_waiting_chosen, false);
});

check("a card waiting is said plainly, and nothing has changed yet", () => {
  const v = frontView({ ...VIEW, waiting: true });
  assert.equal(v.waiting, true);
  assert.equal(v.line, CASES.front_words.waiting);
  assert.equal(v.mode, DEFAULT_FRONT, "still leaving it where it is while the card waits");
  assert.equal(v.lastWords, "");
});

check("a damaged file reads as 'Leave it where it is', in the PC's words", () => {
  const v = frontView({ ...VIEW, why: CASES.front_words.damaged });
  assert.equal(v.mode, DEFAULT_FRONT);
  assert.equal(v.raises, false);
  assert.equal(v.line, CASES.front_words.damaged);
  assert.equal(v.why, CASES.front_words.damaged);
});

check("anything not the PC's shape is 'could not read it', never a guess", () => {
  for (const bad of [undefined, null, {}, [], "leave_in_place", { mode: "forever" },
                     { mode: 1 }, { mode: null }]) {
    const v = frontView(bad);
    assert.equal(v.available, false, JSON.stringify(bad));
    assert.equal(v.mode, DEFAULT_FRONT, JSON.stringify(bad));
    assert.equal(v.raises, false, JSON.stringify(bad));
    assert.equal(v.line, HANDOFF_FRONT.unread, JSON.stringify(bad));
  }
});

check("how the last card ended rides along in the PC's own words", () => {
  const v = frontView({ ...VIEW, last: { message: CASES.front_words.off_now } });
  assert.equal(v.lastWords, CASES.front_words.off_now);
  assert.equal(frontView({ ...VIEW, last: null }).lastWords, "");
  assert.equal(frontView({ ...VIEW, last: { message: 7 } }).lastWords, "");
});

check("the body carries one of the two names and nothing else", () => {
  assert.deepEqual(JSON.parse(frontBody("leave_in_place")), { mode: "leave_in_place" });
  assert.deepEqual(JSON.parse(frontBody("bring_to_front")), { mode: "bring_to_front" });
  for (const bad of ["", "on", "off", "raise", "front", "LEAVE_IN_PLACE",
                     "leave_in_place ", null, 1, undefined]) {
    assert.equal(frontBody(bad), null, `${bad}`);
  }
});

check("choosing 'Bring it to the front' is the loosening one", () => {
  assert.equal(isLoosening("bring_to_front"), true);
  assert.equal(isLoosening("leave_in_place"), false);
  assert.equal(isLoosening("anything else"), false);
});

check("the labels and the lines are one copy, from the PC's table", () => {
  for (const id of FRONT_MODES) {
    assert.equal(FRONT_LABELS[id], CASES.front_words[id]);
    assert.equal(FRONT_HELP[id], CASES.front_words[`${id}_detail`]);
  }
});

check("the route is the setting's own - a sibling of the hand-off, not one of its routes", () => {
  assert.equal(CASES.routes.front, FRONT_PATH);
  assert.equal(FRONT_PATH, "/api/chatbot/handoff_front");
  assert.ok(!FRONT_PATH.startsWith("/api/chatbot/handoff/"));
});

check("the Rust command carries only a choice, and only the loosening waits", () => {
  const rs = read("src-tauri/src/handoff.rs");
  assert.match(rs, /const FRONT_PATH: &str = "\/api\/chatbot\/handoff_front"/);
  assert.match(rs, /FRONT_MODES: &\[&str\] = &\["leave_in_place", "bring_to_front"\]/);
  // Only "set" + not leave_in_place may be held on a stale link (rule 4).
  assert.match(
    rs,
    /action == "set" && mode\.as_deref\(\) != Some\("leave_in_place"\) && look::stale\(&app\)/,
  );
  assert.match(rs, /pub async fn handoff_front\(/);
  // Registered, or the page could never reach it.
  assert.match(read("src-tauri/src/lib.rs"), /handoff::handoff_front,/);
  // And the ACL: the command exists, its set exists, the settings window holds it.
  assert.match(read("src-tauri/build.rs"), /"handoff_front",/);
  assert.match(read("src-tauri/permissions/surfaces.toml"),
    /identifier = "handoff-front"/);
  assert.match(read("src-tauri/permissions/surfaces.toml"),
    /permissions = \["allow-handoff-front"\]/);
  assert.match(read("src-tauri/capabilities/settings.json"), /"handoff-front",/);
  assert.match(read("src-tauri/permissions/autogenerated/handoff_front.toml"),
    /identifier = "allow-handoff-front"/);
});

check("the Settings page really carries the card, the choices, the jump link and the script", () => {
  const html = read("src/settings.html");
  assert.match(html, /<section class="card" id="handoff-front">/);
  assert.match(html, /id="hf-choices" role="radiogroup"/);
  assert.match(html, /<a href="#handoff-front">When a captcha stops Jarvis<\/a>/);
  assert.match(html, /<script type="module" src="handoff-front.js"><\/script>/);
  const js = read("src/handoff-front.js");
  assert.match(js, /TAURI\.core\.invoke\("handoff_front", \{ action: "read" \}\)/);
  assert.match(js, /TAURI\.core\.invoke\("handoff_front", \{ action: "set", mode \}\)/);
  // The loosening one waits for a live link; the default never does.
  assert.match(js, /input\.disabled = busy \|\| \(isLoosening\(id\) && looseningBlocked\)/);
});

check("the setting's own words are not the other captcha setting's words", () => {
  const mode = read("src/handoff-mode-rules.js");
  assert.ok(!mode.includes(HANDOFF_FRONT.title), "the two cards have different titles");
  assert.ok(!read("src/handoff-front-rules.js").includes("When the phone does not answer"));
});

check("CONTROL: this settings page still never pictures a window, passes input or raises one", () => {
  for (const f of ["src/handoff-front.js", "src/handoff-front-rules.js",
                   "src-tauri/src/handoff.rs"]) {
    const text = read(f);
    assert.ok(!/\/api\/chatbot\/handoff\/(?:start|frame|input|end)\b/.test(text), f);
    assert.ok(!/screenshot|\.mouse|keyboard\.type/.test(text), f);
    assert.ok(!/SetForegroundWindow|ShowWindow|SetWindowPos/.test(text), f);
  }
});

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join("; ")}`);
  process.exit(1);
}
console.log("\nall passed");
